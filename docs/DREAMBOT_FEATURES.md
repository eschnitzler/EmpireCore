# DreamBot Feature Roadmap (Based on BB.pdf)

This document outlines the features to be implemented in `EmpireCore` to support the future "DreamBot". The goal is to build robust, low-level API capabilities in `EmpireCore` that `DreamBot` can leverage for high-level automation and Discord integration.

## 1. Attack Warnings & Defense
**Goal**: Real-time detection and notification of incoming attacks.

| Feature | Details | EmpireCore Implementation |
|---------|---------|---------------------------|
| **Attack Detection** | Detect attacks on Main, Outposts, Labs, Monuments, Storm Islands. | `Protocol`: Decode `lli` (Login Info) & update packets.<br>`Service`: `AttackService` to monitor incoming movement list. |
| **Attack Analysis** | Extract: Kingdom color, Commander perks, Defense ratio (<50% warning), Soldier count. | `Models`: Enhance `attack.py` models to parse commander equipment and unit counts.<br>`Utils`: Helper to calculate defense/offense ratios. |
| **Support/Capture** | Distinguish between normal attacks, captures, and support. | `Protocol`: Check `MT` (Movement Type) field in packets. |
| **Outer Realms** | Support for Outer Realms events. | `Account`: Support switching to OR instance/world ID. |

## 2. Alliance Management & Tracking
**Goal**: Monitor alliance status, members, and assets.

| Feature | Details | EmpireCore Implementation |
|---------|---------|---------------------------|
| **Member Tracking** | Track: Birds (protection), Ranks, Name changes, Join/Leave events. | `Service`: `AllianceService` to poll member list periodically.<br>`State`: Persist member snapshots to DB for history/diffing. |
| **Asset Tracking** | Track: Capitals, Metropolises, KTs, Towers. | `Service`: `MapService` to scan alliance assets.<br>`Models`: Ensure `map.py` covers all asset types. |
| **Online Lists** | Snapshot of who is online (up to 2 days history). | `Service`: `AllianceService` to check "online status" bit in member list.<br>`DB`: Time-series storage for online status. |
| **Alliance Map** | Visual map of player locations. | `Service`: `MapService` to fetch coordinates for all members.<br>`Bot`: Visualization logic (Dreambot side). |
| **Spying** | "Spy all non-birded members". | `Service`: `SpyService` with queueing logic.<br>`Automation`: Batch `csm` (Create Spy Mission) commands with delays to avoid bans. |

## 3. Communication (Chat)
**Goal**: Bidirectional sync between Game and Discord.

| Feature | Details | EmpireCore Implementation |
|---------|---------|---------------------------|
| **Chat Sync** | Relay messages Game <-> Discord. | `Protocol`: `acm` (Alliance Chat Message) packet handling.<br>`Service`: `ChatService` with `on_message` callbacks. |
| **Ping Support** | `@user` in game -> Discord ping. | `Service`: Parsing logic in `ChatService` to identify mentions. |
| **Security** | "Dot spam" handling (hiding/backing up chat). | `Service`: Detection of spam patterns (e.g., messages with only "."); exposed via API. |

## 4. Automation & Utilities
**Goal**: Quality of Life features.

| Feature | Details | EmpireCore Implementation |
|---------|---------|---------------------------|
| **Auto Help** | Automatically click "Help Alliance". | `Service`: `AllianceService` auto-trigger `help_alliance` on login/timer. |
| **Anti-Nuke** | Protect against unauthorized kicks. | `Service`: Monitor `kick` events; if unauthorized, trigger counter-action (demotion) - *High Risk*. |
| **Event Boosts** | Start alliance boosts remotely. | `Service`: API to trigger alliance boost actions. |
| **User Admin** | Verify users, manage permissions. | `Service`: `VerificationService` (generate tokens/codes in game profile for Discord verification). |

## 5. Technical Implementation Strategy

### Phase 1: Core API Expansion (EmpireCore)
Focus on the `src/empire_core` directory.
1.  **Protocol Layer (`src/empire_core/protocol/`)**:
    *   Verify all packet definitions for Attack (`cra`, `lli`), Chat (`acm`), and Alliance (`gai`, `gmi`) are complete.
    *   Add missing fields for Commander Equipment and Unit details.
2.  **Service Layer (`src/empire_core/services/`)**:
    *   **`AttackService`**: Create a specialized service that maintains a live list of incoming attacks.
    *   **`ChatService`**: Implement robust polling or event-based chat listening.
    *   **`AllianceService`**: Add methods for `get_all_members_detailed()`, `get_assets()`.
3.  **State Management (`src/empire_core/state/`)**:
    *   Ensure `WorldState` or `AllianceState` can store historical data (needed for "Online Lists" and "Member History").

### Phase 2: Automation Primitives
1.  **`SpyManager`**: A class to handle batch spying (rate limiting, coin checks).
2.  **`MapScanner`**: Optimized scanning for generating alliance maps.

### Phase 3: Dreambot Integration
*   Dreambot will import `EmpireCore`.
*   Dreambot will handle Discord API interactions.
*   Dreambot will call `empire_client.attack_service.on_attack(callback)` to trigger Discord alerts.

---
*Reference: Based on `BB.pdf` feature set.*
