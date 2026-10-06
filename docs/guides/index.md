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
client.defense      client.ranking     client.events
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

## Game state and data

<div class="grid cards" markdown>

-   :material-database-sync-outline:{ .lg .middle } **[State and freshness](game-state.md)**

    ---

    What `client.state` holds, and how old it is.

-   :material-run-fast:{ .lg .middle } **[Reacting to movements](movements.md)**

    ---

    Callbacks for incoming attacks, arrivals, recalls and removals.

-   :material-magnify:{ .lg .middle } **[Lookups by name](game-data.md)**

    ---

    Generals, skills, units and more, by the key that names them.

-   :material-format-list-numbered:{ .lg .middle } **[Generated ids](game-data-ids.md)**

    ---

    Game-data ids as enums, for autocomplete.

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
