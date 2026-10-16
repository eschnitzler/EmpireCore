import pytest


@pytest.fixture(autouse=True)
def config_home(monkeypatch, tmp_path):
    """Keep every console test away from the real settings file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config"
