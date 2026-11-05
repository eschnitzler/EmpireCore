"""Session location is separate from the last joined area."""

import threading
from typing import Any

import pytest

from empire_core import SessionLocation
from empire_core.enums import MapItemType
from tests.state.state_helpers import login


def joined(owner=1001, occupier=-1, kind=MapItemType.CASTLE, explicit_owner=True):
    row = [int(kind), 10, 20, 42, owner, 1, 1, 1, 0, 0, "Castle", 0, 0, 0, 0, occupier, 0]
    area: dict[str, Any] = {"A": row}
    if explicit_owner:
        area["O"] = {"OID": owner}
    return {"KID": 0, "T": int(kind), "gca": area}


@pytest.mark.parametrize("command", ["gaa", "gtwara", "rst"])
def test_map_transitions_keep_the_joined_area(state, command):
    login(state, 1001)
    assert state.get_session_location() is None
    state.update_from_packet("jaa", joined())
    area = state.get_joined_area()
    assert state.get_session_location() is SessionLocation.ISO
    assert state.is_in_own_castle()
    state.update_from_packet(command, {})
    assert state.get_session_location() is SessionLocation.WORLDMAP
    assert state.is_on_map()
    assert not state.is_in_own_castle()
    assert state.get_joined_area() is area
    state.reset()
    assert state.get_session_location() is None


@pytest.mark.parametrize(
    "owner,occupier,own,spectated,occupied",
    [
        (1001, -1, True, False, False),
        (2002, -1, False, True, False),
        (1001, 2002, False, False, False),
        (2002, 1001, False, False, True),
        (1001, 0, True, False, False),
    ],
)
def test_outpost_ownership(state, owner, occupier, own, spectated, occupied):
    login(state, 1001)
    state.update_from_packet("jaa", joined(owner, occupier, MapItemType.OUTPOST))
    assert state.is_in_own_castle() is own
    assert state.is_in_spectated_castle() is spectated
    assert state.is_in_occupied_castle() is occupied


def test_non_outpost_uses_row_owner_when_owner_block_is_absent(state):
    login(state, 1001)
    state.update_from_packet("jaa", joined(explicit_owner=False))
    assert state.is_in_own_castle()


def test_explicit_owner_overrides_row(state):
    login(state, 1001)
    data = joined()
    data["gca"]["O"] = {"OID": 2002}
    state.update_from_packet("jaa", data)
    assert state.is_in_spectated_castle()


def test_unreadable_owner_does_not_claim_ownership(state, caplog):
    login(state, 1001)
    data = joined()
    data["gca"]["O"] = {"OID": {}}
    state.update_from_packet("jaa", data)
    assert not state.is_in_own_castle()
    assert "owner" in caplog.text


def test_location_reads_during_concurrent_joins(state):
    login(state, 1001)
    errors = []

    def write():
        try:
            for _ in range(100):
                state.update_from_packet("jaa", joined())
                state.update_from_packet("gaa", {})
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=write)
    thread.start()
    while thread.is_alive():
        assert state.get_session_location() in (None, SessionLocation.ISO, SessionLocation.WORLDMAP)
        assert isinstance(state.is_in_own_castle(), bool)
    thread.join()
    assert not errors


def test_leave_area_changes_location_only_after_successful_send(state):
    from unittest.mock import patch

    from empire_core.exceptions import ConnectionClosedError
    from tests.service_helpers import make_client

    login(state, 1001)
    state.update_from_packet("jaa", joined())
    client = make_client(state=state)
    with patch.object(client.connection, "send", side_effect=ConnectionClosedError("closed")):
        with pytest.raises(ConnectionClosedError):
            client.castle.leave_area()
    assert state.get_session_location() is SessionLocation.ISO
    client.castle.leave_area()
    assert state.get_session_location() is SessionLocation.KINGDOM_MAP
    assert state.is_on_map()


def test_failed_relocation_does_not_leave_castle(state):
    from empire_core.enums import GGEError

    login(state, 1001)
    state.update_from_packet("jaa", joined())
    state.update_from_packet("rst", {}, error_code=int(GGEError.NOT_ENOUGH_RUBIES))
    assert state.get_session_location() is SessionLocation.ISO


@pytest.mark.parametrize("intervening", ["reset", "join", "map", "disconnect", "new_session"])
def test_leave_does_not_overwrite_intervening_state(state, intervening):
    from unittest.mock import patch

    from tests.service_helpers import conn, make_client

    login(state, 1001)
    state.update_from_packet("jaa", joined())
    client = make_client(state=state)
    connection = conn(client)

    def during_send(_frame):
        if intervening == "reset":
            state.reset()
        elif intervening == "join":
            state.update_from_packet("jaa", joined(owner=2002))
        elif intervening == "map":
            state.update_from_packet("gaa", {})
        elif intervening == "disconnect":
            connection.connected = False
        else:
            connection.generation += 1

    with patch.object(connection, "send", side_effect=during_send):
        client.castle.leave_area()
    expected = {"reset": None, "map": SessionLocation.WORLDMAP}.get(intervening, SessionLocation.ISO)
    assert state.get_session_location() is expected


def test_leaving_advances_area_revision(state):
    from tests.service_helpers import make_client

    state.update_from_packet("jaa", joined())
    revision = state.area_revision
    make_client(state=state).castle.leave_area()
    assert state.area_revision > revision


@pytest.mark.parametrize("owner,occupier", [(1001, 2002), (2002, 1001)])
def test_unreadable_outpost_does_not_claim_to_be_unconquered(state, caplog, owner, occupier):
    login(state, 1001)
    payload = joined(owner=owner, occupier=occupier, kind=MapItemType.OUTPOST)
    payload["gca"]["A"][10] = {"unexpected": "name shape"}
    state.update_from_packet("jaa", payload)
    assert not state.is_in_own_castle()
    assert not state.is_in_occupied_castle()
    assert not state.is_in_spectated_castle()
    assert "map row" in caplog.text
