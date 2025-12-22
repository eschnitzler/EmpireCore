#!/usr/bin/env python3
"""
Map Persistence Demo - Shows how to use the database-backed map scanner.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts
from empire_core.utils.enums import MapObjectType

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MapDemo")


async def main():
    # 1. Setup
    account = accounts.get_default()
    if not account:
        logger.error("No account found.")
        return

    client = account.get_client()

    try:
        # 2. Login
        logger.info("🔐 Logging in...")
        await client.login()
        await asyncio.sleep(2)

        # 3. Check current database state
        summary = await client.scanner.get_scan_summary()
        logger.info(
            f"📊 Initial DB State: {summary['database_objects']} objects, {summary['total_chunks_scanned']} chunks."
        )

        # 4. Scan a small area if DB is empty
        if summary["database_objects"] < 10:
            logger.info("🗺️ Database is empty. Starting initial scan around main castle...")
            player = client.state.local_player
            if player and player.castles:
                main_castle = list(player.castles.values())[0]
                # Scan 3x3 chunks around castle
                await client.scanner.scan_area(main_castle.x, main_castle.y, radius=1)

                summary = await client.scanner.get_scan_summary()
                logger.info(f"📊 New DB State: {summary['database_objects']} objects.")
        else:
            logger.info("✅ Using cached data from database.")

        # 5. Find targets using DB query (no network needed for this part!)
        logger.info("🔍 Searching for level 1-10 NPC camps in database...")
        npc_types = [
            MapObjectType.NOMAD_CAMP,
            MapObjectType.SAMURAI_CAMP,
            MapObjectType.ALIEN_CAMP,
        ]

        # Search around main castle coordinates from DB data
        if client.state.local_player and client.state.local_player.castles:
            castle = list(client.state.local_player.castles.values())[0]

            targets = await client.scanner.find_nearby_targets(
                origin_x=castle.x,
                origin_y=castle.y,
                max_distance=30.0,
                target_types=npc_types,
                max_level=10,
                use_db=True,
            )

            logger.info(f"✨ Found {len(targets)} matching targets in persistent world map.")
            for i, (target, dist) in enumerate(targets[:5]):
                # Target can be a record (from DB) or MapObject (from memory)
                name = getattr(target, "name", "Unknown")
                lvl = getattr(target, "level", 0)
                tx = getattr(target, "x", 0)
                ty = getattr(target, "y", 0)

                logger.info(f"   [{i+1}] {name} (Lvl {lvl}) at ({tx}, {ty}) - {dist:.1f} tiles away")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
