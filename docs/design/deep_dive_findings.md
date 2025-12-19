# Deep Dive Analysis of Private Repositories

**Date:** 2025-12-04
**Source:** `eschnitzler/websockets` (Private Repo)

## Overview

This repository contains advanced automation scripts for Goodgame Empire, specifically focusing on high-level botting tasks like automated attacking (`khan.py`), Berimond event farming (`beri.py`), and resource/tool management. The scripts utilize a direct WebSocket connection and construct raw protocol packets manually.

## 1. Attack System (`khan.py`, `utils/attack_setup.py`)

### Command: `cra` (Create Army Attack)
The repository reveals the detailed structure of the `cra` packet used for sending complex attacks with wave and flank configurations.

**Payload Structure:**
```json
{
  "SX": 1122, "SY": 229,       // Source X, Y
  "TX": 1115, "TY": 226,       // Target X, Y
  "KID": 0,                    // Kingdom ID
  "LID": 29,                   // Location ID (Target Castle ID)
  "WT": 0,                     // World Type
  "HBW": 1007,                 // (Unknown - likely "Has Barricade/Wall" or similar flag)
  "BPC": 0,                    // (Unknown)
  "ATT": 0,                    // Attack Type (0 = Normal, maybe others for capture/pillage)
  "AV": 0,                     // (Unknown)
  "LP": 1,                     // (Unknown - Loot Priority?)
  "FC": 0,                     // Fast Cast / Feather (Speed up)
  "PTT": 0,                    // (Unknown)
  "SD": 0,                     // Scheduled Date (Time of arrival?)
  "ICA": 0,                    // (Unknown)
  "CD": 99,                    // Cooldown/Check digit? (Hardcoded 99 in `khan.py`)
  "A": [                       // Army Waves (Array of Objects)
    {
      "L": {                   // Left Flank
        "T": [[168, 5], [143, 10]],  // Tools: [[ToolID, Count], ...]
        "U": [[214, 96], [-1, 0]]    // Units: [[UnitID, Count], ...]
      },
      "R": { ... },            // Right Flank (same structure)
      "M": { ... }             // Middle Flank (same structure)
    },
    // ... Additional waves
  ],
  "BKS": [],                   // (Unknown - possibly "Back Support" or hero?)
  "AST": [-1, -1, -1],         // (Unknown - Attack Strategy/Tactics?)
  "RW": [[215, 2000], ...]     // (Unknown - Rewards/Loot capacity check?)
}
```

**Key Findings:**
*   **Waves:** The `A` field is a list, supporting multiple waves.
*   **Flanks:** Each wave has `L` (Left), `R` (Right), `M` (Middle) sections.
*   **Slots:** Units (`U`) and Tools (`T`) are arrays of arrays `[ID, Count]`. Empty slots are represented as `[-1, 0]`.
*   **Hardcoded Values:** `CD: 99` is consistently used.

### Helper Functions (`schunked` in `attack_setup.py`)
*   Logic exists to chunk tools and units into slots (likely 2 slots for tools, more for units).
*   Fills empty slots with `[-1, 0]`.

## 2. Defense Management (`khan.py`)

### Command: `dfw` (Defense Wall)
Sets up units and tools on the castle wall.

**Payload:**
```json
{
  "CX": 1122, "CY": 229,       // Castle Coordinates
  "AID": 6273103,              // Area ID / Castle ID
  "L": {                       // Left Flank
    "S": [[624, 99], ...],     // Slots (Tools): [[ToolID, Count], ...]
    "UP": 49,                  // Units Placed? (Percentage/Ratio?)
    "UC": 0                    // Unit Count?
  },
  "M": { ... },                // Middle Flank
  "R": { ... }                 // Right Flank
}
```

### Command: `dfm` (Defense Moat)
Sets up tools in the moat.

**Payload:**
```json
{
  "CX": 1122, "CY": 229,
  "AID": 6273103,
  "LS": [[625, 99]],           // Left Slots
  "MS": [[625, 99]],           // Middle Slots
  "RS": [[625, 99]]            // Right Slots
}
```

### Command: `dfk` (Defense Keep?)
Found in commented-out code in `khan.py`.
```json
{
  "CX": 170, "CY": 376,
  "AID": 9940961,
  "MAUCT": 0,                  // (Unknown)
  "S": [[108, 98], ...],       // Slots?
  "STS": [[-1, 0], ...]        // (Unknown)
}
```

## 3. Donation & Recruitment

### Command: `sbp` (Start Build/Production?)
Used for donating resources or possibly starting unit production (the function name is `recruit` but uses `sbp` which often relates to alliance/resource actions).

**Payload (Donation?):**
```json
{
  "PID": 474,                  // Project ID?
  "BT": 0,
  "TID": 49,                   // Task ID?
  "AMT": 120,                  // Amount
  "KID": 0,
  "AID": -1,
  ...
}
```

### Command: `ado` (Alliance Donation)
Explicit alliance donation command.

**Payload:**
```json
{
  "AID": 2339796,              // Alliance ID
  "KID": 0,
  "RV": {                      // Resource Values
    "O": 225000,               // Wood (Oil?) - Likely Wood
    "G": 225000,               // Stone (Glass?) - Likely Stone
    "C": 225000                // Food (Crop?) - Likely Food
  }
}
```

## 4. Map Data & Logic

*   **Notes (`notes.txt`):** Contains analysis of targets (level, hits, defenses) based on map object IDs (e.g., `[25, 717, 555...]`).
*   **Troops (`troops.json`):** Huge database of unit IDs mapping to names (e.g., `"Militia": 620`, `"SamuraiAttackerMelee": 34`). This is a valuable resource for `UnitType` enums.
*   **Logic:** `khan.py` iterates through a list of cached `coms` (Commanders/Targets?) and sends attacks (`cra`) with a sleep delay.

## 5. Potential New Features for EmpireCore

Based on this deep dive, `EmpireCore` can be expanded with:

1.  **Advanced Combat:**
    *   Implement `send_detailed_attack` using the `cra` packet structure.
    *   Support multiple waves and flank configurations.
    *   Add "tools" support to attacks.

2.  **Defense Automation:**
    *   Implement `set_wall_defense` (`dfw`) and `set_moat_defense` (`dfm`).
    *   Create a `DefenseManager` to auto-equip best defensive tools.

3.  **Alliance Contributions:**
    *   Implement `donate_to_alliance` (`ado`).

4.  **Unit Database:**
    *   Expand `empire_core.utils.enums.UnitType` with the extensive ID list from `troops.json`.

5.  **Event Farming:**
    *   The presence of `beri_bot` suggests logic for finding and attacking Berimond targets specifically. This likely involves filtering map objects by specific IDs found in `notes.txt`.
