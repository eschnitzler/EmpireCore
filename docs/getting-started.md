---
description: Install EmpireCore, log in, read your castles and run a first map scan.
---

# Getting started

This page takes you from an empty virtual environment to a script that logs in,
reads your castles, scans a kingdom and handles the errors it can meet on the
way.

## Install

=== "uv"

    ```bash
    uv add empire-core
    ```

=== "pip"

    ```bash
    pip install empire-core
    ```

EmpireCore supports Python 3.10 and newer and needs pydantic 2.5 or newer. It
ships a `py.typed` marker, so mypy and pyright check your calls against its
models.

??? note "Working on the library itself"

    ```bash
    git clone https://github.com/eschnitzler/EmpireCore.git
    cd EmpireCore
    uv sync --extra dev    # a plain `uv sync` has no pytest, ruff or mypy
    uv run pytest
    ```

    To build these docs locally, `uv run --group docs mkdocs serve`.

## Log in

```python
from empire_core import EmpireClient

client = EmpireClient(username="your_user", password="your_pass")
client.login()
```

`login()` runs the game client's handshake: the WebSocket connection, the
SmartFox version check and zone login, joining the lobby room, the game's own
version check (`vck`) and finally the account login (`lli`). It returns once the
server has sent the login data (`gbd`), which fills `client.state` with your
player and castles. The [login and requests](internals/login-and-requests.md)
page draws the whole exchange.

Every failure raises. A wrong password raises `LoginError`, too many attempts
`LoginCooldownError`, a banned account `AccountBannedError`, and an account that
lives on another server `WrongServerError`. The connection and its threads are
closed before the error reaches you, so a failed login leaks nothing.

### Choose a server and client version

The default configuration connects to the `EmpireEx_21` zone. To pick another
server, list the servers of a network and build a config for one:

```python
from empire_core import EmpireClient, EmpireConfig, fetch_network_instances

servers = fetch_network_instances(game_id=GAME_ID, network_id=NETWORK_ID)
config = EmpireConfig.for_instance(servers[0], client_version="1.169.11")

client = EmpireClient(username="your_user", password="your_pass", config=config)
```

The game and network ids come from the page the game runs in. When the server
raises `ClientVersionError`, set `client_version` to the current game client's
version.

### Log in again without the password

After a login the server pushes a login token, which the client keeps in
`client.login_token`. The push arrives just after the login data, so read it a
moment after `login()` returns:

```python
token = client.login_token
later = EmpireClient(username="your_user", login_token=token)
later.login()
```

`login(recaptcha_token=...)` sends a reCAPTCHA v3 token, or calls a function
for one, the way the browser does. The library cannot make one itself; logins
are accepted without it today.

## Close the client

A logged-in client runs a receive thread, a keepalive thread and a callback
thread. Use the client as a context manager so all of them stop however your
code exits:

```python
with EmpireClient(username="your_user", password="your_pass") as client:
    client.login()
    ...
```

Without the `with` block, call `client.close()` yourself, in a `finally`. The
context manager does not log in for you, so the errors of `login()` stay
visible where you call it.

## Read your castles

```python
castles = client.castle.get_all()
for castle in castles:
    print(castle.castle_id, castle.castle_name, castle.kingdom_id)

resources = client.castle.get_resources(castle_id=castles[0].castle_id)
print(resources.wood, resources.stone)
```

Methods that act on one of your castles take its id alone: the kingdom comes
from the castle list the server sent at login. An id that is not one of your
castles raises `UnknownCastleError`, and one listed in several of your kingdoms
raises `AmbiguousCastleError`.

`client.castle.get_all()` asks the server. What the login data already told the
client is in `client.state`, readable without a request:

```python
player = client.state.get_local_player()      # None until the login data arrives
for castle in client.state.get_castles():
    print(castle.id, castle.name)
```

State is only as fresh as the last packet that carried it; see
[State and freshness](guides/game-state.md) before trusting resources read from
it.

## Scan the map

```python
from empire_core import Kingdom, MapItemType

result = client.map.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])
print(f"{len(result.items)} castles, {len(result.failed_chunks)} chunks failed")

for item in result.items[:5]:
    print(item.name, item.x, item.y, item.owner_id)
```

A full scan walks the kingdom breadth-first from your castle and can take a few
minutes. Always look at `failed_chunks`: a partial scan is not an empty kingdom.
[Map scanning](guides/map-scanning.md) shows how to re-scan cheaply.

## Handle errors

Everything the library raises derives from `EmpireError`:

```python
from empire_core import CommandError, EmpireError, EmpireTimeoutError

try:
    castles = client.castle.get_all()
except CommandError as e:
    print(f"the server refused {e.command} with code {e.code}")
except EmpireTimeoutError:
    print("no reply in time")
except EmpireError as e:
    print(f"{type(e).__name__}: {e}")
```

[Error handling](guides/errors.md) lists every error and when you meet it.

## A complete script

The repository's examples run end to end. This one logs in, lists your castles
and prints the movements in flight:

```python title="examples/login_and_castles.py"
--8<-- "examples/login_and_castles.py"
```

## Next steps

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **[Guides](guides/index.md)**

    ---

    One page per part of the game: alliance, castle, army, attacks, spies,
    the map and more.

-   :material-api:{ .lg .middle } **[API reference](reference/index.md)**

    ---

    Every service, model and enum, with field descriptions and wire keys.

</div>
