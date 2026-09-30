"""
A pool that leases one logged-in client per account.

Provides lease/release semantics for account management, automatic cooldown
handling, and tag-based filtering for different use cases (e.g., tracking,
scanning, alerts).
"""

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from empire_core.accounts import Account, AccountRegistry
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
        registry = AccountRegistry()
        registry.load(file_path="farmers.json")
        pool = AccountPool(registry)

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
        Every method may be called from any thread. An account is marked busy
        before its login starts, so two concurrent leases never get the same
        account; the login itself runs outside the pool's lock, so leases of
        different accounts log in in parallel.
    """

    def __init__(self, registry: AccountRegistry):
        """
        Args:
            registry: Where this pool's accounts come from.
        """
        self.registry = registry
        self._lock = threading.Lock()
        self._busy: set[str] = set()  # Usernames currently in use
        self._clients: dict[str, EmpireClient] = {}  # Active clients by username
        self._last_leased_index = -1  # For round-robin cycling

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
        with self._lock:
            return self._available(self.all_accounts, tag)

    def _available(self, all_accs: list[Account], tag: str | None) -> list[Account]:
        """Free accounts in round-robin order; called under the lock."""
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

    def _candidates(self, all_accs: list[Account], username: str | None, tag: str | None) -> list[Account]:
        """The accounts a lease may try, in order; called under the lock.

        The username branch applies the same filters as get_available() and
        folds case the way AccountRegistry.get_by_username and has_tag do -
        asking for an account by name must not be a way to bypass the active
        flag or the tag filter.
        """
        if not username:
            return self._available(all_accs, tag)
        wanted = username.lower()
        return [
            acc
            for acc in all_accs
            if acc.username.lower() == wanted
            and acc.username not in self._busy
            and acc.active
            and (not tag or acc.has_tag(tag))
        ]

    def _reserve(self, username: str | None, tag: str | None, tried: set[str]) -> Account | None:
        """Mark the next untried free candidate busy and return it; None when none is left."""
        all_accs = self.all_accounts
        with self._lock:
            for account in self._candidates(all_accs, username, tag):
                if account.username in tried:
                    continue
                self._busy.add(account.username)
                self._last_leased_index = next(i for i, acc in enumerate(all_accs) if acc.username == account.username)
                return account
        return None

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
        tried: set[str] = set()
        last_error: Exception | None = None

        # Try each candidate until one succeeds
        while (account := self._reserve(username, tag, tried)) is not None:
            tried.add(account.username)
            client: EmpireClient | None = None
            leased = False

            try:
                client = account.get_client()

                if login:
                    # login() reports failure by raising and always returns True,
                    # as its own docstring says. `if not client.login()` was dead
                    # code, and a trap: it would reject every successful lease the
                    # day that vestigial bool return becomes None.
                    client.login()

                with self._lock:
                    self._clients[account.username] = client
                leased = True
                logger.info(f"AccountPool: Leased {account.username}")
                return client

            except LoginCooldownError as e:
                logger.warning(f"AccountPool: {account.username} on cooldown ({e.cooldown}s), trying next...")
                last_error = e
            except Exception as e:
                logger.error(f"AccountPool: Failed to lease {account.username}: {e}")
                last_error = e
            finally:
                # Also on KeyboardInterrupt/SystemExit: the account must not stay busy.
                if not leased:
                    self._safe_close(client)
                    with self._lock:
                        self._busy.discard(account.username)

        if not tried:
            logger.warning(f"AccountPool: No available accounts (user={username}, tag={tag})")
            return None

        # Candidates existed but none could be leased. Raising (rather than
        # returning None) keeps this distinct from 'no accounts available', and
        # the chained cause preserves the real reason.
        logger.error("AccountPool: All candidate accounts failed")
        raise LoginError(
            f"All {len(tried)} candidate account(s) failed to lease (user={username}, tag={tag})"
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
                client.map.scan_kingdom(Kingdom.GREEN)

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

        with self._lock:
            self._clients.pop(username, None)
            self._busy.discard(username)
        logger.info(f"AccountPool: Released {username}")

    def release_all(self, logout: bool = True) -> None:
        """Release all leased accounts."""
        with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            self.release(client, logout=logout)

    def get_client(self, username: str) -> EmpireClient | None:
        """Get a leased client by username."""
        with self._lock:
            return self._clients.get(username)

    @property
    def busy_count(self) -> int:
        """Number of currently leased accounts."""
        with self._lock:
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
