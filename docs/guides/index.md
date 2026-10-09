---
description: Task-oriented guides for every part of the game EmpireCore covers.
---

# Guides

Every service hangs off the client, built when the client is: there is nothing
to wire up. Each guide below covers one of them, or one of the parts that sit
beside them.

```python
client.alliance     client.castle      client.army       client.attack
client.commanders   client.equipment   client.skills     client.spy
client.map          client.movements   client.messages   client.player
client.defense      client.ranking     client.events     client.rewards
```

## Services

<div class="grid cards" markdown>

-   :material-account-group:{ .lg .middle } **[Alliance](alliance.md)**

    ---

    Chat, help requests, applications, ranks and the treasury.

-   :material-email-outline:{ .lg .middle } **[Messages](messages.md)**

    ---

    The mailbox, reading and sending mail, battle reports.

-   :material-castle:{ .lg .middle } **[Castle](castle.md)**

    ---

    Castles, resources, buildings, the construction queue and tax.

-   :material-shield-outline:{ .lg .middle } **[Defense](defense.md)**

    ---

    Reading and setting a castle's keep, wall and moat.

-   :material-account-multiple-plus:{ .lg .middle } **[Army](army.md)**

    ---

    Units, recruitment and the hospital.

-   :material-chess-knight:{ .lg .middle } **[Commanders](commanders.md)**

    ---

    Commanders and castellans, and renaming them.

-   :material-star-four-points-outline:{ .lg .middle } **[Skills and generals](skills.md)**

    ---

    Generals, their abilities, and the skill trees.

-   :material-shield-sword-outline:{ .lg .middle } **[Equipment](equipment.md)**

    ---

    The equipment inventory, equipping and unequipping.

-   :material-sword:{ .lg .middle } **[Attack](attack.md)**

    ---

    Sending an attack with waves you build yourself, and attack presets.

-   :material-auto-fix:{ .lg .middle } **[Filling waves](filling-waves.md)**

    ---

    Waves filled from a target's coordinates, the way the game does it.

-   :material-incognito:{ .lg .middle } **[Spy](spy.md)**

    ---

    Spy missions planned for risk, and their reports.

-   :material-map-search-outline:{ .lg .middle } **[Map scanning](map-scanning.md)**

    ---

    Kingdom scans and cheap re-scans.

-   :material-trophy-outline:{ .lg .middle } **[Events](events.md)**

    ---

    The running events and their scoreboards.

-   :material-gift-outline:{ .lg .middle } **[Daily rewards](rewards.md)**

    ---

    The login and startup bonuses, lost and found, the activity chest, the weekly honour reward and patch note rewards.

</div>

The smaller services have no guide of their own; their
[API pages](../reference/index.md#areas) list every call:

- `client.player`: `get_player_info(player_id)`, `get_player_details_bulk(player_ids)`
  and `search_player_by_name(name)`.
- `client.ranking`: `get_highscore(list_type, search_value)` and the event
  leaderboards, `get_ranking_list`, `get_own_ranking_page`,
  `get_ranking_window` and `search_leaderboard`.
- `client.events`: `refresh()`, `get_active_events()` with the events' in-game
  titles, `get_league_id(event_id)` for the leaderboards, `get_scores(event)`
  and `get_own_points(event)` for your own rank and points;
  the running events and their scoreboards have a [guide](events.md).

## Spending rubies

No call spends rubies unless you pass `spend_rubies=True`, the one name for
that consent everywhere. Without it a call that would spend them raises
`ValueError` (`PremiumCommanderCostError` for the premium commander) before
anything is sent. Where the price can be known, from [game data](game-data.md)
or state, only a call that costs rubies needs the flag; where it cannot, the
call always does.

| Rubies are spent on | Calls | Needs the flag |
|---|---|---|
| A ruby price of the item | `castle.build`, `upgrade_building`, `upgrade_defense`, `army.produce_units`, `heal_units` | when the game data prices it in rubies |
| Missing resources | `castle.build`, `upgrade_building`, `upgrade_defense`, `repair_building`, `army.produce_units` | with the flag they are paid with rubies; without it never |
| Finishing at once | `castle.finish_construction` | over 240 seconds left, or a time left it cannot work out |
| | `castle.repair_all`, `army.skip_heal`, `double_production_slot` | always |
| | `army.heal_all` | a price above 0 |
| Travel | `castle.send_resources`, `send_support`, `send_troops`, `attack.send_attack`, the `client.spy` sends | a horse that costs rubies (not paid with feathers), any slowdown, the premium commander when none is free |
| The rest | `castle.buy_expansion`, `rename`, `start_tax`, `player.start_research`, `alliance.donate` | a premium expansion; a rename with no premium account; tax types 5 and 6; a ruby research; donated rubies |

Pricing from game data needs `client.load_game_data()` first, or the call
raises `GameDataNotLoadedError`. Minute skips are items, not rubies, and need
no flag.

## Game state and data

<div class="grid cards" markdown>

-   :material-database-sync-outline:{ .lg .middle } **[State and freshness](game-state.md)**

    ---

    What `client.state` holds, and how old it is.

-   :material-run-fast:{ .lg .middle } **[Reacting to movements](movements.md)**

    ---

    Callbacks for incoming attacks, arrivals, recalls and removals.

-   :material-magnify:{ .lg .middle } **[Game data](game-data.md)**

    ---

    Units, buildings, researches, quests and more, as typed tables keyed by their ids.

-   :material-format-list-numbered:{ .lg .middle } **[Generated ids](game-data-ids.md)**

    ---

    Game-data ids as enums, for autocomplete.

-   :material-translate:{ .lg .middle } **[Game texts](texts.md)**

    ---

    The game's own texts and error messages, in any language.

</div>

## Beyond one client

<div class="grid cards" markdown>

-   :material-account-switch-outline:{ .lg .middle } **[Multiple accounts](multiple-accounts.md)**

    ---

    An account pool that leases one logged-in client per account.

-   :material-code-json:{ .lg .middle } **[Protocol models](protocol-models.md)**

    ---

    Sending any request model directly.

-   :material-alert-circle-outline:{ .lg .middle } **[Error handling](errors.md)**

    ---

    Every error, and what an empty result means.

</div>
