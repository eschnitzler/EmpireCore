# Contributing to EmpireCore

This guide covers how to add new protocol commands and services to EmpireCore.

## Architecture Overview

```
src/empire_core/
├── client/
│   └── client.py          # Main EmpireClient - auto-attaches services
├── protocol/
│   ├── models/            # Pydantic models for all GGE commands
│   │   ├── base.py        # BaseRequest, BaseResponse, registry
│   │   ├── chat.py        # Chat commands (acm, acl)
│   │   ├── alliance.py    # Alliance commands (ahc, aha, ahr)
│   │   ├── castle.py      # Castle commands (gcl, dcl, jca, etc.)
│   │   └── ...
│   └── packet.py          # Low-level packet parsing
├── services/              # High-level service APIs
│   ├── base.py            # BaseService, @register_service
│   ├── alliance.py        # AllianceService
│   └── castle.py          # CastleService
└── state/                 # Game state models
```

## Adding a New Protocol Command

Protocol models define the request/response structure for GGE commands. Each command has:
- A **request model** (what you send)
- A **response model** (what you receive)

### Step 1: Add the Command Code

Add the command code to `GGECommand` in `protocol/models/base.py`:

```python
class GGECommand:
    # ... existing commands ...
    
    # Your new command
    XYZ = "xyz"  # Description of what it does
```

### Step 2: Create Request Model

Request models inherit from `BaseRequest` and define:
- `command` class variable (the command code)
- Fields with `Field(alias="X")` for wire format

```python
# protocol/models/your_domain.py

from pydantic import Field
from .base import BaseRequest

class YourRequest(BaseRequest):
    """
    Description of what this request does.
    
    Command: xyz
    Payload: {"FID": field_id, "V": value}
    """
    
    command = "xyz"
    
    field_id: int = Field(alias="FID")
    value: str = Field(alias="V")
```

**Key points:**
- Use `Field(alias="X")` to map Python names to wire format
- Add `@classmethod` factory methods for common patterns
- Document the command and payload format

### Step 3: Create Response Model

Response models inherit from `BaseResponse`:

```python
from pydantic import Field
from .base import BaseResponse

class YourResponse(BaseResponse):
    """
    Response from xyz command.
    
    Command: xyz
    Payload: {"R": result, "S": success}
    """
    
    command = "xyz"  # Auto-registers in response registry
    
    result: str = Field(alias="R")
    success: bool = Field(alias="S", default=True)
```

**Key points:**
- Setting `command = "xyz"` auto-registers the response model
- Use `parse_response("xyz", payload)` to parse responses

### Step 4: Export Models

Add exports to `protocol/models/__init__.py`:

```python
from .your_domain import (
    YourRequest,
    YourResponse,
)

__all__ = [
    # ... existing exports ...
    "YourRequest",
    "YourResponse",
]
```

### Complete Example: Adding a New Command

Here's a complete example adding a hypothetical "get bookmarks" command:

```python
# protocol/models/bookmarks.py

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, Position


class GetBookmarksRequest(BaseRequest):
    """
    Get player's map bookmarks.
    
    Command: gbl
    Payload: {} (empty)
    """
    
    command = "gbl"


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
        return Position(X=self.x, Y=self.y, KID=self.kingdom_id)


class GetBookmarksResponse(BaseResponse):
    """
    Response containing player's bookmarks.
    
    Command: gbl
    Payload: {"BL": [bookmark, ...]}
    """
    
    command = "gbl"
    
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

```python
# services/bookmarks.py

from __future__ import annotations

from typing import Callable

from empire_core.protocol.models import (
    Bookmark,
    GetBookmarksRequest,
    GetBookmarksResponse,
)

from .base import BaseService, register_service


@register_service("bookmarks")
class BookmarksService(BaseService):
    """
    Service for bookmark operations.
    
    Accessible via client.bookmarks after auto-registration.
    
    Usage:
        client = EmpireClient(...)
        client.login()
        
        bookmarks = client.bookmarks.get_all()
        for b in bookmarks:
            print(f"{b.name} at ({b.x}, {b.y})")
    """
    
    def get_all(self, timeout: float = 5.0) -> list[Bookmark]:
        """
        Get all bookmarks.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            List of Bookmark objects
        """
        request = GetBookmarksRequest()
        response = self.send(request, wait=True, timeout=timeout)
        
        if isinstance(response, GetBookmarksResponse):
            return response.bookmarks
        
        return []
```

### Step 2: Register Service

Add the import to `services/__init__.py`:

```python
from .base import BaseService, register_service, get_registered_services

# Import services to trigger registration
from .alliance import AllianceService
from .castle import CastleService
from .bookmarks import BookmarksService  # Add this

__all__ = [
    "BaseService",
    "register_service",
    "get_registered_services",
    # Services
    "AllianceService",
    "CastleService",
    "BookmarksService",  # Add this
]
```

### Service Patterns

#### Fire-and-forget (no response needed)

```python
def send_chat(self, message: str) -> None:
    request = AllianceChatMessageRequest.create(message)
    self.send(request)  # No wait
```

#### Wait for response

```python
def get_resources(self, castle_id: int) -> ResourceAmount | None:
    request = GetResourcesRequest(CID=castle_id)
    response = self.send(request, wait=True, timeout=5.0)
    
    if isinstance(response, GetResourcesResponse):
        return response.resources
    return None
```

#### Subscribe to incoming messages

```python
def __init__(self, client) -> None:
    super().__init__(client)
    self._callbacks: list[Callable] = []
    
    # Register internal handler
    self.on_response("acm", self._handle_message)

def on_message(self, callback: Callable) -> None:
    """Register callback for incoming messages."""
    self._callbacks.append(callback)

def _handle_message(self, response) -> None:
    """Internal handler dispatches to callbacks."""
    if isinstance(response, AllianceChatMessageResponse):
        for callback in self._callbacks:
            try:
                callback(response)
            except Exception:
                pass
```

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
class HelpMemberRequest(BaseRequest):
    command = "ahc"
    
    player_id: int = Field(alias="PID")
    castle_id: int = Field(alias="CID")
    help_type: int = Field(alias="HT")
    
    @classmethod
    def heal(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a heal help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.HEAL)
    
    @classmethod
    def repair(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a repair help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.REPAIR)
```

## Testing

Run tests with:

```bash
uv run pytest
```

Verify imports work:

```bash
uv run python -c "from empire_core.services import get_registered_services; print(get_registered_services())"
```

## Guidelines

1. **No logging in library code** - Libraries should not emit logs
2. **Use type hints** - All public methods should have complete type hints
3. **Document wire format** - Include the command code and payload format in docstrings
4. **Handle errors gracefully** - Return `None` or empty lists rather than raising exceptions
5. **Use descriptive names** - Python names should be readable, aliases handle the wire format
