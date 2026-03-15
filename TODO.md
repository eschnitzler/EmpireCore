# EmpireCore Refactoring TODO

## 🔴 High Priority

- [ ] **1. Split `scan_kingdom()` into a `MapScanner` class** (`client/client.py`)
  - 220-line god method with nested functions (`chunk_bounds`, `process_chunk`), BFS, retry, filtering, timing, logging all mixed together
  - Extract to `client/map_scanner.py` as a `MapScanner` class with focused methods

- [ ] **2. Split `_handle_gbd()` into focused parse methods** (`state/manager.py`)
  - 90-line method parsing player, XP, currencies, inventory, VIP, alliance, castles, DCL, SEI all at once
  - Extract into `_parse_player()`, `_parse_castles()`, `_parse_alliance()` etc.

- [ ] **3. Replace `update_from_packet()` if/elif chain with dispatch dict** (`state/manager.py`)
  - Long chain dispatching on command strings — replace with `_HANDLERS: dict[str, Callable]` built at class init

- [ ] **4. Fix duplicate encoding in `send_alliance_chat()`** (`client/client.py`)
  - Manually re-encodes `%`, `"`, `'`, `\n`, `\` — identical logic already in `AllianceChatMessageRequest.create()`
  - Should delegate to the model instead of duplicating

- [ ] **5. Fix `get_player_details_bulk()` temp handler pattern** (`client/client.py`)
  - Registers a closure as a handler then manually removes it with index check — fragile
  - Replace with `threading.Event` + `queue.Queue` pattern

---

## 🟡 Medium Priority

- [ ] **6. Remove all `if TYPE_CHECKING:` blocks**
  - Files: `client/client.py` (both module-level and class-body), `services/base.py`, `services/alliance.py`, `services/lords.py`, `services/accounts.py`
  - Services have no real circular imports — import directly and drop the guards
  - The class-body `if TYPE_CHECKING:` in `client.py` is especially unusual and confusing

- [ ] **7. Replace raw `dict | None` returns with typed models** (`client/client.py`)
  - `get_player_info()`, `get_alliance_info()`, `get_alliance_chat()` return untyped dicts
  - Inconsistent with every other method — return typed response models like the rest of the API

- [ ] **8. Merge `_handle_atv()` and `_handle_ata()` into one method** (`state/manager.py`)
  - Identical method bodies: mark arrived → fire callback → pop from movements
  - Consolidate into `_handle_movement_arrived()` called by both

- [ ] **9. Make state callbacks support multiple listeners** (`state/manager.py`)
  - `on_incoming_attack`, `on_movement_recalled`, `on_movement_arrived` are `Optional[Callable]` (single listener)
  - `_handlers` in `client.py` already supports lists — state callbacks should be consistent

---

## 🟢 Low Priority

- [ ] **10. Modernize `typing` imports codebase-wide**
  - All files import `Dict`, `List`, `Optional`, `Set`, `Callable`, `Tuple` from `typing`
  - Replace with Python 3.10+ built-in generics: `dict`, `list`, `X | None`, `set`, `tuple`, `callable`
  - Files: `client/client.py`, `state/manager.py`, `state/models.py`, `state/world_models.py`, `state/report_models.py`, `state/unit_models.py`, `state/quest_models.py`, `network/connection.py`, `protocol/models/base.py`, `storage/database.py`, `utils/calculations.py`, `utils/decorators.py`, `config.py`

- [ ] **11. Delete `_archive/` directory**
  - Entire directory of dead code, never imported anywhere
  - Dead weight in the repo

- [ ] **12. Fix `_chat_callbacks` type annotation** (`services/alliance.py`)
  - Typed as `list[Callable]` — should be `list[Callable[[AllianceChatMessageResponse], None]]`
