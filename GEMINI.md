# EmpireCore - AI Context File

## Project Overview
**EmpireCore** is a modern, async Python library for automating the browser game *Goodgame Empire*.
It provides a high-level, type-safe API for interacting with the game server via WebSocket (SmartFoxServer protocol).

---

## Technical Stack & Tooling
*   **Package Manager**: `uv` (standard for this repo).
*   **Build System**: `hatchling` (PEP 621).
*   **Linter/Formatter**: `ruff`.
*   **Type Checker**: `mypy`.
*   **Git Hooks**: `pre-commit` (configured for Ruff, Mypy, and Conventional Commits).

---

## Core Architecture

### 1. Account System (`empire_core.accounts`)
The entry point for all automation.
*   **`AccountRegistry` (`accounts`)**: Singleton that loads credentials from `accounts.json`.
*   **`Account`**: Represents a game account. Use `account.get_client()` to start.

### 2. The Client (`empire_core.client`)
*   **Composition over Inheritance**: Features are exposed via composed services.
    *   `client.quests`, `client.reports`, `client.alliance`, `client.chat`, `client.defense`.

### 3. State Management (`empire_core.state`)
*   **`GameState`**: The source of truth. Updated automatically by incoming packets.
*   **Models**: Pydantic v2 models for type safety.

---

## Development Guidelines

1.  **Conventional Commits**: All commits must follow the `feat:`, `fix:`, `refactor:` pattern.
2.  **Type Safety**: `mypy` must pass with zero errors. Always use type hints.
3.  **No God Objects**: Keep `EmpireClient` lean. Add logic to Services or Managers.
4.  **CLI first**: New high-level status or diagnostic features should be added to `cli.py`.

## Essential Commands
```bash
uv sync --extra dev      # Sync all dependencies
uv run empire status     # CLI check
uv run pytest            # Run tests
uv run pre-commit run --all-files # Final check before commit
```