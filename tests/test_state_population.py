import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.utils.account_loader import get_test_account

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("StateTest")


async def main():
    account = get_test_account()
    if not account:
        logger.error("No test account found in accounts.json")
        return

    config = EmpireConfig(username=account["username"], password=account["password"])
    client = EmpireClient(config)

    try:
        await client.login()

        logger.info("Waiting for state population...")
        await asyncio.sleep(10)  # Wait for 'gbd' and processing

        player = client.state.local_player
        if player:
            logger.info("================ GAME STATE REPORT ================")
            logger.info(f"Player: {player.name} (ID: {player.id})")
            logger.info(f"Level: {player.level}")
            logger.info(f"Rubies: {player.rubies}")
            logger.info(f"Gold: {player.gold}")
            logger.info(f"Castles: {len(player.castles)}")
            for cid, castle in player.castles.items():
                logger.info(f" - Castle [{cid}]: {castle.name} (KID: {castle.kingdom_id})")
            logger.info("===================================================")

            if len(player.castles) > 0:
                logger.info("TEST SUCCESS: State populated.")
            else:
                logger.warning("TEST WARNING: Logged in but no castles found (New account?)")
        else:
            logger.error("TEST FAILED: Local player not found in state.")

    except Exception as e:
        logger.error(f"TEST FAILED: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
