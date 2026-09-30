<h1 align="center">EmpireCore</h1>

<p align="center">
  <strong>A fully typed Python client for Goodgame Empire</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/empire-core/"><img src="https://img.shields.io/pypi/v/empire-core.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/empire-core/"><img src="https://img.shields.io/pypi/pyversions/empire-core.svg" alt="Python versions"></a>
  <a href="https://github.com/eschnitzler/EmpireCore/actions/workflows/ci.yml"><img src="https://github.com/eschnitzler/EmpireCore/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://eschnitzler.github.io/EmpireCore/"><img src="https://github.com/eschnitzler/EmpireCore/actions/workflows/docs.yml/badge.svg" alt="Docs"></a>
  <img src="https://img.shields.io/badge/typed-py.typed-brightgreen.svg" alt="PEP 561 typed">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT licence">
</p>

<p align="center">
  <a href="https://eschnitzler.github.io/EmpireCore/"><strong>Documentation</strong></a> ·
  <a href="https://eschnitzler.github.io/EmpireCore/getting-started/">Getting started</a> ·
  <a href="https://eschnitzler.github.io/EmpireCore/guides/">Guides</a> ·
  <a href="https://eschnitzler.github.io/EmpireCore/reference/">API reference</a> ·
  <a href="https://github.com/eschnitzler/EmpireCore/blob/master/CHANGELOG.md">Changelog</a>
</p>

---

EmpireCore logs in to Goodgame Empire the way the game's own client does, then
gives you typed services for your castles, army, commanders, alliance, mail,
spies and the world map. Every request and reply is a pydantic model written
against the game client's code, every failure is a typed exception, and a
background thread keeps a thread-safe picture of your account current while
your code runs.

> [!WARNING]
> **Pre-1.0.** Every minor release may break the API, and the
> [changelog](https://github.com/eschnitzler/EmpireCore/blob/master/CHANGELOG.md)
> lists each breaking change. Pin a minor line, such as `empire-core>=0.41,<0.42`.

## What you get

- **Services for the whole game**: `client.alliance`, `castle`, `army`,
  `attack`, `commanders`, `equipment`, `skills`, `spy`, `map`, `movements`,
  `messages`, `player`, `defense`, `ranking` and `events`.
- **Typed end to end**: pydantic v2 models with snake_case fields over the wire
  keys, and a `py.typed` marker so your type checker sees them.
- **Honest failures**: one `EmpireError` base, no leaked pydantic or socket
  errors, and no empty list that secretly means "the request failed".
- **Live, thread-safe state** with callbacks for incoming attacks, arrivals and
  recalls.
- **Wave filling** from nothing but a target's coordinates, the way the game's
  "Fill waves" button does it.
- **Fast map scans** and an **account pool** for running many accounts.

## Install

```bash
uv add empire-core        # or: pip install empire-core
```

Python 3.10 or newer.

## Quick start

```python
from empire_core import EmpireClient, Kingdom, MapItemType

with EmpireClient(username="your_user", password="your_pass") as client:
    client.login()

    for castle in client.castle.get_all():
        print(f"{castle.castle_name} at ({castle.x}, {castle.y})")

    scan = client.map.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])
    print(f"{len(scan.items)} castles, {len(scan.failed_chunks)} chunks failed")

    client.state.on_incoming_attack(lambda m: print("incoming from", m.source_player_name))
```

The [getting started guide](https://eschnitzler.github.io/EmpireCore/getting-started/)
covers choosing a server, login tokens, reading state and handling errors.

## Highlights

- **Checked against the game client.** Requests follow the client's own
  command objects, key order included; models cite the client class and line
  they mirror; and the command ids are checked weekly against the live client.
- **Live-verified where the code can't tell.** Where the client's code cannot
  settle what the server does, the library goes by what a live server did and
  says so, and the docs mark what is still unknown.
- **Fast scans.** Map requests go out back to back, as the client sends them:
  a live scan of 289 chunks ran at about 17 requests a second without a
  refusal. Re-scanning only the chunks that held anything takes roughly a third
  fewer requests.

## Documentation

Everything else lives at **<https://eschnitzler.github.io/EmpireCore/>**: a
guide for each part of the game, diagrams of the login and request flow, and an
API reference generated from the source with every model's fields, wire keys
and descriptions. Runnable scripts are in
[`examples/`](https://github.com/eschnitzler/EmpireCore/tree/master/examples).

## Contributing

Contributions are welcome. See
[CONTRIBUTING.md](https://github.com/eschnitzler/EmpireCore/blob/master/CONTRIBUTING.md)
for adding protocol commands and services, the model conventions and the tests.

```bash
git clone https://github.com/eschnitzler/EmpireCore.git
cd EmpireCore
uv sync --extra dev
uv run pytest
```

## Contact

- 📧 Email: [colossusdynamis@gmail.com](mailto:colossusdynamis@gmail.com)
- 💬 Discord: `colossus1`

Bugs and feature requests are best filed as
[issues](https://github.com/eschnitzler/EmpireCore/issues).

---

<p align="center">
  <sub>MIT licensed. Not affiliated with Goodgame Studios. For educational purposes only; use responsibly.</sub>
</p>
