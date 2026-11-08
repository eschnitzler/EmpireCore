# Player

Player profiles, search and Legendary skills behind `client.player`.

Global effect boosts can be purchased with
`client.player.activate_global_effect_boost(effect_id, spend_rubies=True)`.
This spends rubies: inspect `state.get_event(Event.GLOBAL_EFFECT_BUFF)` for
the offer's `cost` and `boost_value` before opting in. The method waits for
the purchase acknowledgement; `player.boosted_global_effects` changes when
the separate `bie` push arrives. After a timeout, check fresh state before
trying again.

## `player.service`

::: empire_core.player.service

## `player.models.account`

::: empire_core.player.models.account

## `player.models.economy`

::: empire_core.player.models.economy

## `player.models.info`

::: empire_core.player.models.info

## `player.models.profile`

::: empire_core.player.models.profile

## `player.models.progress`

::: empire_core.player.models.progress

## `player.titles`

::: empire_core.player.titles
