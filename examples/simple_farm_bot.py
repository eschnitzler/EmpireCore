#!/usr/bin/env python3
"""
Simple farming bot example.
Demonstrates building a custom bot using the EmpireCore API.
This replaces the old pre-packaged 'FarmingBot' to show how to use the tools directly.
"""

import asyncio
import logging
import os
import sys
from typing import Dict

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts
from empire_core.automation import tasks
from empire_core.automation.target_finder import TargetFinder

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("FarmBot")


async def main():
    # Setup
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()

    # Bot Configuration
    interval: float = 300.0
    max_distance: float = 30.0
    default_units: Dict[int, int] = {620: 50}  # 50 militia

    # Define the farming loop using the tasks decorator
    @tasks.loop(seconds=interval)
    async def farm_loop():
        """Main farming logic."""
        player = client.state.local_player
        if not player or not player.castles:
            logger.warning("No player/castles for farming")
            return

        # Get castle coordinates (using first castle)
        castle_id = list(player.castles.keys())[0]
        castle = player.castles[castle_id]

        origin_x, origin_y = castle.x, castle.y
        logger.info(f"Scanning for targets around {castle.name} ({origin_x}, {origin_y})...")

        # Find targets
        finder = TargetFinder(client.state.map_objects)
        targets = finder.find_npc_camps(origin_x, origin_y, max_distance)

        if not targets:
            logger.info("No farming targets found.")
            return

        # Attack first target
        target, distance = targets[0]
        logger.info(f"Attacking target at ({target.x}, {target.y}), distance: {distance:.1f}")

        try:
            # Note: In a real bot, you'd check for available units first!
            await client.send_attack(
                origin_x=origin_x,
                origin_y=origin_y,
                target_x=target.x,
                target_y=target.y,
                target_area_id=target.area_id,
                middle_units=default_units,
                kingdom_id=castle.kingdom_id,
            )
            logger.info("Attack sent successfully")
        except Exception as e:
            logger.error(f"Failed to send attack: {e}")

    # Ensure client is ready before starting loop
    @farm_loop.before_loop
    async def before_farming():
        logger.info("Waiting for login...")
        while not client.is_logged_in:
            await asyncio.sleep(1)

        # Refresh state manually to ensure we have castle data
        await client.get_detailed_castle_info()
        logger.info("Ready to farm.")

    try:
        # Login
        logger.info("Logging in...")
        await client.login()

        # Start the background task
        farm_loop.start()

        # Keep the script running
        logger.info("Bot started. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        farm_loop.cancel()
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
