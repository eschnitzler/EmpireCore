---
description: The running events, their scores and leagues, and their scoreboards, by the event's name.
---

# Events and their scoreboards

The state keeps every running event, as the server's `sei` and `tei` packets
describe it, and `client.events` reads an event's scoreboard the way its dialog
does: it picks the board, the command and your league for you.

## The running events

Events are named by the game data's `Event` enum, which uses the client's own
names: Berimond is `Event.FACTION`.

```python
from empire_core.gamedata.ids import Event

for event_id, event in client.state.get_events().items():
    print(event_id, type(event).__name__, round(event.remaining_seconds()))

point = client.state.get_event(Event.POINT_EVENT)       # None when it is not running
if point is not None:
    print(point.league_id, point.own_rank, point.own_points)

client.state.is_event_active(Event.SAMURAI_INVASION)
```

Each event is a model of its kind, with the fields its game dialog reads, and
`raw` holding what the server sent:

| Model | Events | What it adds |
|---|---|---|
| `ScoredEvent` | the score events below | `league_id`, `own_rank` (-1 unranked), `own_points`, `max_points`, `difficulty_id`, `parts` |
| `PointEvent` | `POINT_EVENT` | `point_event_type` |
| `BeggingKnightsEvent` | `BEGGING_KNIGHTS` | `reward_set_id`, `total_hours` |
| `LongTermPointEvent` | `LONG_TERM_POINT_EVENT` | `reward_set_id`, `upcoming_event_ids` |
| `GachaEvent` | the gacha events | `reward_set_id`, `free_chest_reset_time` |
| `InvasionEvent` | the alien, red alien, nomad and samurai invasions, the Berimond invasion | your and your alliance's scores in `parts` (`SP` and `A`; `FB`, `FR` and `A` for the Berimond invasion; the nomads' khan camp in `AC`) |
| `BerimondEvent` | `FACTION` | `league_id`, `unlocked`, `own_rank`, `own_points`, your faction |
| `RaidBossEvent` | `ALLIANCE_RAIDBOSS_EVENT` | your `score`, the alliance's `league_id`, `alliance_points` and `alliance_rank`, `boss_level_points` |
| `TempServerEvent` | `TEMP_SERVER` | `daily_reset_time`, `castle_bought` |
| `DonationEvent` | `DONATION_EVENT` | `setting_id` |
| `KingdomsLeagueEvent` | `SEASON_LEAGUE` | `remaining_days`, `original_days`, `has_alliance_ranking` |
| `GlobalEffectEvent`, `GlobalEffectBuffEvent` | `GLOBAL_EFFECT`, `GLOBAL_EFFECT_BUFF` | the effects and their ends, the boosts |
| `SpecialEvent` | any other | `event_id`, `event`, `end_time`, `raw` |

Your points arrive in the server's `pep` pushes as you score. A later entry
for a running event is read over it the way the game reads it: a field it
leaves out mostly keeps its value, but the samurai and Berimond invasions build
their scores anew from every entry, and Berimond's own rank and points start
over with each one. The models never change: each packet replaces them.

`client.events.refresh()` asks the server for the events again and returns
them once its answer is applied. `client.events.get_active_events()` lists the
running events with their in-game titles (from the game's language CDN, in the
language you ask for; a CDN outage only costs the titles):

```python
for event in client.events.get_active_events(lang="de"):
    print(event.display_name, event.details.remaining_seconds())
```

`client.state.on_event_added`, `on_event_removed` and `on_events_updated` call
you back when an event starts, ends, or a packet updates the events.

## An event's scores

```python
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
kingdoms league, the alliance mobilisation and raid boss events, the
tournaments and the temporary-server and battle-ground boards are not covered
yet; the `client.ranking` calls reach their lists directly.

## Leagues and pages

Your league is the one the event's model holds (for the invasions, the one of
that board's part), and league 1 when the server named none, as in the game;
`client.events.get_league_id(event_id, part)` reads it, and raises
`EventNotRunningError` for an event that is not running. The donation board
has no league.

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
its time (the entry's `RS`) runs out; one never given a time has ended, as in
the game. The kingdoms league and the global effect events come in `tei`
packets instead and end with a `tee` (or a `see`); they carry no `RS`: the
kingdoms league runs while it has more than a day left, and on its last day
ends with the season event, and a global effect event ends with the last of its
effects.

```python
from empire_core import EventNotRunningError

try:
    client.events.get_scores(Event.SAMURAI_INVASION, alliance=True)
except EventNotRunningError:
    print("not running")
```

Asking for a board the event does not have (the player board of the nomad
invasion, say) raises `ValueError`.
