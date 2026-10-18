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

`get_raid_boss_status()` requests the current boss identity, level, health, revival
percentage, stage, cards and walls. Boss ids use the generated `RaidBoss` enum;
unknown bosses and card statuses remain integers. Health rounds up to two decimal
places as in the client. Wall regeneration times are seconds at receipt.

The running `RaidBossEvent.boss_status` also updates from embedded `sei.BSE` and
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

BREAKING CHANGE: event 129 is now `Event.GRAND_TOURNAMENT`, with `GrandTournamentEvent`,
`GrandTournamentQuestStatus`, `GrandTournamentQuestSlot`, `GrandTournamentQuestProgress`,
`GrandTournamentContribution`, `get_grand_tournament_status()` and
`get_grand_tournament_contributions()`. The previous backend-derived public names are removed.
