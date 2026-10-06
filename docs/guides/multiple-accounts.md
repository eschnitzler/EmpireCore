---
description: An account pool that leases one logged-in client per account, safely across threads.
---

# Multiple accounts

`AccountPool` hands out one logged-in client per account and refuses to lease
the same account twice. Prefer `leased()`: it releases the account and closes
the client even if your code raises.

```python
from empire_core import AccountPool, PoolExhaustedError
from empire_core.accounts import AccountRegistry

registry = AccountRegistry()
registry.load(file_path="accounts.json")
pool = AccountPool(registry)

try:
    with pool.leased(tag="scanning") as client:
        result = client.map.scan_kingdom()
except PoolExhaustedError:
    ...   # no candidate account was free
```

`leased()` takes a `username` to lease one account, or a `tag` to lease any
free account carrying it (tags match case-insensitively). `PoolExhaustedError`
means nothing was tried: no account matched, or every match was busy.
`LoginError` means every candidate was tried and each one failed to log in; the
cause is chained onto it.

The pool is safe to use from several threads.

## Keeping clients logged in

By default every lease logs in and every release closes the client. A consumer
that leases per request pays a login each time, and frequent logins risk a
login cooldown. Make the pool with `keep_alive=True` to keep released clients
logged in instead:

```python
pool = AccountPool(registry, keep_alive=True)

with pool.leased(username="scanner1") as client:   # logs in
    ...
with pool.leased(username="scanner1") as client:   # same client, no login
    ...

pool.release_all()   # closes the kept clients too
```

A kept client pings the server every 60 seconds, as the game client does, so an
idle session stays open. If its session dropped while it waited, the next lease
closes it and logs in a fresh client; a cooldown on that login moves the lease
on to the next candidate as usual. `release(client, logout=True)` closes a
client even in a `keep_alive` pool.

A lease you hold for the whole process never reaches either path. Set
`client.keep_session = True` on it and the client logs a dropped session in
again by itself, honouring login cooldowns (see
[Keeping the session](game-state.md#keeping-the-session)):

```python
client = pool.lease(username="watcher1")
client.keep_session = True
client.on_session_restored(lambda: print("watcher1 is back"))
client.on_session_lost(lambda error: print("watcher1 is gone:", error))
```

A release closes the client or keeps it as before, and closing ends any
re-login. A `keep_alive` pool keeps a client released while it logs back in,
and leaves it to finish: until `client.is_restoring_session` turns False its
account is not available, so a lease moves on to the next candidate, and one
for that username alone returns None (`pool.leased()` raises
`PoolExhaustedError`). A restore that gives up leaves the client logged out,
and the next lease closes it and logs in a fresh one. To log in afresh without
waiting, close the client yourself: `pool.get_client(username).close()`. While a
held client waits out a cooldown, `client.remaining_login_cooldown()` says for
how long: the seconds the server last named, counting down. A lease that
fails chains its last failure to the `LoginError` it raises; a
`LoginCooldownError` there carries the seconds.

The next lease gets the very client object you held, so let go of your handle
when you release it. `pool.leased()` releases only its own lease, but a manual
`pool.release(client)` cannot tell your handle from the next leaseholder's:
call it once per lease. Releasing a client the account is not leased with
changes nothing and logs a warning.

!!! warning "Callbacks outlive the lease"

    The next leaseholder gets the client as you left it. Callbacks you
    registered on it (`client.on_disconnect`, `client.state.on_incoming_attack`
    and the like) keep firing during their lease. Remove them before the
    `with` block ends, or release with `logout=True`. Streams of
    `client.listen()` are the exception: release ends them.

    What the client announced stays announced, also across `close()` and
    `login()`: an attack or occupation announced to you is not announced again
    to the next leaseholder. It reads `client.state.get_announced_attacks()` and
    `get_occupations()`, or calls `client.state.reannounce(movement_id)`,
    with `when_listed=True` while the movement list has not come yet (see [Movements](movements.md#what-was-announced-and-announcing-again)).
    Release drops the `when_listed` calls you left waiting, so they do not
    fire during the next lease.

## Where accounts come from

`registry.load()` reads the file you name plus every `EMPIRE_ACCOUNT_*`
environment variable:

=== "accounts.json"

    ```json
    [
        {
            "username": "YOUR_USERNAME",
            "password": "YOUR_PASSWORD"
        }
    ]
    ```

=== "Environment"

    ```bash
    # CSV: username,password,world
    export EMPIRE_ACCOUNT_MAIN='your_user,your_pass,EmpireEx_21'
    # or JSON, when the password contains a comma
    export EMPIRE_ACCOUNT_ALT='{"username": "u", "password": "p"}'
    ```

A `.env` file is read only if you opt in with
`registry.load(load_env_file=True)`: importing the library never changes your
environment.

!!! danger "Keep `accounts.json` private"

    It holds passwords in plain text. Keep it out of version control and
    `chmod 600` it; the library warns when it is group- or world-readable.

## Scanning with several accounts

The server limits the request rate per account, so map scans go faster spread
over several accounts. Lease them and hand them to `scan_kingdom_with`, which
gives each its own thread and moves a dropped client's chunks to the others:

```python
from contextlib import ExitStack

from empire_core import Kingdom
from empire_core.map import scan_kingdom_with

with ExitStack() as leases:
    clients = [leases.enter_context(pool.leased(tag="scanner")) for _ in range(4)]
    result = scan_kingdom_with(clients, Kingdom.GREEN)
```

See [Map scanning](map-scanning.md#scanning-with-several-accounts) for what
it returns and how far threads in one process go.

## Runnable example

```python title="examples/account_pool.py"
--8<-- "examples/account_pool.py"
```

**API:** [`AccountPool`](../reference/client.md#empire_core.pool.AccountPool),
[`AccountRegistry`](../reference/client.md#empire_core.accounts.AccountRegistry)
