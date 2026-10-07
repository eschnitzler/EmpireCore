---
description: The EmpireCore API, generated from the source.
---

# API reference

Generated from the source's docstrings. Each model lists its fields, with the
wire key each one is read from and what it holds.

!!! info "What is public"

    A name is public when the package root or a first-level package exports
    it in its `__all__`:

    - `from empire_core import ...`: the client, its configuration, the
      account pool, every error, the state models and the common enums.
    - `from empire_core.<area> import ...`: each game area (`map`, `castle`,
      `alliance`, `spy`, ...) exports its service, its request and response
      models and its enums.
    - `empire_core.enums`, `gamedata`, `combat`, `protocol`, `state`,
      `services`, `texts`, `accounts`, `config`, `pool` and `exceptions` export the
      same way.

    The modules inside them (`empire_core.map.models.items`,
    `empire_core.spy.service`, ...) are private: this reference shows where
    each name is defined, but those paths may move in any release.
    `empire_core.client` and `empire_core.network` are private as a whole;
    what they hold that you need is exported from the root.

## Core

| Page | What it covers |
|---|---|
| [Client](client.md) | `EmpireClient`, `EmpireConfig`, accounts and the account pool, `BaseService` |
| [State](state.md) | `GameState` and the state models |
| [Exceptions](exceptions.md) | Every error, and the server's error codes as `GGEError` |
| [Enums](enums.md) | Game constants, one module per area |
| [Game data](gamedata.md) | `GameData`, its row models and the generated ids |
| [Texts](texts.md) | The game's texts and error messages from its language file |
| [Protocol](protocol.md) | Request and response bases, packets, codecs and the connection |
| [Utilities](utils.md) | Internal: cancelling long calls |

## Areas

Each area page starts with its service, reached as `client.<area>`, then its
models.

| Page | Service |
|---|---|
| [Map](map.md) | `client.map` |
| [Ranking](ranking.md) | `client.ranking` |
| [Quests](quests.md) | read from `client.state` |
| [Events](events.md) | `client.events` |
| [Commanders](commanders.md) | `client.commanders`, `client.equipment`, `client.skills` |
| [Castle](castle.md) | `client.castle` |
| [Army](army.md) | `client.army` |
| [Movements](movements.md) | `client.movements` |
| [Messages](messages.md) | `client.messages` |
| [Rewards](rewards.md) | `client.rewards` |
| [Defense](defense.md) | `client.defense` |
| [Combat](combat.md) | used by `client.attack` |
| [Player](player.md) | `client.player` |
| [Attack](attack.md) | `client.attack` |
| [Alliance](alliance.md) | `client.alliance` |
| [Spy](spy.md) | `client.spy` |
