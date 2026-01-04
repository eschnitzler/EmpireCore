"""
Multi-account management and account pooling.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from empire_core.accounts import Account, accounts
from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.exceptions import LoginCooldownError

logger = logging.getLogger(__name__)


@dataclass
class AccountConfig:
    """Configuration for a single account."""

    username: str
    password: str
    enabled: bool = True
    farm_interval: int = 300
    collect_interval: int = 600
    tags: Optional[List[str]] = None  # e.g., ["farmer", "fighter"]

    @classmethod
    def from_account(cls, acc: Account) -> "AccountConfig":
        return cls(username=acc.username, password=acc.password, enabled=acc.active, tags=acc.tags)


class AccountPool:
    """
    Manages a pool of accounts loaded from the central registry.
    Allows bots to 'lease' accounts so they aren't used by multiple processes simultaneously.
    Implements automatic cycling and cooldown handling.
    """

    def __init__(self):
        self._busy_accounts: Set[str] = set()  # Set of usernames currently in use
        self._clients: Dict[str, EmpireClient] = {}  # Active clients
        self._last_leased_index = -1

    @property
    def all_accounts(self) -> List[AccountConfig]:
        """Get all accounts wrapped in AccountConfig."""
        return [AccountConfig.from_account(acc) for acc in accounts.get_all()]

    def get_available_accounts(self, tag: Optional[str] = None) -> List[AccountConfig]:
        """Returns a list of idle accounts, optionally filtered by tag."""
        available = []
        all_accs = self.all_accounts

        # Sort/Cycle logic: Start from the next index after the last leased one
        num_accs = len(all_accs)
        if num_accs == 0:
            return []

        start_idx = (self._last_leased_index + 1) % num_accs
        cycled_indices = [(start_idx + i) % num_accs for i in range(num_accs)]

        for idx in cycled_indices:
            acc = all_accs[idx]
            if acc.username not in self._busy_accounts and acc.enabled:
                if tag is None or (acc.tags and tag in acc.tags):
                    available.append(acc)
        return available

    async def lease_account(self, username: Optional[str] = None, tag: Optional[str] = None) -> Optional[EmpireClient]:
        """
        Leases an account from the pool, logs it in, and returns the client.
        Automatically cycles through available accounts if one is on cooldown.
        """
        candidates = []

        if username:
            for acc in self.all_accounts:
                if acc.username == username and acc.username not in self._busy_accounts:
                    candidates.append(acc)
        else:
            candidates = self.get_available_accounts(tag)

        if not candidates:
            logger.warning(f"AccountPool: No idle accounts found (User: {username}, Tag: {tag})")
            return None

        for target_account in candidates:
            # Update last leased index to ensure true cycling
            all_accs = self.all_accounts
            for i, acc in enumerate(all_accs):
                if acc.username == target_account.username:
                    self._last_leased_index = i
                    break

            # Mark as busy immediately
            self._busy_accounts.add(target_account.username)

            try:
                # Create and login client
                config = EmpireConfig(username=target_account.username, password=target_account.password)
                client = EmpireClient(config)
                await client.login()

                # Cache the client
                self._clients[target_account.username] = client
                logger.info(f"AccountPool: Leased and logged in {target_account.username}")
                return client

            except LoginCooldownError as e:
                logger.warning(f"AccountPool: {target_account.username} on cooldown ({e.cooldown}s). Trying next...")
                self._busy_accounts.remove(target_account.username)
                await client.close()
                continue

            except Exception as e:
                logger.error(f"AccountPool: Failed to login {target_account.username}: {e}")
                self._busy_accounts.remove(target_account.username)
                await client.close()
                continue

        logger.error("AccountPool: All available candidate accounts failed to login.")
        return None

    async def release_account(self, client: EmpireClient):
        """Logs out and returns the account to the pool."""
        if not client.username:
            return

        username = client.username

        try:
            if client.is_logged_in:
                await client.close()
        except Exception as e:
            logger.error(f"Error closing client for {username}: {e}")
        finally:
            if username in self._clients:
                del self._clients[username]
            if username in self._busy_accounts:
                self._busy_accounts.remove(username)
            logger.info(f"AccountPool: Released {username}")

    async def release_all(self):
        """Releases all active accounts."""
        active_usernames = list(self._clients.keys())
        for username in active_usernames:
            client = self._clients[username]
            await self.release_account(client)


class MultiAccountManager:
    """Manage multiple active game sessions."""

    def __init__(self):
        self.clients: Dict[str, EmpireClient] = {}

    def load_from_registry(self, tag: Optional[str] = None):
        """
        Load accounts from the central registry into the manager.

        Args:
            tag: Optional tag to filter accounts (e.g., 'farmer').
        """
        target_accounts = accounts.get_by_tag(tag) if tag else accounts.get_all()
        count = 0
        for acc in target_accounts:
            if acc.active and acc.username not in self.clients:
                self.clients[acc.username] = acc.get_client()
                count += 1
        logger.info(f"Manager: Loaded {count} accounts (Total: {len(self.clients)})")

    async def login_all(self):
        """Login to all managed accounts."""
        if not self.clients:
            logger.warning("No accounts loaded in manager.")
            return

        logger.info(f"Logging in to {len(self.clients)} accounts...")

        tasks = []
        for username, client in self.clients.items():
            if not client.is_logged_in:
                tasks.append(self._login_client(username, client))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success = sum(1 for r in results if r is True)
            logger.info(f"Logged in {success}/{len(tasks)} accounts")

    async def _login_client(self, username: str, client: EmpireClient) -> bool:
        """Login to single client."""
        try:
            await client.login()
            # staggered delay to avoid burst
            await asyncio.sleep(1)

            # Get initial state
            await client.get_detailed_castle_info()

            logger.info(f"✅ {username} logged in")
            return True

        except Exception as e:
            logger.error(f"❌ {username} login failed: {e}")
            return False

    async def logout_all(self):
        """Logout all accounts."""
        for username, client in self.clients.items():
            try:
                await client.close()
                logger.info(f"Logged out: {username}")
            except Exception as e:
                logger.error(f"Error logging out {username}: {e}")

        self.clients.clear()

    def get_client(self, username: str) -> Optional[EmpireClient]:
        """Get client for username."""
        return self.clients.get(username)

    def get_all_clients(self) -> List[EmpireClient]:
        """Get all managed clients."""
        return list(self.clients.values())

    async def execute_on_all(self, func, *args, **kwargs):
        """
        Execute an async function on all clients.
        The function must accept 'client' as the first argument.
        """
        tasks = []

        for client in self.clients.values():
            if client.is_logged_in:
                task = func(client, *args, **kwargs)
                tasks.append(task)

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def get_total_resources(self) -> Dict[str, int]:
        """Get total resources across all accounts."""
        total_wood = 0
        total_stone = 0
        total_food = 0
        total_gold = 0
        total_rubies = 0

        for client in self.clients.values():
            player = client.state.local_player
            if not player:
                continue

            total_gold += player.gold
            total_rubies += player.rubies

            for castle in player.castles.values():
                total_wood += castle.resources.wood
                total_stone += castle.resources.stone
                total_food += castle.resources.food

        return {
            "wood": total_wood,
            "stone": total_stone,
            "food": total_food,
            "gold": total_gold,
            "rubies": total_rubies,
        }

    def get_stats(self) -> Dict:
        """Get statistics for all accounts."""
        resources = self.get_total_resources()
        total_castles = 0
        total_population = 0
        logged_in_count = 0

        for client in self.clients.values():
            if client.is_logged_in:
                logged_in_count += 1
            player = client.state.local_player
            if player:
                total_castles += len(player.castles)
                for castle in player.castles.values():
                    total_population += castle.population

        return {
            "logged_in": logged_in_count,
            "total_castles": total_castles,
            "total_population": total_population,
            "resources": resources,
        }
