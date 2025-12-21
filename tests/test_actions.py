#!/usr/bin/env python3
"""
Test action commands (READ-ONLY test - doesn't actually send actions)
"""

import asyncio
import logging
import sys

sys.path.insert(0, "src")

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ActionTest")


async def main():
    from empire_core.utils.account_loader import get_test_account

    account = get_test_account()
    if not account:
        logger.error("No test account found in accounts.json. Please create one based on accounts.json.template")
        return

    username = account["username"]
    password = account["password"]

    config = EmpireConfig(username=username, password=password)
    client = EmpireClient(config)

    try:
        logger.info("🔐 Logging in...")
        await client.login()
        await asyncio.sleep(2)

        player = client.state.local_player
        if not player:
            logger.error("No player data")
            return

        logger.info(f"\n✅ Logged in as {player.name}")
        logger.info(f"Level: {player.level}, Gold: {player.gold:,}")

        # Get castle info
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)

        if len(player.castles) == 0:
            logger.warning("No castles found")
            return

        # Get first castle
        castle_id, castle = list(player.castles.items())[0]

        logger.info(f"\n📍 Castle: {castle.name} (ID: {castle_id})")
        logger.info(
            f"   Resources: W:{castle.resources.wood:,} S:{castle.resources.stone:,} F:{castle.resources.food:,}"
        )
        logger.info(f"   Buildings: {len(castle.buildings)}")

        logger.info("\n" + "=" * 70)
        logger.info("ACTION COMMAND API TEST")
        logger.info("=" * 70)

        logger.info("\n✅ Available action methods:")
        logger.info("   • client.send_attack(origin, target, units, kingdom)")
        logger.info("   • client.send_transport(origin, target, wood, stone, food)")
        logger.info("   • client.upgrade_building(castle, building_id, building_type)")
        logger.info("   • client.recruit_units(castle, unit_id, count)")

        logger.info("\n📝 Example usage:")
        logger.info("   # Send attack")
        logger.info(f"   await client.send_attack({castle_id}, 16654500, {{620: 10, 614: 5}})")
        logger.info("   ")
        logger.info("   # Send resources")
        logger.info(f"   await client.send_transport({castle_id}, 16654500, wood=1000, stone=500)")
        logger.info("   ")
        logger.info("   # Upgrade building")
        logger.info(f"   await client.upgrade_building({castle_id}, 10)")
        logger.info("   ")
        logger.info("   # Recruit units")
        logger.info(f"   await client.recruit_units({castle_id}, 620, 10)")

        logger.info("\n⚠️  NOTE: These commands will actually send actions to the game!")
        logger.info("⚠️  Use carefully on test accounts only.")

        logger.info("\n" + "=" * 70)
        logger.info("✅ Action API ready for use!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
