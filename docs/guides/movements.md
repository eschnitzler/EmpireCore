---
description: React to incoming attacks and occupations, arrivals, recalls and removals with state callbacks.
---

# Reacting to movements

Every army on the move is a `Movement` in `client.state`. Register callbacks
on the state to react as movements appear, arrive, turn back or vanish.

```python
def on_attack(movement):
    print(f"{movement.troop_count} troops from {movement.source_player_name}, "
          f"{movement.time_remaining}s out")

def on_arrived(movement_id, movement):
    print(f"{movement_id} arrived: {movement}")

client.state.on_incoming_attack(on_attack)
client.state.on_movement_arrived(on_arrived)
```

Each one unregisters with its `.remove`, as in
`client.state.on_incoming_attack.remove(on_attack)`; removing a callback not
registered raises `ValueError`.

| Register | Fires |
|---|---|
| `on_incoming_attack(cb)` | Once per newly seen hostile attack |
| `on_incoming_attack_updated(cb)` | When a later packet changes an announced attack |
| `on_incoming_attack_withdrawn(cb)` | When the server removes an announced attack before it arrives |
| `on_occupation_started(cb)` | Once per newly seen occupation of your or an alliance member's area |
| `on_occupation_updated(cb)` | When a later packet changes an announced occupation |
| `on_occupation_ended(cb)` | When an announced occupation leaves state: captured, or driven off |
| `on_movement_arrived(cb)` | Once a movement's travel time is up |
| `on_movement_recalled(cb)` | On the reply to your own recall |
| `on_movement_removed(cb)` | When the server removes a movement (`mrm`) |

## A movement's life

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Tracked: gam, abr/asr or<br/>a send's reply lists it
    Tracked --> Tracked: later packets refresh it
    Tracked --> Arrived: travel time is up<br/>(on_movement_arrived)
    Tracked --> Returning: mcm, your recall<br/>(on_movement_recalled)
    Tracked --> [*]: mrm<br/>(on_movement_removed)
    Arrived --> [*]: removed at once
    Arrived --> Stationed: a support that stays
    Stationed --> [*]: its wait is over
    Returning --> Arrived: home again
```

- **Incoming attacks.** `on_incoming_attack` fires once per attack movement
  that is not your own, is not on its way home and had not already landed when
  first seen, and that is aimed at you or the daimyo township (whoever sends
  it; an alien attack only at you) or at another member of your alliance. On
  an alliance member it fires for a player's attack, an alien attack, the
  alliance nomad camp, and NPCs that are not dungeon owners (outpost, capital
  and metropolis owners, the plague monk, NPC ids the client does not know);
  robber barons, camps, event dungeons and other dungeon owners do not fire
  it. `NPCOwner` names these NPC owner ids, e.g. `NPCOwner.DAIMYO_TOWNSHIP`
  and `NPCOwner.ALLIANCE_NOMAD_CAMP`. An alliance member's attack on someone outside the alliance does not
  fire. An attack whose attacker's record comes in a later packet fires then.
  It does not fire again on later refreshes, nor when a reconnect lists the
  same attack again.
- **Arrival.** The server sends no arrival packet: as in the game client, a
  movement arrives once its travel time is up, and the callback fires then:
  a timer of the state's own waits for the next arrival, so no packet is
  needed. A movement first seen after it arrived does not fire.
- **Stationed supports.** An army that stays at its target is kept in state
  until its wait is over; every other movement is removed before the arrival
  callbacks run.
- **The way home.** An army's way home is a movement of its own, so
  `on_movement_arrived` fires again when the army gets back. Check
  `movement.is_returning` to tell the two apart.
- **Removal.** `mrm` does not say why: a battle ending, a finished recall and a
  support sent home all look the same.
- **Updated attacks.** `on_incoming_attack_updated(old, new)` fires when a
  later packet for an announced attack changes its army (`units`,
  `estimated_size`), its arrival (`estimated_arrival`, by two seconds or more,
  as a speed-up does), its target (`target_id`, `target_area_id`, `target_x`,
  `target_y`) or its commander (`commander`, its equipment and area effects
  included). `old` is the attack as state had it before the packet.
  A packet that changes none of these does not fire it, and neither does the
  packet that announces the attack. Units, the size estimate and the
  commander a later packet leaves out are kept from the earlier one.
- **Withdrawn attacks.** When `mrm` removes an attack that `on_incoming_attack`
  announced and its travel time is not up yet, `on_incoming_attack_withdrawn`
  fires with the attack, after `on_movement_removed`. Use it to retract an
  alert. It is derived from the arrival time, not reported: neither the server
  nor the game client says why a movement is removed. An attack removed within
  two seconds of its `estimated_arrival` (which can run a second late), at or
  after it, or one state no longer tracks, does not fire.
- **Occupations.** A capture attack that lands and wins is followed by an
  occupation (`MovementType.SIEGE` or `OCCUPY_FACTION`, `movement.is_occupation`):
  the game lists it as "Occupying forces", and its travel time is the time the
  occupier must hold the area before it is captured. The capture attack is an
  ordinary attack and goes through `on_incoming_attack`; the occupation is not
  an attack, so the attack callbacks never report it. `on_occupation_started`
  and `on_occupation_updated` do, by the same rules for refreshes, reconnects
  and changes. An occupation counts when it is not your own, is not on its way
  home and holds an area of yours or the daimyo township's, or of another
  member of your alliance, whoever sends it: the game client raises no attack
  warning for occupations, and these are the ones its movement list shows to
  you or your alliance.
- **Ended occupations.** `on_occupation_ended(movement, captured)` fires once
  when an announced occupation leaves state. `captured` is `True` when its
  time ran out, at its arrival (after `on_movement_arrived`) or on an `mrm`
  within two seconds of it or later (after `on_movement_removed`): the area is
  captured. It is `False` when `mrm` removes it earlier (after
  `on_movement_removed`): the occupation was broken, "Occupying forces driven
  off!" in the game. Derived from the arrival time, as withdrawn attacks are.
  An occupation that ends while no session is logged in is not reported.

## What was announced, and announcing again

`client.state.get_announced_attacks()` and `get_occupations()` list what
`on_incoming_attack` and `on_occupation_started` announced that has not
arrived or ended, in the order announced, each as the latest packet has it. That is not
`get_incoming_attacks()`, which lists only attacks aimed at you; the announced
list includes attacks on alliance members.

If a callback could not act on an announcement (an alert that failed to send),
`client.state.reannounce(movement_id)` fires `on_incoming_attack` or
`on_occupation_started` again with the movement as state has it now, and returns
`True`. It returns `False`, firing nothing, for a movement that is not in
those lists: never announced, arrived, removed, or not listed again since a
reconnect (see below). Nothing is re-announced on its own: the movement stays announced,
and later packets for it fire only the `_updated` callbacks. A re-announcement
reaches every `on_incoming_attack` or `on_occupation_started` callback and every
`client.listen()` stream of them as an ordinary `incoming_attack` or
`occupation_started` event; nothing marks it as a repeat.

After a reconnect a movement is listed again only once the movement list the
server pushes after the login has come. With `keep_session`,
`on_session_restored` fires once that list has reached state, or once
`config.request_timeout` passed without it (a warning is logged), so pass
`when_listed=True` there too. The same goes for earlier calls, say to retry an
alert as soon as the session drops: the call returns `True` and the callbacks
fire once the next packet lists the movement, once however often you asked.
The queued call is dropped, firing nothing, if no packet lists the movement
before its travel time is over, the server removes it, or it comes back with
its arrival behind it:

```python
def on_drop() -> None:
    for movement_id in failed_alerts:
        client.state.reannounce(movement_id, when_listed=True)

client.on_disconnect(on_drop)
```

What was announced outlives the session: a reconnect, and also `close()`
followed by `login()`, announces none of it again. A client handed on, as an
[account pool](multiple-accounts.md) lease is, does not announce to its next
holder what it announced to the previous one; read `get_announced_attacks()`
and `get_occupations()`, or call `reannounce`, to catch up. The release drops
the `when_listed` calls still waiting, so the next holder gets none of them.

## Callback signatures

`on_incoming_attack`, `on_incoming_attack_withdrawn` and `on_occupation_started`
take the `Movement`, the `_updated` callbacks the old and the new one, and
`on_occupation_ended` the `Movement` and `captured`.
Arrival, recall and removal callbacks take either the movement id alone or the
id and the `Movement`:

```python
def on_removed(movement_id): ...
def on_removed(movement_id, movement): ...    # prefer this form
```

Prefer the two-argument form. An arrived or removed movement is usually gone
from state before the callback runs, so the id alone can no longer be
resolved. `movement` is `None` only when the server removes a movement state
never tracked.

## Which thread callbacks run on

State callbacks run one at a time on a single callback thread, in the order
their packets arrived, never on the receive thread. A callback may make a
request and wait for its reply, but every callback queued behind it waits too,
so hand long work to another thread.
On an event loop, `client.listen()` delivers the same calls as an
`async for` stream; see [From an asyncio program](game-state.md#from-an-asyncio-program).

The callbacks survive a disconnect and keep working after the next login. When
the connection drops, state is emptied until the login refills it; see
[Disconnects](game-state.md#disconnects).

## The attacker's commander

A movement that carries its commander (the `UM` block, as an attack does) keeps
it whole in `movement.commander`, the same `Commander` model as a `gli` roster
entry; the game client builds both with one factory. Its bonuses resolve the
same way too, equipment set bonuses included. A default commander (a negative
`commander_id`, such as the bought premium commander, -14, or a robber baron
attack's, -15) resolves to its `lords` row's effects in the game data instead
of equipment.

```python
from empire_core.combat import EffectResolver, attacker_flank_effects, commander_bonuses
from empire_core.gamedata import GameData

game_data = GameData.load()
resolver = EffectResolver(game_data)

def on_attack(movement):
    if movement.commander is None:
        return
    bonuses = commander_bonuses(game_data, movement.commander)
    effects = attacker_flank_effects(
        resolver, bonuses, area_type=movement.target_type, player_target=True
    )
    print(effects.melee_bonus, effects.range_bonus, effects.wall_reduction)
    print(resolver.yard_capacity_bonus(bonuses, area_type=movement.target_type, player_target=True))
```

`attacker_flank_effects` gives the multipliers and the wall, gate and moat
reductions the game uses for the fight; a `target_type` of -1 (no target area)
keeps every effect, as the game does. `resolver.yard_capacity_bonus` and
`yard_capacity_boost` are the courtyard additions that `yard_capacity` takes.

`player_target=True` because the attack is on a player, you or an alliance
member: the game client picks the effect filter from the owner of the
movement's target
(`LordEffectHelper.getFilterStrategyByMovementVO`). A player's castle gets the
player-versus-player attack filter, which leaves out the effects flagged for
NPC fights only.

The movement's commander comes with the area effects (`AE`) of the castle it
was sent from. So it matches a roster commander resolved with that castle's
`aci` area effects, passed as `area_effects=` to `commander_bonuses`, not the
bare `gli` entry.

`commander_bonuses` leaves the general's passive effects out, as the game's
movement tooltip does; `attack_dialog_bonuses` with the commander's
`general_skill_ids` adds them. Legend skills belong to the attacking player and
a movement does not carry them.

## Asking for movements

```python
movements = client.movements.get_movements()       # asks the server
attacks = client.movements.get_incoming_attacks()   # reads state
client.movements.recall(movement_id)
```

`recall` works on your own movements that are still heading to their target
(attacks only within 600 seconds of leaving, with exceptions) and your
supports in either direction.

**API:** [`MovementsService`](../reference/movements.md#empire_core.movements.service.MovementsService),
[`Movement`](../reference/movements.md#empire_core.movements.tracked.Movement)
