"""
Account pool for managing multiple GGE client connections.

Provides lease/release semantics for account management, automatic cooldown
handling, and tag-based filtering for different use cases (e.g., tracking,
scanning, alerts).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from empire_core.accounts import Account, AccountRegistry, accounts
from empire_core.client.client import EmpireClient
from empire_core.exceptions import EmpireError, LoginCooldownError, LoginError

__all__ = ["AccountPool", "PoolExhaustedError"]

logger = logging.getLogger(__name__)


class PoolExhaustedError(EmpireError):
    """Raised when the pool has no candidate account to hand out.

    Distinct from :class:`~empire_core.exceptions.LoginError`: nothing was tried
    and nothing failed, there was simply nothing free (none configured, all
    busy, all inactive, or none matching the requested username/tag). Callers
    should back off and retry rather than treat it as a credential problem.
    """


class AccountPool:
    """
    Manages a pool of accounts for concurrent GGE operations.

    Allows callers to 'lease' accounts so they aren't used by multiple
    operations simultaneously. Implements automatic cycling and cooldown handling.

    Usage:
        pool = AccountPool()

        # Or with an explicit account set, instead of the process-wide default
        registry = AccountRegistry()
        registry.load(file_path="farmers.json")
        pool = AccountPool(registry=registry)

        # Scoped lease: released even if the body raises (preferred)
        with pool.leased(tag="tracking") as client:
            ...

        # Manual lease/release, for callers that cannot use a with-block
        client = pool.lease()
        try:
            ...
        finally:
            pool.release(client)

    Thread Safety:
        This class is NOT thread-safe. If using from multiple threads,
        wrap calls with appropriate locking.
    """

    def __init__(self, registry: AccountRegistry | None = None):
        """
        Args:
            registry: Account source for this pool. Defaults to the module-level
                ``empire_core.accounts.accounts`` singleton, which lazily loads
                credentials from the environment and the working directory.
        """
        self._registry = registry
        self._busy: set[str] = set()  # Usernames currently in use
        self._clients: dict[str, EmpireClient] = {}  # Active clients by username
        self._last_leased_index = -1  # For round-robin cycling

    @property
    def registry(self) -> AccountRegistry:
        """The account source in use (the global singleton unless one was injected)."""
        # Resolved per call rather than captured in __init__ so that replacing the
        # module-level singleton keeps working for pools built before the swap.
        return self._registry if self._registry is not None else accounts

    @property
    def all_accounts(self) -> list[Account]:
        """Get all configured accounts."""
        return self.registry.get_all()

    def get_available(self, tag: str | None = None) -> list[Account]:
        """
        Get list of available (not busy) accounts.

        Args:
            tag: Optional tag to filter accounts.

        Returns:
            List of available accounts, ordered for round-robin cycling.
        """
        all_accs = self.all_accounts
        if not all_accs:
            return []

        # Round-robin: start from next index after last leased
        num_accs = len(all_accs)
        start_idx = (self._last_leased_index + 1) % num_accs
        cycled_indices = [(start_idx + i) % num_accs for i in range(num_accs)]

        available = []
        for idx in cycled_indices:
            acc = all_accs[idx]
            if acc.username in self._busy:
                continue
            if not acc.active:
                continue
            if tag and not acc.has_tag(tag):
                continue
            available.append(acc)

        return available

    def lease(
        self,
        username: str | None = None,
        tag: str | None = None,
        login: bool = True,
    ) -> EmpireClient | None:
        """
        Lease an account from the pool.

        Marks the account as busy and optionally logs in. If a specific account
        is on cooldown, automatically tries the next available account.

        Args:
            username: Specific username to lease (optional).
            tag: Tag to filter accounts (optional).
            login: Whether to login the client (default True).

        Returns:
            Connected EmpireClient, or None if there were no candidate accounts
            to try (none configured, all busy, or none matching username/tag).

        Raises:
            LoginError: Every candidate was tried and every one failed. The last
                failure is attached as ``__cause__``, so credential problems,
                cooldowns and outright bugs stay distinguishable instead of
                collapsing into a None that means 'nothing configured'.
        """
        # Build candidate list.
        # The username branch applies the same filters as get_available() and
        # folds case the way AccountRegistry.get_by_username and has_tag do -
        # asking for an account by name must not be a way to bypass the active
        # flag or the tag filter.
        if username:
            wanted = username.lower()
            candidates = [
                acc
                for acc in self.all_accounts
                if acc.username.lower() == wanted
                and acc.username not in self._busy
                and acc.active
                and (not tag or acc.has_tag(tag))
            ]
        else:
            candidates = self.get_available(tag)

        if not candidates:
            logger.warning(f"AccountPool: No available accounts (user={username}, tag={tag})")
            return None

        # Try each candidate until one succeeds
        last_error: Exception | None = None
        for account in candidates:
            # Update round-robin index
            all_accs = self.all_accounts
            for i, acc in enumerate(all_accs):
                if acc.username == account.username:
                    self._last_leased_index = i
                    break

            # Mark as busy
            self._busy.add(account.username)
            client: EmpireClient | None = None

            try:
                # Create client
                client = account.get_client()

                if login:
                    # login() reports failure by raising and always returns True,
                    # as its own docstring says. `if not client.login()` was dead
                    # code, and a trap: it would reject every successful lease the
                    # day that vestigial bool return becomes None.
                    client.login()

                # Cache and return
                self._clients[account.username] = client
                logger.info(f"AccountPool: Leased {account.username}")
                return client

            except LoginCooldownError as e:
                logger.warning(f"AccountPool: {account.username} on cooldown ({e.cooldown}s), trying next...")
                last_error = e
                self._busy.discard(account.username)
                self._safe_close(client)
                continue

            except Exception as e:
                logger.error(f"AccountPool: Failed to lease {account.username}: {e}")
                last_error = e
                self._busy.discard(account.username)
                self._safe_close(client)
                continue

        # Candidates existed but none could be leased. Raising (rather than
        # returning None) keeps this distinct from 'no accounts available', and
        # the chained cause preserves the real reason.
        logger.error("AccountPool: All candidate accounts failed")
        raise LoginError(
            f"All {len(candidates)} candidate account(s) failed to lease (user={username}, tag={tag})"
        ) from last_error

    @contextmanager
    def leased(
        self,
        username: str | None = None,
        tag: str | None = None,
        login: bool = True,
    ) -> Iterator[EmpireClient]:
        """
        Lease an account for the duration of a ``with`` block.

        Preferred over :meth:`lease`/:meth:`release`: the release happens in a
        ``finally``, so a caller exception cannot leak the busy slot and the live
        client. The pool has no lease timeout or reaper, so a leaked slot means
        the account is unavailable until the process restarts.

        Usage::

            with pool.leased(tag="scanner") as client:
                client.scan_kingdom(Kingdom.GREEN)

        Args:
            username: Specific username to lease (optional).
            tag: Tag to filter accounts (optional).
            login: Whether to login the client (default True).

        Yields:
            The leased, connected client.

        Raises:
            PoolExhaustedError: No candidate account was available to try.
            LoginError: Every candidate was tried and every one failed.
        """
        client = self.lease(username=username, tag=tag, login=login)
        if client is None:
            raise PoolExhaustedError(f"No account available to lease (user={username}, tag={tag})")
        try:
            yield client
        finally:
            self.release(client)

    @staticmethod
    def _safe_close(client: EmpireClient | None) -> None:
        if client is None:
            return
        try:
            client.close()
        except Exception:
            pass

    def release(self, client: EmpireClient, logout: bool = True) -> None:
        """
        Release an account back to the pool.

        Args:
            client: The client to release.
            logout: Whether to logout/close the client (default True).
        """
        if not client or not client.username:
            return

        username = client.username

        if logout:
            # Always close: a client leased with login=False (or whose login
            # failed) still holds an open websocket and receive thread.
            try:
                client.close()
            except Exception as e:
                logger.error(f"AccountPool: Error closing {username}: {e}")

        # Remove from tracking
        self._clients.pop(username, None)
        self._busy.discard(username)
        logger.info(f"AccountPool: Released {username}")

    def release_all(self, logout: bool = True) -> None:
        """Release all leased accounts."""
        # Copy keys to avoid mutation during iteration
        usernames = list(self._clients.keys())
        for username in usernames:
            client = self._clients.get(username)
            if client:
                self.release(client, logout=logout)

    def get_client(self, username: str) -> EmpireClient | None:
        """Get a leased client by username."""
        return self._clients.get(username)

    @property
    def busy_count(self) -> int:
        """Number of currently leased accounts."""
        return len(self._busy)

    @property
    def available_count(self) -> int:
        """Number of available accounts."""
        return len(self.get_available())

    def __len__(self) -> int:
        """Total number of configured accounts."""
        return len(self.all_accounts)

    def __repr__(self) -> str:
        return f"AccountPool(total={len(self)}, busy={self.busy_count}, available={self.available_count})"
