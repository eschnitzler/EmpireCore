# Events

Active game events and their scoreboards behind `client.events`.

## `events.service`

::: empire_core.events.service

## `events.models`

::: empire_core.events.models

## `events.titles`

::: empire_core.events.titles

## Alliance mobilisation status

`get_mobilization_status()` requests participating member count and typed quest slots.
The running `AllianceMobilizationEvent.quest_status` retains the last successful response,
using a new event snapshot for each update. Slot ids preserve their original zero-based
positions even when a malformed row is skipped with a warning. Quest definition ids remain
integers because no generated alliance quest enum is available.

`get_mobilization_contributions()` requests ranked player contributions. Both methods
require a running mobilisation and accept keyword-only `timeout`. Refusals and transport
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
