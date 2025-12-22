#!/usr/bin/env python3
"""
World Mapper - A tool to build a local database of the game world.
Usage: 
    uv run examples/world_mapper.py [radius] [quit_after_empty_chunks]
    uv run examples/world_mapper.py --full
"""

import asyncio
import logging
import os
import sys

from tabulate import tabulate
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts

# Configure logging to be less verbose for the demo
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("WorldMapper")
logger.setLevel(logging.INFO)


async def main(radius: int = 5, quit_on_empty: int = 5, full_scan: bool = False):
    # 1. Get default account
    account = accounts.get_default()
    if not account:
        logger.error("No accounts configured.")
        return

    client = account.get_client()

    try:
        # 2. Login
        logger.info(f"🔐 Logging in as {account.username}...")
        await client.login()

        # 3. Wait for initial data
        if not full_scan:
            logger.info("📡 Fetching initial castle data...")
            await client.get_detailed_castle_info()
            await asyncio.sleep(2)

        # 4. Show current DB status
        summary = await client.scanner.get_scan_summary()
        logger.info(
            f"📊 Current Database: {summary['database_objects']} objects across {summary['total_chunks_scanned']} chunks."
        )

        # 5. Start Scanning
        logger.info("🛰️ Starting world scan...")

        # Setup progress bar
        pbar = tqdm(total=0, unit="chunk", desc="Scanning")

        def update_progress(progress):
            if pbar.total == 0:
                pbar.total = progress.total_chunks
            pbar.n = progress.completed_chunks
            pbar.set_postfix(objects=progress.objects_found)
            pbar.refresh()

        client.scanner.on_progress(update_progress)

        if full_scan:
            await client.scanner.scan_area(
                center_x=600,
                center_y=600,
                radius=60,
                kingdom_id=0,
                rescan=False,
                quit_on_empty=None,
            )
        else:
            await client.scanner.scan_around_castles(radius=radius, quit_on_empty=quit_on_empty)

        pbar.close()

        # 6. Final Report
        final_summary = await client.scanner.get_scan_summary()

        print("\n" + "=" * 60)
        print("🌎 WORLD MAP SUMMARY")
        print("=" * 60)

        stats_data = [
            ["Total Objects", final_summary["database_objects"]],
            ["Total Chunks Scanned", final_summary["total_chunks_scanned"]],
            ["Memory Objects", final_summary["memory_objects"]],
        ]
        print(tabulate(stats_data, headers=["Metric", "Value"], tablefmt="fancy_grid"))

        print("\n📂 CATEGORY BREAKDOWN")
        cat_data = [[cat, count] for cat, count in final_summary["objects_by_category"].items() if count > 0]
        print(tabulate(cat_data, headers=["Category", "Count"], tablefmt="fancy_grid"))

        print("\n📦 DETAILED TYPE BREAKDOWN")
        breakdown_data = []
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
    scan_radius = 5
    early_quit = 5
    full_scan = False

    args = sys.argv[1:]

    if "--full" in args:
        full_scan = True
    elif len(args) >= 1:
        try:
            scan_radius = int(args[0])
            if len(args) >= 2:
                early_quit = int(args[1])
        except ValueError:
            pass

    asyncio.run(main(radius=scan_radius, quit_on_empty=early_quit, full_scan=full_scan))
