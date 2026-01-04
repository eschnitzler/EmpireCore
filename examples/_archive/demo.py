#!/usr/bin/env python3
"""
EmpireCore Demo Script
Shows all currently working features of the library.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Demo")


async def main():
    """Demo the EmpireCore client capabilities."""

    # 1. Load configuration
    account = accounts.get_default()
    if not account:
        logger.error("No account found. Please create accounts.json or set env vars.")
        return

    logger.info(f"Using account: {account.username}")

    client = account.get_client()

    try:
        # 3. Login
        logger.info("🔐 Logging in...")
        await client.login()

        # 4. Wait for initial data to populate
        await asyncio.sleep(2)

        # 5. Query game state
        logger.info("\n=== Game State ===")
        if client.state.local_player:
            player = client.state.local_player
            logger.info(f"Player: {player.name}")
            logger.info(f"Level: {player.level} (LL: {player.legendary_level})")
            logger.info(f"Gold: {player.gold:,}")
            logger.info(f"Rubies: {player.rubies}")
            logger.info(f"Castles: {len(player.castles)}")

            for _castle_id, castle in player.castles.items():
                logger.info(f"  - Castle '{castle.name}' (ID: {castle.OID}) in K{castle.KID}")

        # 6. Request detailed castle info
        logger.info("\n📍 Requesting detailed castle info...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)

        # 7. Request movements
        logger.info("\n🚶 Requesting army movements...")
        await client.get_movements()
        await asyncio.sleep(1)

        # 8. Request map chunk around first castle
        if client.state.local_player and client.state.local_player.castles:
            first_castle = list(client.state.local_player.castles.values())[0]
            logger.info(f"\n🗺️  Requesting map chunk for K{first_castle.KID}...")
            # Request small chunk around castle (coordinates would need to be calculated)
            await client.get_map_chunk(kingdom=first_castle.KID, x=0, y=0)
            await asyncio.sleep(1)

        logger.info("\n📊 State Summary:")
        logger.info(f"   Total Players: {len(client.state.players)}")
        logger.info(f"   Total Castles: {len(client.state.castles)}")
        logger.info(f"   Map Objects: {len(client.state.map_objects)}")
        logger.info(f"   Movements: {len(client.state.movements)}")

        # Keep connection alive to observe real-time events
        logger.info("\n⏳ Keeping connection alive for 10s to observe events...")
        await asyncio.sleep(10)

        logger.info("\n✅ Demo completed successfully!")

    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
