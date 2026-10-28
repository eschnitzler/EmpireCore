---
description: The running events, their scores and leagues, and their scoreboards, by the event's name.
---

# Events and their scoreboards

The state keeps every running event, as the server's `sei` and `tei` packets
describe it, and `client.events` reads an event's scoreboard the way its dialog
does: it picks the board, the command and your league for you.

## The running events

Events are named by the game data's `Event` enum, after the English title
players see: Berimond is `Event.BATTLE_FOR_BERIMOND`, event 106
`Event.OUTER_REALMS`. An event without a title keeps the client's name, and
each member's docstring gives both. The names are English;
`Event.OUTER_REALMS.display_name("de")` (any language code) gives the title
players see in their language.

```python
from empire_core.gamedata import Event

for event_id, event in client.events.running.items():
    print(event_id, type(event).__name__, round(event.remaining_seconds()))

point = client.state.get_event(Event.NOBILITY_CONTEST)       # None when it is not running
if point is not None:
    print(point.league_id, point.own_rank, point.own_points)

client.events.is_running(Event.SAMURAI_INVASION)
```

Each event is a model of its kind, with the fields its game dialog reads, and
`raw` holding what the server sent:

| Model | Events | What it adds |
|---|---|---|
| `ScoredEvent` | the score events below | `league_id`, `own_rank` (-1 unranked), `own_points`, `max_points`, `difficulty_id`, `parts` |
| `NobilityContestEvent` | `NOBILITY_CONTEST` | `point_event_type` |
| `MaraudersContestEvent` | `MARAUDERS_CONTEST` | `reward_set_id`, `total_hours` |
| `GrandNobilityPrizeEvent` | `GRAND_NOBILITY_PRIZE` | `reward_set_id`, `upcoming_event_ids` |
| `GachaEvent` | the gacha events | `reward_set_id`, `free_chest_reset_time` |
| `InvasionEvent` | the alien, red alien, nomad and samurai invasions, the Berimond invasion | your and your alliance's scores in `parts` (`SP` and `A`; `FB`, `FR` and `A` for the Berimond invasion; the nomads' khan camp in `AC`) |
| `BerimondEvent` | `BATTLE_FOR_BERIMOND` | `league_id`, `unlocked`, `own_rank`, `own_points`, your faction |
| `RiftRaidEvent` | `RIFT_RAID` | your `score`, the alliance's `league_id`, `alliance_points` and `alliance_rank`, `boss_level_points` |
| `OuterRealmsEvent` | `OUTER_REALMS` | `daily_reset_time`, `castle_bought` |
| `ImperialPatronageEvent` | `IMPERIAL_PATRONAGE` | `setting_id`, `donated_points` |
| `KingdomsLeagueEvent` | `KINGDOMS_LEAGUE` | `remaining_days`, `original_days`, `has_alliance_ranking` |
| `GlobalEffectEvent`, `GlobalEffectBuffEvent` | `GLOBAL_EFFECT`, `GLOBAL_EFFECT_BUFF` | the effects and their ends, the boosts |
| `AllianceTournamentEvent` | `ALLIANCE_TOURNAMENT` | your alliance's score in `parts["A"]` |
| `GrandTournamentEvent` | `GRAND_TOURNAMENT` | your and your alliance's scores in `parts` (`SP` and `A`), `subdivision_id`, `division_round_id` |
| `WheelOfFortuneEvent` | `WHEEL_OF_FORTUNE`, `WHEEL_OF_UNIMAGINABLE_AFFLUENCE` | the point event score, `has_free_spin`, `pro_mode`, `win_class`, the jackpot sets |
| `SeasonEvent` | `THORN_KING`, `BLADE_COAST`, `UNDERWORLD` | `unlocked`, `finished`, `map_id`, `reward_id` |
| `TravelingKnightsEvent` | the Traveling Knights event | `parts_found`, `artifact_league_id`, `skin_id` |
| `TournamentEvent` | `TOURNAMENT` | `own_rank`, `own_fame_points`, `booby_prize_min_fame`, the `ranking` (each a `TournamentRank`) |
| `CampaignEvent`, `CampaignQuestEvent` | `TIME_LIMITED_CAMPAIGN_EVENT`, `TIME_LIMITED_CAMPAIGN_QUEST_EVENT` | the campaign's `quests` (each a `Quest`), its reward ids; the quests (`QuestId`) the quest event times |
| `BannerOfGloryEvent`, `AllianceBonusEvent` | `BANNER_OF_GLORY`; `PRIME_ALLI_BONUS`, `ALLIANCE_PRIME_DAY` | `bonus_percent` |
| `DiscountSaleEvent` | `RELIC_ENCHANTER_PRIME_SALE`, `SEASON_PASS_PRIME_SALE` | `discount` |
| `WorldCupEvent` | `WORLD_CUP` | the teams, `vote`, `bet_price_rubies`, `rubies_spent`, `bonus_rubies` |
| `SkipForFreeEvent`, `GiftEvent`, `FortuneTellerEvent` | `SKIP_FOR_FREE`, `GIFT_BOX`, `FORTUNE_TELLER` | `free_skip_seconds`; `collected`; `tries`, `daily_reset_time` |
| `SpecialEvent` | any other | `event_id`, `event`, `end_time`, `raw` |

An event's rewards come from its reward sets, which are not `rewards` rows but
keys into the game data: `league_rewards()` on a `reward_set_id` event (and
on `BerimondEvent`, or an `EventPart` given its event) gives your league's
`LeagueTypeEventDef`, its points thresholds and reward lists, and
`leaderboard_rewards()` on a scored event or `ImperialPatronageEvent` gives the
leaderboard's rank bands (`LeaderboardRewardDef`). Each row's `rewards()` reads
what the rewards give, as typed collectables. Both load the game data.

```python
event = client.state.get_event(Event.MARAUDERS_CONTEST)
row = event.league_rewards()
for points, rewards in zip(row.needed_points, row.rewards()):
    print(points, rewards)
```

Your points arrive in the server's `pep` pushes as you score, and
`client.events.get_own_points(event)` asks for them (see [Your own rank and
points](#your-own-rank-and-points)). A later entry
for a running event is read over it the way the game reads it: a field it
leaves out mostly keeps its value, but the samurai and Berimond invasions build
their scores anew from every entry, and Berimond's own rank and points start
over with each one. A `cqs` push reads the running campaign's quests again. The models never change: each packet replaces them.

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
scores = client.events.get_scores(Event.BATTLE_FOR_BERIMOND)

print(scores.league_id, scores.total)  # the league shown, and how many are ranked
for row in scores.scores:
    print(row.rank, row.name, row.points, row.alliance_name)
```

By default you get the page that holds your own score, where the game's dialogs
open. Other pages:

```python
client.events.get_scores(Event.BATTLE_FOR_BERIMOND, rank=1)            # the top of your league
client.events.get_scores(Event.BATTLE_FOR_BERIMOND, name="Someone")    # around a name
client.events.get_scores(Event.BATTLE_FOR_BERIMOND, league_id=3)       # the top of another league
client.events.get_scores(Event.NOMAD_INVASION_72, alliance=True)  # the alliance board
```

Berimond's leagues are its lists: 1 blue, 2 red, 3 and 4 the legendary blue
and red. While Berimond is locked to you, its board opens on the top of
league 1, as in the game.

Each row is an `EventScore`: `rank`, `points` and `name` always, and what the
board gives besides. Player rows on most boards carry `player_id`, `level`,
`alliance_id` and `alliance_name`; alliance rows carry the alliance's
`alliance_id` and `member_count`, with its name in both `name` and
`alliance_name`; the leaderboards (Grand Nobility Prize and Imperial Patronage) carry
`alliance_name` and the game server in `instance_id`, but no ids.

## Your own rank and points

`client.events.get_own_points(event)` asks the server for your rank and points
in a running event, as the game does when an event's dialog opens. Only some
events keep them, `POINT_EVENTS` (in `empire_core.events`), the ones whose game
model has a rank and points:

| In the game | `Event` |
|---|---|
| Battle for Berimond | `BATTLE_FOR_BERIMOND` |
| Nobility Contest, Marauders' contest, Grand Nobility Prize | `NOBILITY_CONTEST`, `MARAUDERS_CONTEST`, `GRAND_NOBILITY_PRIZE` |
| the alliance tournament | `ALLIANCE_TOURNAMENT` |
| the alien, red alien, nomad, samurai and Berimond invasions | `WAR_OF_THE_REALMS`, `BLOODCROW_INVASION`, `NOMAD_INVASION_72`, `SAMURAI_INVASION`, `BERIMOND_INVASION` |
| the alliance Grand Tournament and raid boss | `GRAND_TOURNAMENT`, `RIFT_RAID` |
| the Wheels of Fortune | `WHEEL_OF_FORTUNE`, `WHEEL_OF_UNIMAGINABLE_AFFLUENCE` |
| the gacha events | `GACHA_DECO2X2`, `ENCHANTED_SNOWGLOBE`, `SUMMONING_OF_THE_HOLLOW_MOON`, `SANDS_OF_FORTUNE`, `KINGS_BANQUET`, `HALLOWEEN_BANQUET`, `MIDNIGHT_MARKET`, `CARNIVAL_OF_MASKS` |

Any other event (the shops, sales and skins, the Imperial Patronage) raises
`EventHasNoPointsError` without asking, as the server leaves such a request
unanswered (seen live); one that is not running raises `EventNotRunningError`.

```python
points = client.events.get_own_points(Event.SAMURAI_INVASION)
print(points.own_ranks, points.own_points)   # [yours, your alliance's]

event = client.state.get_event(Event.SAMURAI_INVASION)  # updated by the same reply
if event is not None:
    print(event.parts["SP"].own_points, event.parts["A"].own_points)
```

The reply's `own_ranks`, `own_points` and `max_points` are lists with one value
per score the event keeps (-1 is unranked):

| Events | The values |
|---|---|
| the score events (nobility contest, marauders, Grand Nobility Prize, gacha) | yours |
| Berimond, the Wheel of Fortune | yours, in the first value only |
| the alliance tournament | your alliance's, in the first value only |
| the alien, red alien, nomad and samurai invasions, the alliance Grand Tournament | yours, your alliance's |
| the Berimond invasion | the blue players', the red players', your alliance's |
| the Rift Raid | yours, your alliance's, and `boss_level_points` |

The state applies the reply before the call returns, read the event's way:
`own_rank` and `own_points` on a score event, Berimond or a Wheel of Fortune, one per
part in `parts` on an invasion, the alliance Grand Tournament or the alliance
tournament, `score` and `alliance_points` on the raid boss.

## Which events have a board

`EVENT_SCOREBOARDS` (in `empire_core.events`) maps each event with a board to
its `Scoreboard`, the boards its dialogs open; `client.events.scoreboard(event)`
reads one, and raises `ValueError`, naming the events that have one, for an
event without.

| In the game | `Event` | Player board | Alliance board |
|---|---|---|---|
| Battle for Berimond | `BATTLE_FOR_BERIMOND` | list 30 | |
| Nobility Contest | `NOBILITY_CONTEST` | list 40 | |
| Marauders' contest | `MARAUDERS_CONTEST` | list 41 | |
| War of the Realms (alien invasion) | `WAR_OF_THE_REALMS` | list 44 | list 45 |
| Nomad Invasion | `NOMAD_INVASION_72` | | list 47 |
| Samurai Invasion | `SAMURAI_INVASION` | | list 52 |
| Grand Nobility Prize | `GRAND_NOBILITY_PRIZE` | leaderboard 53 | |
| Berimond Invasion | `BERIMOND_INVASION` | lists 54 (blue) and 55 (red) | list 56 |
| Bloodcrow invasion | `BLOODCROW_INVASION` | list 58 | list 59 |
| Imperial Patronage (donations) | `IMPERIAL_PATRONAGE` | leaderboard 79 | |

Berimond Invasion has a player board per faction; name the one you want:

```python
from empire_core.enums import RankingType

client.events.get_scores(Event.BERIMOND_INVASION, list_type=RankingType.BERIMOND_INVASION_PLAYER_RED)
```

The top of every board of every running event:

```python
for event in client.events.running_score_events:
    for board in client.events.scoreboard(event).lists:
        top = client.events.get_scores(event, list_type=board, rank=1)
        print(event.name, board.name, [row.points for row in top.scores[:3]])
```

The nomad and samurai invasions have only an alliance board in the game. Events
the game shows no board for are not listed: the Wheel of Fortune and the gacha
events show only your own rank (`get_own_points` reads it), and the colossus uses a command of its own. The
kingdoms league, the alliance Grand Tournament and raid boss events, the
tournaments and the Outer Realms and Beyond the Horizon boards are not covered
yet; the `client.ranking` calls reach their lists directly.

## Leagues and pages

Your league is the one the event's model holds (for the invasions, the one of
that board's part), and league 1 when the server named none, as in the game;
`client.events.league_id(event_id, part)` reads it, and raises
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

## Minigames

The minigame calls update the event they play, as the game does:

| Call | Event | Rubies |
|---|---|---|
| `spin_wheel_of_fortune(wheel)`, `change_wheel_of_fortune_mode()` | the Wheels of Fortune | no, tickets |
| `buy_wheel_of_fortune_jackpot()`, `increase_wheel_of_fortune_win_class()` | `WHEEL_OF_FORTUNE` | `spend_rubies` |
| `pull_gacha(event, pulls)` | the gacha events | `spend_rubies` (the price is in game data the library does not load) |
| `donate_to_colossus(castle_id, wood=, stone=)`, `donate_to_gold_colossus(coins)` | the colossi | no |
| `get_imperial_patronage_progress()`, `donate_items({item_id: amount})`, `donated_points` | `IMPERIAL_PATRONAGE` | `donate_items` needs `spend_rubies` (an item can be rubies, in game data the library does not load) |
| `give_marauder_packages(castle_id, ...)` | `MARAUDERS_CONTEST` | no; returns your points |
| `buy_artifact_pieces(event, pieces)` | the Traveling Knights event | `spend_rubies` |
| `validate_shady_lady_target()`, `skip_shady_lady_target()` | `SHADY_LADY` | the skip needs `spend_rubies` |
| `buy_fortune_teller_reading()` | `FORTUNE_TELLER` | `spend_rubies` |
| `vote_world_cup(vote)` | `WORLD_CUP` | no |
| `get_collector_currency(player_id)` | the collector events | no |

A free gacha chest (`cfc`) and an artifact piece found (`saf`) come as pushes and
update their event.

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
