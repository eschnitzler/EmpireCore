# GGE Protocol Notes from Manual Testing

## WebSocket Connection
- Server: `ep-live-us1-game.goodgamestudios.com:443` (WSS)
- Frames MUST be masked (client->server requirement)

## Handshake Sequence

### 1. Policy File Request
**Send:** `<policy-file-request/>\x00`
**Response:** Cross-domain policy (Flash legacy)

### 2. Version Check  
**Send:** `<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>\x00`
**Response:** `<msg t='sys'><body action='apiOK' r='0'></body></msg>`

### 3. Login
**Send:** 
```xml
<msg t='sys'><body action='login' r='0'>
  <login z='EmpireEx_21'>
    <nick><![CDATA[username]]></nick>
    <pword><![CDATA[password]]></pword>
  </login>
</body></msg>\x00
```

**Responses:**
- Game info: `%xt%nfo%1%0%{"XML_E4K":"757.RC.02","XML_EP":"757.02","minNameSize":3,"sectorCountY":99,"sectorCountX":99}%`
- Core info: `%xt%core_nfo%1%0%{...}%`  
- Room join: `%xt%rlu%-1%1%0%100000%2%Lobby%`

## Protocol Format
- XML format: `<msg>...</msg>\x00`
- XT format: `%xt%command%param1%param2%...%`

## Next Steps
- Send `gbd` (get big data) to get player info
- Send `dcl` (detailed castle list) to get castle data
- Explore available commands (ata, tru, bui, etc.)
