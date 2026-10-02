---
description: Build and send any request model directly, and parse its typed reply.
---

# Protocol models

The services cover the common commands. For everything else, and for full
control, send the request models yourself. Every command has a request model
(what you send) and a response model (what comes back), and
`empire_core.protocol.models` re-exports them all.

```python
from empire_core.protocol.models import (
    AllianceChatMessageRequest,
    GetCastlesRequest,
    GetCastlesResponse,
)

request = AllianceChatMessageRequest.create("Hello 100%!")
client.frame(request)
# once the login has joined room 1:
# '%xt%EmpireEx_21%acm%1%{"M":"Hello 100&percnt;!"}%'

client.send(request)                                     # fire and forget
response = client.send(GetCastlesRequest(), wait=True)   # or wait for the reply
castles = client.request(GetCastlesRequest(), GetCastlesResponse)
```

`client.frame(request)` is the frame as this session sends it, in its zone and
the room it joined. `request.to_packet(zone=..., room_id=...)` builds one for
any zone and room.

## Three ways to send

| Call | Returns | On a server refusal |
|---|---|---|
| `client.send(request)` | `None`, without waiting | nothing: no reply is awaited |
| `client.send(request, wait=True)` | the parsed response | raises `CommandError` |
| `client.request(request, ResponseType)` | the response, checked to be `ResponseType` | raises `CommandError` |

Waiting calls also raise `EmpireTimeoutError`, `ConnectionClosedError`,
`NetworkError` or `PacketError`; see [Error handling](errors.md). How a reply
is matched to its request is drawn on
[Login and requests](../internals/login-and-requests.md#requests-and-replies).

## Models

Models are pydantic v2 models with snake_case fields; each field's wire key is
its alias, and both are accepted when you build one:

```python
from empire_core import AttackWave, WaveFlank

AttackWave(left=WaveFlank(units=[[487, 100]]))
AttackWave(L=WaveFlank(U=[[487, 100]]))       # the same wave, by wire keys
```

Prefer field names: with pydantic's mypy plugin, mypy checks those calls for
missing fields, wrong types and typos, and rejects wire keys.

`model_dump(by_alias=True)` gives the wire form back. The
[API reference](../reference/index.md) lists every model's fields with their
wire keys and descriptions.

## Subscribing to raw packets

Services register typed handlers for the pushes they care about. To see every
packet of one command yourself, subscribe on the connection:

```python
def on_packet(packet):
    print(packet.command_id, packet.payload)

client.connection.subscribe("acm", on_packet)
client.connection.unsubscribe("acm", on_packet)
```

Subscribers run on the receive thread and must not wait for replies there.

!!! info "Adding a command"

    [Contributing](../contributing.md) explains how to add a request and
    response model, and the tests that check each one against the game
    client's own command list.

**API:** [Protocol](../reference/protocol.md)
