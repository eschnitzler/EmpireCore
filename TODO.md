# Modernization & Packaging Roadmap

## Phase 1: Project Metadata & `uv` Migration
- [x] Audit current `pyproject.toml`
- [x] Migrate dependencies from `requirements.txt` to `pyproject.toml` (PEP 621)
- [x] Remove `requirements.txt`
- [x] Verify `uv` lockfile generation

## Phase 2: Code Quality & Hooks
- [x] Configure `ruff` (Linter/Formatter) in `pyproject.toml`
- [x] Configure `mypy` (Type Checking)
- [x] Create `.pre-commit-config.yaml` (Ruff, Mypy, Conventional Commits)

## Phase 3: CLI Entry Point
- [x] Add `typer` dependency
- [x] Create `src/empire_core/cli.py` skeleton
- [x] Register script entry point (`empire`)

## Phase 4: Storage & Persistence
- [x] Integrate `SQLModel` for ORM capabilities
- [x] Implement `aiosqlite` for non-blocking DB access
- [x] Persistent world map caching

## Phase 5: Release Automation (Ready for CI)
- [x] Configure `conventional-pre-commit` for commit validation
- [ ] Setup GitHub Actions for automated publishing