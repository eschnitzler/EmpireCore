# Dreambot.py Analysis

**Source:** `Dreambot.py` (Local Folder)
**Date:** 2025-11-30

## Abstract Data Types (ADTs) Analysis

Analysis of `scripts/gge.py`, `scripts/map_parsing.py`, and `utils/location_utils.py` reveals several ADT patterns.

### 1. `GGEWebSocket` (Connection Manager)
*   **Encapsulation:** Encapsulates the `websocket.WebSocket` instance and connection state (`is_connected`).
*   **Abstraction:** Provides high-level methods `connect()`, `log_account()`, `keep_alive()` hiding the raw socket operations and protocol handshake (XML login -> XT login).
*   **Immutability:** Mutable state (`is_connected`, `ws`).
*   **Methods:** `__init__`, `connect`, `log_account`, `keep_alive`. (4 methods)

### 2. `Member` (Entity Model)
*   **Encapsulation:** Represents a player/member with attributes like `id`, `name`, `alliance`, `rank`, `locations`, `bird_time`.
*   **Abstraction:** abstracts parsing of locations (JSON) and dates. Provides a property `main_castle_cords`.
*   **Immutability:** Mostly mutable (attributes can be changed, though no setters are explicit).
*   **Methods:** `__init__`, `main_castle_cords` (property), `get_location`, `__str__`. (4 methods)

### 3. `Alliance` (Entity Model & Collection)
*   **Encapsulation:** Represents an alliance with metadata (`id`, `name`) and a collection of `members`.
*   **Abstraction:** Manages member list. Provides methods to add/remove/update members.
*   **Immutability:** Mutable.
*   **Methods:** `__init__`, `add_member`, `remove_member`, `update_member`, `get_member`, `get_members`, `get_member_ids`. (7 methods)

### 4. `Change` (Value Object / Event)
*   **Encapsulation:** Represents a state change event (`AllianceChangeType`, `MemberChangeType`). Holds context: `old` value, `new` value, `member`, `alliance`.
*   **Abstraction:** Generic container for different change types.
*   **Immutability:** Effectively immutable after initialization (no methods modify state).
*   **Methods:** `__init__`. (1 method)

### 5. `ChangeList` (Collection)
*   **Encapsulation:** Wraps a `list[Change]`.
*   **Abstraction:** specialized collection for changes. Provides filtering (`get_change_type`), aggregation (`add_changes`), and formatting (`get_discord_embeds` - which is a bit of a violation of separation of concerns, mixing view logic with model).
*   **Immutability:** Mutable.
*   **Methods:** `__init__`, `add_change`, `add_changes`, `remove_change`, `get_change_type`, `get_color_for_change_type`, `get_discord_embeds`, plus 9 private helper formatting methods. (~16 methods)

### 6. `AllianceList` (Repository / Collection)
*   **Encapsulation:** Wraps a `dict[int, Alliance]`.
*   **Abstraction:** Repository pattern. Provides access to alliances and members across alliances. Also contains complex logic to diff two AllianceLists (`get_change_list`).
*   **Immutability:** Mutable.
*   **Methods:** `__init__`, `get_alliance`, `get_alliances`, `get_member`, `get_change_list`, `save_to_db`, plus 6 private helper/diffing methods. (~12 methods)

### Findings Summary
*   **Patterns:** Strong use of Domain Model pattern (`Member`, `Alliance`) and Collection/Repository patterns (`AllianceList`). The "Diffing" logic is a key feature, encapsulated in `AllianceList` producing a `ChangeList`.
*   **Data Structures:** Heavily relies on Dictionaries for O(1) lookups (`members: dict[int, Member]`) and Lists for collections.
*   **Immutability:** Low. Most objects are mutable.
*   **Parsing Logic:** `map_parsing.py` shows a functional approach (`traverse_map`, `parse_locations`) rather than object-oriented for the map scraping process itself. It relies on generating coordinate lists and parsing raw JSON responses.

### Code Quality Notes
*   `ChangeList` has mixed responsibilities (storage vs presentation/discord formatting).
*   `GGEWebSocket` mixes connection logic with specific login sequence hardcoded strings (less flexible than `EmpireCore`'s config approach).
*   `map_parsing.py` uses raw string manipulation (`message[12:-1]`) which is brittle compared to a robust protocol parser.
