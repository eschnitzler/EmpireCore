# EmpireCore: AI Developer Context & System Instructions

**Role:** You are an Expert Python Systems Architect and Reverse Engineering Specialist.
**Objective:** Implement `EmpireCore`, a high-performance, asynchronous, reverse-engineered client library for "Goodgame Empire" (GGE).

## 1. Core Design Philosophy
*   **Async-First:** All I/O (Network, File) must use `asyncio`. No blocking `socket` or `requests` calls.
*   **Type Safety:** 100% type hint coverage. Use `pydantic` for all data models.
*   **Stability:** Do not use hardcoded strings for logic that can be dynamic. Abstract the protocol.
*   **Stateful:** The client must maintain a "living" representation of the game world, not just return API responses.

## 2. Architecture Stack
The library is divided into four distinct layers. **Do not violate these boundaries.**

1.  **Network Layer (`src/empire_core/network`)**:
    *   Manages `asyncio.StreamReader` and `StreamWriter`.
    *   Handles SSL/TLS encryption.
    *   **Responsibility:** Connection lifecycles, reconnection logic, and raw byte buffering.
    *   **Output:** Yields complete, delimited packets to the Protocol Layer.

2.  **Protocol Layer (`src/empire_core/protocol`)**:
    *   **SmartFoxServer (SFS) 2.X Driver**.
    *   **Handshake:** Implements the XML-based login sequence (Policy -> VerChk -> Login).
    *   **Command Parsing:** Handles the `%xt%` delimited string format.
    *   **Responsibility:** converting `bytes` <-> `Packet` objects.

3.  **State Layer (`src/empire_core/state`)**:
    *   **Identity Map Pattern:** Ensures unique Python objects for game entities (e.g., `Castle(id=1)` is always the same instance).
    *   **Reactive:** Objects emit events when modified (e.g., `castle.food = 500` triggers `on_resource_change`).
    *   **Responsibility:** Mirroring the game server's state locally.

4.  **Client Layer (`src/empire_core/client`)**:
    *   **High-Level API:** `client.login()`, `client.attack()`, `client.get_castle()`.
    *   **Event Bus:** Dispatches typed events (e.g., `AttackIncomingEvent`) to user callbacks.

## 3. Protocol Specifications (Reverse Engineered)

### Connection Handshake (Sequence is strict)
1.  **Policy Request:** Send `<policy-file-request/>\x00`.
2.  **Version Check:** Send `<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>\x00`.
3.  **Login:**
    *   Send: `<msg t='sys'><body action='login' r='0'><login z='EmpireEx_21'><nick><![CDATA[]]></nick><pword><![CDATA[{HASHED_PASSWORD}]]></pword></login></body></msg>\x00`
    *   *Note:* `EmpireEx_21` is the zone name.
4.  **Join Room:** `<msg t='sys'><body action='autoJoin' r='-1'></body></msg>\x00`

### Extended Protocol (`%xt%`)
After login, traffic switches to a delimited format:
*   **Format:** `%xt%{Zone}%{Command}%{RequestId}%{Payload}%`
*   **Example:** `%xt%EmpireEx_21%lli%1%{"JSON": "DATA"}%`
*   **Terminator:** All packets end with a null byte `\x00`.

## 4. Development Roadmap
Follow this order to build the framework:

1.  **Scaffold:** Create directory structure and `pyproject.toml` (Done).
2.  **Phase 1 - Protocol Definitions:** Define `Packet`, `LoginPacket`, `XtPacket` using `dataclasses`/`pydantic`.
3.  **Phase 2 - Network Loop:** Implement `SFSConnection` class to handle reading/writing bytes and splitting by `\x00`.
4.  **Phase 3 - Handshake Logic:** Implement the XML state machine to get from "Connected" to "Logged In".
5.  **Phase 4 - Event Dispatcher:** Build the system to route parsed packets to handlers.
6.  **Phase 5 - Game Models:** Define `Player`, `Castle`, `Troops`.

## 5. Tools & Libraries
*   **Runtime:** Python 3.10+
*   **Networking:** `asyncio` (stdlib) - *Do not use `websocket-client` library, use native asyncio or `aiohttp` if WSS is needed.*
*   **Parsing:** `xml.etree.ElementTree` (for handshake), `json` (for payloads).
*   **Models:** `pydantic`.

## 6. Critical Rules
*   **Never** commit raw passwords. Use `os.getenv`.
*   **Never** mix game logic (e.g., "Send attack") into the Network layer.
*   **Always** implement a `close()` method to clean up pending tasks.

## 7. Reference & Reverse Engineering Sources
Use these resources to resolve protocol ambiguities or implementation details:

*   **Existing Codebases (Reference ONLY):**
    *   `Dreambot.py` (Local Folder): Use `scripts/gge.py` and `scripts/incomings.py` to understand the login handshake XML structure and how attack packets (`%xt%gam%`) are parsed.
    *   `pygge` (GitHub): Use as a reference for basic socket management and `get_account_infos` payload structure.
*   **Source of Truth:**
    *   **Game Bundle (JS):** `https://empire-html5.goodgamestudios.com/default/Game.bundle.ec7519bb37451214187e.js`
    *   *Usage:* Search this JS file for string constants (e.g., `"lli"`, `"att"`) to find the full list of command IDs and expected payload structures. Use this to verify the field names in your Pydantic models.