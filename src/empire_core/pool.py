"""
A pool that leases one logged-in client per account.

Provides lease/release semantics for account management, automatic cooldown
handling, and tag-based filtering for different use cases (e.g., tracking,
scanning, alerts).
"""

import itertools
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

    Keeping clients logged in:
        With ``keep_alive=True``, :meth:`release` hands the client back to the
        pool still logged in, and the next lease of that account reuses it
        without a login. A kept client whose session dropped meanwhile is
        closed and replaced by a fresh login, so a cooldown on that login sends
        the lease on to the next candidate as usual. While kept, the connection
        pings every 60 seconds as the game client does, which keeps an idle
        session open. :meth:`release_all` closes kept clients too.
        Client: ``BasicSmartfoxClient.onJoinRoom`` (dll line 7165) and
        ``activatePing`` (dll line 7167).

        The next leaseholder gets the same client object. :meth:`leased`
        releases only its own lease, but :meth:`release` cannot tell one
        holder's handle from the next one's: release a manual handle once, and
        never after its lease ended.

        Release ends the streams a leaseholder opened with
        :meth:`EmpireClient.listen`. Otherwise the client is handed over as it
        is: callbacks a leaseholder registered
        (``on_disconnect``, ``on_incoming_attack`` and the like) stay
        registered and fire during the next lease. Remove them before
        releasing, or release with ``logout=True`` to close the client.

    Thread Safety:
        Every method may be called from any thread. An account is marked busy
        before its login starts, so two concurrent leases never get the same
        account; the login itself runs outside the pool's lock, so leases of
        different accounts log in in parallel.
    """

    def __init__(self, registry: AccountRegistry, keep_alive: bool = False):
        """
        Args:
            registry: Where this pool's accounts come from.
            keep_alive: Keep released clients logged in for the next lease
                instead of closing them.
        """
        self.registry = registry
        self.keep_alive = keep_alive
        self._lock = threading.Lock()
        self._busy: set[str] = set()  # Usernames currently in use
        self._clients: dict[str, EmpireClient] = {}  # Leased and kept clients by username
        self._lease_ids: dict[str, int] = {}  # The live lease of each busy account
        self._lease_counter = itertools.count()
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
                self._lease_ids[account.username] = next(self._lease_counter)
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
        is on cooldown, automatically tries the next available account. A
        client kept by a ``keep_alive`` pool is reused while it is still
        logged in, also when ``login`` is False.

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
                client = self._take_kept(account.username)
                if client is not None:
                    leased = True
                    logger.info(f"AccountPool: Leased {account.username} (kept logged in)")
                    return client

                client = account.get_client()

                if login:
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
                    with self._lock:
                        kept = self._clients.pop(account.username, None)
                    self._safe_close(client)
                    if kept is not client:
                        self._safe_close(kept)
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
        with self._lock:
            lease_id = self._lease_ids[str(client.username)]
        try:
            yield client
        finally:
            self._release(client, None, lease_id)

    def _take_kept(self, username: str) -> EmpireClient | None:
        """The client kept for a reserved account if its session is still up; a dead one is closed and forgotten."""
        with self._lock:
            client = self._clients.get(username)
        if client is None:
            return None
        if client.is_logged_in and client.connection.connected:
            return client
        logger.info(f"AccountPool: Kept client of {username} lost its session ({client.connection.close_error})")
        with self._lock:
            self._clients.pop(username, None)
        self._safe_close(client)
        return None

    @staticmethod
    def _safe_close(client: EmpireClient | None) -> None:
        if client is None:
            return
        try:
            client.close()
        except Exception as e:
            logger.error(f"AccountPool: Error closing {client.username}: {e}")

    def release(self, client: EmpireClient, logout: bool | None = None) -> None:
        """
        Release an account back to the pool.

        Only a client the account is leased with now is released. Any other
        leaves the pool as it is, with a warning: a client the pool did not
        hand out, or one whose lease already ended. Such a client is still
        closed as ``logout`` says, unless it is the client a ``keep_alive``
        pool holds for its account, which a later leaseholder may be using.

        Args:
            client: The client to release.
            logout: Whether to close the client. The default closes it, unless
                the pool was made with ``keep_alive``. A ``keep_alive`` pool
                keeps a logged-in client released with ``logout=False`` or the
                default for the next lease; one that is not logged in is closed.
        """
        self._release(client, logout, None)

    def _release(self, client: EmpireClient, logout: bool | None, lease_id: int | None) -> None:
        """Release ``client``'s lease; with a ``lease_id``, only while that lease is the live one."""
        if not client or not client.username:
            return

        username = client.username
        if logout is None:
            logout = not self.keep_alive

        with self._lock:
            held = self._clients.get(username)
            current = held is client and username in self._busy and lease_id in (None, self._lease_ids.get(username))
            keep = current and self.keep_alive and not logout and client.is_logged_in
            if current and not keep:
                del self._clients[username]
        # A keep_alive pool closes every client it does not keep.
        logout = logout or (self.keep_alive and not keep)

        if not current:
            logger.warning(f"AccountPool: {username} is not leased with this client; pool unchanged")
            if logout and held is not client:
                self._safe_close(client)
            return

        client.close_streams()
        client.state._forget_queued_reannounces()
        if logout:
            # Always close: a client leased with login=False (or whose login
            # failed) still holds an open websocket and receive thread.
            self._safe_close(client)

        with self._lock:
            self._busy.discard(username)
        logger.info(f"AccountPool: Released {username}{', kept logged in' if keep else ''}")

    def release_all(self, logout: bool = True) -> None:
        """Release all leased accounts and, with ``logout``, close the clients a ``keep_alive`` pool kept."""
        with self._lock:
            leased = [client for username, client in self._clients.items() if username in self._busy]
            idle = [username for username in self._clients if username not in self._busy] if logout else []
            kept = [self._clients.pop(username) for username in idle]
        for client in kept:
            self._safe_close(client)
        for client in leased:
            self.release(client, logout=logout)

    def get_client(self, username: str) -> EmpireClient | None:
        """Get a leased or kept client by username."""
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
