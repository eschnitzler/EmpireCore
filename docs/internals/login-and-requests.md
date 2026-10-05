---
description: The login handshake, how a reply finds its request, and how the packages are layered.
---

# Login and requests

## The login handshake

`client.login()` runs the same exchange as the game's HTML5 client, step for
step. The XML messages are SmartFox system messages; the rest are `%xt%`
extension messages.

```mermaid
sequenceDiagram
    autonumber
    participant C as EmpireClient
    participant S as Game server
    C->>S: open the WebSocket
    C->>S: verChk (XML)
    S-->>C: apiOK
    C->>S: zone login with the build number (XML)
    S-->>C: rlu, the room list
    C->>S: autoJoin (XML)
    S-->>C: joinOK, with the room id
    Note over C: the room must be the lobby
    C->>S: roundTrip (XML)
    C->>S: vck, the game version check
    par
        S-->>C: roundTripRes
    and
        S-->>C: vck
    end
    C->>S: lli, the account login, with the measured times
    S-->>C: lli
    S-->>C: gbd, the login data
    Note over C: login() returns
    S-->>C: slt, a fresh login token
    S-->>C: gam, the movement list
    loop every 60 seconds
        C->>S: pin
    end
```

- `joinOK`'s room id goes into every `%xt%` message after it.
- `vck` refused with code 1 or 2 raises `ClientVersionError`; set
  `EmpireConfig.client_version` to the current client's version.
- `lli` sends the connection time and the round-trip time the client measured,
  and either the password or a login token.
- A refused `lli` raises a typed `LoginError`: `LoginCooldownError`,
  `AccountBannedError`, `WrongServerError`, or `LoginError` itself.
- `login()` waits for `gbd`, which fills the player and castles in state.
  `slt` and `gam` arrive just after it; `client.login_token` is updated from
  `slt`.
- Any failure closes the connection and its threads before the error reaches
  you.

## Requests and replies

Most replies do not say which request they answer; they only carry the command
id. So a request holds a per-command lock from before it is sent until its
reply arrives, and at most one request per command id is in flight.

```mermaid
sequenceDiagram
    participant U as Your thread
    participant L as Command lock
    participant R as Receive thread
    participant St as GameState
    U->>L: acquire, e.g. "gcl"
    U->>U: register a waiter for "gcl"
    U->>R: send the frame
    R->>R: reply arrives under "gcl"
    R->>R: pick the first waiter that accepts it
    R->>St: apply the packet to state
    R-->>U: wake the waiter with the packet
    R->>R: notify the "gcl" subscribers
    U->>L: release
    U->>U: raise CommandError on a non-zero code,<br/>else parse the typed response
```

- The waiter is registered **before** the send, so an immediate reply cannot
  be missed.
- State is updated **before** the waiter wakes, so reading state right after a
  request sees what the reply carried.
- Some request models can check that a reply is theirs (`accepts_reply`); for
  those, replies about something else pass to state and subscribers without
  being taken. Error replies carry nothing to check and always go to the
  oldest waiter. A successful reply goes to a waiter still waiting before one
  that is only owed a reply (below) and has a check.
- A request that times out still owes its reply. Its waiter stays registered
  for as long again as the timeout and takes the late reply (or any error)
  when it comes, so the reply reaches state and subscribers but no later
  request. The next request for a command without a reply check is sent only
  once that reply is in or the window has passed, and then still gets its
  whole timeout: after a lost reply it can take up to the earlier request's
  timeout longer. One with a check is sent at once.
  `Connection.send_and_drop_reply` sends a request whose reply nobody waits
  for in the same way, after taking the command's lock (except on the receive
  thread): the library uses it for `get_movements(wait=False)` and the `gam`
  it asks for after an `mvf` push. A plain `send(wait=False)` gives up
  pairing: its reply can answer a concurrent request for that command.
- Commands whose replies can't be told apart: `gam`, `gcl`, `dcl`, `gli`,
  `gui`, `gpa` and other reads without parameters (any of their replies
  answers any caller, as long as the joined castle stays the same), `hgh`, `bsd`, `rms`, `wsp`, `fnm`, `fec`, the attack-info family,
  chat, and writes whose reply is only a status. For these the timeout drain
  above is the only protection. It fails when a server push under the same
  command id is taken for the owed reply, or when the owed reply never comes
  and the next request's error is taken instead (that request times out).
- Time spent waiting for the lock counts against the call's `timeout`;
  waiting for an owed reply does not.
- Threads waiting for one command's lock are not served in arrival order;
  every wait is still bounded by its timeout.
- The receive thread never waits for a reply itself: a waiting call made on it
  raises `ReceiveThreadError`. Alliance chat callbacks and connection
  subscribers run there; state callbacks run on their own callback thread.

## The package layers

The library is organised by game area. Arrows point down, toward what a layer
may import: an area imports only areas of a lower rank, the shared plumbing at
the bottom imports no area, and the client, state and network sit above them all.
`tests/test_layers.py` checks every import against these ranks.

```mermaid
flowchart TB
    t["<b>Above the areas</b><br/>client · state · network · accounts · pool"]
    r7["<b>Rank 7</b><br/>spy"]
    r6["<b>Rank 6</b><br/>attack · alliance"]
    r5["<b>Rank 5</b><br/>combat · player"]
    r4["<b>Rank 4</b><br/>defense"]
    r3["<b>Rank 3</b><br/>movements · messages"]
    r2["<b>Rank 2</b><br/>army"]
    r1["<b>Rank 1</b><br/>commanders · castle"]
    r0["<b>Rank 0</b><br/>map · ranking · events"]
    p["<b>Plumbing</b><br/>protocol · enums · gamedata · exceptions · config · utils · services"]
    t --> r7 --> r6 --> r5 --> r4 --> r3 --> r2 --> r1 --> r0 --> p
```

Each area package holds its models (a `models.py` or a `models/` package) and,
where the game has one, a `service.py` reached as `client.<area>`. An area's
`__init__` exports its models and its service, and is the area's public
import path (see [What is public](../reference/index.md)). The library itself
imports from the modules inside an area, which are private.
`empire_core.protocol.models` imports every area's models so the response
registry is full; it is private too.
