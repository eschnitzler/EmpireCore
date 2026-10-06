---
description: Scan a kingdom for castles, outposts and capitals, and re-scan it cheaply.
---

# Map scanning

`client.map.scan_kingdom` finds a kingdom's castles, outposts, capitals and
other map objects. It discovers the kingdom breadth-first from your castle's
position, and a full scan can take a few minutes.

```python
from empire_core import Kingdom, MapItemType

result = client.map.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])
print(f"{len(result.items)} items, {len(result.failed_chunks)} failed chunks")
```

!!! danger "Always check `failed_chunks`"

    A partial scan is not an empty kingdom, and only this field tells them
    apart.

## What a scan returns

A `ScanResult` holds:

| Field | What it is |
|---|---|
| `items` | Every `MapAreaItem` found, read by its area type's layout; empty with [`on_chunk`](#keeping-only-what-you-need). |
| `objects` | The owner records (`MapObject`) the chunks sent, by player id; empty with `on_chunk`. |
| `kingdom` | The kingdom scanned; every item carries it too. |
| `failed_chunks` | Chunks that still failed after their retries, or were left unscanned by a timeout, a cancel or a dropped connection. |
| `content_chunks` | Chunks that answered and held items. |

An item's `owner_id` is below 0 for an NPC owner. `NPCOwner` (in
`empire_core.enums`) names those ids, e.g. `NPCOwner.ROBBER_BARON` or
`NPCOwner.OUTPOST` for an unclaimed outpost.

Requests go out back to back, as the game client sends its map requests; a
live scan of 289 chunks at about 17 requests a second ran without a refusal.
A chunk that times out, or is refused with a cooldown, is retried after a short
backoff. `chunk_delay` adds a fixed wait before every request if you want one.

A session that drops mid-scan ends the scan with what it has, the rest in
`failed_chunks`. The drop, a close by the server or a reset connection, is
logged once, as a warning naming the client and the cause, and
reported by `client.on_disconnect`; the scan adds one INFO line with the
number of chunks it left, and the chunks themselves only at DEBUG.

## Re-scanning cheaply

Feed `content_chunks` back into `scan_chunks()` to re-scan a known region
without paying for the breadth-first discovery again, which takes roughly a
third fewer requests. Run a full `scan_kingdom()` now and then to pick up
content in chunks that were empty before.

```python
discovery = client.map.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])

fresh = client.map.scan_chunks(
    Kingdom.GREEN, list(discovery.content_chunks), item_types=[MapItemType.CASTLE]
)
```

```mermaid
flowchart LR
    A[scan_kingdom<br/>breadth-first discovery] -->|content_chunks| B[scan_chunks<br/>known chunks only]
    B -->|often| B
    B -.->|now and then| A
```

For very frequent scans, split `content_chunks` across several logged-in
accounts, in interleaved slices `chunks[i::n]`, and run their `scan_chunks()`
calls at the same time. The server limits the request rate per account; see
[Multiple accounts](multiple-accounts.md).

Scans run in their calling thread, and parsing a chunk's reply holds the GIL:
a dense chunk takes a few tens of milliseconds. `scripts/bench_map_parse.py`
times one.

## Keeping only what you need

A `ScanResult` keeps every item and owner record of the kingdom, and Python's
full garbage collections walk all of them while the result lives: for a dense
kingdom that is a pause of a tenth of a second or more each time. Pass
`on_chunk` to take each chunk as it is read and keep only what you need; the
scan then keeps nothing itself, and `items` and `objects` come back empty:

```python
wanted_players = {1234, 5678}
castles: dict[tuple[int, int], int] = {}

def keep_castles(chunk, items, objects):
    for item in items:
        if item.owner_id in wanted_players:
            castles[(item.x, item.y)] = item.owner_id

result = client.map.scan_kingdom(Kingdom.GREEN, on_chunk=keep_castles)
```

`on_chunk` is called for every chunk that answered, empty ones too; failed
chunks are still in `failed_chunks`, and `content_chunks` is filled as usual.
An exception raised by `on_chunk` ends the scan.

## Cancelling a scan

Pass a `threading.Event` as `cancel` to `scan_kingdom()` or `scan_chunks()`.
Once it is set, the scan stops before its next chunk and returns what it has,
with the chunks it did not scan in `failed_chunks`, as a timeout does:

```python
import threading

stop = threading.Event()
result = client.map.scan_kingdom(Kingdom.GREEN, cancel=stop)
# on another thread: stop.set()
```

The chunk in flight is not abandoned: it ends with its reply or its
`request_timeout`, so its reply cannot reach the next map request. The same
event can cancel spy missions too (see [Spy](spy.md)).

## The session leaves its castle

A scan moves the session off the castle it had joined and drops
`client.state.get_mines()`; `get_joined_area()` still names the castle, as the
game keeps it. `client.army` methods
join their castle again themselves; anything else castle-scoped needs
`client.castle.select()` first.

## Other map calls

- `client.map.find_next(area_type)` finds the nearest object of one area type,
  with the map rows around it.
- `client.map.find_next_enemy_castle(x, y, index=0)` finds an enemy castle
  near a position, as the game's "search enemy" button does. The button asks
  with `index` 0 to 9 in turn, so each press finds another castle; pass
  `min_level` and `max_level` to narrow it. Outposts count: on a live
  account, the first three indexes found three players' outposts. The request names no kingdom;
  pass `kingdom` for the one the reply's rows are read in.
- `client.map.find_next_tower()` finds the next Berimond tower, the button's
  search in Berimond.

Each find returns `None` when nothing matches, and `found()` on the reply
gives the row it found.
- `client.map.scan_map_area(x1, y1, x2, y2)` reads one rectangle of the map.
- `client.castle.join_area(x, y)` joins an outpost, capital, metropolis or
  faction camp by its position.

## Runnable example

```python title="examples/kingdom_scan.py"
--8<-- "examples/kingdom_scan.py"
```

**API:** [`MapService`](../reference/map.md#empire_core.map.service.MapService),
[`ScanResult`](../reference/map.md#empire_core.map.scanner.ScanResult),
[`MapAreaItem`](../reference/map.md#empire_core.map.models.items.MapAreaItem)
