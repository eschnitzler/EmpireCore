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
    export EMPIRE_ACCOUNT_ALT='{"username": "u", "password": "p", "world": "EmpireEx_21"}'
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
