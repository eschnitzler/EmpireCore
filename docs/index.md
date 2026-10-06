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

A fully typed Python client for Goodgame Empire that follows the game's own
client. Read your account and castles, react to incoming attacks and other
events as they happen, send armies and spies, and run several accounts at once.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Guides](guides/index.md){ .md-button }

</div>

<div class="ec-hero__code" markdown>

```python
import time

from empire_core import EmpireClient, Movement


def warn(attack: Movement) -> None:
    print(f"Attack from {attack.source_player_name}, "
          f"landing in {attack.time_remaining}s")


with EmpireClient(
    username="you", password="...", keep_session=True
) as client:
    client.login()

    for castle in client.castle.get_all():
        res = client.castle.get_resources(castle.castle_id)
        print(f"{castle.castle_name}: {res.wood:,} wood, "
              f"{res.stone:,} stone, {res.food:,} food")

    client.state.on_incoming_attack(warn)
    time.sleep(3600)
```

<div class="ec-output" markdown>

```text
Ironhold: 12,400 wood, 9,850 stone, 21,300 food
Attack from Redmane, landing in 1742s
```

</div>

</div>

</div>

!!! warning "EmpireCore is in alpha"

    The API is not stable yet, and a minor release may break it; the
    [changelog](changelog.md) lists every change that does. EmpireCore talks to
    the live game servers, so use it at your own risk and with the game's terms
    of service in mind.

<div class="ec-stats">
  <div><strong>16 services</strong><span>castle, army, attack, spy, map and more</span></div>
  <div><strong>Python 3.10–3.14</strong><span>typed, with a <code>py.typed</code> marker</span></div>
</div>

<div class="grid cards" markdown>

-   :material-shield-check-outline:{ .lg } **[Typed end to end](guides/protocol-models.md)**

    Pydantic models for every request and reply, with readable field names,
    so your editor and type checker know every field.

-   :material-source-branch-check:{ .lg } **[Follows the real client](internals/index.md)**

    Requests are built the way the game client builds them, and each model
    names the client code it mirrors.

-   :material-sync:{ .lg } **[Live state and events](guides/game-state.md)**

    A background thread keeps your account's state current. Register callbacks
    for incoming attacks, chat and more, or stream them with
    [`asyncio`](guides/game-state.md#from-an-asyncio-program).

-   :material-connection:{ .lg } **[Stays logged in](guides/game-state.md#keeping-the-session)**

    With `keep_session=True` the client logs back in after a dropped
    connection, and your callbacks keep firing.

-   :material-account-multiple-outline:{ .lg } **[Several accounts](guides/multiple-accounts.md)**

    `AccountPool` hands out one logged-in client per account, safely across
    threads.

-   :material-alert-circle-outline:{ .lg } **[Clear errors](guides/errors.md)**

    One `EmpireError` base for everything the library raises. An empty list
    always means there was nothing there.

</div>

## Install

```bash
uv add empire-core        # or: pip install empire-core
```

Pin a minor line, for example `empire-core>=0.48,<0.49`, since a minor release
may change the API. Next, [Getting started](getting-started.md) walks through
logging in, reading your castles and the errors to expect.
