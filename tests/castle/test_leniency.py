"""Reply blocks read as leniently as the client reads them: one bad value costs only itself."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.castle.models.actions import SelectCastleResponse
from empire_core.castle.models.buildings import BuildResponse, CollectExtensionGiftResponse, SellBuildingResponse
from empire_core.castle.models.details import CastleProductionArea, GetDetailedCastleResponse
from empire_core.castle.models.objects import ConstructionList
from empire_core.enums import Kingdom
from tests.service_helpers import conn, make_client, xt_packet


class TestProductionAreaLeniency:
    @pytest.mark.parametrize(
        ("block", "field", "expected"),
        [
            # AreaDataCommonInfo.parseGPA: e.DFC / 10, so null reads as 0
            ({"DFC": None}, "food_consumption_delta", 0.0),
            # e.MP ? e.MP : 0
            ({"MP": ""}, "metropolis_food_bonus", 0.0),
            ({"MP": 3}, "metropolis_food_bonus", 3.0),
            # AreaDataUpdater.parseGPA hands RS1 on as sent
            ({"RS1": None}, "barracks_speed", 0.0),
            ({"RSH": "12.5"}, "hospital_speed", 12.5),
        ],
    )
    def test_numbers(self, block: dict[str, Any], field: str, expected: float):
        assert getattr(CastleProductionArea.model_validate(block), field) == expected

    def test_storage_capacity_is_kept_as_sent(self):
        # AreaDataStorageItem.parseGPA: this._maxAmount = e["MR" + key]
        area = CastleProductionArea.model_validate({"MRW": 7000.5, "MRS": "x", "MRF": 7000})
        assert (area.storage_capacity.wood, area.storage_capacity.stone, area.storage_capacity.food) == (
            7000.5,
            0,
            7000,
        )

    def test_production_and_bonus_read_non_numbers_as_0(self):
        area = CastleProductionArea.model_validate({"DW": None, "DS": "20", "WM": None})
        assert (area.production.wood, area.production.stone, area.production_bonus_percent.wood) == (0.0, 2.0, 0.0)


class TestJoinLeniency:
    def test_a_bad_kingdom_reads_as_0(self):
        assert SelectCastleResponse.model_validate({"KID": "x"}).kingdom_id == 0

    def test_a_gpa_with_nulls_still_joins(self):
        joined = SelectCastleResponse.model_validate({"KID": 1, "gpa": {"DFC": None, "MP": "", "RS1": None}})
        assert joined.production_area is not None and joined.production_area.food_consumption_delta == 0.0

    def test_an_unreadable_block_is_none_and_costs_only_itself(self):
        joined = SelectCastleResponse.model_validate(
            {"KID": 1, "gca": {"scl": {"OIDL": "x"}, "CI": None}, "grc": {"AID": [1, 2]}, "gpa": 5}
        )
        assert joined.kingdom_id == 1
        assert joined.production_area is None

    def test_join_still_answers_with_a_broken_block(self):
        jaa = xt_packet("jaa", {"KID": 0, "T": 1, "gpa": {"P": None, "MRW": 1.5}})
        client = make_client({"jaa": jaa}, castles=[(1, Kingdom.GREEN)])
        joined = client.castle.join(1)
        assert conn(client).requested == ["jaa"]
        assert joined.production_area is not None and joined.production_area.storage_capacity.wood == 1.5


class TestBuildingReplyLeniency:
    def test_object_ids_go_through_int(self):
        assert SellBuildingResponse.model_validate({"OID": "6"}).object_id == 6
        assert CollectExtensionGiftResponse.model_validate({"OID": "12", "RID": None}).object_id == 12

    def test_an_unreadable_resources_block_is_none(self):
        reply = BuildResponse.model_validate({"NO": [1, 2, 3, 4], "grc": [1]})
        assert reply.building is not None and reply.resources is None
        # int() of an object is 0, so a malformed grc still reads
        assert BuildResponse.model_validate({"grc": {"AID": {"x": 1}}}).resources is not None

    def test_the_slot_count_is_kept_as_sent(self):
        assert ConstructionList.model_validate({"SSC": 2.5}).slot_count == 2.5
        assert ConstructionList.model_validate({"SSC": "3"}).slot_count == 3


class TestDetailedCastleListLeniency:
    def test_one_bad_entry_costs_only_itself(self):
        payload = {
            "C": [
                {
                    "KID": 0,
                    "AI": [
                        {"AID": "7", "W": 10, "AC": [[1, "2"], "junk", [3]], "gpa": {"DFC": None}},
                        {"AID": [1]},
                        {"AID": 8, "gpa": "x", "HI": None},
                    ],
                }
            ]
        }
        response = GetDetailedCastleResponse.model_validate(payload)
        # int([1]) is 1, as Number([1]) is
        assert [c.castle_id for c in response.castles] == [7, 1, 8]
        first = response.castles[0]
        # AUnitInventory.fillFromWodAmountArray: array entries only, through int()
        assert first.raw_units == [[1, 2], [3]] and first.units == {1: 2}
        assert response.castles[2].production_area is None
