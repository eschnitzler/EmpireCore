import json
import logging

import pytest

from empire_core.protocol.models import (
    Commander,
    EquipEquipmentRequest,
    Equipment,
    EquipmentSlot,
    EquipmentType,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
    WearerType,
    get_response_model,
)

# Shape of a gli EQ entry, which gei shares
HERO_ROW = [6515211559, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]
RELIC_ROW = [6109572530, 1, 2, 5, -1, [[4, 84, [116.2]]], -1, -1, 0, -1, -1, 3, [2, 1, 3500, []]]


class TestWearerType:
    def test_values_follow_the_client(self):
        assert [(m.name, m.value) for m in WearerType] == [("UNDEFINED", -1), ("CASTELLAN", 1), ("COMMANDER", 2)]

    def test_an_item_without_a_wearer_is_undefined(self):
        assert Equipment().wearer_type == WearerType.UNDEFINED == -1
        assert Equipment.model_validate(HERO_ROW).wearer_type == WearerType.COMMANDER


class TestGetEquipmentInventory:
    def test_request_is_empty(self):
        request = GetEquipmentInventoryRequest()

        assert request.to_payload() == {}
        assert request.to_packet().split("%")[3] == "gei"

    def test_items_parse_as_equipment(self):
        response = GetEquipmentInventoryResponse.model_validate({"I": [HERO_ROW, RELIC_ROW]})

        hero, relic = response.items
        assert (hero.equipment_id, hero.slot, hero.equipment_type) == (6515211559, EquipmentSlot.HERO, 1)
        assert [(b.effect_id, b.values) for b in hero.bonuses] == [(242, [25.0])]
        assert relic.is_relic
        assert relic.relic_info is not None and relic.relic_info.might == 3500
        assert relic.equipment_type == EquipmentType.RELIC

    def test_an_entry_that_is_not_a_row_costs_only_itself(self):
        response = GetEquipmentInventoryResponse.model_validate({"I": [None, "x", HERO_ROW, [880, 2, 2]]})

        assert [item.equipment_id for item in response.items] == [6515211559, 880]

    def test_a_missing_list_reads_as_empty(self):
        assert GetEquipmentInventoryResponse.model_validate({}).items == []
        assert GetEquipmentInventoryResponse.model_validate({"I": None}).items == []

    def test_response_is_registered(self):
        assert get_response_model("gei") is GetEquipmentInventoryResponse


class TestEquipEquipment:
    def test_equip_payload_matches_the_client(self):
        # C2SEquipEquipmentVO: EID, LID, then E as int(n?1:0)
        payload = EquipEquipmentRequest(equipment_id=6515211559, commander_id=91, equip=True).to_payload()

        assert payload == {"EID": 6515211559, "LID": 91, "E": 1}
        assert list(payload) == ["EID", "LID", "E"]

    def test_unequip_sends_zero(self):
        payload = EquipEquipmentRequest(equipment_id=880, commander_id=1005, equip=False).to_payload()

        assert payload == {"EID": 880, "LID": 1005, "E": 0}

    def test_the_flag_is_sent_as_an_int(self):
        request = EquipEquipmentRequest(equipment_id=880, commander_id=91, equip=5)

        assert json.loads(request.to_packet().split("%")[5]) == {"EID": 880, "LID": 91, "E": 1}

    def test_wire_keys_are_accepted(self):
        request = EquipEquipmentRequest.model_validate({"EID": 880, "LID": 91, "E": 0})

        assert (request.equipment_id, request.commander_id, request.equip) == (880, 91, 0)


# Wire rows as CastleEquipmentFactory.createEquipmentVO (bundle line 18134) hands them to the
# parseEquipFromArray of BasicEquipmentVO (7115), CastleHeroVO (40585) and RelicEquipmentVO (25039)
DUMPED_ROWS = {
    "generic": [101, 1, 2, 3, 5, [[1, [10]]], 0, -1, 0, -1, -1, 0],
    "gem": [102, 2, 2, 4, 6, [[53, [25.0]]], 803, -1, 1, 3600, 1, 0],
    "hero_text": [103, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, "242&25"],
    "hero_numeric": HERO_ROW,
    "relic_with_gem": [*RELIC_ROW[:12], [1, 6, 2980, [890593, 32, 6, 2770, [[302, 61, [34.7]]], 0]]],
    "relic_without_gem": RELIC_ROW,
}


class TestADumpReadsBack:
    """A model validated again from its own field-name dump is the same model, without a warning."""

    @pytest.mark.parametrize("row", DUMPED_ROWS.values(), ids=DUMPED_ROWS.keys())
    def test_a_commander(self, row, caplog):
        with caplog.at_level(logging.WARNING):
            commander = Commander.model_validate({"ID": 7, "EQ": [row]})
            assert Commander.model_validate(commander.model_dump()) == commander
            assert Commander.model_validate_json(commander.model_dump_json()) == commander
        assert len(commander.equipment) == 1
        assert caplog.records == []

    @pytest.mark.parametrize("row", DUMPED_ROWS.values(), ids=DUMPED_ROWS.keys())
    def test_the_equipment_inventory(self, row, caplog):
        with caplog.at_level(logging.WARNING):
            response = GetEquipmentInventoryResponse.model_validate({"I": [row]})
            assert GetEquipmentInventoryResponse.model_validate(response.model_dump()) == response
            assert GetEquipmentInventoryResponse.model_validate_json(response.model_dump_json()) == response
        assert len(response.items) == 1
        assert caplog.records == []

    def test_no_gem_stays_no_gem(self, caplog):
        with caplog.at_level(logging.WARNING):
            item = Equipment.model_validate(Equipment.model_validate(DUMPED_ROWS["generic"]).model_dump())
        assert item.gem_id is None
        assert caplog.records == []

    def test_a_commander_with_equipment_keeps_its_alien_block_out(self):
        commander = Commander.model_validate({"ID": 7, "EQ": [DUMPED_ROWS["generic"]], "AIE": [[37, [10]]]})
        dumped = Commander.model_validate(commander.model_dump())

        assert dumped == commander
        assert dumped.alien_equipment is not None
        assert not dumped.uses_alien_equipment

    def test_a_commander_on_alien_equipment_keeps_it(self):
        commander = Commander.model_validate({"ID": 7, "EQ": [], "AIE": [[37, [10]]], "GEM": [1]})
        dumped = Commander.model_validate(commander.model_dump())

        assert dumped == commander
        assert dumped.uses_alien_equipment
