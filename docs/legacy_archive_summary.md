# Legacy Archive Summary

This document summarizes the contents of the `archive/` directory which was cleaned up on December 18, 2025. These files represented the initial exploration, reverse engineering, and prototype phases of the EmpireCore project.

## 1. Legacy Codebase (`private_websockets_repo/`)
This directory contained the original, script-based implementation of the automation logic before it was refactored into the modular `src/empire_core` library.
- **Bots:** Specific bot implementations (`beri_bot`, `mads_bot`).
- **Core Logic:** Monolithic scripts like `beri.py`, `mads.py`.
- **Data:** hardcoded lists of coordinates, troops, and profile data.

## 2. Analysis & Reverse Engineering Tools
Scripts used to understand the game protocol and data structures.
- `analyze_packets.py`: Tool for inspecting raw packet dumps.
- `analyze_dcl.py`: Analyzer for the "Detail Castle" (`dcl`) packet response.
- `deep_explore.py` / `interactive_explorer.py`: REPL-style tools for probing the game server.
- `explore_library.py`: Script to introspect the python environment/library.

## 3. Ad-hoc Tests
Prototype tests used before the establishment of the `tests/` directory and `pytest` suite.
- `test_actions_safe.py`, `test_real_actions.py`: Prototypes for `src/empire_core/client/actions.py`.
- `test_movements.py`, `test_movements2.py`: Early implementations of movement tracking.
- `test_handshake_manual.py`: Verification of the login sequence.
- `test_state_capture.py`: Testing state population from server responses.
- `test_full_attack.py`, `test_quick_action.py`: Functional tests for specific game actions.

## 4. Session Notes & Findings
Documentation generated during the development process.
- `PROTOCOL_FINDINGS.md`, `protocol_notes.md`: Detailed notes on the SFS/SmartFoxServer protocol quirks.
- `REFACTORING_REPORT.md`: Notes on the transition from scripts to library.
- `PROJECT_STRUCTURE.md`: Early architectural plans.
- `SESSION_NOTES.md`, `SESSION_SUMMARY.md`: Logs of previous development sessions.
- `DEV_CONTEXT.md`, `HANDOFF.md`: Context files for developer handovers.

*This archive was deleted to maintain a clean project root, with `src/empire_core` serving as the single source of truth.*
