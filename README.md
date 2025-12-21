<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/asyncio-powered-green.svg" alt="Asyncio">
  <img src="https://img.shields.io/badge/pydantic-v2-purple.svg" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/tool-uv-orange.svg" alt="UV">
  <img src="https://img.shields.io/badge/status-WIP-red.svg" alt="Work in Progress">
</p>

<h1 align="center">EmpireCore</h1>

<p align="center">
  <strong>Modern async Python library for Goodgame Empire automation</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#examples">Examples</a> •
  <a href="#documentation">Documentation</a>
</p>

---

> **⚠️ Work in Progress**
> 
> This library is under active development. APIs may change, and some features are incomplete or untested. Use at your own risk.

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Connection** | WebSocket, auto-reconnect, login cooldown handling |
| **State Tracking** | Player, castles, resources, buildings, units, movements |
| **Actions** | Attacks, transports, recruiting, building, with response validation |
| **Automation** | Task loops, multi-account, target finder, map scanner |
| **CLI** | Account status, login testing, state summary |

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for blazing-fast dependency management.

```bash
git clone https://github.com/eschnitzler/EmpireCore.git
cd EmpireCore

# Install dependencies and create venv automatically
uv sync
```

### Traditional Installation (Pip)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

## Configuration

Create an `accounts.json` file in the root directory. You can use the provided template:

```bash
cp accounts.json.template accounts.json
```

Then edit `accounts.json` with your credentials. This file is git-ignored to keep your credentials safe.

## Quick Start

```python
import asyncio
from empire_core import accounts

async def main():
    # Load default account from accounts.json
    account = accounts.get_default()
    if not account:
        print("Please configure accounts.json first!")
        return

    # Create client directly from account object
    client = account.get_client()
    
    await client.login()
    await client.get_detailed_castle_info()
    
    player = client.state.local_player
    print(f"{player.name} | Level {player.level} | {player.gold} gold")
    
    await client.close()

asyncio.run(main())
```

## CLI Tool

The library includes a CLI for quick operations:

```bash
# Check configured accounts
uv run empire status

# Test login and show player stats
uv run empire login
```

## Running Examples & Tests

```bash
# Run the demo
uv run examples/demo.py

# Run unit tests
uv run pytest
```

## Development

We use `ruff` for linting and `mypy` for type checking.

```bash
# Setup pre-commit hooks
uv run pre-commit install

# Run all checks manually
uv run pre-commit run --all-files
```

---

<p align="center">
  <sub>For educational purposes only. Use responsibly.</sub>
</p>