# Protocol Specification

Goodgame Empire uses a custom implementation of the SmartFoxServer (SFS) 2.X protocol. It operates over TCP or WebSockets and involves a mix of XML (for handshake) and a custom delimited string format (for gameplay).

## 1. Connection Phase

The connection follows a strict sequence:

1.  **Policy Request**: The client requests `cross-domain-policy`.
2.  **Version Check (`verChk`)**: Client sends XML to verify client version.
    *   Format: `<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>`
3.  **Login (`login`)**: Client sends hashed credentials.
    *   Format: `<msg t='sys'><body action='login' r='0'><login z='EmpireEx_21'><nick><![CDATA[]]></nick><pword><![CDATA[{HASHED_PW}]]></pword></login></body></msg>`
4.  **Room Join (`autoJoin`)**: Client requests to join the default server room.

## 2. Command Format (Extension Requests)

Once logged in, communication switches to the `%xt%` format.

### Structure
`%xt%{ZoneName}%{CommandName}%{RequestId}%{Payload}%`

*   `xt`: Extension header.
*   `ZoneName`: Usually `EmpireEx_21`.
*   `CommandName`: Short code for the action (e.g., `lli` for Load Login Info, `gam` for Game Map).
*   `RequestId`: Incremental integer (client-side tracking).
*   `Payload`: Often a JSON string, but sometimes delimited arguments.

### Example: Sending an Attack
To send an attack, the client constructs a JSON payload describing the army and target, then wraps it:

```python
payload = {
    "K": 0,   # Kingdom ID
    "T": 123, # Target Castle ID
    "U": [...] # Unit List
}
packet = f"%xt%EmpireEx_21%att%1%{json.dumps(payload)}%"
```

## 3. Packet Handling Strategy

### Inbound Parsing
1.  **Splitter**: The stream buffer is split by the null byte `\x00` or specific delimiters.
2.  **Router**: The `CommandName` (3rd token) is extracted.
3.  **Decoder**:
    *   If the payload looks like JSON (`{...}`), it is parsed as JSON.
    *   If it looks like CSV, it is split by `%`.
4.  **Dispatcher**: The parsed data is sent to the relevant `Handler` (e.g., `AttackHandler`).

### Outbound Serialization
We will use `dataclasses` to define packet structures, which are then serialized by the `NetworkLayer`.

```python
@dataclass
class LoginPacket:
    username: str
    password_hash: str
    
    def to_sfs(self) -> str:
        return f"<msg...><pword>{self.password_hash}</pword>...</msg>"
```
