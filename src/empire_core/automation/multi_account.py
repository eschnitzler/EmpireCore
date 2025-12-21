"""
Multi-account management.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.utils.account_loader import load_accounts_from_file
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


class AccountPool:
    """
    Manages a pool of accounts loaded from configuration.
    Allows bots to 'lease' accounts so they aren't used by multiple processes simultaneously.
    """
    
    def __init__(self, account_file: str = "accounts.json"):
        self.account_file = account_file
        self.accounts: List[AccountConfig] = []
        self._busy_accounts: Set[str] = set()  # Set of usernames currently in use
        self._clients: Dict[str, EmpireClient] = {} # Active clients
        
        self.load_pool()

    def load_pool(self):
        """Loads accounts from the file into the pool."""
        raw_accounts = load_accounts_from_file(self.account_file)
        self.accounts = []
        for acc in raw_accounts:
            # Handle potential missing fields gracefully
            if "username" in acc and "password" in acc:
                self.accounts.append(AccountConfig(
                    username=acc["username"],
                    password=acc["password"],
                    tags=acc.get("tags", [])
                ))
        logger.info(f"AccountPool: Loaded {len(self.accounts)} accounts.")

    def get_available_accounts(self, tag: Optional[str] = None) -> List[AccountConfig]:
        """Returns a list of idle accounts, optionally filtered by tag."""
        available = []
        for acc in self.accounts:
            if acc.username not in self._busy_accounts:
                if tag is None or (acc.tags and tag in acc.tags):
                    available.append(acc)
        return available

    async def lease_account(self, username: Optional[str] = None, tag: Optional[str] = None) -> Optional[EmpireClient]:
        """
        Leases an account from the pool, logs it in, and returns the client.
        Iterates through available accounts if one fails (e.g. cooldown).
        """
        candidates = []

        if username:
            for acc in self.accounts:
                if acc.username == username and acc.username not in self._busy_accounts:
                    candidates.append(acc)
        else:
            candidates = self.get_available_accounts(tag)

        if not candidates:
            logger.warning(f"AccountPool: No idle accounts found (User: {username}, Tag: {tag})")
            return None

        for target_account in candidates:
            # Mark as busy immediately
            self._busy_accounts.add(target_account.username)

            try:
                # Create and login client
                config = EmpireConfig(
                    username=target_account.username,
                    password=target_account.password
                )
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

        logger.error("AccountPool: All available accounts failed to login.")
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
    """Manage multiple game accounts."""
    
    def __init__(self):
        self.accounts: Dict[str, EmpireClient] = {}
        self.configs: Dict[str, AccountConfig] = {}
        self.running = False
    
    def add_account(self, config: AccountConfig):
        """Add an account."""
        self.configs[config.username] = config
        logger.info(f"Added account: {config.username}")
    
    def remove_account(self, username: str):
        """Remove an account."""
        if username in self.configs:
            del self.configs[username]
        if username in self.accounts:
            del self.accounts[username]
        logger.info(f"Removed account: {username}")
    
    async def login_all(self):
        """Login to all accounts."""
        logger.info(f"Logging in to {len(self.configs)} accounts...")
        
        tasks = []
        for username, config in self.configs.items():
            if config.enabled:
                task = self._login_account(username, config)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success = sum(1 for r in results if r is True)
        logger.info(f"Logged in {success}/{len(tasks)} accounts")
    
    async def _login_account(self, username: str, config: AccountConfig) -> bool:
        """Login to single account."""
        try:
            emp_config = EmpireConfig(
                username=config.username,
                password=config.password
            )
            client = EmpireClient(emp_config)
            
            await client.login()
            await asyncio.sleep(1)
            
            # Get initial state
            await client.get_detailed_castle_info()
            
            self.accounts[username] = client
            logger.info(f"✅ {username} logged in")
            return True
            
        except Exception as e:
            logger.error(f"❌ {username} login failed: {e}")
            return False
    
    async def logout_all(self):
        """Logout all accounts."""
        for username, client in self.accounts.items():
            try:
                await client.close()
                logger.info(f"Logged out: {username}")
            except Exception as e:
                logger.error(f"Error logging out {username}: {e}")
        
        self.accounts.clear()
    
    def get_account(self, username: str) -> Optional[EmpireClient]:
        """Get client for account."""
        return self.accounts.get(username)
    
    def get_all_accounts(self) -> List[EmpireClient]:
        """Get all account clients."""
        return list(self.accounts.values())
    
    async def execute_on_all(self, func, *args, **kwargs):
        """Execute function on all accounts."""
        tasks = []
        
        for username, client in self.accounts.items():
            task = func(client, *args, **kwargs)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    def get_total_resources(self) -> Dict[str, int]:
        """Get total resources across all accounts."""
        totals = {'wood': 0, 'stone': 0, 'food': 0, 'gold': 0, 'rubies': 0}
        
        for client in self.accounts.values():
            player = client.state.local_player
            if not player:
                continue
            
            totals['gold'] += player.gold
            totals['rubies'] += player.rubies
            
            for castle in player.castles.values():
                totals['wood'] += castle.resources.wood
                totals['stone'] += castle.resources.stone
                totals['food'] += castle.resources.food
        
        return totals
    
    def get_stats(self) -> Dict:
        """Get statistics for all accounts."""
        stats = {
            'total_accounts': len(self.configs),
            'logged_in': len(self.accounts),
            'total_castles': 0,
            'total_population': 0,
            'resources': self.get_total_resources()
        }
        
        for client in self.accounts.values():
            player = client.state.local_player
            if player:
                stats['total_castles'] += len(player.castles)
                for castle in player.castles.values():
                    stats['total_population'] += castle.population
        
        return stats
