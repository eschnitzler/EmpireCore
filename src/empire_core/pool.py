"""
Account pool for managing multiple GGE client connections.

Provides lease/release semantics for account management, automatic cooldown
handling, and tag-based filtering for different use cases (e.g., tracking,
scanning, alerts).
"""

import logging
from typing import Optional

from empire_core.accounts import Account, accounts
from empire_core.client.client import EmpireClient
from empire_core.exceptions import LoginCooldownError

logger = logging.getLogger(__name__)


class AccountPool:
    """
    Manages a pool of accounts for concurrent GGE operations.

    Allows callers to 'lease' accounts so they aren't used by multiple
    operations simultaneously. Implements automatic cycling and cooldown handling.

    Usage:
        pool = AccountPool()

        # Lease any available account
        client = pool.lease()

        # Lease account with specific tag
        client = pool.lease(tag="tracking")

        # When done
        pool.release(client)

    Thread Safety:
        This class is NOT thread-safe. If using from multiple threads,
        wrap calls with appropriate locking.
    """

    def __init__(self):
        self._busy: set[str] = set()  # Usernames currently in use
        self._clients: dict[str, EmpireClient] = {}  # Active clients by username
        self._last_leased_index = -1  # For round-robin cycling

    @property
    def all_accounts(self) -> list[Account]:
        """Get all configured accounts."""
        return accounts.get_all()

    def get_available(self, tag: Optional[str] = None) -> list[Account]:
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
            if tag and (not acc.tags or tag not in acc.tags):
                continue
            available.append(acc)

        return available

    def lease(
        self,
        username: Optional[str] = None,
        tag: Optional[str] = None,
        login: bool = True,
    ) -> Optional[EmpireClient]:
        """
        Lease an account from the pool.

        Marks the account as busy and optionally logs in. If a specific account
        is on cooldown, automatically tries the next available account.

        Args:
            username: Specific username to lease (optional).
            tag: Tag to filter accounts (optional).
            login: Whether to login the client (default True).

        Returns:
            Connected EmpireClient, or None if no accounts available.
        """
        # Build candidate list
        if username:
            candidates = [
                acc for acc in self.all_accounts if acc.username == username and acc.username not in self._busy
            ]
        else:
            candidates = self.get_available(tag)

        if not candidates:
            logger.warning(f"AccountPool: No available accounts (user={username}, tag={tag})")
            return None

        # Try each candidate until one succeeds
        for account in candidates:
            # Update round-robin index
            all_accs = self.all_accounts
            for i, acc in enumerate(all_accs):
                if acc.username == account.username:
                    self._last_leased_index = i
                    break

            # Mark as busy
            self._busy.add(account.username)

            try:
                # Create client
                client = account.get_client()

                if login:
                    client.login()

                # Cache and return
                self._clients[account.username] = client
                logger.info(f"AccountPool: Leased {account.username}")
                return client

            except LoginCooldownError as e:
                logger.warning(f"AccountPool: {account.username} on cooldown ({e.cooldown}s), trying next...")
                self._busy.discard(account.username)
                try:
                    client.close()
                except Exception:
                    pass
                continue

            except Exception as e:
                logger.error(f"AccountPool: Failed to lease {account.username}: {e}")
                self._busy.discard(account.username)
                try:
                    client.close()
                except Exception:
                    pass
                continue

        logger.error("AccountPool: All candidate accounts failed")
        return None

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
            try:
                if client.is_logged_in:
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

    def get_client(self, username: str) -> Optional[EmpireClient]:
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
