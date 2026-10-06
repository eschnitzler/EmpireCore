<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eschnitzler/EmpireCore/master/docs/assets/logo-lockup-dark.svg">
    <img alt="EmpireCore" src="https://raw.githubusercontent.com/eschnitzler/EmpireCore/master/docs/assets/logo-lockup-light.svg" height="64">
  </picture>
</p>

<p align="center">A fully typed Python client for Goodgame Empire.</p>

<p align="center">
  <a href="https://pypi.org/project/empire-core/"><img src="https://img.shields.io/pypi/v/empire-core?color=1f6f78" alt="PyPI"></a>
  <a href="https://pypi.org/project/empire-core/"><img src="https://img.shields.io/pypi/pyversions/empire-core?color=1f6f78" alt="Python versions"></a>
  <a href="https://github.com/eschnitzler/EmpireCore/actions/workflows/ci.yml"><img src="https://github.com/eschnitzler/EmpireCore/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://eschnitzler.github.io/EmpireCore/"><img src="https://github.com/eschnitzler/EmpireCore/actions/workflows/docs.yml/badge.svg" alt="Docs"></a>
</p>

> [!WARNING]
> EmpireCore is in alpha. The API is not stable yet, and a minor release may
> break it; the [changelog](https://github.com/eschnitzler/EmpireCore/blob/master/CHANGELOG.md)
> lists every change that does. It talks to the live game servers, so use it
> at your own risk and with the game's terms of service in mind.

EmpireCore lets Python code play Goodgame Empire the way the game's own client
does. Log in, read your account and castles, react to incoming attacks and
other events as they happen, send armies and spies, and run several accounts
side by side.

## Why EmpireCore

- **Fully typed.** Every request and reply is a pydantic model with readable
  field names, so your editor completes them and your type checker checks them.
- **Behaves like the real game client.** Logins, requests and their checks
  follow the game's own client code, so the server sees what it expects.
- **Live state and events.** A background thread keeps your account's state
  current. Register callbacks, or stream events with `asyncio`.
- **Built to keep running.** `keep_session` logs back in after a dropped
  connection, and `AccountPool` shares several logged-in accounts across
  threads.

## What it covers

| Service | What it does |
|---|---|
| [`client.castle`](https://eschnitzler.github.io/EmpireCore/guides/castle/) | Castles, buildings, resources, horses, tax, sending goods and troops |
| [`client.army`](https://eschnitzler.github.io/EmpireCore/guides/army/) | Units, recruitment and the hospital |
| [`client.attack`](https://eschnitzler.github.io/EmpireCore/guides/attack/) | Sending attacks, attack presets, and [filling waves](https://eschnitzler.github.io/EmpireCore/guides/filling-waves/) like the game does |
| [`client.commanders`](https://eschnitzler.github.io/EmpireCore/guides/commanders/) | Commanders and castellans |
| [`client.skills`](https://eschnitzler.github.io/EmpireCore/guides/skills/) | Generals, abilities and skill trees |
| [`client.equipment`](https://eschnitzler.github.io/EmpireCore/guides/equipment/) | The equipment inventory |
| [`client.spy`](https://eschnitzler.github.io/EmpireCore/guides/spy/) | Spy missions, sabotage and spy reports |
| [`client.map`](https://eschnitzler.github.io/EmpireCore/guides/map-scanning/) | Kingdom scans and map lookups |
| [`client.movements`](https://eschnitzler.github.io/EmpireCore/guides/movements/) | Army movements, recalls and incoming attacks |
| [`client.alliance`](https://eschnitzler.github.io/EmpireCore/guides/alliance/) | Chat, help requests, members and the treasury |
| [`client.messages`](https://eschnitzler.github.io/EmpireCore/guides/messages/) | The mailbox, mail and battle reports |
| [`client.defense`](https://eschnitzler.github.io/EmpireCore/guides/defense/) | Reading and setting castle defense |
| [`client.rewards`](https://eschnitzler.github.io/EmpireCore/guides/rewards/) | The free daily rewards |
| [`client.player`, `ranking`, `events`](https://eschnitzler.github.io/EmpireCore/guides/) | Players, highscores and events |

## Install

```bash
uv add empire-core        # or: pip install empire-core
```

Python 3.10 or newer.

## Quick start

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

**Documentation:** <https://eschnitzler.github.io/EmpireCore/>, with a guide
for each part of the game and the full API reference.

## Contributing

Contributions are welcome; see
[CONTRIBUTING.md](https://github.com/eschnitzler/EmpireCore/blob/master/CONTRIBUTING.md).
Bugs and feature requests are best filed as
[issues](https://github.com/eschnitzler/EmpireCore/issues).

## Contact

- Email: [colossusdynamis@gmail.com](mailto:colossusdynamis@gmail.com)
- Discord: `colossus1`

<sub>MIT licensed. Not affiliated with Goodgame Studios. For educational purposes only; use responsibly.</sub>
