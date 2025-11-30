"""
Multi-account management.
"""
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

logger = logging.getLogger(__name__)


@dataclass
class AccountConfig:
    """Configuration for a single account."""
    username: str
    password: str
    enabled: bool = True
    farm_interval: int = 300
    collect_interval: int = 600


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
