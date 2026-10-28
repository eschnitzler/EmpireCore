# Events

Active game events and their scoreboards behind `client.events`.

## `events.service`

::: empire_core.events.service

## `events.models`

::: empire_core.events.models

## `events.titles`

::: empire_core.events.titles

## Alliance Grand Tournament status

`get_grand_tournament_status()` requests participating member count and typed quest slots.
The running `GrandTournamentEvent.quest_status` retains the last successful response,
using a new event snapshot for each update. Slot ids preserve their original zero-based
positions even when a malformed row is skipped with a warning. Quest definition ids remain
integers because no generated alliance quest enum is available.

`get_grand_tournament_contributions()` requests ranked player contributions. Both methods
require a running Grand Tournament and accept keyword-only `timeout`. Refusals and transport
failures raise; missing or malformed status containers raise `PacketError`.

::: empire_core.events.status_models

## Alliance raid status

`get_rift_raid_status()` requests the current boss identity, level, health, revival
percentage, stage, cards and walls. Boss ids use the generated `RaidBoss` enum;
unknown bosses and card statuses remain integers. Health rounds up to two decimal
places as in the client. Wall regeneration times are seconds at receipt.

The running `RiftRaidEvent.boss_status` also updates from embedded `sei.BSE` and
`bbs` broadcasts. Updates preserve prior identity, stage and walls only where the
client does; inactive replies clear the active boss fields. These models add no
raid selection, start, abort, claim or other mutation API.

## Grand Tournament quests

`start_grand_tournament_quest(slot_id, alliance_quest_id)` accepts a slot's current quest
and consumes an event ticket. `complete_grand_tournament_quest()` collects your completed
quest. `reroll_grand_tournament_quest(slot_id, alliance_quest_id)` rerolls an unassigned slot.
The server checks tickets, assignment, completion and eligibility; a refusal raises `CommandError`.

`cancel_grand_tournament_quest(spend_rubies=True)` cancels your active quest and permits its
configured ruby cost (the client defaults to 199). `skip_grand_tournament_cooldown(slot_id,
alliance_quest_id, spend_rubies=True)` permits the client's 999-ruby cooldown skip.
Neither premium action sends without explicit consent. These methods do not purchase tickets.

Each action returns a typed response whose `status` holds the reply's event id and quest slots.
The cached event receives the slots in packet order while retaining any known participant count;
that count is `None` when no status query has supplied it. Replies after a timeout or an event
or alliance context change cannot update a replacement context. A changed context raises
`ReplyMismatchError`, including leaving and rejoining the same alliance. All methods require a running
Grand Tournament and accept keyword-only `timeout`.

BREAKING CHANGE: event 129 is now `Event.GRAND_TOURNAMENT`, with ranking list
`RankingType.GRAND_TOURNAMENT` (84), `GrandTournamentEvent`,
`GrandTournamentQuestStatus`, `GrandTournamentQuestSlot`, `GrandTournamentQuestProgress`,
`GrandTournamentContribution`, `get_grand_tournament_status()` and
`get_grand_tournament_contributions()`. The previous backend-derived public names are removed.


## Raid boss controls

`select_raid_boss(boss_id)` selects a boss; `abort_raid()` aborts the current raid.
Both require the running raid event and leader or deputy permission, which the server checks.
Known boss cards must be available for selection, and the last playable boss cannot be aborted.
These actions have no client ruby payment path and accept keyword-only `timeout`.

Both return typed acknowledgements without inventing a boss status. The existing `bbs`
broadcast handler updates the event in receive order; use `get_rift_raid_status()` to request
a fresh snapshot. Refusals raise `CommandError`; timeouts and malformed replies raise.

## Battle for Berimond

`get_berimond_targets()` requests the event’s special camp candidate identifiers and
returns a tuple of `BerimondTarget` records in server order. Each `special_camp_id` is
a `BerimondSpecialCamp`, the watchtower or capital's row of `GameData.berimond_special_camps`;
unknown identifiers stay ints and duplicates are preserved.
Membership in this list does not establish attack eligibility: faction, spectator,
protection and destroyed-target restrictions still apply.
These identifiers are not map area ids or coordinates. Obtain map positions separately;
`client.attack.get_attack_info()` supports Berimond village, tower and capital
attack pre-calculations through its `area_type` argument, and the faction camp conquest
(`cfi`) with `area_type=MapItemType.FACTION_CAMP, conquer=True`.

`get_berimond_balance()` returns a `BerimondBalance` with `red_players` and `blue_players`.
Negative counts clamp to zero as in the client. No faction percentage is inferred when
both counts are zero because the client retains its prior percentage in that case.

Both reads require a running Battle for Berimond event, accept keyword-only `timeout`,
and return fresh results without caching them. Choosing or joining a faction is not
required. Refusals raise `CommandError`, transport failures retain their typed exception,
and missing or malformed successful payloads raise `PacketError`.

`get_berimond_points()` returns `BerimondPoints`, the `red_points` and `blue_points` of
the two factions.

`join_berimond(camp)` joins the event with one of its prebuilt camps, a `PrebuiltCastle`
such as `PrebuiltCastle.BERIMOND_SIMPLE_CAMP`. The camp whose only price is rubies is bought
with them and needs `spend_rubies=True`; any other is bought with its resources, the game
offering no ruby price for it, and `spend_rubies` pays the missing ones with rubies. A refusal, such as
`FACTION_LAST_MAN_STANDING_ACTIVE`, raises `CommandError`.

`berimond_kingdom_status` sends nothing: it is the last `BerimondKingdomStatus` (`fki`),
pushed on its own or inside a `kpi`, kept on the running `BerimondEvent` as
`kingdom_status`. It says whether last man standing is on for either faction, whether
you still take part, and which capital is open to attack.

::: empire_core.events.berimond_models

## Season event maps

`join_season_camp(event)` enters a running season event's map (the Thorn King, the Blade
Coast, the Underworld) at your camp there. `unlock_season_camp(camp)`
starts on the map with one of its prebuilt camps (`PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP`), the
camp naming its map, with the same ruby consent as `join_berimond`; `ruby_price=True`
(with `spend_rubies=True`) buys a camp priced in resources at its ruby price instead. The transfers to the map and their skips are on `client.movements`
(`skip_treasure_map_transfer_time(map_id, transfer_type, minute_skip)` among them).

::: empire_core.events.season_models
