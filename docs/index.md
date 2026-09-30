---
title: EmpireCore
description: A fully typed Python client for Goodgame Empire.
hide:
  - navigation
  - toc
---

<div class="ec-hero" markdown>

<div class="ec-hero__pitch" markdown>

# EmpireCore

A fully typed Python client for Goodgame Empire. Log in, read your castles,
scan the map and send attacks, with every request and reply checked against
the game's own client.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Guides](guides/index.md){ .md-button }

</div>

<div class="ec-hero__code" markdown>

```python
from empire_core import EmpireClient, Kingdom, MapItemType

with EmpireClient(username="you", password="...") as client:
    client.login()

    castles = client.castle.get_all()
    print(f"{len(castles)} castle(s)")

    scan = client.map.scan_kingdom(
        Kingdom.GREEN, item_types=[MapItemType.CASTLE]
    )
    print(f"Green kingdom: {len(scan.items):,} castles")
```

<div class="ec-output" markdown>

```text
1 castle(s)
Green kingdom: 8,862 castles
```

</div>

</div>

</div>

<div class="ec-stats">
  <div><strong>8,862 castles in 15 s</strong><span>a whole kingdom, one account</span></div>
  <div><strong>15 services</strong><span>castle, army, attack, spy, map and more</span></div>
  <div><strong>Python 3.10–3.14</strong><span>typed, with a <code>py.typed</code> marker</span></div>
</div>

<div class="grid cards" markdown>

-   :material-shield-check-outline:{ .lg } **[Typed end to end](guides/protocol-models.md)**

    Pydantic models for every request and reply, with readable field names,
    so your editor and type checker know every field.

-   :material-source-branch-check:{ .lg } **[Follows the real client](internals/index.md)**

    Requests are built the way the game client builds them, and each model
    names the client code it mirrors.

-   :material-alert-circle-outline:{ .lg } **[Clear errors](guides/errors.md)**

    One `EmpireError` base for everything the library raises. An empty list
    always means there was nothing there.

-   :material-radar:{ .lg } **[Fast map scans](guides/map-scanning.md)**

    Scan a whole kingdom, then re-scan only the parts that held anything.
    Every chunk that failed is reported.

-   :material-sword-cross:{ .lg } **[Fills waves like the game](guides/filling-waves.md)**

    Give `fill_attack` a target's coordinates and it fills every wave the way
    the game's own button does.

-   :material-sync:{ .lg } **[Live state](guides/game-state.md)**

    A background thread keeps your account's state current, with callbacks
    for incoming attacks.

</div>

## Install

```bash
uv add empire-core        # or: pip install empire-core
```

EmpireCore is pre-1.0: a minor release may change the API, and the
[changelog](changelog.md) lists every change that does. Pin a minor line, for
example `empire-core>=0.42,<0.43`. Next, [Getting started](getting-started.md)
walks through logging in, reading castles, a first map scan and the errors to
expect.
