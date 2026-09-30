---
description: The EmpireCore API, generated from the source.
---

# API reference

Generated from the source's docstrings. Each model lists its fields, with the
wire key each one is read from and what it holds.

!!! info "What is public"

    Names exported from the package root, `from empire_core import ...`, are
    the stable surface. Names reached only through submodules are listed here
    for reference, and may move in any release.

## Core

| Page | What it covers |
|---|---|
| [Client](client.md) | `EmpireClient`, `EmpireConfig`, accounts and the account pool, `BaseService` |
| [State](state.md) | `GameState` and the state models |
| [Exceptions](exceptions.md) | Every error, and the server's error codes as `GGEError` |
| [Enums](enums.md) | Game constants, one module per area |
| [Game data](gamedata.md) | `GameData`, its row models and the generated ids |
| [Protocol](protocol.md) | Request and response bases, packets, codecs and the connection |
| [Utilities](utils.md) | CDN-backed event and troop data |

## Areas

Each area page starts with its service, reached as `client.<area>`, then its
models.

| Page | Service |
|---|---|
| [Map](map.md) | `client.map` |
| [Ranking](ranking.md) | `client.ranking` |
| [Events](events.md) | `client.events` |
| [Commanders](commanders.md) | `client.commanders`, `client.equipment`, `client.skills` |
| [Castle](castle.md) | `client.castle` |
| [Army](army.md) | `client.army` |
| [Movements](movements.md) | `client.movements` |
| [Messages](messages.md) | `client.messages` |
| [Defense](defense.md) | `client.defense` |
| [Combat](combat.md) | used by `client.attack` |
| [Player](player.md) | `client.player` |
| [Attack](attack.md) | `client.attack` |
| [Alliance](alliance.md) | `client.alliance` |
| [Spy](spy.md) | `client.spy` |
