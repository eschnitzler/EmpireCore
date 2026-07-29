"""Scan a kingdom for castles, then re-scan only the chunks that had content.

A full ``scan_kingdom()`` walks the map by BFS from your own castle and takes
minutes. ``result.content_chunks`` records which chunks actually held items, so
a follow-up ``scan_chunks()`` refreshes the same region for roughly a third
fewer requests. Run the full scan occasionally, the targeted one often.

    export GGE_USERNAME=your_user
    export GGE_PASSWORD=your_pass
    python examples/kingdom_scan.py
"""

import logging
import os
import sys

from empire_core import EmpireClient, EmpireError, Kingdom, MapItemType, ScanResult

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("websocket").setLevel(logging.WARNING)

KINGDOM = Kingdom.GREEN
ITEM_TYPES = [MapItemType.CASTLE]


def summarise(label: str, result: ScanResult) -> None:
    print(
        f"{label}: {len(result.items)} items, {len(result.objects)} objects, "
        f"{len(result.content_chunks)} chunks with content, "
        f"{len(result.failed_chunks)} failed chunks"
    )
    if result.failed_chunks:
        # Failed chunks are reported, not silently dropped: the scan is partial.
        print(f"  failed: {result.failed_chunks[:10]}{'...' if len(result.failed_chunks) > 10 else ''}")


def main() -> int:
    username = os.getenv("GGE_USERNAME")
    password = os.getenv("GGE_PASSWORD")
    if not username or not password:
        print("Set GGE_USERNAME and GGE_PASSWORD first.", file=sys.stderr)
        return 2

    client = EmpireClient(username=username, password=password)
    try:
        client.login()

        # chunk_delay paces the requests. The server drops connections that
        # sustain a high request rate, so leave the default alone unless you
        # have measured what this account tolerates.
        discovery = client.scan_kingdom(KINGDOM, item_types=ITEM_TYPES)
        summarise("discovery scan", discovery)

        if not discovery.content_chunks:
            print("Nothing found; skipping the targeted re-scan.")
            return 0

        fresh = client.scan_chunks(KINGDOM, list(discovery.content_chunks), item_types=ITEM_TYPES)
        summarise("targeted re-scan", fresh)

        for item in fresh.items[:10]:
            print(f"  {item}")

    except EmpireError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
