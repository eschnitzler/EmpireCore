#!/usr/bin/env python3
"""
World Mapper - A tool to build a local database of the game world.
Usage: uv run examples/world_mapper.py [radius] [quit_after_empty_chunks]
"""

import asyncio
import logging
import os
import sys

from tabulate import tabulate

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("WorldMapper")


async def main(radius: int = 5, quit_on_empty: int = 5):
    # 1. Get default account
    account = accounts.get_default()
    if not account:
        logger.error("No accounts configured.")
        return

    client = account.get_client()

    try:
        # 3. Login
        logger.info(f"🔐 Logging in as {account.username}...")
        await client.login()

        # 4. Wait for initial data
        logger.info("📡 Fetching initial castle data...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)

        # 5. Show current DB status
        summary = await client.scanner.get_scan_summary()
        logger.info(
            f"📊 Current Database: {summary['database_objects']} objects across {summary['total_chunks_scanned']} chunks."
        )

        # 6. Start Scanning
        logger.info(f"🛰️ Starting world scan (Radius: {radius} chunks, Early quit: {quit_on_empty})...")

        await client.scanner.scan_around_castles(radius=radius, quit_on_empty=quit_on_empty)

        # 7. Final Report
        final_summary = await client.scanner.get_scan_summary()
        
        print("\n" + "=" * 60)
        print("🌎 WORLD MAP SUMMARY")
        print("=" * 60)
        
        # General Stats Table
        stats_data = [
            ["Total Objects", final_summary["database_objects"]],
            ["Total Chunks Scanned", final_summary["total_chunks_scanned"]],
            ["Memory Objects", final_summary["memory_objects"]],
        ]
        print(tabulate(stats_data, headers=["Metric", "Value"], tablefmt="fancy_grid"))
        
        print("\n📦 OBJECT BREAKDOWN")
        # Breakdown Table
        breakdown_data = []
        # Sort by count descending
        sorted_types = sorted(final_summary["objects_by_type"].items(), key=lambda x: x[1], reverse=True)
        for obj_type, count in sorted_types:
            if count > 0:
                breakdown_data.append([obj_type, count])
        
        print(tabulate(breakdown_data, headers=["Object Type", "Count"], tablefmt="fancy_grid"))
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"❌ Error during mapping: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    # Args: [radius] [quit_on_empty]
    scan_radius = 5
    early_quit = 5
    
    if len(sys.argv) > 1:
        try:
            scan_radius = int(sys.argv[1])
        except ValueError: pass
    
    if len(sys.argv) > 2:
        try:
            early_quit = int(sys.argv[2])
        except ValueError: pass

    asyncio.run(main(scan_radius, early_quit))