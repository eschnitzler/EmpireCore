import pytest

from empire_core.config import EmpireConfig, NetworkInstance
from empire_core.console import app
from empire_core.console.app import credentials, run, zone_config


def instance(zone: str, server: str, country: str, loca: str = "") -> NetworkInstance:
    return NetworkInstance(
        instance_id=1,
        server=server,
        port=443,
        zone=zone,
        zone_id=1,
        instance_number=1,
        is_international=False,
        is_favorite=False,
        default_country="default",
        instance_loca_id=loca or f"generic_country_{country}",
        countries=[country],
    )


FRANCE = instance("EmpireEx_3", "ep-live-fr1-game.example", "FR")
US = instance("EmpireEx_21", "ep-live-us1-game.example", "US")
PORTUGUESE = instance("EmpireEx_6", "ep-live-pt1-game.example", "PT", loca="generic_language_pt")


def test_no_zone_means_us1_without_asking_the_server_list(monkeypatch):
    monkeypatch.setattr(app, "instance_for_zone", lambda zone: pytest.fail("fetched the server list"))
    config = zone_config(None)
    assert config.default_zone == "EmpireEx_21" and config.game_url == EmpireConfig().game_url


def test_a_zone_is_looked_up_in_the_server_list(monkeypatch):
    monkeypatch.setattr(app, "instance_for_zone", {"EmpireEx_3": FRANCE}.__getitem__)
    config = zone_config("EmpireEx_3")
    assert config.default_zone == "EmpireEx_3" and config.game_url == FRANCE.game_url


def test_an_unknown_zone_stops_before_anything_starts(monkeypatch, capsys):
    def unknown(zone):
        raise ValueError(f"No world {zone!r}")

    monkeypatch.setattr(app, "instance_for_zone", unknown)
    assert run(["--zone", "Nowhere", "--no-login"]) == 2
    assert "Nowhere" in capsys.readouterr().err


def test_list_zones_prints_every_world_and_marks_the_default(monkeypatch, capsys):
    monkeypatch.setattr(app, "fetch_network_instances", lambda game_id, network_id: [FRANCE, US, PORTUGUESE])
    assert run(["--list-zones"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert any("EmpireEx_3" in line and "FR" in line and FRANCE.server in line for line in lines)
    assert any("EmpireEx_21" in line and "*" in line for line in lines)
    assert not any("generic_" in line for line in lines)


def test_credentials_prompt_for_what_is_missing(monkeypatch):
    monkeypatch.delenv("GGE_PASSWORD", raising=False)
    asked: list[str] = []

    def ask(prompt):
        asked.append(prompt)
        return "someone"

    def ask_secret(prompt):
        asked.append(prompt)
        return "secret"

    assert credentials(None, ask=ask, ask_secret=ask_secret) == ("someone", "secret")
    assert asked[0].startswith("Username") and asked[1].startswith("Password")


def test_credentials_take_the_flag_and_environment(monkeypatch):
    monkeypatch.setenv("GGE_PASSWORD", "from-env")

    def never(prompt):
        pytest.fail(f"asked {prompt!r}")

    assert credentials("me", ask=never, ask_secret=never) == ("me", "from-env")


def test_keep_session_is_off_unless_asked(monkeypatch):
    built: list[bool] = []

    class Stop(Exception):
        pass

    def client(**kwargs):
        built.append(kwargs.get("keep_session", False))
        raise Stop

    monkeypatch.setattr(app, "EmpireClient", client)
    for argv in (["--no-login"], ["--no-login", "--keep-session"]):
        with pytest.raises(Stop):
            run(argv)
    assert built == [False, True]
