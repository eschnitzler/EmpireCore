#!/usr/bin/env python3
"""
Simple farming bot example.
"""
import asyncio
import logging
import sys

sys.path.insert(0, '../src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.automation.farming import FarmingBot
from empire_core.automation.scheduler import TaskScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger("FarmBot")


async def main():
    # Setup
    config = EmpireConfig(username="YourUsername", password="YourPassword")
    client = EmpireClient(config)
    
    try:
        # Login
        logger.info("Logging in...")
        await client.login()
        await asyncio.sleep(2)
        
        # Get state
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)
        
        player = client.state.local_player
        logger.info(f"Logged in as {player.name}, Level {player.level}")
        
        # Setup farming bot
        farm_bot = FarmingBot(client)
        farm_bot.farm_interval = 300  # 5 minutes
        farm_bot.max_distance = 30.0
        farm_bot.default_units = {620: 50}  # 50 militia
        
        # Setup scheduler
        scheduler = TaskScheduler()
        
        # Add tasks
        scheduler.add_task(
            "farm",
            farm_bot._farm_cycle,
            interval=300
        )
        
        scheduler.add_task(
            "refresh_state",
            client.get_detailed_castle_info,
            interval=600
        )
        
        # Run
        logger.info("Starting bot... Press Ctrl+C to stop")
        await scheduler.start()
        
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
