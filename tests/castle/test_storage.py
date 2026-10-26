"""The decoration storage: sin reads it, mbs marks it seen, sob, sds and pio change it; and districts (mde, rde)."""

from __future__ import annotations

from typing import Any, cast

import pytest

from empire_core.castle import (
    DecorationStorageResponse,
    MarkStorageSeenRequest,
    MoveToDistrictRequest,
    PlaceStoredDecorationRequest,
    RemoveFromDistrictRequest,
    SelectCastleResponse,
    SellStoredDecorationRequest,
    ShowInventoryRequest,
    StoreBuildingRequest,
)
from empire_core.enums import DecorationStorageId, Kingdom
from empire_core.exceptions import CommandError
from empire_core.gamedata import Building, TreasureMapId
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

# DecoStorageVO.parseSIN: RD [wod, amount, new], CD [wod, custom id, value, new], UD [wod, unique id, fusion xp, new]
MAIN = {"SID": 1, "RD": [[300, 3, 1]], "CD": [[301, 55, 20, 1]], "UD": [[302, 77, 40, 0]]}
ROW = [300, 9, 4, 6, 0, 0, 0, 100, 100, 100, 0, 0, 0, 0, 0]


class TestModels:
    def test_a_storage_list_reads_each_kind_of_decoration(self):
        reply = parse_response("sin", [MAIN, {"SID": 10}, {"SID": "23"}, {"SID": 99}])
        assert isinstance(reply, DecorationStorageResponse)
        main, kingdom, season_map, unknown = reply.storages
        assert main.storage_id is DecorationStorageId.GLOBAL
        assert kingdom.storage_id is Kingdom.BERIMOND
        assert season_map.storage_id is TreasureMapId.UNDERWORLD_NORMAL
        assert unknown.storage_id == 99
        (regular,) = main.decorations
        assert (regular.wod_id, regular.amount, regular.new_amount) == (Building(300), 3, 1)
        (custom,) = main.custom_decorations
        assert (custom.custom_id, custom.value, custom.is_new) == (55, 20, True)
        (unique,) = main.unique_decorations
        assert (unique.unique_id, unique.fusion_xp, unique.is_new) == (77, 40, False)

    def test_the_inventory_read_has_no_parameter(self):
        assert ShowInventoryRequest().to_packet() == "%xt%EmpireEx_21%sin%-1%"

    def test_requests_send_the_client_keys(self):
        assert MarkStorageSeenRequest(storage_id=2).to_payload() == {"SID": 2}
        assert MarkStorageSeenRequest(storage_id=TreasureMapId.THORNKING_NORMAL).to_payload() == {"SID": 21}
        assert StoreBuildingRequest(object_id=9).to_payload() == {"OID": 9}
        sell = SellStoredDecorationRequest(wod_id=300, amount=2)
        assert sell.to_payload() == {"WID": 300, "AMT": 2, "UID": -1} and sell.wod_id is Building.DECO_FLAGPOLE_L1
        assert PlaceStoredDecorationRequest(decoration_id=55, x=4, y=6, rotation=1).to_payload() == {
            "COID": 55,
            "X": 4,
            "Y": 6,
            "R": 1,
        }
        assert MoveToDistrictRequest(object_id=9, district_object_id=3).to_payload() == {"OID": 9, "DOID": 3}
        assert RemoveFromDistrictRequest(object_id=9, x=1, y=2).to_payload() == {"OID": 9, "X": 1, "Y": 2, "R": 0}

    def test_a_join_reads_its_storages(self):
        reply = SelectCastleResponse.model_validate({"KID": 0, "sin": [MAIN]})
        assert [storage.storage_id for storage in reply.storages] == [DecorationStorageId.GLOBAL]


class TestState:
    def test_each_storage_named_replaces_the_one_before(self):
        state = GameState()
        state.update_from_packet("sin", cast(Any, [MAIN, {"SID": 2, "RD": [[300, 1, 0]]}]))
        state.update_from_packet("sob", {"OID": 9, "sin": [{"SID": 2, "RD": [[300, 2, 1]]}]})

        storages = state.get_decoration_storages()
        assert storages[1].decorations[0].amount == 3
        assert storages[2].decorations[0].amount == 2
        assert state.get_last_packet_time("sin") is not None

    @pytest.mark.parametrize("command", ["ebu", "ebe", "pio", "sds", "sbp", "jaa"])
    def test_the_replies_that_carry_a_storage_update_it(self, command: str):
        state = GameState()
        state.update_from_packet(command, {"sin": [MAIN]})
        assert set(state.get_decoration_storages()) == {DecorationStorageId.GLOBAL}

    def test_a_refused_reply_changes_nothing(self):
        state = GameState()
        state.update_from_packet("sds", {"sin": [MAIN]}, error_code=1)
        state.update_from_packet("sin", cast(Any, [MAIN]), error_code=1)
        assert state.get_decoration_storages() == {}


class TestService:
    def test_get_decoration_storages_reads_and_keeps_the_storages(self):
        client = make_client({"sin": xt_packet("sin", [MAIN])}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet

        storages = client.castle.get_decoration_storages()

        assert conn(client).request_frames[0].endswith("%sin%-1%")
        assert [storage.storage_id for storage in storages] == [DecorationStorageId.GLOBAL]
        assert set(client.castle.decoration_storages) == {DecorationStorageId.GLOBAL}

    def test_store_sell_and_place(self):
        client = make_client(
            {
                "sob": xt_packet("sob", {"OID": 9, "sin": [MAIN]}),
                "sds": xt_packet("sds", {"gcu": {"C1": 500, "C2": 10}, "sin": [MAIN]}),
                "pio": xt_packet("pio", {"NO": ROW, "sin": [MAIN]}),
            }
        )

        stored = client.castle.store_decoration(9)
        sold = client.castle.sell_stored_decoration(Building(300), 2)
        placed = client.castle.place_stored_decoration(55, 4, 6)
        client.castle.mark_storage_seen(DecorationStorageId.GLOBAL)

        assert conn(client).request_payloads == [
            ("sob", {"OID": 9}),
            ("sds", {"WID": 300, "AMT": 2, "UID": -1}),
            ("pio", {"COID": 55, "X": 4, "Y": 6, "R": 0}),
            ("mbs", {"SID": 1}),
        ]
        assert stored.object_id == 9 and stored.storages[0].storage_id is DecorationStorageId.GLOBAL
        assert sold.currencies is not None
        assert placed.building is not None and placed.building.object_id == 9

    def test_selling_nothing_sends_nothing(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.castle.sell_stored_decoration(Building.DECO_FLAGPOLE_L1, 0)
        assert conn(client).request_payloads == []

    def test_district_moves_return_the_row(self):
        moved: dict[str, Any] = {"MO": ROW}
        client = make_client({"mde": xt_packet("mde", moved), "rde": xt_packet("rde", moved)})

        into = client.castle.move_to_district(9, 3)
        out = client.castle.remove_from_district(9, 4, 6, 1)

        assert conn(client).request_payloads == [
            ("mde", {"OID": 9, "DOID": 3}),
            ("rde", {"OID": 9, "X": 4, "Y": 6, "R": 1}),
        ]
        assert into is not None and out is not None and out.x == 4

    def test_a_refused_store_raises(self):
        client = make_client({"sob": xt_packet("sob", error_code=21)})
        with pytest.raises(CommandError):
            client.castle.store_decoration(9)
