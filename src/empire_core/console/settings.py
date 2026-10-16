"""What the console remembers between runs: its layout, theme, frame filter and world. Never credentials."""

import json
import os
from pathlib import Path

from pydantic import Field, ValidationError

from empire_core.console.theme import ThemeName
from empire_core.protocol.base import EmpireModel


class Settings(EmpireModel):
    theme: ThemeName = Field(default="dark", description="The colour theme")
    zone: str | None = Field(default=None, description="The world to log in to; US1 when None")
    column: float = Field(default=0.5, ge=0.2, le=0.8, description="The code column's share of the width")
    input_rows: int = Field(default=5, ge=1, le=40, description="Lines of the input")
    frames: float = Field(default=0.55, ge=0.15, le=0.85, description="The frame list's share of its column")
    filter: list[str] = Field(default_factory=list, description="Commands the frame list shows; all when empty")
    raw: bool = Field(default=False, description="Whether the detail pane shows the raw payload")


def settings_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "empire-console" / "settings.json"


def load_settings(path: Path) -> Settings:
    """The saved settings; any value missing, unknown or out of range takes its default instead."""
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(saved, dict):
        return Settings()
    kept = {}
    for name in Settings.model_fields:
        if name in saved:
            try:
                Settings.model_validate({name: saved[name]})
            except ValidationError:
                continue
            kept[name] = saved[name]
    return Settings.model_validate(kept)


def save_settings(settings: Settings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".tmp")
    partial.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    partial.replace(path)
