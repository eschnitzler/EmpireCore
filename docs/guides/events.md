---
description: The running events and their scoreboards, by the event's name.
---

# Events and their scoreboards

`client.events` knows which events run (from the server's `sei` packets) and
reads an event's scoreboard the way its dialog does: it picks the board, the
command and your league for you.

## An event's scores

Events are named by the game data's `Event` enum, which uses the client's own
names: Berimond is `Event.FACTION`.

```python
from empire_core.gamedata.ids import Event

scores = client.events.get_scores(Event.FACTION)

print(scores.league_id, scores.total)  # the league shown, and how many are ranked
for row in scores.scores:
    print(row.rank, row.name, row.points, row.alliance_name)
```

By default you get the page that holds your own score, where the game's dialogs
open. Other pages:

```python
client.events.get_scores(Event.FACTION, rank=1)            # the top of your league
client.events.get_scores(Event.FACTION, name="Someone")    # around a name
client.events.get_scores(Event.FACTION, league_id=3)       # the top of another league
client.events.get_scores(Event.ALLIANCE_NOMAD_INVASION, alliance=True)  # the alliance board
```

Berimond's leagues are its lists: 1 blue, 2 red, 3 and 4 the legendary blue
and red. While Berimond is locked to you, its board opens on the top of
league 1, as in the game.

Each row is an `EventScore`: `rank`, `points` and `name` always, and what the
board gives besides. Player rows on most boards carry `player_id`, `level`,
`alliance_id` and `alliance_name`; alliance rows carry the alliance's
`alliance_id` and `member_count`, with its name in both `name` and
`alliance_name`; the leaderboards (long-term points and donations) carry
`alliance_name` and the game server in `instance_id`, but no ids.

## Which events have a board

`EVENT_SCOREBOARDS` (in `empire_core.events`) maps each event with a board to
its `Scoreboard`, the boards its dialogs open; `client.events.scoreboard(event)`
reads one, and raises `ValueError`, naming the events that have one, for an
event without.

| In the game | `Event` | Player board | Alliance board |
|---|---|---|---|
| Battle for Berimond | `FACTION` | list 30 | |
| Nobility Contest | `POINT_EVENT` | list 40 | |
| Marauders' contest | `BEGGING_KNIGHTS` | list 41 | |
| War of the Realms (alien invasion) | `ALLIANCE_ALIEN_INVASION` | list 44 | list 45 |
| Nomad Invasion | `ALLIANCE_NOMAD_INVASION` | | list 47 |
| Samurai Invasion | `SAMURAI_INVASION` | | list 52 |
| Grand Nobility Prize (long-term points) | `LONG_TERM_POINT_EVENT` | leaderboard 53 | |
| Berimond Invasion | `FACTION_INVASION` | lists 54 (blue) and 55 (red) | list 56 |
| Bloodcrow invasion | `RED_ALLIANCE_ALIEN_INVASION` | list 58 | list 59 |
| Imperial Patronage (donations) | `DONATION_EVENT` | leaderboard 79 | |

Berimond Invasion has a player board per faction; name the one you want:

```python
from empire_core.enums import RankingType

client.events.get_scores(Event.FACTION_INVASION, list_type=RankingType.FACTION_INVASION_PLAYER_RED)
```

The top of every board of every running event:

```python
for event in client.events.get_running_score_events():
    for board in client.events.scoreboard(event).lists:
        top = client.events.get_scores(event, list_type=board, rank=1)
        print(event.name, board.name, [row.points for row in top.scores[:3]])
```

The nomad and samurai invasions have only an alliance board in the game. Events
the game shows no board for are not listed: the lucky wheel and the gacha
events show only your own rank, and the colossus uses a command of its own. The
kingdoms league, the alliance mobilisation and raid events, the tournaments and
the temporary-server and battle-ground boards are not covered yet; the
`client.ranking` calls reach their lists directly.

## Leagues and pages

Your league is the one the server's `sei` packet named for the event (for the
invasions, the one for that board), and league 1 when it named none, as in the
game; `client.events.get_league_id(event_id)` reads it. The donation board has
no league.

Most boards are `hgh` lists, and the server decides how long their pages are
(8 rows, seen live); `rank` asks for the page around that rank. The two
leaderboards page with `llsp`, from `rank`, `page_size` rows at a time (10 by
default), and a name search there pages to the first hit, or comes back empty
when there is none.

`hgh` is shared with other lists, the alliance search among them. If a request
times out, its late reply can still arrive and answer your next `hgh` call: a
reply for a list that is not the event's raises `ReplyMismatchError`, but one
for the same board cannot be told apart, so the call after a timeout may
return the late page. Seen live with no event running: asking for
your own page of a player board got no answer at all, where `rank=1` was
answered.

## When an event is not running

An event runs from the `sei` packet that names it until a `see` push ends it or
its time (the entry's `RS`) runs out.

```python
from empire_core import EventNotRunningError

try:
    client.events.get_scores(Event.SAMURAI_INVASION, alliance=True)
except EventNotRunningError:
    print("not running")
```

Asking for a board the event does not have (the player board of the nomad
invasion, say) raises `ValueError`.
