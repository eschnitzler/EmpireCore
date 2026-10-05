"""
Time reading ``gaa`` replies: parsing a dense one, and scanning chunks shaped like live ones.

    uv run python scripts/bench_map_parse.py
    uv run python scripts/bench_map_parse.py --runs 50 --dense reply.json --chunk reply.json

Prints the median of ``--runs`` timed runs of each, after one untimed warm-up:
the whole dense reply, its owner records alone and its map rows alone; then
``MapScanner.scan_chunks`` over ten chunks that each answer with the chunk reply
(castles only, as a scan collects by default), and the receive thread's
``GetMapAreaRequest.accepts_reply`` check of that reply.

Both fixtures are made up and 90 x 90 tiles, one scan chunk. The dense one is
packed with castles, outposts, villages and camps and the owner records they
name. The chunk one is shaped like a live chunk: mostly three-field rows, a few
hundred castle rows naming no player (free plots and NPC castles), which a
scan drops, and a few dozen player castles.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from empire_core.enums import Kingdom
from empire_core.map.models.areas import GetMapAreaRequest, GetMapAreaResponse, MapObject
from empire_core.map.models.items import parse_area_rows
from empire_core.map.scanner import MapScanner
from empire_core.protocol.packet import Packet

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "data"
DENSE_REPLY = FIXTURES / "gaa_dense.json"
CHUNK_REPLY = FIXTURES / "gaa_scan_chunk.json"
CHUNK = (6, 7)
"""The chunk both fixtures lie in, at a chunk size of 90."""


class _OneReply:
    """A client that answers every gaa request with the same reply."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.connection = SimpleNamespace(connected=True)
        self.reply = Packet(raw_data="", is_xml=False, command_id="gaa", payload=payload)

    def request_packet(self, request: Any, response_command: str, timeout: float = 5.0) -> Packet:
        return self.reply


def median_seconds(run: Callable[[], Any], runs: int) -> float:
    """The median wall time of ``runs`` calls of ``run``, after one warm-up call."""
    run()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        run()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def benchmarks(dense: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Callable[[], Any]]:
    """What is timed, by name."""
    scanner = MapScanner(_OneReply(chunk))  # type: ignore[arg-type]
    x1, y1, x2, y2 = scanner._chunk_bounds(*CHUNK)
    request = GetMapAreaRequest(kingdom=Kingdom.GREEN, x1=x1, y1=y1, x2=x2, y2=y2)
    chunks = [(CHUNK[0] + offset, CHUNK[1]) for offset in range(10)]
    return {
        "reply": lambda: GetMapAreaResponse.model_validate(dense),
        "owners": lambda: [MapObject.model_validate(record) for record in dense["OI"]],
        "rows": lambda: parse_area_rows(dense["AI"]),
        "scan x10": lambda: scanner.scan_chunks(Kingdom.GREEN, chunks),
        "accepts": lambda: request.accepts_reply(chunk),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dense", type=Path, default=DENSE_REPLY, help="A dense gaa reply payload as JSON")
    parser.add_argument("--chunk", type=Path, default=CHUNK_REPLY, help="A live-shaped gaa reply payload as JSON")
    parser.add_argument("--runs", type=int, default=20, help="Timed runs per benchmark")
    args = parser.parse_args()
    dense, chunk = json.loads(args.dense.read_text()), json.loads(args.chunk.read_text())
    print(f"dense: {len(dense['AI'])} rows, {len(dense['OI'])} owner records; chunk: {len(chunk['AI'])} rows")
    print(f"median of {args.runs}:")
    for name, run in benchmarks(dense, chunk).items():
        print(f"  {name:<9} {median_seconds(run, args.runs) * 1000:7.2f} ms")


if __name__ == "__main__":
    main()
