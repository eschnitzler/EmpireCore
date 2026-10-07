"""client.attack preset methods: gas, sas and upan."""

from __future__ import annotations

import pytest

from empire_core.gamedata import WodAmount
from empire_core.protocol.models import AttackWave, PresetArmy
from tests.service_helpers import conn, make_client, xt_packet

GAS = {
    "S": [
        {"S": 0, "SN": "Farm", "A": "[[1,2],[],[],[10,20],[],[]]"},
        {"S": 1, "SN": None, "A": None},
    ]
}


class TestGetPresets:
    def test_lists_the_unlocked_slots(self):
        client = make_client({"gas": xt_packet("gas", GAS)})

        presets = client.attack.get_presets()

        assert [(p.index, p.name) for p in presets] == [(0, "Farm"), (1, None)]
        army = presets[0].army()
        assert army is not None and army.middle_units == ((10, 20),)
        assert conn(client).request_payloads == [("gas", {})]


class TestSavePreset:
    def test_saves_a_wave_as_the_client_does(self):
        client = make_client()
        wave = AttackWave.model_validate({"M": {"T": [[1, 2], [-1, 0]], "U": [[10, 20]]}, "R": {"U": [[12, 7]]}})

        assert client.attack.save_preset(3, wave) is True

        assert conn(client).request_payloads == [("sas", {"S": 3, "A": "[[1,2],[],[],[10,20],[],[12,7]]"})]

    def test_saves_a_preset_army(self):
        client = make_client()
        client.attack.save_preset(0, PresetArmy(left_units=(WodAmount(10, 5),)))
        assert conn(client).request_payloads == [("sas", {"S": 0, "A": "[[],[],[],[],[10,5],[]]"})]

    def test_a_refusal_is_false(self):
        client = make_client({"sas": xt_packet("sas", error_code=1)})
        assert client.attack.save_preset(9, PresetArmy()) is False


class TestRenamePreset:
    def test_sends_the_name_as_typed(self):
        client = make_client()
        assert client.attack.rename_preset(1, "Night raid") is True
        assert conn(client).request_payloads == [("upan", {"S": 1, "SN": "Night raid"})]

    @pytest.mark.parametrize("name", ["", "   ", "x" * 16, "Farm (1)", "50%", "a;b", "it's"])
    def test_names_the_dialog_refuses(self, name: str):
        client = make_client()
        with pytest.raises(ValueError):
            client.attack.rename_preset(1, name)
        assert conn(client).request_payloads == []

    def test_fifteen_characters_fit(self):
        client = make_client()
        client.attack.rename_preset(1, "x" * 15)
        assert conn(client).request_payloads == [("upan", {"S": 1, "SN": "x" * 15})]
