"""Login values in config: the build number and the ids the login sends."""

import re

import pytest

from empire_core import config as config_module
from empire_core.config import EmpireConfig, build_number, generate_aid, generate_session_id


@pytest.mark.parametrize(
    ("version", "build"),
    # Results of the client's own function (bundle line 10446), run in node.
    [("1.169.11", "1169011"), ("1.2.3", "1002003"), ("1.169.11-beta", "1169011")],
)
def test_build_number(version, build):
    assert build_number(version) == build


def test_config_build_number_follows_the_client_version():
    assert EmpireConfig().build_number == "1169011"
    assert EmpireConfig(client_version="1.170.2").build_number == "1170002"


def test_session_id_looks_like_the_clients():
    # (Math.random() * Number.MAX_VALUE).toFixed() gives e.g. "4.122952659252254e+307" in node.
    assert re.fullmatch(r"\d(\.\d+)?e\+30[0-8]", generate_session_id())


def test_session_id_below_1e21_is_a_whole_number(monkeypatch):
    monkeypatch.setattr(config_module._random, "random", lambda: 1e-300)
    assert generate_session_id() == str(round(1e-300 * 1.7976931348623157e308))


def test_aid_is_milliseconds_and_an_unpadded_number(monkeypatch):
    monkeypatch.setattr(config_module.time, "time", lambda: 1790728893.677)
    monkeypatch.setattr(config_module._random, "random", lambda: 0.0000001)
    assert generate_aid() == "17907288936770"
