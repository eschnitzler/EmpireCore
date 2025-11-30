# Game Bundle Analysis

**Source:** `Game.bundle.ec7519bb37451214187e.js` (Empire HTML5 Client)
**Date:** 2025-11-30

## 1. Protocol Overview
The client uses SmartFoxServer (SFS) with a mix of XML (Handshake) and JSON-over-String (Extended Protocol `%xt%`).
Command mappings are stored in the `ClientConstSF` object in the minified JS.

## 2. Command Mappings (Key Commands)
Extracted from `ClientConstSF`.

| Category | Constant Name | Command ID | Description |
|---|---|---|---|
| **Auth** | `C2S_LOGIN` | "lli" | Login with username/password/token |
| **Auth** | `C2S_VERSION_CHECK` | "vck" | Pre-login version check |
| **Attack** | `C2S_CREATE_ARMY_ATTACK_MOVEMENT` | "cra" | Send attack |
| **Attack** | `C2S_GET_ATTACK_INFO` | "gai" | Get attack details/pre-calc |
| **Attack** | `C2S_GET_ATTACK_CASTLE_INFOS` | "aci" | Get castle defense info |
| **Player** | `C2S_GET_DETAILPLAYERINFO` | "gdi" | Get player profile |
| **Player** | `C2S_SEARCH_PLAYER` | "wsp" | Search for a player by name |
| **Castle** | `C2S_RENAME_CASTLE` | "arc" | Rename castle |

*To extract all commands:*
```bash
grep -o -E "ClientConstSF\.[A-Z0-9_]+\"[^\"]+\"" game_bundle.js > client_commands.txt
```

## 3. Payload Structures (Value Objects)

The client uses `C2S...VO` classes to structure requests. The minified code assigns properties to `this` (aliased as `g` or `y` in the minified function) which represent the JSON keys sent to the server.

### Login (`lli`) - `C2SLoginVO`
**Command:** `lli`
**Javascript Constructor:** `function C2SLoginVO(t,i,n,s,r,l,c,u,d,p,h)`
**Fields (JSON Keys):**
*   `CONM`: Connection Name / User Name (String)
*   `RTM`: (Unknown) - Default 0
*   `PLFID`: Platform ID - (Int)
*   *(Note)*: Password is usually sent in the XML login step, or hashed in `CONM`? The XML login packet in `DEV_CONTEXT` shows password in XML. This `lli` might be the "User Enter" event after SFS login.

### Attack (`cra`) - `C2SCreateArmyAttackMovementVO`
**Command:** `cra`
**Javascript Constructor:** `function C2SCreateArmyAttackMovementVO(t,i,n,o,s,r,l,c,u,d,p,h,g,C,_,m,f,O,E)`
**Fields (JSON Keys):**
*   `SX`, `SY`: Source Coordinates (int) - `t.x`, `t.y`
*   `TX`, `TY`: Target Coordinates (int) - `i.x`, `i.y`
*   `A`: Army / Units Data (Object) - Argument `n`
*   `KID`: Kingdom ID (int) - Argument `h`
*   `LID`: Location ID / Target Castle ID (int) - Argument `d`
*   `WT`: World Type (int) - Argument `o`
*   `HBW`: (Unknown) - Related to argument `g` (boolean?)
*   `BPC`: (Unknown) - Argument `r`
*   `ATT`: Attack Type (int) - Argument `l` (e.g., Capture, Pillage?)
*   `AV`: (Unknown) - Argument `c` (boolean flag?)
*   `LP`: (Unknown) - Argument `u`
*   `FC`: Fast Cast / Feather? (int) - Argument `p` (boolean flag?)
*   `PTT`: (Unknown) - Argument `g` (flag?)
*   `SD`: Scheduled Date (int) - Argument `C` (Timestamp for timed attacks?)
*   `ICA`: (Unknown) - Argument `_`
*   `BKS`: (Unknown) - Argument `m`
*   `AST`: (Unknown) - Argument `f`
*   `CD`: Countdown/Cooldown? - Hardcoded `99`
*   `RW`: (Unknown) - Argument `O`
*   `ASCT`: (Unknown) - Argument `E`

## 4. Strategies for Reverse Engineering
1.  **Find the VO**: Search for `function C2S...VO` to find the class definition.
2.  **Map Arguments**: Look at the constructor arguments and how they map to `this.XX` properties.
3.  **Find Usage**: Search for `new C2S...VO` to see what actual values are passed (e.g., `u.CastleModel.userData...`).
