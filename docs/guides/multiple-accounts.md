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

The server limits the request rate per account, so frequent map scans go
faster split across accounts. Give each its interleaved slice of the chunks a
discovery scan found:

```python
from concurrent.futures import ThreadPoolExecutor

from empire_core import Kingdom

chunks = list(discovery.content_chunks)
names = ["scanner1", "scanner2", "scanner3"]

def scan(index):
    with pool.leased(username=names[index]) as client:
        return client.map.scan_chunks(Kingdom.GREEN, chunks[index::len(names)])

with ThreadPoolExecutor(len(names)) as executor:
    results = list(executor.map(scan, range(len(names))))
```

## Runnable example

```python title="examples/account_pool.py"
--8<-- "examples/account_pool.py"
```

**API:** [`AccountPool`](../reference/client.md#empire_core.pool.AccountPool),
[`AccountRegistry`](../reference/client.md#empire_core.accounts.AccountRegistry)
