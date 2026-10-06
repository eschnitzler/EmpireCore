# Contributing to EmpireCore

This guide covers how to add new protocol commands and services to EmpireCore.

## Architecture Overview

```
src/empire_core/
├── client/
│   └── client.py          # Main EmpireClient - auto-attaches services
├── protocol/
│   ├── base.py            # BaseRequest, BaseResponse, GGECommand, the registry
│   ├── models.py          # Re-exports every area's models (public namespace)
│   └── packet.py          # Low-level packet parsing
├── map/                   # One package per game area:
│   ├── models/            #   its request/response models
│   └── ...
├── castle/
│   ├── models/            #   castles, details, actions, buildings, support
│   └── service.py         #   CastleService, where the area has a service
├── ...                    # commanders, army, movements, messages, defense,
│                          # player, attack, spy, alliance, ranking, events
├── combat/                # Wave solver, capacity and bonus math
├── enums/                 # Every game enum, one module per area
├── services/
│   └── base.py            # BaseService
├── network/               # WebSocket connection, receive loop, redaction
├── state/                 # Thread-safe game state
└── utils/                 # event titles and troop data from the CDN
```

Areas import only areas below them (map, ranking and events at the bottom, then
commanders and castle, army, movements and messages, defense, combat and player,
attack and alliance, and spy at the top); `tests/test_layers.py` enforces the
order. Library code imports models from their area, never from
`empire_core.protocol.models`.

Design notes for the trickier layers live in [`docs/design/`](https://eschnitzler.github.io/EmpireCore/internals/) —
read [`state_management.md`](https://eschnitzler.github.io/EmpireCore/design/state_management/) before touching
`state/`.

## Adding a New Protocol Command

Protocol models define the request/response structure for GGE commands. Each command has:
- A **request model** (what you send)
- A **response model** (what you receive)

### Step 1: Add the Command Code

Add the command code to `GGECommand` in `protocol/base.py`:

```python
class GGECommand:
    # ... existing commands ...
    
    # Your new command
    XYZ = "xyz"  # Description of what it does
```

The id must be one the game client has: `tests/protocol/test_client_commands.py`
fails for any request, response or `GGECommand` id, or command id the code uses as
a plain string (a handler, a waiter, `state/manager.py`'s tables), missing from
`tests/data/client_commands.json`, a snapshot of the client's `C2S_`/`S2C_`
constants. A weekly workflow fails when the live client's tables differ from it;
regenerate it with `uv run python scripts/extract_client_commands.py --download`
and commit the diff.

### Step 2: Create Request Model

Request models inherit from `BaseRequest` and define:
- `command` class variable (the command code)
- Fields with `Field(alias="X")` for wire format

```python
# <area>/models.py, or <area>/models/<topic>.py

from pydantic import Field

from empire_core.protocol.base import BaseRequest

class YourRequest(BaseRequest):
    """
    Description of what this request does.
    
    Command: xyz
    Payload: {"FID": field_id, "V": value}

    Client: ``C2SYourVO`` (bundle line 12345)
    """
    
    command = "xyz"
    
    field_id: int = Field(alias="FID")
    value: str = Field(alias="V")
```

**Key points:**
- Name the client class that builds the payload in a `Client:` line (see
  [Client reference](#client-reference))
- Use `Field(alias="X")` to map Python names to wire format
- Build models by field name (`cls(target_id=...)`, not `cls(ID=...)`): mypy's
  pydantic plugin checks those calls and rejects wire keys
- Add `@classmethod` factory methods for common patterns
- Document the command and payload format

### Step 3: Create Response Model

Response models inherit from `BaseResponse`:

```python
from pydantic import Field

from empire_core.protocol.base import BaseResponse

class YourResponse(BaseResponse):
    """
    Response from xyz command.
    
    Command: xyz
    Payload: {"R": result, "S": success}

    Client: ``XYZCommand.executeCommand`` (bundle line 12345)
    """
    
    command = "xyz"  # Auto-registers in response registry
    
    result: str = Field(alias="R")
    finished: bool = Field(alias="S", default=True)
```

**Key points:**
- Setting `command = "xyz"` auto-registers the response model — registering a
  command twice raises at class-definition time, so pick one that is not
  already in the registry
- Never name a field `success`: `BaseResponse.success` is a property derived
  from the packet's status code, and a same-named field is silently shadowed
  (pydantic warns, and your field becomes unreachable)
- Use `parse_response("xyz", payload)` to parse responses

### Step 4: Export Models

List the new names in the module's `__all__`; the area's `__init__` re-exports
them. To make them public in `empire_core.protocol.models` as well, import them
there from their module and add them to its `__all__`:

```python
# protocol/models.py
from empire_core.map.models.bookmarks import YourRequest, YourResponse

__all__ = [
    # ... existing exports ...
    "YourRequest",
    "YourResponse",
]
```

Importing `empire_core` imports the aggregator (through the client), which is
what fills the response registry: a model module nothing imports never registers.

### Complete Example: Adding a New Command

Here's a complete example adding a hypothetical "get bookmarks" command:

```python
# map/models/bookmarks.py

from __future__ import annotations

from pydantic import ConfigDict, Field

from empire_core.protocol.base import BaseRequest, BaseResponse, Position


class GetBookmarksRequest(BaseRequest):
    """
    Get player's map bookmarks (illustrative command id 'zzb' — 'gbl' itself is already registered by the library).
    
    Command: zzb
    Payload: {} (empty)
    """
    
    command = "zzb"


class Bookmark(BaseResponse):
    """A single bookmark entry."""
    
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    
    bookmark_id: int = Field(alias="BID")
    name: str = Field(alias="N")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom_id: int = Field(alias="KID", default=0)
    
    @property
    def position(self) -> Position:
        return Position(x=self.x, y=self.y, kingdom=self.kingdom_id)


class GetBookmarksResponse(BaseResponse):
    """
    Response containing player's bookmarks.
    
    Command: zzb
    Payload: {"BL": [bookmark, ...]}
    """
    
    command = "zzb"
    
    bookmarks: list[Bookmark] = Field(alias="BL", default_factory=list)


__all__ = [
    "GetBookmarksRequest",
    "GetBookmarksResponse",
    "Bookmark",
]
```

## Adding a New Service

Services provide high-level APIs that use protocol models. They are auto-attached to the client.

### Step 1: Create Service Class

A service lives in its area's `service.py`, one service per area. The example
below is a hypothetical new `bookmarks` area; for an area that already has a
service (`client.map`, `client.castle`, ...), add the method to that class
instead.

```python
# bookmarks/service.py

from __future__ import annotations

from empire_core.bookmarks.models import Bookmark, GetBookmarksRequest, GetBookmarksResponse
from empire_core.services.base import BaseService


class BookmarksService(BaseService):
    """
    Service for bookmark operations.

    Reached as client.bookmarks.
    """

    def get_all(self, timeout: float = 5.0) -> list[Bookmark]:
        """
        Get all bookmarks.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetBookmarksRequest(), GetBookmarksResponse, timeout=timeout).bookmarks
```

A new area also needs an `__init__.py` (re-exporting its models, never its
service) and a row in the `RANK` table of `tests/test_layers.py`, ranked above
every area it imports.

### Step 2: Attach the Service

Import the service in `client/client.py`, annotate the attribute next to the
others and build it in `_attach_services()`:

```python
from empire_core.bookmarks.service import BookmarksService

class EmpireClient:
    bookmarks: BookmarksService

    def _attach_services(self) -> None:
        ...
        self.bookmarks = BookmarksService(self)
```

Then add it to `SERVICE_TYPES` in `tests/test_smoke.py`.

### Service Patterns

#### Fire-and-forget (no response needed)

```python
def send_chat(self, message: str) -> None:
    request = AllianceChatMessageRequest.create(message)
    self.send(request)  # No wait
```

#### Wait for response

```python
def get_resources(self, castle_id: int) -> CastleResources:
    request = GetResourcesRequest(castle_id=castle_id, kingdom_id=self._require_own_castle(castle_id).kingdom_id)
    return self.request(request, GetResourcesResponse, timeout=5.0)
```

#### Reporting failure

Every service method follows one rule, so callers learn it once:

- transport errors and unexpected server errors raise;
- `None` only for a not-found (or nothing-to-do) outcome mapped from a named
  `GGEError`, documented on the method;
- an empty collection only when the collection really is empty;
- invalid arguments raise `ValueError`, or a typed error from `exceptions.py`
  when the caller needs to tell it apart (`NotInAllianceError`, `UnknownCastleError`);
- a malformed reply raises `PacketError`;
- an action the server refuses returns `False` (`BaseService.execute`).

Four kinds of method follow rules of their own, documented on the method:

- state read without a request returns `None` while the login data or push it
  comes from has not arrived yet (`client.castle.get_horses()` before a `gpc`);
- a call made of several requests returns a result object naming each outcome
  (`SpyOutcome.COMMAND_FAILED` on a `SpyResult`, the `failed` and `timed_out`
  players of `get_player_details_bulk()`);
- a best-effort fill goes on without a read the server refuses and names it
  (`FilledAttack.unread`);
- a request the server never answers, waiting for a push instead, returns
  `None` when no push came in time (`open_activity_chest()`).

Match server errors on `CommandError.error`, never on a number:

```python
except CommandError as e:
    if e.error is GGEError.NO_PLAYER_FOUND:
        return None
    raise
```

`tests/services/test_failure_rule.py` fails on a bare number in `src/` where a
name belongs: a name ending in `code` or `status` compared with or matched on a
non-zero integer literal, `GGEError(<int>)` or `from_code(<int>)`, and any
comparison on `.code` (compare `.error` instead). A status that is not a
`GGEError` gets an enum of its own, as `VersionCheckStatus` does for `vck`.

#### Subscribe to incoming messages

Declare the event once on the service, typed by the arguments its callbacks
take; `utils/callbacks.py` gives it registration, `.remove`, the lock and
`client.listen()` streaming:

```python
on_message = Event[AllianceChatMessageResponse]()
"""Register a callback for incoming messages. ..."""

def __init__(self, client) -> None:
    super().__init__(client)
    self.on_response("acm", self._handle_message)

def _handle_message(self, response) -> None:
    if isinstance(response, AllianceChatMessageResponse):
        self._fire(self.on_message, response)
```

A consumer registers with `client.<service>.on_message(cb)` and unregisters
with `client.<service>.on_message.remove(cb)`. `_fire` calls a snapshot of the
callbacks on the receive thread and logs one that raises, so a bad consumer
callback neither stops the others nor vanishes.

## BaseService API Reference

```python
class BaseService:
    def __init__(self, client: EmpireClient) -> None:
        self.client = client
    
    @property
    def zone(self) -> str:
        """Get the game zone from client config."""
        return self.client.config.default_zone
    
    def send(
        self, 
        request: BaseRequest, 
        wait: bool = False, 
        timeout: float = 5.0
    ) -> BaseResponse | None:
        """
        Send a request to the server.
        
        Args:
            request: The request model to send
            wait: Whether to wait for a response
            timeout: Timeout in seconds when waiting
            
        Returns:
            The parsed response if wait=True, otherwise None
        """
    
    def on_response(self, command: str, handler: Callable) -> None:
        """
        Register a handler for a specific response type.
        
        Args:
            command: The command code to handle (e.g., "acm")
            handler: Callback that receives the parsed response
        """
```

## Protocol Model Conventions

### Client reference

The game client is the source of truth, so every model with a `command` names
the client code it mirrors in a docstring line: the `C2S...VO` that builds a
request, and the code that reads a reply (the `XXXCommand.executeCommand` or
the parser it hands the reply to), with the bundle or dll line, for example:

```
Client: ``C2SIsoBuyObjectVO`` (bundle line 31940)
Client: ``CastleAttackInfoVO.fillFromParamObject`` (bundle line 30620)
```

Line numbers drift between client releases; the class names do not.

A new or changed model needs its `Client:` line, and a field the client does
not read needs a note saying where it was observed instead.
`tests/protocol/test_client_lines.py` fails for a model without one; a model the
client has no code for goes in its `CLIENT_LESS` list with the reason.

### Field Naming

Use descriptive Python names with short aliases:

```python
# Good
player_id: int = Field(alias="PID")
castle_name: str = Field(alias="CN")

# Bad - don't use the wire names directly
PID: int
CN: str
```

An alias names a wire key and nothing else. Values the server sends by
position in a list (a castle list row, a building row) have no key: give
those fields no alias, read the list in a `from_list` / `from_entry`
classmethod, and list the positions in the class docstring.

### Optional Fields

Use `| None` with `default=None`:

```python
error_message: str | None = Field(alias="EM", default=None)
```

### Lists

Use `default_factory=list`:

```python
castles: list[CastleInfo] = Field(alias="C", default_factory=list)
```

### Nested Models

Create separate model classes for nested structures:

```python
class ChatMessageData(BaseModel):
    player_name: str = Field(alias="PN")
    message_text: str = Field(alias="MT")

class AllianceChatMessageResponse(BaseResponse):
    command = "acm"
    chat_message: ChatMessageData = Field(alias="CM")
```

### Factory Methods

Add `@classmethod` factory methods for common patterns:

```python
class AskHelpRequest(BaseRequest):
    command = "ahr"

    target_id: int = Field(alias="ID")
    type_id: int = Field(alias="T")

    @classmethod
    def repair(cls, building_id: int) -> "AskHelpRequest":
        """Ask for help repairing a building."""
        return cls(target_id=building_id, type_id=HelpType.REPAIR)

    @classmethod
    def build(cls, building_id: int) -> "AskHelpRequest":
        """Ask for help building a building."""
        return cls(target_id=building_id, type_id=HelpType.BUILD)
```

## Development Setup

```bash
uv sync --extra dev     # `dev` is an extra, not a default group: a plain
                        # `uv sync` leaves you without pytest/ruff/mypy
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

The commit-msg hook matters: commits must follow
[Conventional Commits](https://www.conventionalcommits.org/), because the
release version and changelog are derived from them.

> [!IMPORTANT]
> A breaking change needs a **`BREAKING CHANGE:`** footer (or
> `BREAKING-CHANGE:`). `BREAKING:` alone looks right, passes review, and is
> silently ignored by the release tooling — the change then ships with nothing
> in the changelog telling users why their code stopped working.
>
> ```
> fix(pool): raise instead of returning None when every candidate fails
>
> BREAKING CHANGE: lease() raises LoginError when all candidates fail; None
> now means only "no candidates".
> ```

If you change dependencies, run `uv lock` and commit `uv.lock` with the
change; CI installs with `--locked` and will reject a stale lockfile.

## Testing

```bash
uv run pytest                       # the suite
uv run pre-commit run --all-files   # exactly what CI's lint job runs
```

> [!TIP]
> `uv run mypy src` is **not** enough — the hook type-checks `tests/` and
> `examples/` too, so run pre-commit before pushing.

Verify the client still builds every service:

```bash
uv run pytest tests/test_smoke.py
```

### What to test

This library parses bytes from a server we do not control, so a fix is not
finished until a test pins it. **Watch the test fail first** — a test that was
green before your change proves nothing about your change.

- **Drift.** For every accessor a caller is told to use, add a case where the
  server sends the wrong shape or type (a string where an int is documented, a
  dict where a list is). It must skip or degrade with a log, never raise a raw
  `pydantic.ValidationError` or `AttributeError` past the library's API.
- **Silence.** If your code skips or degrades bad input, assert on the log
  record (`caplog`). A silent skip turns a server-side schema change into
  quietly incomplete results, which is far harder to diagnose than a crash.
- **Concurrency.** State is written by the receive thread and read by user
  threads. If you touch it, test it under a concurrent writer — several real
  bugs here only appeared that way.
- **Failure, not just success.** Cover the timeout, the non-zero error code and
  the dropped connection, and assert the exception *type* callers are told to
  catch.

## Guidelines

1. **Log to a named logger** — Use `logging.getLogger(__name__)`; never print. Never swallow an exception without at least logging it
2. **Use type hints** — All public methods should have complete type hints
3. **Document wire format** — Include the command code and payload format in docstrings
4. **Fail loudly and precisely** — Raise the typed exceptions from `empire_core.exceptions` (`CommandError`, `EmpireTimeoutError`, ...) instead of collapsing failures into `None`. Action methods may return `False` for server-rejected actions, but transport failures must raise
5. **Never return an empty collection to mean "it failed"** — `[]` must mean "there is nothing", so a caller can trust it. If the answer is unknown, raise
6. **Degrade loudly** — When you skip a malformed entry, count the skips and log one warning per response. Silently dropping drifted data turns a schema change into a "successful" empty result
7. **Never leak another library's exceptions** — `pydantic.ValidationError`, `socket.error` and friends must not escape the public API; wrap them in an `EmpireError` subclass. Callers are told `except EmpireError` is enough
8. **Swap, don't mutate** — Readers hold references to state containers without a lock. Build the replacement and swap it in rather than editing in place, so nobody observes a half-updated object
9. **Redact credentials before logging** — Frames can carry passwords. Anything that logs raw wire data must go through the redaction helpers, at any log level
10. **Use descriptive names** — Python names should be readable, aliases handle the wire format
11. **Anything public is forever-ish** — Re-export it from `empire_core/__init__.py` and treat deep-module paths as internal. Removing or renaming an exported name is a breaking change and needs the footer above
