# Modernization & Packaging Roadmap

## Phase 1: Project Metadata & `uv` Migration
- [ ] Audit current `pyproject.toml`
- [ ] Migrate dependencies from `requirements.txt` to `pyproject.toml` (PEP 621)
- [ ] Remove `requirements.txt`
- [ ] Verify `uv` lockfile generation

## Phase 2: Code Quality & Hooks
- [ ] Configure `ruff` (Linter/Formatter) in `pyproject.toml`
- [ ] Configure `mypy` (Type Checking)
- [ ] Create `.pre-commit-config.yaml` (Ruff, Mypy, Conventional Commits)

## Phase 3: CLI Entry Point
- [ ] Add `typer` dependency
- [ ] Create `src/empire_core/cli.py` skeleton
- [ ] Register script entry point (`empire-cli`)

## Phase 4: Release Automation
- [ ] Configure `commitizen` for version bumping and changelogs
