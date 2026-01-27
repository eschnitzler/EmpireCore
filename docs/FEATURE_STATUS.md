# EmpireCore Feature Status & Gap Analysis

**Based on Requirements from `BB.pdf`**

This document tracks the implementation status of features requested for the DreamBot integration. It maps high-level requirements to existing `EmpireCore` capabilities and identifies missing components.

**Status Legend:**
*   ✅ **Implemented**: Core logic, Protocol models, and Service methods exist.
*   ⚠️ **Partial**: Protocol models exist, but Service/High-level automation logic is missing.
*   ❌ **Missing**: No support in `EmpireCore` (requires new models or services).
*   🤖 **Bot-Side**: Feature belongs in the Discord Bot layer, not EmpireCore (but EmpireCore must provide the API).

---

## 1. Attack Warnings & Defense
**Requirement**: "Attack warnings within DC... commander perks... defense ratio... spam pings."

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Attack Detection** | ✅ | Implemented in `client.get_incoming_attacks()` and `state.on_incoming_attack` callback. |
| **Attack Details** | ✅ | `Movement` model (`state/world_models.py`) parses: Source/Target (Player/Alliance), Unit Count, Arrival Time. |
| **Commander/Perks** | ⚠️ | `Movement` model has `commander_equipment` / `commander_effects` raw fields, but no parser/enum mapping for specific perks. |
| **Defense Ratio** | ⚠️ | `utils/troops.py` helps count units, but logic to calculate "Defense %" (Melee/Range vs Tools) is not in Core. |
| **Spam Pings** | 🤖 | Bot-side logic. Core provides the event trigger. |
| **Support Detection** | ✅ | `Movement.is_support` and `Movement.is_attack` flags exist. |
| **Outer Realms** | ⚠️ | `EmpireConfig` supports zones, but seamless switching/tracking OR events needs testing. |

## 2. Alliance Management
**Requirement**: "Track alliances... birds... assets... scores... maps... spy members."

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Member List** | ✅ | `client.alliance.get_members()` fetches list with Ranks & Levels. |
| **Online Status** | ✅ | `client.alliance.get_online_members()` exists. |
| **Member History** | ❌ | "Up to 2 days in the past" requires Database persistence. `storage/database.py` exists but needs integration for member snapshots. |
| **Birds/Protection** | ❌ | Parsing "Bird" status (protection mode) from member list is not explicitly implemented in `AllianceMember` model. |
| **Asset Tracking** | ✅ | `client.scan_kingdom(item_types=[...])` supports Capitals, Metros, KTs, etc. Filter by owner ID (from member list) to get alliance assets. |
| **Alliance Map** | ✅ | `client.scan_kingdom()` provides the raw data. Visualization is Bot-side. |
| **Spying** | ⚠️ | `csm` (Create Spy Mission) protocol exists in `protocol/models/attack.py`. `SpyService` needed for batching/logic. |

## 3. Communication (Chat)
**Requirement**: "Alliance chat integration... Discord... Warnings."

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Send Message** | ✅ | `client.alliance.send_chat()` implemented with encoding. |
| **Receive/Sync** | ✅ | `client.alliance.on_chat_message()` callback implemented. |
| **Chat History** | ✅ | `client.alliance.get_chat_log()` implemented. |
| **Ping (@User)** | 🤖 | Text parsing belongs in Bot layer. Core just passes raw strings. |
| **Backup/Security** | 🤖 | "Backup chat" is a Bot feature. Core provides the data. |

## 4. Automation & Utilities
**Requirement**: "Auto alliance help... Anti-nuke... Event boosts."

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Auto Help** | ✅ | `client.alliance.help_all()` exists. Bot needs to call it on a loop/timer. |
| **Anti-Nuke** | ❌ | No "Kick" event listener in `AllianceService`. Logic to detect kicks and counter-demote is missing. |
| **Event Boosts** | ❌ | No `AllianceService` methods to start/contribute to alliance boosts (models likely missing). |
| **User Admin** | 🤖 | Verification logic (checking descriptions/names) is Bot-side. |

---

## 5. Technical Gap Analysis

### Missing Services
To fully support the requirements, the following Services need to be created or expanded:

1.  **`SpyService`**:
    *   **Goal**: Handle "Spy all members" and individual spy missions.
    *   **Needs**: logic to check spy coins, queue requests to avoid rate limits, parse spy reports (which come as messages/reports).

2.  **`MapService`** (Enhancement):
    *   **Goal**: "Alliance Map" and "Asset Tracking".
    *   **Needs**: Efficient scanning of specific coordinates (Alliance Member castles) rather than just full kingdom scans. Methods to identify asset types (Capital, Metro, etc.).

3.  **`DefenseService`**:
    *   **Goal**: "Defense Ratio" and "Commander Perks".
    *   **Needs**: logic to look up equipment IDs (XML/CDN data) to determine commander stats. Logic to categorize incoming units (Melee vs Range vs Tools).

### Database Integration
The "Member History" and "Online Lists (Past)" features require persistence.
*   **Current State**: `EmpireCore` is stateless (mostly).
*   **Requirement**: A `HistoryService` or integration with `storage/database.py` to save `AllianceMember` snapshots every X minutes.

### Event Handling
*   **Current**: `on_incoming_attack`, `on_chat_message`.
*   **Needed**: `on_member_update` (for tracking rank changes/birds), `on_kick` (for Anti-nuke).

---

## 6. Implementation Plan (Documentation Only)

1.  **Refine Protocol Models**: Ensure `AllianceMember` model captures "protection/bird" status.
2.  **Expand `AllianceService`**: Add event listeners for member changes (polling based diffing).
3.  **Create `SpyService`**: Wrapper around `csm` command.
4.  **Bot Layer (Dreambot)**: Will consume `EmpireCore` to provide the UI/Commands.
