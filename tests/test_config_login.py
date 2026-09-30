"""Login values in config: build number, ids, and the network.xml server list."""

import re

import pytest
import requests

from empire_core import config as config_module
from empire_core.config import (
    EmpireConfig,
    build_number,
    fetch_network_instances,
    generate_aid,
    generate_session_id,
    network_config_url,
    parse_network_instances,
)
from empire_core.exceptions import NetworkError


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


NETWORK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<network>
  <general><networkname>Example</networkname></general>
  <instances>
    <instance value="21">
      <server>ep-live-example-game.example.com</server>
      <port>443</port>
      <zone>EmpireEx_21</zone>
      <zoneId>21</zoneId>
      <instanceName>3</instanceName>
      <isInternational>1</isInternational>
      <defaultcountry>US</defaultcountry>
      <instanceLocaId>instance_int_3</instanceLocaId>
      <countries>["US","GB"]</countries>
    </instance>
    <instance value="1">
      <server>ep-live-other-game.example.com</server>
      <zone>EmpireEx</zone>
      <isInternational>0</isInternational>
      <countries>null</countries>
    </instance>
  </instances>
  <test-instances>
    <instance value="900"><server>test.example.com</server><zone>EmpireTest</zone></instance>
  </test-instances>
</network>
"""


class TestNetworkXml:
    """Parsed as NetworkXMLParser does (dll line 20254-20264)."""

    def test_instances(self):
        first, second = parse_network_instances(NETWORK_XML)
        assert first.instance_id == 21
        assert first.server == "ep-live-example-game.example.com"
        assert first.port == 443
        assert first.zone == "EmpireEx_21"
        assert first.zone_id == 21
        assert first.instance_number == 3
        assert first.is_international is True
        assert first.default_country == "US"
        assert first.instance_loca_id == "instance_int_3"
        assert first.countries == ["US", "GB"]
        assert second.port == 0
        assert second.is_international is False
        assert second.countries == []

    def test_test_instances_only_when_asked(self):
        assert [i.zone for i in parse_network_instances(NETWORK_XML, include_test=True)] == [
            "EmpireEx_21",
            "EmpireEx",
            "EmpireTest",
        ]

    def test_a_config_for_an_instance(self):
        config = EmpireConfig.for_instance(parse_network_instances(NETWORK_XML)[0], username="u")
        assert config.game_url == "wss://ep-live-example-game.example.com:443"
        assert config.default_zone == "EmpireEx_21"
        assert config.username == "u"

    @pytest.mark.parametrize("text", ["not xml", '<!DOCTYPE x [<!ENTITY a "b">]><network/>'])
    def test_bad_files_raise(self, text):
        with pytest.raises(ValueError):
            parse_network_instances(text)

    def test_fetch(self, monkeypatch):
        urls = []

        class Reply:
            text = NETWORK_XML

            def raise_for_status(self):
                pass

        def get(url, timeout):
            urls.append(url)
            return Reply()

        monkeypatch.setattr(config_module.requests, "get", get)
        assert len(fetch_network_instances(12, 1)) == 2
        assert urls == [network_config_url(12, 1)]
        assert urls[0] == "https://content.goodgamestudios.com/games-netconf/12/1.xml"

    def test_fetch_failure_is_a_network_error(self, monkeypatch):
        def get(url, timeout):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(config_module.requests, "get", get)
        with pytest.raises(NetworkError):
            fetch_network_instances(12, 1)


def test_network_config_url_host_parts_and_test_servers():
    # Client: LiveEnvironment.initPatterns (dll line 3894-3900).
    assert network_config_url(1, 2, cdn_sub_domain="cdn", domain="example.com") == (
        "https://cdn.example.com/games-netconf/1/2.xml"
    )
    assert network_config_url(1, 2, test_servers=True) == (
        "https://files.goodgamestudios.com/games-netconf-test/1/2.xml"
    )
