"""Tests for the commanders service."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from empire_core.exceptions import CommandError
from empire_core.protocol.models import EquipmentSlot, EquipmentType, WearerType
from tests.service_helpers import conn, make_client, xt_packet


class TestSkillListUpdates:
    """``SKLCommand`` and ``EGOCommand`` both hand a skill list to ``parse_SKL``."""

    def test_a_skl_packet_reaches_the_callback(self):
        client = make_client()
        seen: list[Any] = []
        client.skills.on_skill_list(seen.append)

        client._on_packet(xt_packet("skl", {"SID": [3], "SIDS": [90], "SP": 10, "RS": 0, "RC": 1}))

        assert [(s.legend_skill_ids, s.reset_count) for s in seen] == [([3], 1)]

    def test_the_skl_block_of_an_ego_push_reaches_the_callback(self):
        client = make_client()
        seen: list[Any] = []
        client.skills.on_skill_list(seen.append)

        client._on_packet(xt_packet("ego", {"skl": {"SID": [], "SIDS": [90], "SSA": [{"ID": 91, "RS": 60}]}}))
        client._on_packet(xt_packet("ego", {"A": {"OID": 5}}))

        assert len(seen) == 1
        assert [(s.skill_id, s.remaining_seconds) for s in seen[0].activating] == [(91, 60)]

    def test_one_raising_callback_does_not_stop_the_others(self, caplog):
        client = make_client()
        seen: list[Any] = []

        def boom(skills: Any) -> None:
            raise RuntimeError("callback bug")

        client.skills.on_skill_list(boom)
        client.skills.on_skill_list(seen.append)

        with caplog.at_level(logging.ERROR, logger="empire_core.commanders.service"):
            client._on_packet(xt_packet("skl", {"SID": [3]}))

        assert len(seen) == 1
        assert "callback error" in caplog.text.lower()

    def test_a_removed_callback_is_not_called(self):
        client = make_client()
        seen: list[Any] = []
        client.skills.on_skill_list(seen.append)

        client.skills.remove_skill_list_callback(seen.append)
        client.skills.remove_skill_list_callback(seen.append)
        client._on_packet(xt_packet("skl", {"SID": [3]}))

        assert seen == []


class TestGeneralCommands:
    def test_assign_general_returns_the_commander_list(self):
        client = make_client({"gla": xt_packet("gla", {"gli": {"C": [{"ID": 7, "GID": 103}], "B": []}})})

        response = client.skills.assign_general(7, 103)

        assert conn(client).request_payloads == [("gla", {"LID": 7, "GID": 103})]
        assert [(c.commander_id, c.general_id) for c in response.commander_roster.commanders] == [(7, 103)]

    def test_set_abilities_sends_every_slot(self):
        client = make_client()

        assert client.skills.set_abilities(103, [(101031, 10073), (101033, -1)]) is True

        assert conn(client).request_payloads == [("gaae", {"GID": 103, "SAIDS": [[101031, 10073], [101033, -1]]})]

    @pytest.mark.parametrize(
        ("call", "command", "payload"),
        [
            (lambda s: s.unlock_skill(10317), "guse", {"ID": 10317}),
            (lambda s: s.reset_skills(103), "grs", {"GID": 103}),
            (lambda s: s.add_xp(103, 7001, 5), "gaxp", {"GID": 103, "CID": 7001, "AMT": 5}),
        ],
    )
    def test_the_no_body_commands(self, call, command, payload):
        client = make_client()

        assert call(client.skills) is True

        assert conn(client).request_payloads == [(command, payload)]

    def test_a_rejected_command_is_false(self):
        client = make_client({"grs": xt_packet("grs", error_code=114)})

        assert client.skills.reset_skills(103) is False


# =============================================================================
# CommandersService
# =============================================================================


class TestCommandersService:
    def test_commanders_parse(self):
        payload = {"C": [{"ID": -14, "N": ""}, {"ID": 91, "N": "Bloodwing"}]}
        client = make_client({"gli": xt_packet("gli", payload)})

        commanders = client.commanders.get_commanders()

        assert [(c.commander_id, c.name) for c in commanders] == [(-14, ""), (91, "Bloodwing")]
        assert conn(client).request_payloads == [("gli", {})]

    def test_empty_commander_list(self):
        client = make_client({"gli": xt_packet("gli", {})})
        assert client.commanders.get_commanders() == []

    def test_error_raises(self):
        client = make_client({"gli": xt_packet("gli", error_code=21)})
        with pytest.raises(CommandError):
            client.commanders.get_commanders()

    def test_assigned_general_is_parsed(self):
        # A commander's gli entry names the general assigned to it; that
        # general's skills are what size an attack's waves.
        payload = {"C": [{"ID": 1, "N": "The Blackthorn", "GID": 101, "ST": 4, "L": 50}]}
        client = make_client({"gli": xt_packet("gli", payload)})

        commander = client.commanders.get_commanders()[0]

        assert commander.general_id == 101
        assert commander.star_level == 4
        assert commander.level == 50

    def test_commander_without_a_general(self):
        client = make_client({"gli": xt_packet("gli", {"C": [{"ID": 1}]})})
        assert client.commanders.get_commanders()[0].general_id is None

    def test_combat_record_parsed(self):
        payload = {"C": [{"ID": 91, "N": "Bloodwing", "W": 42, "D": 7, "SPR": 3}]}
        client = make_client({"gli": xt_packet("gli", payload)})

        commander = client.commanders.get_commanders()[0]

        assert (commander.wins, commander.defeats, commander.win_spree) == (42, 7, 3)

    def test_effects_parsed(self):
        payload = {"C": [{"ID": 91, "E": [[12, [5]]], "AE": [[34, [10]]]}]}
        client = make_client({"gli": xt_packet("gli", payload)})

        commander = client.commanders.get_commanders()[0]

        assert [(e.effect_id, e.values) for e in commander.effects] == [(12, [5])]
        assert [(e.effect_id, e.values) for e in commander.area_effects] == [(34, [10])]

    def test_equipment_parsed(self):
        # EQ entry: [id, slot, wearer, rareID, graphic, bonuses, uniqueID,
        #            setID, enchantLevel, durationSecs, gemID, equipmentTypeID]
        entry = [880, 2, 2, 4, 3, [[12, [5]]], 5501, 17, 3, 0, -1, 1]
        client = make_client({"gli": xt_packet("gli", {"C": [{"ID": 91, "EQ": [entry]}]})})

        item = client.commanders.get_commanders()[0].equipment[0]

        assert item.equipment_id == 880
        assert item.slot == EquipmentSlot.WEAPON
        assert item.wearer_type == WearerType.COMMANDER
        assert item.rarity_id == 4
        assert item.graphic == 3
        assert [(b.effect_id, b.values) for b in item.bonuses] == [(12, [5])]
        assert item.unique_id == 5501
        assert item.set_id == 17
        assert item.enchantment_level == 3
        assert item.gem_id == -1
        assert item.equipment_type == 1
        assert item.is_permanent

    def test_equipment_short_entry_does_not_raise(self):
        client = make_client({"gli": xt_packet("gli", {"C": [{"ID": 91, "EQ": [[880, 2, 2]]}]})})

        item = client.commanders.get_commanders()[0].equipment[0]

        assert (item.equipment_id, item.slot) == (880, EquipmentSlot.WEAPON)
        assert item.equipment_type == 0
        assert item.is_permanent

    def test_live_equipment_entry(self):
        # Captured from a live gli response: the graphic slot is an int and a
        # permanent item reports -1 seconds, not 0.
        entry = [6515210043, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]
        client = make_client({"gli": xt_packet("gli", {"C": [{"ID": 91, "EQ": [entry]}]})})

        item = client.commanders.get_commanders()[0].equipment[0]

        assert item.equipment_id == 6515210043
        assert item.slot == EquipmentSlot.HERO
        assert item.wearer_type == WearerType.COMMANDER
        assert [(b.effect_id, b.values) for b in item.bonuses] == [(242, [25.0])]
        assert item.set_id == 22
        assert item.duration_seconds == -1
        assert item.is_permanent
        assert not item.has_gem
        assert item.equipment_type == EquipmentType.UNIQUE

    def test_temporary_equipment(self):
        entry = [880, 2, 2, 4, 3, [], 5501, 17, 0, 3600, -1, 0]
        client = make_client({"gli": xt_packet("gli", {"C": [{"ID": 91, "EQ": [entry]}]})})

        item = client.commanders.get_commanders()[0].equipment[0]

        assert item.duration_seconds == 3600
        assert not item.is_permanent

    def test_castellans_parse(self):
        payload = {"B": [{"ID": 1005, "N": "Warden"}], "C": [{"ID": 91}]}
        client = make_client({"gli": xt_packet("gli", payload)})

        castellans = client.commanders.get_castellans()

        assert [(c.commander_id, c.name) for c in castellans] == [(1005, "Warden")]

    def test_castellans_absent(self):
        client = make_client({"gli": xt_packet("gli", {"C": [{"ID": 91}]})})
        assert client.commanders.get_castellans() == []

    def test_rename_sends_the_client_payload_and_reads_the_new_list(self):
        reply = {"gli": {"C": [{"ID": 91, "WID": 2, "N": "farm-1"}], "B": [{"ID": 1005, "WID": 1, "N": "Warden"}]}}
        client = make_client({"arl": xt_packet("arl", reply)})

        response = client.commanders.rename(91, "farm-1")

        # C2SRenameLordVO sets LID before N
        assert conn(client).request_payloads == [("arl", {"LID": 91, "N": "farm-1"})]
        assert list(conn(client).request_payloads[0][1]) == ["LID", "N"]
        roster = response.commander_roster
        assert [(c.commander_id, c.name) for c in roster.commanders] == [(91, "farm-1")]
        assert [c.commander_id for c in roster.castellans] == [1005]

    def test_rename_rejection_raises(self):
        client = make_client({"arl": xt_packet("arl", error_code=21)})
        with pytest.raises(CommandError):
            client.commanders.rename(91, "farm-1")


# =============================================================================
# EquipmentService
# =============================================================================


class TestEquipmentService:
    def test_inventory_parses(self):
        rows = [[6515211559, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1], [880, 2, 2]]
        client = make_client({"gei": xt_packet("gei", {"I": rows})})

        items = client.equipment.get_inventory()

        assert [(i.equipment_id, i.slot) for i in items] == [(6515211559, EquipmentSlot.HERO), (880, 2)]
        assert conn(client).request_payloads == [("gei", {})]

    def test_inventory_error_raises(self):
        client = make_client({"gei": xt_packet("gei", error_code=21)})
        with pytest.raises(CommandError):
            client.equipment.get_inventory()

    def test_equip_sends_one(self):
        client = make_client()

        assert client.equipment.equip(equipment_id=880, commander_id=91) is True
        assert conn(client).request_payloads == [("eeq", {"EID": 880, "LID": 91, "E": 1})]

    def test_unequip_sends_zero(self):
        client = make_client()

        assert client.equipment.unequip(equipment_id=880, commander_id=1005) is True
        assert conn(client).request_payloads == [("eeq", {"EID": 880, "LID": 1005, "E": 0})]

    def test_a_rejected_equip_returns_false(self):
        client = make_client({"eeq": xt_packet("eeq", error_code=21)})

        assert client.equipment.equip(equipment_id=880, commander_id=91) is False
