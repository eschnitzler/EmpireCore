import json

from empire_core.protocol.models import (
    EquipEquipmentRequest,
    EquipmentSlot,
    EquipmentType,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
    get_response_model,
)

# Shape of a gli EQ entry, which gei shares
HERO_ROW = [6515211559, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]
RELIC_ROW = [6109572530, 1, 2, 5, -1, [[4, 84, [116.2]]], -1, -1, 0, -1, -1, 3, [2, 1, 3500, []]]


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
        payload = EquipEquipmentRequest(EID=6515211559, LID=91, E=True).to_payload()

        assert payload == {"EID": 6515211559, "LID": 91, "E": 1}
        assert list(payload) == ["EID", "LID", "E"]

    def test_unequip_sends_zero(self):
        payload = EquipEquipmentRequest(EID=880, LID=1005, E=False).to_payload()

        assert payload == {"EID": 880, "LID": 1005, "E": 0}

    def test_the_flag_is_sent_as_an_int(self):
        request = EquipEquipmentRequest(EID=880, LID=91, E=5)

        assert json.loads(request.to_packet().split("%")[5]) == {"EID": 880, "LID": 91, "E": 1}

    def test_wire_keys_are_accepted(self):
        request = EquipEquipmentRequest.model_validate({"EID": 880, "LID": 91, "E": 0})

        assert (request.equipment_id, request.commander_id, request.equip) == (880, 91, 0)
