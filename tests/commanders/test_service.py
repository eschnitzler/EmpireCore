"""Tests for the commanders service."""

from __future__ import annotations

import logging
import threading
from typing import Any

import pytest

from empire_core.commanders import PREMIUM_COMMANDER_ID
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError, GameDataNotLoadedError, PremiumCommanderCostError
from empire_core.gamedata import GameData
from empire_core.protocol.models import EquipmentSlot, EquipmentType, WearerType
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, wave, xt_packet


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


# Two viplevels rows as the items payload has them: below level 5 there is no freePremiumGeneralsPerDay.
VIP_LEVELS = [
    {"vipLevelID": "4", "thresholdMin": "3000", "thresholdMax": "7999", "attackSpeedBoost": "15"},
    {"vipLevelID": "5", "thresholdMin": "8000", "thresholdMax": "19999", "freePremiumGeneralsPerDay": "25"},
]


def premium_client(vip: dict[str, Any] | None = None, boi: dict[str, Any] | None = None, *, game_data: bool = True):
    state = GameState()
    login: dict[str, Any] = {"gpi": {"PID": 7}}
    if vip is not None:
        login["vip"] = vip
    if boi is not None:
        login["boi"] = boi
    state.update_from_packet("gbd", login)
    client = make_client(state=state)  # type: ignore[arg-type]
    if game_data:
        client.game_data = GameData.parse("786.03", {"viplevels": VIP_LEVELS})
    return client


class TestFreePremiumCommanders:
    """``CastleVIPData.remainingPremiumCommanders``: the active VIP level's free ones a day less ``UPG``."""

    def test_the_vip_level_free_ones_less_those_used(self):
        client = premium_client({"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 3})

        assert client.commanders.free_premium_commanders() == 22
        assert client.commanders.premium_commander_is_free()

    def test_a_level_without_free_ones_has_none(self):
        client = premium_client({"VP": 5000, "VRL": 4, "VRS": 3600, "UPG": 0})

        assert client.commanders.free_premium_commanders() == 0

    def test_points_above_the_top_level_count_as_the_top_level(self):
        client = premium_client({"VP": 900000, "VRL": 5, "VRS": 3600, "UPG": 0})

        assert client.commanders.free_premium_commanders() == 25

    def test_none_without_vip_time(self):
        client = premium_client({"VP": 9000, "VRL": 5, "VRS": 0, "UPG": 0}, game_data=False)

        assert client.commanders.free_premium_commanders() == 0

    def test_vip_time_runs_out_from_when_it_was_read(self):
        client = premium_client({"VP": 9000, "VRL": 5, "VRS": 60, "UPG": 0})
        read_at = client.state.get_last_packet_time("vip")
        assert read_at is not None

        assert client.commanders.free_premium_commanders(now=read_at + 59) == 25
        assert client.commanders.free_premium_commanders(now=read_at + 60) == 0

    def test_all_used_is_zero(self):
        client = premium_client({"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 30})

        assert client.commanders.free_premium_commanders() == 0
        assert not client.commanders.premium_commander_is_free()

    def test_unknown_before_the_vip_section(self):
        client = premium_client()

        assert client.commanders.free_premium_commanders() is None
        assert not client.commanders.premium_commander_is_free()

    def test_vip_time_needs_the_game_data(self):
        client = premium_client({"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 0}, game_data=False)

        with pytest.raises(GameDataNotLoadedError):
            client.commanders.free_premium_commanders()

    def test_a_vip_push_updates_the_count(self):
        client = premium_client({"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 0})

        client.state.update_from_packet("vip", {"VP": 9000, "VRL": 5, "VRS": 3500, "UPG": 1})

        assert client.commanders.free_premium_commanders() == 24

    def test_a_premium_account_makes_it_free(self):
        # CastlePostAttackDialog.startAttack: the cost is 0 while premiumAccountVO.isActive
        client = premium_client({"VP": 0, "VRL": 0, "VRS": 0, "UPG": 0}, {"PA": 3600, "PT": 1}, game_data=False)

        assert client.commanders.free_premium_commanders() == 0
        assert client.commanders.premium_commander_is_free()


class TestPremiumCommanderSends:
    NO_FREE = {"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 25}
    FREE = {"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 0}

    @staticmethod
    def send_support(client, **options: Any) -> bool:
        return client.castle.send_support(12345, 700, 710, [[487, 1]], **options)

    @staticmethod
    def send_troops(client, **options: Any) -> bool:
        return client.castle.send_troops(100, 200, 110, 205, [[620, 1]], **options)

    @staticmethod
    def send_attack(client, **options: Any) -> bool:
        waves = [wave(units=[[487, 1]])]
        return client.attack.send_attack(500, 510, 700, 710, waves, kingdom_id=Kingdom.GREEN, **options)

    SENDS = [send_support, send_troops, send_attack]

    @pytest.mark.parametrize("send", SENDS)
    def test_none_free_is_refused_before_sending(self, send):
        client = premium_client(self.NO_FREE)

        with pytest.raises(PremiumCommanderCostError) as raised:
            send(client, commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

        assert raised.value.free_premium_commanders == 0
        assert conn(client).request_payloads == []

    @pytest.mark.parametrize("send", SENDS)
    def test_the_premium_commander_id_alone_counts(self, send):
        client = premium_client(self.NO_FREE)

        with pytest.raises(PremiumCommanderCostError):
            send(client, commander_id=PREMIUM_COMMANDER_ID)

        assert conn(client).request_payloads == []

    @pytest.mark.parametrize("send", SENDS)
    def test_unknown_is_refused(self, send):
        client = premium_client()

        with pytest.raises(PremiumCommanderCostError) as raised:
            send(client, commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

        assert raised.value.free_premium_commanders is None

    @pytest.mark.parametrize("send", SENDS)
    def test_spend_rubies_sends_anyway(self, send):
        client = premium_client(self.NO_FREE)

        assert send(client, commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True, spend_rubies=True)

        assert conn(client).request_payloads[0][1]["BPC"] == 1

    @pytest.mark.parametrize("send", SENDS)
    def test_a_free_one_sends(self, send):
        client = premium_client(self.FREE)

        assert send(client, commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

        assert (conn(client).request_payloads[0][1]["LID"], conn(client).request_payloads[0][1]["BPC"]) == (-14, 1)

    @pytest.mark.parametrize("send", SENDS)
    def test_a_premium_account_sends(self, send):
        client = premium_client(self.NO_FREE, {"PA": 3600, "PT": 1})

        assert send(client, commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

    @pytest.mark.parametrize("send", SENDS)
    def test_another_commander_is_not_checked(self, send):
        client = premium_client()

        assert send(client, commander_id=5)

        assert conn(client).request_payloads[0][1]["BPC"] == 0


class TestOwnPremiumSends:
    """Library policy: an accepted premium send counts as used until the next vip, as cra and cds bring none."""

    ONE_FREE = {"VP": 9000, "VRL": 5, "VRS": 3600, "UPG": 24}

    @staticmethod
    def send_support(client, **options: Any) -> bool:
        return client.castle.send_support(
            12345, 700, 710, [[487, 1]], commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True, **options
        )

    def test_an_accepted_send_counts_until_the_next_vip(self):
        client = premium_client(self.ONE_FREE)

        assert self.send_support(client)
        assert client.commanders.free_premium_commanders() == 0
        with pytest.raises(PremiumCommanderCostError):
            self.send_support(client)

        client.state.update_from_packet("vip", {"VP": 9000, "VRL": 5, "VRS": 3500, "UPG": 23})
        assert client.commanders.free_premium_commanders() == 2

    def test_a_refused_send_is_not_counted(self):
        client = premium_client(self.ONE_FREE)
        client.connection = conn(make_client({"cds": xt_packet("cds", error_code=5)}))

        assert not self.send_support(client)
        assert client.commanders.free_premium_commanders() == 1

    def test_a_send_with_a_premium_account_is_not_counted(self):
        client = premium_client(self.ONE_FREE, {"PA": 3600, "PT": 1})

        assert self.send_support(client)
        assert client.commanders.free_premium_commanders() == 1

    def test_a_send_with_another_commander_is_not_counted(self):
        client = premium_client(self.ONE_FREE)

        assert client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=5)
        assert client.commanders.free_premium_commanders() == 1

    def test_two_sends_at_once_cannot_both_take_the_last_free_one(self):
        client = premium_client(self.ONE_FREE)
        second: list[BaseException] = []

        def other_send() -> None:
            try:
                client.commanders.premium_send(PREMIUM_COMMANDER_ID, True, lambda: True, spend_rubies=False)
            except PremiumCommanderCostError as error:
                second.append(error)

        thread = threading.Thread(target=other_send)

        def first_send() -> bool:
            thread.start()
            thread.join(0.2)
            assert thread.is_alive()
            return True

        assert client.commanders.premium_send(PREMIUM_COMMANDER_ID, True, first_send, spend_rubies=False)
        thread.join(5)

        assert len(second) == 1
        assert "no premium account is known to run" in str(second[0])
