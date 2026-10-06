"""
Time one chunk scan spread over several clients: threads in one process against separate processes.

    uv run python scripts/bench_multi_scan.py
    uv run python scripts/bench_multi_scan.py --clients 8 --chunks 289 --rtt 0.05

Each made-up client waits ``--rtt`` seconds for every ``gaa`` reply, as a live
session waits for the server, and answers with the live-shaped chunk reply of
``tests/data/gaa_scan_chunk.json``, decoded from its frame as the receive
thread decodes it. Prints the wall time of ``--chunks`` chunks
scanned by one client, by ``--clients`` clients through ``scan_kingdom_with``
in one process, and by as many processes each scanning its interleaved slice
with ``MapScanner.scan_chunks`` (process start-up not counted).

Waiting for a reply releases the GIL; parsing one holds it. Threads in one
process overlap the waits but not the parsing, so one process cannot go faster
than the parse time of every chunk added up, however many clients it has.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from empire_core.enums import Kingdom
from empire_core.map.scanner import MapScanner, scan_kingdom_with
from empire_core.protocol.packet import Packet

CHUNK_REPLY = Path(__file__).resolve().parent.parent / "tests" / "data" / "gaa_scan_chunk.json"


class _SlowReply:
    """A client that answers every gaa request with the same reply frame, decoded after ``rtt`` seconds."""

    def __init__(self, payload: dict[str, Any], rtt: float) -> None:
        self.connection = SimpleNamespace(connected=True)
        self.state = SimpleNamespace(get_castles=list)
        self.frame = f"%xt%gaa%1%0%{json.dumps(payload)}%".encode()
        self.rtt = rtt

    def request_packet(self, request: Any, response_command: str, timeout: float = 5.0) -> Packet:
        time.sleep(self.rtt)
        return Packet.from_bytes(self.frame)


def _chunks(count: int) -> list[tuple[int, int]]:
    return [(index % 20, index // 20) for index in range(count)]


def _process_scan(payload: dict[str, Any], rtt: float, chunks: list[tuple[int, int]], go: Any, out: Any) -> None:
    scanner = MapScanner(_SlowReply(payload, rtt))  # type: ignore[arg-type]
    go.wait()
    start = time.time()
    scanner.scan_chunks(Kingdom.GREEN, chunks)
    out.put((start, time.time()))


def in_processes(payload: dict[str, Any], rtt: float, chunks: list[tuple[int, int]], clients: int) -> float:
    """Wall time from the first process starting its scan to the last one finishing."""
    go = multiprocessing.Event()
    out: multiprocessing.Queue[tuple[float, float]] = multiprocessing.Queue()
    workers = [
        multiprocessing.Process(target=_process_scan, args=(payload, rtt, chunks[index::clients], go, out))
        for index in range(clients)
    ]
    for worker in workers:
        worker.start()
    time.sleep(1.0)
    go.set()
    spans = [out.get() for _ in workers]
    for worker in workers:
        worker.join()
    return max(end for _, end in spans) - min(start for start, _ in spans)


def in_threads(payload: dict[str, Any], rtt: float, chunks: list[tuple[int, int]], clients: int) -> float:
    fakes = [_SlowReply(payload, rtt) for _ in range(clients)]
    start = time.perf_counter()
    scan_kingdom_with(fakes, Kingdom.GREEN, chunks=chunks)  # type: ignore[arg-type]
    return time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clients", type=int, default=8, help="Clients scanning together")
    parser.add_argument("--chunks", type=int, default=289, help="Chunks to scan")
    parser.add_argument("--rtt", type=float, default=0.05, help="Seconds each reply takes to arrive")
    args = parser.parse_args()
    payload = json.loads(CHUNK_REPLY.read_text())
    chunks = _chunks(args.chunks)

    parse = MapScanner(_SlowReply(payload, 0.0))  # type: ignore[arg-type]
    start = time.perf_counter()
    parse.scan_chunks(Kingdom.GREEN, chunks)
    parsing = time.perf_counter() - start

    print(f"{args.chunks} chunks, {args.rtt * 1000:.0f} ms a reply, {parsing:.2f} s of decoding and parsing in all")
    timings = {
        "1 client": in_threads(payload, args.rtt, chunks, 1),
        f"{args.clients} clients, one process": in_threads(payload, args.rtt, chunks, args.clients),
        f"{args.clients} clients, {args.clients} processes": in_processes(payload, args.rtt, chunks, args.clients),
    }
    for name, seconds in timings.items():
        print(f"  {name:<26} {seconds:6.2f} s")


if __name__ == "__main__":
    main()
