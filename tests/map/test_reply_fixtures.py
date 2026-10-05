"""Made-up gaa replies: what they parse and scan to, and that reading them stays cheap (scripts/bench_map_parse.py)."""

import hashlib
import json
import statistics
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from empire_core.enums import Kingdom, MapItemType
from empire_core.map.models import owners
from empire_core.map.models.areas import GetMapAreaResponse
from empire_core.map.models.items import MapAreaItem
from empire_core.map.scanner import KingdomTopology, MapScanner
from empire_core.protocol.packet import Packet

FIXTURES = Path(__file__).resolve().parent.parent / "data"

# sha256 of the dense reply's model_dump(mode="json") with sorted keys, as v0.45.0 parsed it
V0_45_DIGEST = "534b5284e4fe2bd12f86127d61f0bf941cc7bc4902c219b202dde3fbb020d837"

# sha256 of a one-chunk scan of the live-shaped reply (see _scan_digest), as v0.45.0 scanned it
V0_45_SCAN_DIGESTS = {
    "castles": "f0100860ee57b3cf906909800fb8f9213de0f0cbb59609de8c29b33bb1be4c5a",
    "every type": "00c10f4a10df32821d391099a82b1e5100299adf1da7ef56f33903b763e87d5b",
    "castles, unowned too": "1848517c30ea3645ce828c2a6b75381bf74d706498ee78c3416bd8e476fae159",
}
SCANS: dict[str, dict[str, Any]] = {
    "castles": {},
    "every type": {"item_types": []},
    "castles, unowned too": {"include_unowned_types": {MapItemType.CASTLE}},
}


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "gaa_dense.json").read_text())


@pytest.fixture(scope="module")
def chunk() -> dict[str, Any]:
    return json.loads((FIXTURES / "gaa_scan_chunk.json").read_text())


class _OneReply:
    """A client that answers every gaa request with the same reply."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.connection = SimpleNamespace(connected=True)
        self.reply = Packet(raw_data="", is_xml=False, command_id="gaa", payload=payload)

    def request_packet(self, request: Any, response_command: str, timeout: float = 5.0) -> Packet:
        return self.reply


def _scan(payload: dict[str, Any], **kwargs: Any) -> Any:
    scanner = MapScanner(_OneReply(payload), KingdomTopology())  # type: ignore[arg-type]
    return scanner.scan_chunks(Kingdom.GREEN, [(6, 7)], **kwargs)


def _scan_digest(result: Any) -> str:
    dump = {
        "items": [item.model_dump(mode="json") for item in result.items],
        "objects": {str(oid): record.model_dump(mode="json") for oid, record in result.objects.items()},
    }
    return hashlib.sha256(json.dumps(dump, sort_keys=True).encode()).hexdigest()


def test_parses_as_v0_45_did(payload):
    dump = GetMapAreaResponse.model_validate(payload).model_dump(mode="json")
    assert hashlib.sha256(json.dumps(dump, sort_keys=True).encode()).hexdigest() == V0_45_DIGEST


@pytest.mark.parametrize("scan", SCANS)
def test_a_live_shaped_chunk_scans_as_v0_45_did(chunk, scan):
    assert _scan_digest(_scan(chunk, **SCANS[scan])) == V0_45_SCAN_DIGESTS[scan]


def test_a_scan_builds_only_the_rows_it_keeps_and_those_it_cannot_judge_unbuilt(chunk, monkeypatch):
    built: list[tuple[int, int]] = []
    init = MapAreaItem.__init__

    def counting(self: MapAreaItem, **values: Any) -> None:
        built.append((values["raw_data"][1], values["raw_data"][2]))
        init(self, **values)

    monkeypatch.setattr(MapAreaItem, "__init__", counting)
    result = _scan(chunk)
    castles = [row for row in chunk["AI"] if row[0] == 1]
    # A castle row's owner is read through int(), but a free plot's occupier as sent: the fixture's
    # plots whose occupier is neither an int nor None can only be judged once built
    unjudged = [row for row in castles if len(row) == 4 and type(row[3]) not in (int, type(None))]
    assert len(castles) > 500 and len(result.items) == 43 and len(unjudged) == 3
    assert len(built) == len(set(built))
    assert set(built) == {(item.x, item.y) for item in result.items} | {(row[1], row[2]) for row in unjudged}


def test_a_scan_reads_the_values_of_only_the_castle_rows_it_builds(chunk, monkeypatch):
    read: list[Any] = []
    row_values = MapAreaItem.row_values

    def counting(data: Any, kingdom: Kingdom = Kingdom.GREEN) -> dict[str, Any]:
        read.append(data)
        return row_values(data, kingdom)

    monkeypatch.setattr(MapAreaItem, "row_values", staticmethod(counting))
    result = _scan(chunk)
    # The 43 castles kept, two of them plots judged only once built, plus the plot with occupier -1.0 dropped built
    assert len(result.items) == 43 and len(read) == 44 and len(set(map(id, read))) == 44


def test_only_positions_that_are_not_plain_ints_go_through_pydantic(payload, monkeypatch):
    validated: list[Any] = []

    class Counting:
        @staticmethod
        def validate_python(fields: Any) -> Any:
            validated.append(fields)
            return original.validate_python(fields)

    original = owners._POSITION
    monkeypatch.setattr(owners, "_POSITION", Counting)
    response = GetMapAreaResponse.model_validate(payload)
    assert sum(len(o.castle_positions) + len(o.village_positions) for o in response.owners) > 2500
    # The fixture's two rows that are not plain ints: one of numbers as text, one with a position of "x"
    assert validated == [["1", "2345678", "50", "60", "10"], [0, 1, "x", 4, 1]]


def test_parsing_a_dense_reply_stays_fast(payload):
    # About 30 ms on a laptop, 100 ms under coverage (40 ms in v0.45.0). The bound is loose so CI noise
    # cannot trip it; the test above is the one that catches positions going back through pydantic
    GetMapAreaResponse.model_validate(payload)
    times = []
    for _ in range(5):
        start = time.perf_counter()
        GetMapAreaResponse.model_validate(payload)
        times.append(time.perf_counter() - start)
    assert statistics.median(times) < 1.0
