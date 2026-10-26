"""Season event maps: entering the camp (jea), taking a prebuilt camp (csc) and the msm request."""

import pytest

from empire_core.enums import KingdomTransferType
from empire_core.events import MinuteSkipSeasonTransferRequest, SelectSeasonCampRequest
from empire_core.exceptions import CommandError, EventNotRunningError
from empire_core.gamedata import Currency, PrebuiltCastle
from empire_core.gamedata.ids.events import Event
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, with_prebuilt_castles, xt_packet


def season_client(script=None):
    client = make_client(script or {}, state=GameState())
    client._on_packet(xt_packet("sei", {"E": [{"EID": 2, "RS": 600, "UL": {"MID": 21, "UL": 1}}]}))
    return client


def test_join_season_camp_sends_the_running_events_map():
    client = season_client()
    client.events.join_season_camp(Event.THORN_KING)
    assert conn(client).request_payloads == [("jea", {"MID": 21})]


def test_joining_a_season_event_that_is_not_running_raises():
    client = season_client()
    with pytest.raises(EventNotRunningError):
        client.events.join_season_camp(Event.UNDERWORLD)
    assert conn(client).request_payloads == []


def test_a_refused_join_raises():
    client = season_client({"jea": xt_packet("jea", error_code=1)})
    with pytest.raises(CommandError):
        client.events.join_season_camp(Event.THORN_KING)


def test_select_season_camp_keeps_the_client_key_order_and_int_flags():
    payload = SelectSeasonCampRequest(
        prebuilt_camp_id=PrebuiltCastle.THORN_KING_SIMPLE_CAMP, ruby_camp=True, space_id=21
    ).to_payload()
    assert list(payload) == ["ID", "PWR", "OC2", "SID"]
    assert payload == {"ID": 13, "PWR": 0, "OC2": 1, "SID": 21}


def test_unlock_season_camp_sends_its_first_space_and_its_ruby_consent():
    client = with_prebuilt_castles(make_client())
    client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP)
    with pytest.raises(ValueError, match="29000 rubies"):
        client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_WARLORDS_CAMP)
    client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_WARLORDS_CAMP, spend_rubies=True)
    client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP, spend_rubies=True)
    client.events.unlock_season_camp(PrebuiltCastle.BLADE_COAST_SIMPLE_CAMP)
    assert [payload for _, payload in conn(client).request_payloads] == [
        {"ID": 22, "PWR": 0, "OC2": 0, "SID": 23},
        {"ID": 24, "PWR": 0, "OC2": 1, "SID": 23},
        {"ID": 22, "PWR": 1, "OC2": 0, "SID": 23},
        {"ID": 28, "PWR": 0, "OC2": 0, "SID": 22},
    ]


def test_ruby_price_buys_a_camp_at_its_ruby_price():
    client = with_prebuilt_castles(make_client())
    with pytest.raises(ValueError, match="10000 rubies"):
        client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP, ruby_price=True)
    client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP, ruby_price=True, spend_rubies=True)
    with pytest.raises(ValueError, match="no ruby price"):
        client.events.unlock_season_camp(PrebuiltCastle.BLADE_COAST_SIMPLE_CAMP, ruby_price=True, spend_rubies=True)
    assert conn(client).request_payloads == [("csc", {"ID": 22, "PWR": 0, "OC2": 1, "SID": 23})]


@pytest.mark.parametrize("castle", [PrebuiltCastle.ICE_SIMPLE_CASTLE, PrebuiltCastle.OUTER_REALMS_ROYAL_KEEP_32])
def test_a_castle_that_starts_a_kingdom_or_server_is_no_season_camp(castle):
    client = with_prebuilt_castles(make_client())
    with pytest.raises(ValueError, match="no season camp"):
        client.events.unlock_season_camp(castle)
    assert conn(client).request_payloads == []


def test_a_refused_season_camp_raises():
    client = with_prebuilt_castles(make_client({"csc": xt_packet("csc", error_code=1)}))
    with pytest.raises(CommandError):
        client.events.unlock_season_camp(PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP)


def test_minute_skip_sends_map_type_then_skip_key():
    request = MinuteSkipSeasonTransferRequest(
        map_id=21, transfer_type=KingdomTransferType.GOODS, minute_skip=Currency.SKIP_1_MINUTE
    )
    payload = request.to_payload()
    assert list(payload) == ["MID", "TT", "MST"]
    assert payload == {"MID": 21, "TT": 2, "MST": "MS1"}


def test_an_event_with_no_map_is_refused():
    client = make_client(state=GameState())
    client._on_packet(xt_packet("sei", {"E": [{"EID": 3, "RS": 600, "UL": 1}]}))
    with pytest.raises(ValueError, match="no season event"):
        client.events.join_season_camp(Event.BATTLE_FOR_BERIMOND)
