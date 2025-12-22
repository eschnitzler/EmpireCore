#!/usr/bin/env python3
"""
World Mapper - A tool to build a local database of the game world.
Usage: uv run examples/world_mapper.py [radius]
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("WorldMapper")


async def main(radius: int = 5):
    # 1. Setup
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()

    try:
        # 2. Login
        logger.info(f"🔐 Logging in as {account.username}...")
        await client.login()

        # 3. Show current DB status
        summary = await client.scanner.get_scan_summary()
        logger.info(
            f"📊 Current Database: {summary['database_objects']} objects across {summary['total_chunks_scanned']} chunks."
        )

        # 4. Start Scanning
        logger.info(f"🛰️ Starting world scan (Radius: {radius} chunks around each castle)...")

        # We can use scan_around_castles which iterates over all your outposts/main
        results = await client.scanner.scan_around_castles(radius=radius)

        # 5. Final Report
        total_found = sum(r.objects_found for r in results)
        logger.info(f"✅ Scan complete! Found {total_found} new objects.")

        final_summary = await client.scanner.get_scan_summary()

        print("\n" + "=" * 50)
        print("🌎 WORLD MAP SUMMARY")
        print("=" * 50)
        print(f"Total Objects in DB: {final_summary['database_objects']}")
        print(f"Total Chunks Scanned: {final_summary['total_chunks_scanned']}")
        print("-" * 50)
        print("Objects by Type:")
        # Sort by count descending
        sorted_types = sorted(final_summary["objects_by_type"].items(), key=lambda x: x[1], reverse=True)
        for obj_type, count in sorted_types:
            if count > 0:
                print(f"  - {obj_type:<20}: {count}")
        print("=" * 50 + "\n")

    except Exception as e:
        logger.error(f"❌ Error during mapping: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    # Get radius from args if provided
    scan_radius = 3  # Default to 3 for demo
    if len(sys.argv) > 1:
        try:
            scan_radius = int(sys.argv[1])
        except ValueError:
            pass

    asyncio.run(main(scan_radius))
