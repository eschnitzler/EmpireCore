import json

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from empire_core.client.client import EmpireClient
from empire_core.console.app import Console
from empire_core.console.settings import Settings, load_settings, save_settings, settings_path


def test_settings_round_trip(tmp_path):
    path = tmp_path / "console" / "settings.json"
    saved = Settings(theme="light", zone="EmpireEx_3", column=0.3, input_rows=8, frames=0.4, filter=["gbd"], raw=True)
    save_settings(saved, path)
    assert load_settings(path) == saved


def test_a_missing_or_broken_file_gives_the_defaults(tmp_path):
    assert load_settings(tmp_path / "missing.json") == Settings()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert load_settings(broken) == Settings()


def test_values_out_of_range_or_unknown_are_dropped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "light", "column": 5, "colour": "red"}))
    assert load_settings(path) == Settings(theme="light")


def test_the_file_follows_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings_path() == tmp_path / "empire-console" / "settings.json"


def test_a_console_starts_from_settings_and_reports_its_own(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        settings = Settings(theme="light", column=0.3, input_rows=8, frames=0.4, filter=["gbd"], raw=True)
        console = Console(EmpireClient(username="u", password="p"), history=tmp_path / "h", settings=settings)
        assert console.theme == "light" and console.raw and console.frames.filter == {"gbd"}
        assert (console.sizes.column, console.sizes.input_rows, console.sizes.frames) == (0.3, 8, 0.4)
        console.execute_command(":theme dark")
        console.sizes.column = 0.6
        now = console.settings()
        assert now.theme == "dark" and now.column == 0.6 and now.zone == "EmpireEx_21" and now.filter == ["gbd"]
