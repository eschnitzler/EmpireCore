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

<p align="center">
  <img alt="A run of the quick start: logged in, one castle listed, and the Green kingdom's 8,862 castles scanned in 15.4 seconds" src="https://raw.githubusercontent.com/eschnitzler/EmpireCore/master/docs/assets/terminal.svg" width="560">
</p>

## Why EmpireCore

- **Fully typed.** Every request and reply is a pydantic model with readable
  field names, so your editor completes them and your type checker checks them.
- **Behaves like the real game client.** Logins, requests and their checks
  follow the game's own client code, so the server sees what it expects.
- **Fast.** One account scans the Green kingdom's roughly 8,900 castles in
  15 to 17 seconds; split across 8 accounts, it takes 2.9 seconds.

## What it covers

| Service | What it does |
|---|---|
| [`client.castle`](https://eschnitzler.github.io/EmpireCore/guides/castle/) | Castles, buildings, resources, horses, tax, sending goods and troops |
| [`client.army`](https://eschnitzler.github.io/EmpireCore/guides/army/) | Units, recruitment and the hospital |
| [`client.attack`](https://eschnitzler.github.io/EmpireCore/guides/attack/) | Sending attacks, and [filling waves](https://eschnitzler.github.io/EmpireCore/guides/filling-waves/) like the game does |
| [`client.commanders`](https://eschnitzler.github.io/EmpireCore/guides/commanders/) | Commanders and castellans |
| [`client.skills`](https://eschnitzler.github.io/EmpireCore/guides/skills/) | Generals, abilities and skill trees |
| [`client.equipment`](https://eschnitzler.github.io/EmpireCore/guides/equipment/) | The equipment inventory |
| [`client.spy`](https://eschnitzler.github.io/EmpireCore/guides/spy/) | Spy missions, sabotage and spy reports |
| [`client.map`](https://eschnitzler.github.io/EmpireCore/guides/map-scanning/) | Kingdom scans and map lookups |
| [`client.movements`](https://eschnitzler.github.io/EmpireCore/guides/movements/) | Army movements, recalls and incoming attacks |
| [`client.alliance`](https://eschnitzler.github.io/EmpireCore/guides/alliance/) | Chat, help requests, members and the treasury |
| [`client.messages`](https://eschnitzler.github.io/EmpireCore/guides/messages/) | The mailbox, mail and battle reports |
| [`client.player`, `defense`, `ranking`, `events`](https://eschnitzler.github.io/EmpireCore/guides/) | Players, castle defense, highscores and events |

## Install

```bash
uv add empire-core        # or: pip install empire-core
```

Python 3.10 or newer. EmpireCore is pre-1.0, so a minor release may change the
API; the [changelog](https://github.com/eschnitzler/EmpireCore/blob/master/CHANGELOG.md)
lists every change that does.

## Quick start

```python
from empire_core import EmpireClient, Kingdom, MapItemType

with EmpireClient(username="you", password="...") as client:
    client.login()

    castles = client.castle.get_all()
    print(f"{len(castles)} castle(s)")

    scan = client.map.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])
    print(f"Green kingdom: {len(scan.items):,} castles")
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
