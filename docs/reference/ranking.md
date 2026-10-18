# Ranking

Highscore lists and leaderboards behind `client.ranking`.

## `ranking.service`

::: empire_core.ranking.service

## `ranking.models`

::: empire_core.ranking.models

## Dedicated event boards

`client.ranking.get_colossus_highscore(search_value="-1")` returns donor records and
pagination metadata. Search by donor name or rank; use the last rank to stop paging.
Donation points are before the client conversion (.01, or .01093 for coin colossus).
The request contains no event id and addresses the server's current colossus.

`get_season_info()` returns division, medals, passes and payout information supplied by
the server. Missing sections remain `None`. `get_season_ranks()` returns your own ranks;
use `get_highscore()` with `RankingType.KINGDOMS_LEAGUE_SEASON` or
`KINGDOMS_LEAGUE_SEASON_EVENT` for paginated player boards and their alliance equivalents
for alliance boards. These requests concern the current season, not a previous run.

::: empire_core.ranking.event_models

`client.events.get_battleground_rank(alliance_id)` returns only your alliance's
rank; `get_battleground_timers()` returns relink/revival seconds. Both require a
running battleground event. `get_player_performance(event, player_id)` requests
`gpe` counters as `PerformanceStatistic` values (unknown ids stay integers).
`get_temporary_server_ranks()` returns current daily and overall points/ranks.
Unavailable event context raises `EventNotRunningError`; unavailable server
context and other refusals raise `CommandError`. Transport failures propagate.

Temporary-server and battleground board pages already use `ranking.get_highscore()`:
select the current list or `TEMPSERVER_PREVIOUS_RUN_PLAYER`,
`ALLIANCE_BATTLE_GROUND_PREVIOUS_RUN_ALLIANCE` or
`ALLIANCE_BATTLE_GROUND_PREVIOUS_RUN_PLAYER` for previous-run boards. Those rows
carry their display name and shown rank; owner information is retained when supplied.
`abgph`, `trt`, `gpe` and `tsh` carry no pagination controls or previous-run selector.

::: empire_core.events.board_models
