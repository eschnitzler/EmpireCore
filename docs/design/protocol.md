Checked against client release: a4a25ae6

# Protocol

Goodgame Empire speaks a SmartFoxServer dialect over a WebSocket
(`wss://<host>:<port>`). The handshake is XML system messages; everything after
it is `%xt%` extension messages. Frames from the server end with a null byte;
the client sends its own with none (`sendCommand` and `sendXMLMessage` pass the
bare string to `socket.send`, dll lines 7198-7203), and so does the library
(`Connection.send` strips a trailing null byte before sending).

Line numbers below are `ggs.dll.split.js` lines (see the roadmap issue for how
to fetch and split the client); search by the class name when they drift.

## 1. Handshake

What the HTML5 client does (`BasicSmartfoxClient`, dll lines 7132-7240):

1. **`verChk`**, sent as soon as the socket opens (there is no policy request):
   `<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>`
2. **`apiOK`** comes back. The client then logs in to the zone with an empty
   nick and `<build date>%<language>%<distributor id>` as the password
   (`handleSystemMessage`, `login`):
   `<msg t='sys'><body action='login' r='0'><login z='EmpireEx_21'><nick><![CDATA[]]></nick><pword><![CDATA[...]]></pword></login></body></msg>`
3. **`rlu`** (room list, an `%xt%` message) comes back; the client sends
   `autoJoin` once: `<msg t='sys'><body action='autoJoin' r='-1'></body></msg>`.
4. **`joinOK`** comes back. Its `r` attribute is the room id the client sends in
   every later `%xt%` message (`activeRoomId`).
5. In the lobby room the client measures a `roundTrip` (answered by
   `roundTripRes`), starts a `pin` every 60 seconds (`onJoinRoom`) and sends
   `vck` with the build number, `web-html5`, `<RoundHouseKick>` and the session
   id (`BasicJoinedRoomCommand`, dll line 33011). `sendMessage` sends any
   argument that is falsy but not `0` as `<RoundHouseKick>`, so the empty
   string `vck` passes third goes out as that, and each `pin` is
   `%xt%<zone>%pin%<room id>%<RoundHouseKick>%`.
6. **`lli`**: the account login, whose JSON payload carries the name (`NOM`)
   and password (`PW`).

What the library does today (`EmpireClient._login_sequence`): `verChk`, then
the zone login with `<CONM>%en%0` as the password, `autoJoin`, `roundTrip`, and
`lli`. It sends no `vck` and pings from its own keepalive thread. Section 2
lists where its `%xt%` messages differ too.

## 2. Extension messages

`%xt%<zone>%<command>%<room id>%<argument>%...%`

- **zone**: `EmpireEx_21` unless configured otherwise.
- **command**: the command id, for example `gaa` or `cra`. The ids the client
  knows are in `tests/data/client_commands.json` (see `CONTRIBUTING.md`).
- **room id**: the id from `joinOK`; `BaseRequest.to_packet` always sends `1`.
- **arguments**: nearly every command has one, `JSON.stringify` of its
  `C2S...VO` (`sendCommandVO`). A few, such as `vck` and `pin`, send plain
  `%`-separated arguments. Before sending, the client turns every `%` in a
  string argument into `&percnt;` and drops every `'`
  (`sendMessage`, `TextValide.getValideSmartFoxText`, dll line 5816).
  `BaseRequest.to_packet` does not, so a backslash in a text field, which
  `encode_json_text` writes as `%5C`, goes out as a raw `%` inside the message.

A reply is `%xt%<command>%<room id>%<error code>%<JSON>%`; an error code other
than 0 is a failure.

Example, a `gaa` map request as the client builds it (`C2SGetAreasVO`, bundle line 65991):

```
%xt%EmpireEx_21%gaa%<room id>%{"KID":0,"AX1":0,"AY1":0,"AX2":12,"AY2":12}%
```

## 3. In the library

- `protocol/packet.py`: `Packet.iter_from_bytes` splits a frame on null bytes
  and `Packet.from_bytes` parses one message, XML or `%xt%`, splitting at most
  five times so a `%` in the JSON survives.
- `protocol/base.py`: each command's request model subclasses `BaseRequest`
  (`to_payload`, `to_packet`); each reply model subclasses `BaseResponse` and
  registers itself for its command, so `parse_response(command, payload)` finds
  it.
- `network/connection.py`: the receive loop and the waiters that
  `EmpireClient.send` / `request` block on; see [architecture.md](architecture.md).
