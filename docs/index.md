---
title: EmpireCore
description: A fully typed Python client for Goodgame Empire.
hide:
  - navigation
  - toc
---

<div class="ec-hero" markdown>

# EmpireCore

A fully typed Python client for Goodgame Empire. Log in, read your castles,
scan a kingdom, fill and send attacks, and react to incoming armies, all
through typed models that are checked against the game's own client.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Browse the guides](guides/index.md){ .md-button }
[API reference](reference/index.md){ .md-button }

</div>

<div class="grid cards" markdown>

-   :material-shield-check-outline:{ .lg .middle } **Typed end to end**

    ---

    Pydantic v2 models for every command, snake_case fields over the game's
    wire keys, and a `py.typed` marker so your type checker sees all of it.

    [:octicons-arrow-right-24: Protocol models](guides/protocol-models.md)

-   :material-source-branch-check:{ .lg .middle } **Checked against the client**

    ---

    Requests follow the game client's own command objects, key order
    included, and models cite the client class they mirror.

    [:octicons-arrow-right-24: Internals](internals/index.md)

-   :material-alert-octagon-outline:{ .lg .middle } **Honest failures**

    ---

    One `EmpireError` base for everything. No leaked pydantic or socket
    errors, and no empty list that secretly means "the request failed".

    [:octicons-arrow-right-24: Error handling](guides/errors.md)

-   :material-radar:{ .lg .middle } **Fast map scans**

    ---

    Breadth-first kingdom discovery, then cheap targeted re-scans of the
    chunks that held anything, with every failed chunk reported.

    [:octicons-arrow-right-24: Map scanning](guides/map-scanning.md)

-   :material-sword-cross:{ .lg .middle } **Fill waves like the game**

    ---

    `fill_attack` sizes and fills each wave from nothing but the target's
    coordinates, tools first, then units, the way the game's button does.

    [:octicons-arrow-right-24: Filling waves](guides/filling-waves.md)

-   :material-sync:{ .lg .middle } **Thread-safe live state**

    ---

    A background thread applies server pushes while your code reads
    consistent snapshots and reacts to incoming attacks.

    [:octicons-arrow-right-24: Game state](guides/game-state.md)

</div>

## Install

=== "uv"

    ```bash
    uv add empire-core
    ```

=== "pip"

    ```bash
    pip install empire-core
    ```

EmpireCore needs Python 3.10 or newer.

!!! warning "Pre-1.0"

    Every minor release may break the API; the [changelog](changelog.md) lists
    each breaking change. Pin a minor line, for example
    `empire-core>=0.41,<0.42`.

## Quick start

```python
from empire_core import EmpireClient

with EmpireClient(username="your_user", password="your_pass") as client:
    client.login()

    client.alliance.send_chat("Hello alliance!")

    for castle in client.castle.get_all():
        print(f"{castle.castle_name} at ({castle.x}, {castle.y})")
```

The `with` block closes the connection and stops the background threads on any
exit. Next, [Getting started](getting-started.md) walks through logging in,
reading castles, a first map scan and the errors to expect, and the
[guides](guides/index.md) cover each part of the game in turn.
