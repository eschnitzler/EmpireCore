"""Login values in config: build number, ids, and the network.xml server list."""

import re

import pytest
import requests

from empire_core import config as config_module
from empire_core.config import (
    CLIENT_BASE_URL,
    EmpireConfig,
    build_number,
    fetch_client_version,
    fetch_network_instances,
    forget_client_version,
    generate_aid,
    generate_session_id,
    instance_for_zone,
    live_client_version,
    network_config_url,
    parse_network_instances,
)
from empire_core.exceptions import ClientVersionUnreadableError, NetworkError


@pytest.mark.parametrize(
    ("version", "build"),
    # Results of the client's own function (bundle line 10446), run in node.
    [("1.169.11", "1169011"), ("1.2.3", "1002003"), ("1.169.11-beta", "1169011")],
)
def test_build_number(version, build):
    assert build_number(version) == build


INDEX_HTML = '<script src="vendor.bundle.4aee.js"></script><script src="CacheBreaker.bundle.de68e795.js"></script>'
CACHE_BREAKER = '858:function(e){e.exports={name:"TranspilationEmpire",version:"1.171.3",description:"Transpiled"}}'


def serve_client(monkeypatch, pages):
    """Answer requests.get from ``pages`` by URL; returns the URLs asked for."""
    urls = []

    class Reply:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

    def get(url, timeout):
        urls.append(url)
        if url not in pages:
            raise requests.HTTPError(f"404 {url}")
        return Reply(pages[url])

    monkeypatch.setattr(config_module.requests, "get", get)
    return urls


class TestClientVersion:
    PAGES = {
        f"{CLIENT_BASE_URL}/index.html": INDEX_HTML,
        f"{CLIENT_BASE_URL}/CacheBreaker.bundle.de68e795.js": CACHE_BREAKER,
    }

    def test_the_cache_breaker_bundle_names_the_version(self, monkeypatch):
        urls = serve_client(monkeypatch, self.PAGES)
        assert fetch_client_version() == "1.171.3"
        assert urls == list(self.PAGES)

    def test_a_page_without_the_bundle_is_a_value_error(self, monkeypatch):
        serve_client(monkeypatch, {f"{CLIENT_BASE_URL}/index.html": "<html></html>"})
        with pytest.raises(ClientVersionUnreadableError, match="CacheBreaker"):
            fetch_client_version()

    def test_a_bundle_without_the_version_is_a_value_error(self, monkeypatch):
        serve_client(monkeypatch, {**self.PAGES, f"{CLIENT_BASE_URL}/CacheBreaker.bundle.de68e795.js": "x"})
        with pytest.raises(ClientVersionUnreadableError, match="TranspilationEmpire"):
            fetch_client_version()

    def test_a_download_failure_is_a_network_error(self, monkeypatch):
        serve_client(monkeypatch, {})
        with pytest.raises(NetworkError):
            fetch_client_version()

    def test_the_live_version_is_read_once_until_forgotten(self, monkeypatch):
        forget_client_version()
        urls = serve_client(monkeypatch, self.PAGES)
        assert live_client_version() == "1.171.3"
        assert live_client_version() == "1.171.3"
        assert len(urls) == 2
        forget_client_version()
        assert live_client_version() == "1.171.3"
        assert len(urls) == 4

    def test_the_config_sends_the_live_version_unless_pinned(self):
        assert EmpireConfig().client_version is None
        assert EmpireConfig(client_version="1.170.2").client_version == "1.170.2"


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
        assert urls[0] == "https://files-ak.goodgamestudios.com/games-netconf/12/1.xml"

    def test_fetch_falls_back_to_the_fallback_cdn(self, monkeypatch):
        # Client: cdnSubDomain is "media" once _useFallbackCDN is set (dll line 34406)
        urls = []

        class Reply:
            text = NETWORK_XML

            def raise_for_status(self):
                pass

        def get(url, timeout):
            urls.append(url)
            if "files-ak" in url:
                raise requests.ConnectionError("down")
            return Reply()

        monkeypatch.setattr(config_module.requests, "get", get)
        assert len(fetch_network_instances(12, 1)) == 2
        assert urls == [
            "https://files-ak.goodgamestudios.com/games-netconf/12/1.xml",
            "https://media.goodgamestudios.com/games-netconf/12/1.xml",
        ]

    def test_a_zone_names_its_server(self, monkeypatch):
        monkeypatch.setattr(config_module, "_instances", {})
        monkeypatch.setattr(config_module, "fetch_network_instances", lambda g, n: parse_network_instances(NETWORK_XML))
        assert instance_for_zone("EmpireEx").server == "ep-live-other-game.example.com"
        with pytest.raises(ValueError, match="EmpireEx_99"):
            instance_for_zone("EmpireEx_99")

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
