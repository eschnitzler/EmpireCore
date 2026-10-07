"""The bls, blm, bld and mfb models, checked against payloads in the shape the client reads."""

from __future__ import annotations

import copy
import logging

import pytest

from empire_core.enums import (
    AttackAdvisorType,
    AutoSkipCooldownType,
    BattleLogAttackType,
    BattleLogFlank,
    CollectableKind,
    LogResult,
    MapItemType,
    MessageType,
)
from empire_core.gamedata import Currency, Gem
from empire_core.messages.models import BattleLogMeta
from empire_core.protocol.base import parse_response
from empire_core.protocol.models import (
    BattleLogDetailResponse,
    BattleLogMiddleResponse,
    BattleLogShortResponse,
    ForwardBattleLogRequest,
    ForwardBattleLogResponse,
    GetBattleLogDetailRequest,
    GetBattleLogMiddleRequest,
    GetBattleLogShortRequest,
    MessageInfo,
)
from tests.messages.battle_log_payloads import (
    BLD,
    BLM,
    BLS,
    BLS_WITH_DETAILS,
    LOG_ID,
    MAILBOX_ROW,
    MESSAGE_ID,
    NPC_ID,
    PLAYER_ID,
)


class TestRequests:
    def test_short_log_request_sends_mid_then_im(self):
        payload = GetBattleLogShortRequest(message_id=MESSAGE_ID).to_payload()
        assert payload == {"MID": MESSAGE_ID, "IM": 0}
        assert list(payload) == ["MID", "IM"]

    @pytest.mark.parametrize(("im", "sent"), [(True, 1), (1, 1), (False, 0), (0, 0)])
    def test_im_is_sent_as_one_or_zero(self, im, sent):
        assert GetBattleLogShortRequest(message_id=1, include_details=im).to_payload()["IM"] == sent

    @pytest.mark.parametrize("request_type", [GetBattleLogMiddleRequest, GetBattleLogDetailRequest])
    def test_middle_and_detail_requests_send_the_log_id(self, request_type):
        request = request_type(LID=LOG_ID)
        assert request.to_payload() == {"LID": LOG_ID}
        assert request.accepts_reply({"LID": LOG_ID})
        assert request.accepts_reply({"LID": str(LOG_ID)})
        assert request.accepts_reply({"raw": ""})
        assert not request.accepts_reply({"LID": LOG_ID + 1})

    def test_short_request_accepts_its_own_message_or_a_reply_without_mid(self):
        request = GetBattleLogShortRequest(message_id=MESSAGE_ID)
        assert request.accepts_reply({"MID": MESSAGE_ID})
        assert request.accepts_reply({"LID": LOG_ID})
        assert not request.accepts_reply({"MID": MESSAGE_ID + 1})

    def test_forward_sends_mid_before_pid(self):
        payload = ForwardBattleLogRequest(message_id=MESSAGE_ID, player_ids=[7, 8]).to_payload()
        assert payload == {"MID": MESSAGE_ID, "PID": [7, 8]}
        assert list(payload) == ["MID", "PID"]

    @pytest.mark.parametrize(
        ("command", "model"),
        [
            ("bls", BattleLogShortResponse),
            ("blm", BattleLogMiddleResponse),
            ("bld", BattleLogDetailResponse),
            ("mfb", ForwardBattleLogResponse),
        ],
    )
    def test_replies_are_registered(self, command, model):
        assert isinstance(parse_response(command, {}), model)


class TestMailboxHeader:
    def test_a_battle_log_row(self):
        message = MessageInfo.model_validate(MAILBOX_ROW)
        assert message.is_battle_log
        assert message.message_type_enum is MessageType.BATTLE_LOG
        header = message.battle_log_header()
        assert header is not None
        assert header.area_type == MapItemType.CASTLE
        assert header.attack_type is BattleLogAttackType.NPC
        assert header.result is LogResult.DEFENDER_SUCCESS
        assert (header.treasure_map_id, header.treasure_map_area_type) == (-1, -1)
        assert (header.kingdom_id, header.owner_id, header.area_name) == (0, PLAYER_ID, "Home")
        assert message.subject is None

    def test_treasure_map_numbers(self):
        row = [1, 6, "8+0+2+12+2#0+-1", "", -1, 0, 0, 0, 0]
        header = MessageInfo.model_validate(row).battle_log_header()
        assert header is not None
        assert (header.treasure_map_id, header.treasure_map_area_type) == (12, 2)
        assert header.result is LogResult.ATTACKER_FAILED
        assert header.area_name == ""

    def test_unknown_subtypes_read_as_none(self):
        header = MessageInfo.model_validate([1, 6, "1+9+x#0+5", "", -1, 0, 0, 0, 0]).battle_log_header()
        assert header is not None
        assert header.attack_type is None
        assert header.result is None

    @pytest.mark.parametrize("row", [[1, 6, "1+0+3", "", -1, 0, 0, 0, 0], [1, 3, "1+0+1#0+5+x", "", -1, 0, 0, 0, 0]])
    def test_no_header_without_a_hash_part_or_for_other_messages(self, row):
        assert MessageInfo.model_validate(row).battle_log_header() is None


class TestShortLog:
    def test_live_shape(self):
        log = BattleLogShortResponse.model_validate(BLS)

        assert (log.message_id, log.log_id, log.message_type_enum) == (MESSAGE_ID, LOG_ID, MessageType.BATTLE_LOG)
        assert log.defender_won is True
        assert log.parsed_meta == BattleLogMeta(MapItemType.CASTLE, BattleLogAttackType.NPC, LogResult.DEFENDER_SUCCESS)
        assert log.seconds_since_battle == 678547
        assert log.rage_points == -1
        assert (log.attacker_home_castle_id, log.defender_home_castle_id) == (-1, 2001)
        assert (log.defender_had_hospital, log.defender_hospital_full, log.attacker_had_hospital) == (True, True, False)
        assert log.includes_details is False
        assert (log.middle, log.detail) == (None, None)
        assert log.error_code == 0

    def test_participants_and_owners(self):
        log = BattleLogShortResponse.model_validate(BLS)

        npc, player = log.participants
        assert (npc.player_id, npc.front, npc.start_army_size, npc.lost_units) == (NPC_ID, 0, 79, -79)
        assert player.is_defender and not npc.is_defender
        assert [(good.kind, good.amount) for good in player.loot] == [(CollectableKind.COINS, 3790)]
        assert (player.xp, player.faction_points, player.morale_boost) == (69, -1, -100)
        assert (player.reputation_blue, player.reputation_red) == (0, 0)
        assert log.attackers == [npc]
        assert log.defenders == [player]
        assert log.winners == [player]
        assert log.losers == [npc]
        owner = log.owner_of(player)
        assert owner is not None and owner.owner_id == PLAYER_ID
        assert log.owner_of(npc) is None

    def test_commanders(self):
        log = BattleLogShortResponse.model_validate(BLS)

        assert log.attacking_commander is not None
        assert (log.attacking_commander.commander_id, log.attacking_commander.general_id) == (-15, 106)
        assert log.defending_castellan is not None
        assert (log.defending_castellan.commander_id, log.defending_castellan.wins) == (1, 50)

    def test_area(self):
        area = BattleLogShortResponse.model_validate(BLS).area
        assert area is not None
        assert (area.area_type, area.x, area.y, area.owner_id) == (MapItemType.CASTLE, 100, 200, PLAYER_ID)
        assert (area.keep_level, area.moat_level, area.treasure_map_node_id) == (6, 2, -1)
        # E belongs to an alliance tower only
        assert area.alliance_crest is None

    def test_an_alliance_tower_takes_its_alliance_into_the_area(self):
        payload = copy.deepcopy(BLS)
        payload["AI"]["AT"] = MapItemType.ALLIANCE_BATTLE_GROUND_TOWER
        payload.update({"AID": 77, "N": "Tower", "ACVC": 3, "DAR": 2})

        area = BattleLogShortResponse.model_validate(payload).area

        assert area is not None
        assert (area.alliance_id, area.name, area.victory_count, area.daimyo_rank) == (77, "Tower", 3, 2)
        assert area.alliance_crest == {"ACLI": 1, "ACCS": [1]}

    def test_charge_points_read_as_int_of_max_with_zero(self):
        payload = {**BLS, "CPO": 120, "CRO": -3, "CPN": "45.7", "DCPO": None}
        log = BattleLogShortResponse.model_validate(payload)
        assert (log.old_charge_points, log.old_charge_rank, log.new_charge_points) == (120, 0, 45)
        assert (log.new_charge_rank, log.defender_old_charge_points) == (0, 0)

    @pytest.mark.parametrize(("sent", "read"), [(0, -1), (None, -1), ("12", 12), (7, 7)])
    def test_rage_points_are_read_only_when_truthy(self, sent, read):
        assert BattleLogShortResponse.model_validate({**BLS, "RP": sent}).rage_points == read

    def test_faction_reputation(self):
        payload = copy.deepcopy(BLS)
        payload["PBI"][1].append([4, 9])
        payload["PBI"][0].append({"0": 2, "1": 5})
        log = BattleLogShortResponse.model_validate(payload)
        assert (log.participants[1].reputation_blue, log.participants[1].reputation_red) == (4, 9)
        assert (log.participants[0].reputation_blue, log.participants[0].reputation_red) == (2, 5)

    def test_auto_skip_costs_split_as_the_client_splits_them(self):
        # BattleLogVO.fillFromParamObject: ASMS rows above 0 are costs, the others refunds; ASC rubies a cost
        log = BattleLogShortResponse.model_validate({**BLS, "ASMS": [[1004, 2], [1001, -3]], "ASC": 15})

        assert [(c.item, c.amount) for c in log.auto_skip_costs] == [
            (Currency.SKIP_30_MINUTES, 2),
            (Currency.SKIP_1_MINUTE, -3),
        ]
        assert [(c.kind, c.item, c.amount) for c in log.auto_skip_paid] == [
            (CollectableKind.CURRENCY, Currency.SKIP_30_MINUTES, 2),
            (CollectableKind.RUBIES, None, 15),
        ]
        assert [(c.item, c.amount) for c in log.auto_skip_refunded] == [(Currency.SKIP_1_MINUTE, 3)]
        assert BattleLogShortResponse.model_validate(BLS).auto_skip_paid == ()

    @pytest.mark.parametrize(("sent", "item"), [(4, Currency.SKIP_30_MINUTES), (1004, Currency.SKIP_30_MINUTES)])
    def test_a_found_minute_skip_is_one_of_its_currency(self, sent, item):
        skip = BattleLogShortResponse.model_validate({**BLS, "MSF": sent}).found_minute_skip

        assert skip is not None and (skip.kind, skip.item, skip.amount) == (CollectableKind.CURRENCY, item, 1)
        assert BattleLogShortResponse.model_validate({**BLS, "MSF": 0}).found_minute_skip is None

    def test_supporters_wounded(self):
        log = BattleLogShortResponse.model_validate({**BLS, "WSU": [[7, 12], ["8", "3"], "bad"]})
        assert [(row.player_id, row.wounded_units) for row in log.supporters_wounded] == [(7, 12), (8, 3)]
        assert log.supporter_wounded_units(8) == 3
        assert log.supporter_wounded_units(9) == -1

    def test_advisor_and_auto_skip(self):
        log = BattleLogShortResponse.model_validate({**BLS, "AAT": 4, "AAC": 3, "AAN": "2", "ASCT": 1})
        assert (log.advisor_type, log.advisor_movement_count, log.advisor_movement_number) == (
            AttackAdvisorType.BARON,
            3,
            2,
        )
        assert log.auto_skip_type is AutoSkipCooldownType.MINUTE_SKIP
        plain = BattleLogShortResponse.model_validate({k: v for k, v in BLS.items() if k not in ("AAT", "ASCT")})
        assert (plain.advisor_type, plain.auto_skip_type) == (AttackAdvisorType.NONE, None)

    def test_found_equipment_and_gem(self):
        row = [1, 2, 2, 4, 0, [[53, [25.0]]], -1, -1, 0, -1, -1, 0]
        log = BattleLogShortResponse.model_validate({**BLS, "EQF": row, "GF": 999})
        assert log.found_equipment is not None and log.found_equipment.bonuses[0].effect_id == 53
        assert log.found_gem == 999
        plain = BattleLogShortResponse.model_validate({**BLS, "EQF": 0, "GF": 0})
        assert (plain.found_equipment, plain.found_gem) == (None, None)

    def test_unreadable_parts_cost_only_themselves(self):
        payload = {**BLS, "AI": {"AT": "nope"}, "AL": 0, "PBI": [*BLS["PBI"], "bad"], "PI": [{"N": "no id"}]}
        log = BattleLogShortResponse.model_validate(payload)
        assert log.area is None
        assert log.attacking_commander is None
        assert len(log.participants) == 2
        assert log.owners == []

    def test_im_one_carries_the_middle_and_detail_logs(self):
        log = BattleLogShortResponse.model_validate(BLS_WITH_DETAILS)
        assert log.includes_details is True
        assert log.middle is not None and log.middle.log_id == LOG_ID
        assert log.detail is not None and log.detail.log_id == LOG_ID


class TestMiddleLog:
    def test_live_shape(self):
        log = BattleLogMiddleResponse.model_validate(BLM)

        assert log.log_id == LOG_ID
        yard = log.courtyard
        assert (yard.attacker_troops, yard.attacker_lost, yard.defender_troops, yard.defender_lost) == (
            52,
            -52,
            130000,
            -2,
        )
        assert yard.has_defender_info
        (wave,) = log.waves
        assert wave.attacker.player_id == NPC_ID
        assert wave.attacker.left is not None
        assert (wave.attacker.left.soldiers, wave.attacker.left.soldiers_lost) == (27, -27)
        assert wave.defender.left is not None and wave.defender.left.tools_used == 5
        assert wave.attacker.soldiers_survived == 52
        assert wave.got_through_wall
        assert log.pre_combat_wave is not None
        assert log.pre_combat_wave.attacker.player_id is None
        assert log.pre_combat_wave.attacker.middle is not None
        assert log.pre_combat_wave.attacker.middle.soldiers == 26
        assert (log.support_tools.attacker.player_id, log.support_tools.attacker.units) == (NPC_ID, [])
        assert log.reinforcements.soldiers == 0
        assert log.attacking_commander is not None and log.attacking_commander.commander_id == -15
        assert log.defending_castellan is not None
        assert log.defender_used_support_tools is False
        assert (log.attacker_abilities, log.defender_abilities) == ([], [])

    def test_optional_parts(self, caplog):
        payload = {
            "LID": LOG_ID,
            "W": [],
            "SD": [[1, [620, 4, -4]], [2]],
            "AGT": [12, "13", 999],
            "DGT": 0,
            "ALS": [5],
            "DUST": 1,
            "AA": [[33, [[1, 20, "L"], [2, 15, "M"]]], "bad"],
        }
        with caplog.at_level(logging.WARNING):
            log = BattleLogMiddleResponse.model_validate(payload)

        assert log.courtyard.has_defender_info is False
        assert log.pre_combat_wave is None
        assert [(u.wod_id, u.amount, u.lost) for u in log.support_tools.attacker.units] == [(620, 4, -4)]
        assert log.support_tools.defender.units == []
        # Client: e.RW || [0, 0, 0]
        assert (log.reinforcements.soldiers, log.reinforcements.tools_used) == (0, 0)
        assert (log.attacker_triggered_gems, log.defender_triggered_gems) == ((Gem.LIZARDS_EYE_12, 999), ())
        # getGemVO finds no gem for "13" and the client then throws; it is skipped, and said so
        assert "Skipped 1/3 attacker_triggered_gems of a battle log that are not ids, first: '13'" in caplog.text
        assert (log.attacker_legend_skill_ids, log.defender_legend_skill_ids) == ((5,), ())
        assert log.defender_used_support_tools is True
        (ability,) = log.attacker_abilities
        assert ability.ability_id == 33
        assert [(v.wave_id, v.value, v.flank_name) for v in ability.wave_values] == [
            (1, 20, BattleLogFlank.LEFT),
            (2, 15, BattleLogFlank.MIDDLE),
        ]

    def test_an_ability_wave_value_reads_the_wave_as_a_number(self):
        log = BattleLogMiddleResponse.model_validate({"AA": [[33, [["2", "7.5", 3], []]]]})
        (ability,) = log.attacker_abilities
        assert [(v.wave_id, v.value, v.flank_name) for v in ability.wave_values] == [(2, 7.5, None), (0, 0, None)]

    def test_an_ability_wave_value_keeps_a_flank_name_the_client_does_not_give(self, caplog):
        log = BattleLogMiddleResponse.model_validate({"AA": [[33, [[1, 5, "EW"], [1, 5, "Q"]]]]})
        (ability,) = log.attacker_abilities
        assert [v.flank_name for v in ability.wave_values] == [BattleLogFlank.POST_ATTACK, "Q"]
        assert "BattleLogFlank has no member 'Q'" in caplog.text

    def test_a_short_wave_side_has_no_flanks(self):
        log = BattleLogMiddleResponse.model_validate({"W": [[[5], [6, [1, 0, 0]]]]})
        (wave,) = log.waves
        assert (wave.attacker.left, wave.attacker.middle, wave.attacker.right) == (None, None, None)
        assert wave.defender.left is not None and wave.defender.middle is None


class TestDetailLog:
    def test_live_shape(self):
        log = BattleLogDetailResponse.model_validate(BLD)

        assert log.courtyard.attacker.player_id == NPC_ID
        assert [u.wod_id for u in log.courtyard.attacker.units] == [195, 148, 309, 630, 601]
        assert [(u.wod_id, u.amount, u.lost) for u in log.courtyard.defender.units] == [
            (215, 65000, -1),
            (216, 65000, -1),
        ]
        (wave,) = log.waves
        assert wave.attacker.player_id == NPC_ID
        assert [(u.wod_id, u.lost) for u in wave.attacker.left.soldiers][:2] == [(195, -6), (148, -3)]
        assert wave.attacker.left.wall_bonus is None
        defender_left = wave.defender.left
        assert [(u.wod_id, u.amount) for u in defender_left.tools] == [(624, 1), (625, 1), (105, 3)]
        assert (defender_left.wall_bonus, defender_left.gate_bonus, defender_left.moat_bonus) == (120, 0, 40)
        assert wave.defender.middle.gate_bonus == 120
        # No fifth entry: the courtyard flank reads as empty
        assert (wave.attacker.courtyard.soldiers, wave.attacker.courtyard.tools) == ([], [])
        assert log.pre_combat_wave is not None
        assert log.pre_combat_wave.defender.player_id == PLAYER_ID
        assert log.post_combat_wave is not None and log.post_combat_wave.attacker.player_id == -1
        assert log.reinforcements == []

    def test_a_courtyard_flank_and_reinforcements(self):
        side = [1, [[], []], [[], []], [[], []], [[[10, 5, -1]], [[620, 2, 0]]]]
        log = BattleLogDetailResponse.model_validate({"W": [[side, [2]]], "RW": [[10, 3, 0], "bad"], "PW": 0})
        (wave,) = log.waves
        assert [(u.wod_id, u.amount, u.lost) for u in wave.attacker.courtyard.soldiers] == [(10, 5, -1)]
        assert [u.wod_id for u in wave.attacker.courtyard.tools] == [620]
        assert wave.defender.player_id == 2
        assert [(u.wod_id, u.amount) for u in log.reinforcements] == [(10, 3)]
        assert log.pre_combat_wave is None
