"""The world map's size: the nfo push, the state that keeps it and client.map.map_size."""

import pytest

from empire_core.enums import Kingdom
from empire_core.exceptions import StateNotLoadedError
from empire_core.map.models.world import MapSize, ServerInfoResponse
from empire_core.protocol.base import get_response_model
from empire_core.state.manager import GameState
from tests.service_helpers import SERVER_INFO, logged_in_state, make_client

# Shape of a live nfo push
NFO = {"XML_E4K": "787.RC.03", "XML_EP": "787.03", "minNameSize": 3, "sectorCountY": 99, "sectorCountX": 99}


def test_nfo_parses_as_server_info():
    info = ServerInfoResponse.model_validate(NFO)
    assert get_response_model("nfo") is ServerInfoResponse
    assert (info.xml_version, info.min_name_size, info.sector_count_x, info.sector_count_y) == ("787.03", 3, 99, 99)


@pytest.mark.parametrize("kingdom", [Kingdom.GREEN, Kingdom.SANDS, Kingdom.ICE, Kingdom.FIRE, Kingdom.STORM])
def test_a_kingdom_is_as_many_sectors_as_nfo_names(kingdom):
    assert ServerInfoResponse.model_validate(NFO).map_size(kingdom) == MapSize(1287, 1287)


def test_berimond_has_its_fixed_size():
    assert ServerInfoResponse.model_validate(NFO).map_size(Kingdom.BERIMOND) == MapSize(2600, 130)


def test_state_reads_the_map_size_from_the_nfo_push():
    state = GameState()
    with pytest.raises(StateNotLoadedError):
        state.get_map_size(Kingdom.GREEN)
    state.update_from_packet("nfo", NFO)
    assert state.get_map_size(Kingdom.GREEN) == MapSize(1287, 1287)


def test_an_nfo_with_an_error_is_not_kept():
    state = GameState()
    state.update_from_packet("nfo", NFO, error_code=1)
    with pytest.raises(StateNotLoadedError):
        state.get_map_size(Kingdom.GREEN)


def test_a_reset_forgets_the_map_size():
    state = GameState()
    state.update_from_packet("nfo", NFO)
    state.reset()
    with pytest.raises(StateNotLoadedError):
        state.get_map_size(Kingdom.GREEN)


def test_client_map_map_size_reads_state():
    client = make_client(state=logged_in_state())
    sectors = SERVER_INFO["sectorCountX"]
    assert client.map.map_size(Kingdom.GREEN) == MapSize(sectors * 13, sectors * 13)
