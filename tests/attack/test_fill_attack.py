"""Tests for AttackService.fill_attack and its wave sizing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

from empire_core.army.spy_army import SpyArmy
from empire_core.enums import Kingdom
from empire_core.exceptions import AttackBelowMinimumError, EmpireTimeoutError
from empire_core.protocol.models import Commander
from tests.service_helpers import LIVE_ADI, conn, make_client, placed, stub_player, wave, xt_packet


class TestFillAttack:
    """One call producing a complete attack."""

    UNITS: ClassVar[dict[str, list]] = {
        "units": [
            {
                "wodID": 601,
                "name": "Barracks",
                "type": "Sword",
                "role": "melee",
                "meleeAttack": "100",
                "fightType": "0",
            },
            {
                "wodID": 611,
                "name": "Workshop",
                "type": "Ram",
                "typ": "Attack",
                "slotTypes": "1,2,9",
                "gateBonus": "30",
                "fightType": "1",
            },
        ],
        "buildings": [
            {"wodID": 501, "comment2": "Castlewall", "level": "1", "wallBonus": "30"},
            {"wodID": 450, "comment2": "Gate", "level": "1", "gateBonus": "30"},
        ],
        # A daimyo rank jumps at a rank boundary, so the level is looked up and
        # never counted off from the first row.
        "daimyoCastles": [{"id": "1", "rank": "1", "level": "81", "wallBonus": "110", "gateBonus": "110"}],
        "daimyoTownships": [
            {"id": "25", "rank": "3", "level": "110", "wallBonus": "100", "gateBonus": "100"},
            {"id": "26", "rank": "4", "level": "116", "wallBonus": "100", "gateBonus": "100"},
        ],
        "leaguetypes": [
            {"leaguetypeID": "1", "eventID": "80", "minLevel": 10, "maxLevel": "69", "countVictoryMin": "16"},
            {"leaguetypeID": "2", "eventID": "80", "minLevel": 70, "maxLevel": "369", "countVictoryMin": "81"},
        ],
        "eventAutoScalingCamps": [{"eventAutoScalingCampID": "3", "camplevel": "70"}],
    }

    def build(self, inventory):
        from empire_core.gamedata import GameData

        client = make_client({"gui": xt_packet("gui", {"I": inventory})})
        client.game_data = GameData.parse("test", self.UNITS)
        client.state.local_player = stub_player(level=70)
        return client

    def test_waves_and_a_courtyard_wave(self):
        client = self.build([[601, 100_000]])

        result = client.attack.fill_attack(12345, target_level=13)

        assert result.waves
        # Eight slots always go out; at least one of them holds something.
        assert len(result.yard) == 8
        assert [pair for pair in result.yard if pair[0] != -1]
        # The courtyard is sized separately from the flanks.
        assert result.unit_count() > sum(w.unit_count() for w in result.waves)

    def test_the_courtyard_draws_from_what_the_waves_left(self):
        # Only enough for the waves: the courtyard gets the remainder.
        client = self.build([[601, 100]])

        result = client.attack.fill_attack(12345, target_level=13)

        committed = result.unit_count()
        assert committed <= 100

    def test_the_attack_carries_its_minimum(self):
        client = self.build([[601, 100_000]])

        result = client.attack.fill_attack(12345, target_level=16)

        # getMinSoldiers(16): a tenth of the 88 a wave holds
        assert result.min_soldiers == 8
        assert result.wave_unit_count() >= 8

    def test_too_few_units_to_attack_raise(self):
        client = self.build([[601, 5]])

        with pytest.raises(AttackBelowMinimumError) as caught:
            client.attack.fill_attack(12345, target_level=16)

        assert (caught.value.minimum, caught.value.soldiers) == (8, 5)
        assert caught.value.attack.wave_unit_count() == 5

    def test_a_monument_needs_the_level_70_minimum(self):
        client = self.build([[601, 20]])

        with pytest.raises(AttackBelowMinimumError) as caught:
            client.attack.fill_attack(12345, target_level=12, area_type=26)

        assert caught.value.minimum == 32

    def test_a_castle_row_supplies_fortification(self):
        client = self.build([[601, 100_000], [611, 500]])
        row = [1, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "small castle"]

        result = client.attack.fill_attack(12345, target_level=13, target_is_player=True, target_row=row)

        # Wall and gate protection of 30% each, and a ram that cancels 30%.
        payload = result.waves[0].model_dump(by_alias=True)
        assert placed(payload["M"]["T"]) == [[611, 1]]

    def test_the_area_bonuses_widen_the_flanks(self):
        # aci's AE carries attackUnitAmountFlank; the live capture has +30%.
        from empire_core.combat import parse_bonus_entries
        from empire_core.gamedata import GameData

        payload = {
            "units": [{"wodID": 601, "name": "Barracks", "role": "melee", "meleeAttack": "100", "fightType": "0"}],
            "effecttypes": [{"effectTypeID": "28", "name": "attackUnitAmountFlank"}],
            "effects": [{"effectID": "66", "name": "attackUnitAmountFlank", "effectTypeID": "28", "capID": "99"}],
        }
        client = self.build([[601, 100_000]])
        client.game_data = GameData.parse("test", payload)
        area = parse_bonus_entries([[66, [30.0], "CI"]])

        plain = client.attack.fill_waves(12345, level=70)
        widened = client.attack.fill_waves(12345, level=70, area_bonuses=area)

        left = plain[0].model_dump(by_alias=True)["L"]["U"][0][1]
        wider = widened[0].model_dump(by_alias=True)["L"]["U"][0][1]
        # 20% of 320 attackers is 64, then +30%.
        assert (left, wider) == (64, 84)

    FLANK_BONUS_DATA: ClassVar[dict] = {
        "units": [{"wodID": 601, "name": "Barracks", "role": "melee", "meleeAttack": "100", "fightType": "0"}],
        "effecttypes": [
            {"effectTypeID": "28", "name": "attackUnitAmountFlank"},
            {"effectTypeID": "34", "name": "attackUnitAmountFront"},
        ],
        "effects": [
            {"effectID": "66", "name": "flankA", "effectTypeID": "28", "capID": "99"},
            {"effectID": "67", "name": "flankB", "effectTypeID": "28", "capID": "99"},
            {"effectID": "68", "name": "frontA", "effectTypeID": "34", "capID": "99"},
            {"effectID": "69", "name": "frontB", "effectTypeID": "34", "capID": "99"},
            {"effectID": "70", "name": "flankPvP", "effectTypeID": "28", "capID": "99", "isPvPFight": "1"},
        ],
        "legendskills": [
            {
                "skillID": "901",
                "effectType": "additionalUnitAmountOnFlank",
                "totalEffectValue": "10.5",
                "level": "1",
                "tier": "5",
            }
        ],
    }

    def sizes(self, **kwargs):
        from empire_core.gamedata import GameData

        client = self.build([[601, 100_000]])
        client.game_data = GameData.parse("test", self.FLANK_BONUS_DATA)
        wave = client.attack.fill_waves(12345, level=70, **kwargs)[0].model_dump(by_alias=True)
        return wave["L"]["U"][0][1], wave["M"]["U"][0][1]

    def test_the_flank_bonus_is_truncated_once_over_every_source(self):
        # 0.6% from the commander and 0.6% from aci's AE: int(1.2) is 1, where
        # truncating each source first would give 0.
        from empire_core.combat import parse_bonus_entries
        from empire_core.protocol.models import Commander

        commander = Commander.model_validate({"ID": 1, "E": [[66, [0.6], "A"], [68, [0.6], "A"]]})
        area = parse_bonus_entries([[67, [0.6], "CI"], [69, [0.6], "CI"]])

        # getUnitsOnTheFlankBonusForAreaType / Front give 1, and
        # getAmountSoldiers(0, 70, 1) / (1, 70, 0, 1) give 65 and 194 (client, node).
        assert self.sizes(commander=commander, area_bonuses=area) == (65, 194)

    def test_aci_area_effects_replace_the_commanders_own(self):
        # The commander's gli AE and aci's AE carry the same bonus. The attack
        # dialog puts the aci list in place of the commander's, so it counts once.
        from empire_core.combat import parse_bonus_entries
        from empire_core.protocol.models import Commander

        commander = Commander.model_validate({"ID": 1, "AE": [[66, [30.0], "RH"]]})
        area = parse_bonus_entries([[66, [30.0], "CI"]])

        # getAmountSoldiersFlank(70, 30) and (70, 0), from the client in node.
        assert self.sizes(commander=commander, area_bonuses=area)[0] == 84
        # An empty aci list leaves the commander's own AE: the areaEffects
        # setter ignores an empty array.
        assert self.sizes(commander=commander, area_bonuses=[])[0] == 84

    def test_an_alien_camp_takes_the_pvp_effects(self):
        # getFilterStrategyAttackOrDefence: an alien invasion owner is fought
        # with the PvP filter, a robber baron with the PvE one.
        from empire_core.combat import parse_bonus_entries

        area = parse_bonus_entries([[70, [30.0], "CI"]])

        # getAmountSoldiersFlank(70, 30) and (70, 0), from the client in node.
        assert self.sizes(area_type=21, area_bonuses=area)[0] == 84
        assert self.sizes(area_type=2, owner_id=-202, area_bonuses=area)[0] == 64

    def test_effect_156_and_support_tools_add_waves(self):
        from empire_core.gamedata import GameData
        from empire_core.protocol.models import Commander

        payload = {
            "units": [
                {"wodID": 601, "name": "Barracks", "role": "melee", "meleeAttack": "100", "fightType": "0"},
                {"wodID": 700, "name": "Horn", "typ": "Attack", "slotTypes": "10", "effects": "80&1"},
                {"wodID": 701, "name": "Drum", "typ": "Attack", "slotTypes": "10", "effects": "80&0.5"},
            ],
            "effecttypes": [{"effectTypeID": "156", "name": "additionalWave"}],
            "effects": [{"effectID": "80", "name": "additionalWave", "effectTypeID": "156", "capID": "99"}],
        }
        commander = Commander.model_validate({"ID": 1, "E": [[80, [1.5], "A"]]})

        def waves(**kwargs):
            client = self.build([[601, 100_000]])
            client.game_data = GameData.parse("test", payload)
            return len(client.attack.fill_waves(12345, level=70, **kwargs))

        # AttackDialogWaveHandler.initWaves in node, on top of the four waves a
        # level 70 attacker opens with: int(1.5) = 1, plus 1 from the horn; a
        # half wave from the drum settles back to none.
        assert waves() == 4
        assert waves(commander=commander) == 5
        assert waves(commander=commander, support_tools=[700, -1, -1]) == 6
        assert waves(support_tools=[701]) == 4

    def test_an_unknown_support_tool_is_refused(self):
        client = self.build([[601, 100_000]])

        with pytest.raises(ValueError, match="Support tool 9999"):
            client.attack.fill_waves(12345, level=70, support_tools=[9999])

    def test_the_legend_flank_skill_is_truncated_on_its_own(self):
        # int(10.5) on top of int(0): getUnitsOnTheFlankBonusForAreaType gives
        # 10 and getAmountSoldiersFlank(70, 10) 71 (client, node).
        legend = dict(attacker_legend_level=1, owner_legend_level=1, area_type=1, owner_id=4242)

        assert self.sizes(legend_skill_ids=[901], **legend)[0] == 71

    def test_the_legend_skills_take_one_skl_read(self):
        from empire_core.protocol.models import Commander

        client = self.build([[601, 100_000]])
        conn(client).script["skl"] = xt_packet("skl", {"SID": [3], "SIDS": [90], "SP": 10})

        client.attack.fill_attack(12345, target_level=13, commander=Commander.model_validate({"ID": 1}))

        sent = [command for command, _ in conn(client).request_payloads]
        assert sent.count("skl") == 1

    def test_the_skills_are_read_when_not_given(self):
        from empire_core.protocol.models import Commander

        client = self.build([[601, 100_000]])
        conn(client).script["gie"] = xt_packet("gie", {"G": [{"GID": 7, "SIDS": [1, 2]}]})
        conn(client).script["skl"] = xt_packet("skl", {"SID": [3], "SIDS": [], "SP": 10})
        commander = Commander.model_validate({"ID": 1, "GID": 7})

        client.attack.fill_attack(12345, target_level=13, commander=commander)

        sent = [command for command, _ in conn(client).request_payloads]
        assert "gie" in sent and "skl" in sent

    def test_given_skills_are_not_re_read(self):
        from empire_core.protocol.models import Commander

        client = self.build([[601, 100_000]])
        commander = Commander.model_validate({"ID": 1, "GID": 7})

        client.attack.fill_attack(
            12345,
            target_level=13,
            commander=commander,
            general_skill_ids=[],
            legend_skill_ids=[],
        )

        sent = [command for command, _ in conn(client).request_payloads]
        assert "gie" not in sent and "skl" not in sent

    def test_coordinates_are_enough(self):
        # Nothing about the target is passed: the pre-calculation and a one-tile
        # scan supply the row, the spied defenders, the castellan, the area
        # effects and the owner's level.
        client = self.build([[601, 100_000]])
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "small castle"]
        conn(client).script["aci"] = xt_packet(
            "aci",
            {
                "gaa": {"AI": row},
                "S": [[[601, 50]], [], [], [], [], [], []],
                "AE": [],
                "B": {},
            },
        )
        conn(client).script["gaa"] = xt_packet(
            "gaa", {"KID": 0, "AI": [row], "OI": [{"OID": 900, "PID": 4242, "PN": "dweller", "L": 46}]}
        )

        result = client.attack.fill_attack(12345, target_x=700, target_y=710)

        sent = [command for command, _ in conn(client).request_payloads]
        assert "aci" in sent
        assert result.waves

    def test_a_kingdom_the_client_does_not_define_is_refused_before_any_request(self):
        client = self.build([[601, 100_000]])
        sent_before = len(conn(client).request_payloads)

        with pytest.raises(ValueError):
            client.attack.fill_attack(12345, target_x=700, target_y=710, kingdom_id=11)
        with pytest.raises(ValueError):
            client.attack.fill_attack(12345, camp_victories=299, camp_kingdom_id=11)

        assert len(conn(client).request_payloads) == sent_before

    def test_the_owner_legend_level_comes_from_the_scan(self):
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            legendskills=[
                {
                    "skillID": "901",
                    "effectType": "additionalUnitAmountOnFlank",
                    "totalEffectValue": "30",
                    "level": "1",
                    "tier": "5",
                }
            ],
        )
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "castle"]
        widths = []
        for legend_level in (0, 5):
            client = self.build([[601, 100_000]])
            client.game_data = GameData.parse("test", payload)
            cast(Any, client.state.local_player).legendary_level = 1
            conn(client).script["aci"] = xt_packet("aci", {"gaa": {"AI": row}, "S": [], "AE": [], "B": {}})
            conn(client).script["gaa"] = xt_packet(
                "gaa", {"KID": 0, "AI": [row], "OI": [{"OID": 4242, "N": "owner", "L": 70, "LL": legend_level}]}
            )
            result = client.attack.fill_attack(
                12345, target_x=700, target_y=710, legend_skill_ids=[901], general_skill_ids=[]
            )
            widths.append(result.waves[0].model_dump(by_alias=True)["L"]["U"][0][1])

        # getAmountSoldiersFlank(70, 0) and (70, 30), from the client in node.
        assert widths == [64, 84]

    def test_the_owner_legend_level_comes_from_the_pre_calculation(self):
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            legendskills=[
                {
                    "skillID": "901",
                    "effectType": "additionalUnitAmountOnFlank",
                    "totalEffectValue": "30",
                    "level": "1",
                    "tier": "5",
                }
            ],
        )
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "castle"]
        client = self.build([[601, 100_000]])
        client.game_data = GameData.parse("test", payload)
        cast(Any, client.state.local_player).legendary_level = 1
        conn(client).script["aci"] = xt_packet(
            "aci",
            {"gaa": {"AI": row, "OI": [{"OID": 4242, "N": "owner", "L": 70, "LL": 5}]}, "S": [], "AE": [], "B": {}},
        )

        result = client.attack.fill_attack(
            12345, target_x=700, target_y=710, target_row=row, legend_skill_ids=[901], general_skill_ids=[]
        )

        assert result.waves[0].model_dump(by_alias=True)["L"]["U"][0][1] == 84
        assert "gaa" not in [command for command, _ in conn(client).request_payloads]

    def test_conquer_control_rates_the_owner_by_their_own_level(self):
        # CastleFightScreenVO.targetOwnerLevel: the owner's level under conquer
        # control, the landmark's minimum owner level otherwise.
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            legendskills=[
                {"skillID": "902", "effectType": "additionalWave", "totalEffectValue": "1", "level": "1", "tier": "5"}
            ],
        )
        client = self.build([[601, 100_000]])
        client.game_data = GameData.parse("test", payload)
        cast(Any, client.state.local_player).legendary_level = 1
        capital = [3, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "capital"]

        def waves(controlled: bool) -> int:
            result = client.attack.fill_attack(
                12345,
                target_level=60,
                target_is_player=True,
                target_row=capital,
                target_owner_legend_level=5,
                landmark_min_level=70,
                under_conquer_control=controlled,
                legend_skill_ids=[902],
                general_skill_ids=[],
            )
            return len(result.waves)

        assert waves(True) < waves(False)

    def test_a_conquest_attack_carries_its_extra_waves(self):
        client = self.build([[601, 100_000]])

        plain = client.attack.fill_attack(12345, target_level=70, target_is_player=True)
        conquest = client.attack.fill_attack(12345, target_level=70, target_is_player=True, conquer=True)

        assert len(conquest.waves) == len(plain.waves) + 2

    def test_the_legend_tool_skill_widens_the_tool_capacity(self):
        # additionalAttackToolAmountFlank, which applies only in a legendary
        # fight, was resolved and then never used.
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            units=[
                *self.UNITS["units"],
                {
                    "wodID": 614,
                    "name": "Workshop",
                    "type": "Ladder",
                    "typ": "Attack",
                    "slotTypes": "1,2,9",
                    "wallBonus": "1",
                    "fightType": "1",
                },
            ],
            legendskills=[
                # Live shape: the value lives in totalEffectValue.
                {
                    "skillID": "900",
                    "effectType": "additionalAttackToolAmountFlank",
                    "totalEffectValue": "30",
                    "level": "1",
                    "tier": "5",
                }
            ],
        )
        from empire_core.combat import DefenderFlankEffects, Flank

        client = self.build([[601, 100_000], [614, 100_000]])
        client.game_data = GameData.parse("test", payload)
        # A wall the ladders cannot fully cancel, so the flank fills to capacity.
        defense = {
            flank: DefenderFlankEffects(wall_bonus=99.0)
            for flank in (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT, Flank.YARD)
        }

        target = dict(level=70, target_is_player=True, area_type=1, owner_id=4242, defense=defense)
        plain = client.attack.fill_waves(12345, **target)
        skilled = client.attack.fill_waves(12345, legend_skill_ids=[900], **target)
        camp = client.attack.fill_waves(
            12345, level=70, area_type=2, owner_id=-202, defense=defense, legend_skill_ids=[900]
        )

        placed = lambda waves: sum(c for _, c in waves[0].model_dump(by_alias=True)["L"]["T"])  # noqa: E731
        # CastleAttackWaveVO sizes a flank for int(ceil(40 + 30)) tools only
        # against another player's object; an NPC camp gets the base 40.
        assert (placed(plain), placed(skilled), placed(camp)) == (40, 70, 40)

    def test_legend_flank_skills_need_a_legend_owner(self):
        # A level 70 player without legend levels is not a legendary fight for
        # the unit amount; one with legend levels is (AttackDialogHelper.isLegendaryFight).
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            legendskills=[
                {
                    "skillID": "901",
                    "effectType": "additionalUnitAmountOnFlank",
                    "totalEffectValue": "30",
                    "level": "1",
                    "tier": "5",
                },
                {"skillID": "902", "effectType": "additionalWave", "totalEffectValue": "1", "level": "1", "tier": "5"},
            ],
        )
        client = self.build([[601, 100_000]])
        client.game_data = GameData.parse("test", payload)
        target = dict(level=70, target_is_player=True, area_type=1, owner_id=4242, legend_skill_ids=[901, 902])

        capped = client.attack.fill_waves(12345, attacker_legend_level=1, owner_legend_level=0, **target)
        legend = client.attack.fill_waves(12345, attacker_legend_level=1, owner_legend_level=4, **target)
        not_legend = client.attack.fill_waves(12345, attacker_legend_level=0, owner_legend_level=4, **target)

        left = lambda waves: waves[0].model_dump(by_alias=True)["L"]["U"][0][1]  # noqa: E731
        # getAmountSoldiersFlank(70, 0) and (70, 30), from the client in node.
        assert (left(capped), left(legend), left(not_legend)) == (64, 84, 64)
        # getMaxWaveCountWithBonus(70, false, 0 or 1): the extra wave needs a
        # legend attacker and a target level of 70, not a legend owner.
        assert (len(capped), len(legend), len(not_legend)) == (5, 5, 4)

    def test_the_targets_kingdom_reaches_the_tool_gate(self):
        # A tool limited to Berimond (kingdom 10) may be carried there and
        # nowhere else.
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            units=[
                *self.UNITS["units"],
                {
                    "wodID": 613,
                    "name": "Workshop",
                    "type": "Ladder",
                    "typ": "Attack",
                    "slotTypes": "1,2,9",
                    "wallBonus": "20",
                    "allowedToAttack": "10+1",
                    "fightType": "1",
                },
            ],
        )
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "small castle"]

        def fill(kingdom_id):
            client = self.build([[601, 100_000], [613, 500]])
            client.game_data = GameData.parse("test", payload)
            conn(client).script["aci"] = xt_packet("aci", {"gaa": {"AI": row}, "AE": [], "B": {}})
            conn(client).script["gaa"] = xt_packet(
                "gaa", {"KID": kingdom_id, "AI": [row], "OI": [{"OID": 900, "PID": 4242, "L": 13}]}
            )
            result = client.attack.fill_attack(
                12345, target_x=700, target_y=710, kingdom_id=kingdom_id, target_is_player=True
            )
            return [wod for wod, _ in result.waves[0].model_dump(by_alias=True)["M"]["T"]]

        assert 613 in fill(10)
        assert 613 not in fill(0)

    def test_the_castellan_reaches_the_defense(self):
        # It was accepted as a parameter and dropped on the way to the defense,
        # so the target's fortification came out far too low.
        from empire_core.gamedata import GameData
        from empire_core.protocol.models import Commander

        payload = dict(
            self.UNITS,
            units=[
                *self.UNITS["units"],
                # A ladder, so a better-defended wall costs more tools.
                {
                    "wodID": 612,
                    "name": "Workshop",
                    "type": "Ladder",
                    "typ": "Attack",
                    "slotTypes": "1,2,9",
                    "wallBonus": "20",
                    "fightType": "1",
                },
            ],
            effecttypes=[{"effectTypeID": "6", "name": "wallBonus"}],
            effects=[{"effectID": "515", "name": "newDefenseWallBonusPVP", "effectTypeID": "6", "capID": "99"}],
        )
        client = self.build([[601, 100_000], [611, 500], [612, 500]])
        client.game_data = GameData.parse("test", payload)
        row = [1, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "small castle"]
        army = SpyArmy.from_spy_data([[[601, 10]], [], [], [], [], [], []])
        # A castellan worth +200% wall protection.
        castellan = Commander.model_validate({"ID": 1, "E": [[515, [200.0], "EQ"]], "EQ": [], "AE": []})

        plain = client.attack.fill_attack(12345, target_level=13, target_is_player=True, target_row=row, spy_army=army)
        held = client.attack.fill_attack(
            12345,
            target_level=13,
            target_is_player=True,
            target_row=row,
            spy_army=army,
            defending_castellan=castellan,
        )

        # A better-defended wall needs more siege tools.
        placed = lambda a: sum(c for _, c in a.waves[0].model_dump(by_alias=True)["M"]["T"])  # noqa: E731
        assert placed(held) > placed(plain)

    def test_the_defenders_legend_skills_reach_the_defense(self):
        from empire_core.gamedata import GameData

        payload = dict(
            self.UNITS,
            units=[
                *self.UNITS["units"],
                {
                    "wodID": 612,
                    "name": "Workshop",
                    "type": "Ladder",
                    "typ": "Attack",
                    "slotTypes": "1,2,9",
                    "wallBonus": "20",
                    "fightType": "1",
                },
            ],
            # Items payload v786.03 row: the top wall bonus legend skill.
            legendskills=[{"skillID": "434", "effectType": "wallBonus", "totalEffectValue": "30"}],
        )
        client = self.build([[601, 100_000], [611, 500], [612, 500]])
        client.game_data = GameData.parse("test", payload)
        row = [1, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "small castle"]
        army = SpyArmy.from_spy_data([[[601, 10]], [], [], [], [], [], []])

        plain = client.attack.fill_attack(12345, target_level=13, target_is_player=True, target_row=row, spy_army=army)
        skilled = client.attack.fill_attack(
            12345,
            target_level=13,
            target_is_player=True,
            target_row=row,
            spy_army=army,
            defender_legend_skill_ids=[434],
        )

        placed = lambda a: sum(c for _, c in a.waves[0].model_dump(by_alias=True)["M"]["T"])  # noqa: E731
        assert placed(skilled) > placed(plain)

    def test_the_precalculation_supplies_the_defenders_legend_skills(self):
        from empire_core.attack.service import _Target

        client = self.build([[601, 100_000]])
        army = SpyArmy.from_spy_data([[[601, 10]], [], [], [], [], [], []])

        def info(spy):
            return SimpleNamespace(
                target_row=lambda: None,
                spy_army=lambda: spy,
                defending_castellan=lambda: None,
                attacker_bonuses=lambda: [],
                owner_records=lambda: [],
                defender_legend_skill_ids=[434],
            )

        spied = _Target(x=5, y=6)
        client.attack.get_attack_info = lambda **_: info(army)
        client.attack._read_precalculation(spied, timeout=1.0)
        assert spied.defender_legend_skill_ids == [434]

        unspied = _Target(x=5, y=6)
        client.attack.get_attack_info = lambda **_: info(None)
        client.attack._read_precalculation(unspied, timeout=1.0)
        assert unspied.defender_legend_skill_ids is None

    def test_the_inventory_is_read_once(self):
        client = self.build([[601, 100_000]])

        client.attack.fill_attack(12345, target_level=13)

        sent = [command for command, _ in conn(client).request_payloads]
        assert sent.count("gui") == 1

    def test_the_courtyard_cannot_re_spend_the_waves_troops(self):
        # One pool for both passes: what the waves take is already gone.
        client = self.build([[601, 300]])

        result = client.attack.fill_attack(12345, target_level=13)

        assert result.unit_count() <= 300

    def test_a_given_inventory_is_used_instead_of_reading_one(self):
        from empire_core.combat import Inventory

        client = self.build([[601, 100_000]])

        waves = client.attack.fill_waves(12345, level=13, inventory=Inventory({601: 40}))

        sent = [command for command, _ in conn(client).request_payloads]
        assert "gui" not in sent
        assert sum(w.unit_count() for w in waves) == 40

    def test_the_attacking_castle_is_joined_once_for_the_inventory_after_a_scan(self):
        # Scanning moves the client off the castle; only the inventory read is
        # castle-scoped, and it joins the castle itself.
        client = self.build([[601, 100_000]])
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "small castle"]
        conn(client).script["aci"] = xt_packet("aci", {"gaa": {"AI": row}, "AE": [], "B": {}})
        conn(client).script["gaa"] = xt_packet(
            "gaa", {"KID": 0, "AI": [row], "OI": [{"OID": 900, "PID": 4242, "L": 46}]}
        )

        client.attack.fill_attack(12345, target_x=700, target_y=710)

        # The select is acknowledged as jaa, which is what the client waits on.
        sent = [command for command, _ in conn(client).request_payloads]
        assert sent == ["gaa", "aci", "skl", "jaa", "gui"]

    def test_a_pre_calculation_with_the_inventory_leaves_the_session_on_the_map(self):
        # The attack is sent from the map, as the client sends it, so nothing rejoins the castle.
        client = self.build([[601, 100_000]])
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "small castle"]
        conn(client).script["aci"] = xt_packet(
            "aci", {"gaa": {"AI": row}, "gui": {"I": [[601, 100_000]]}, "AE": [], "B": {}}
        )
        conn(client).script["gaa"] = xt_packet(
            "gaa", {"KID": 0, "AI": [row], "OI": [{"OID": 900, "PID": 4242, "L": 46}]}
        )

        client.attack.fill_attack(12345, target_x=700, target_y=710)

        assert [command for command, _ in conn(client).request_payloads] == ["gaa", "aci", "skl"]

    def test_a_camp_is_pre_calculated_with_adi(self):
        # aci on a camp is refused with INVALID_AREA; the client asks adi.
        client = self.build([[601, 100_000]])
        # Type 2 is a camp; field 3 is the espionage age and field 6 the count.
        camp_row = [2, 700, 710, -1, 0, -1, -299]
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [camp_row], "OI": []})
        conn(client).script["adi"] = xt_packet("adi", dict(LIVE_ADI, gaa={"AI": camp_row}, gui={"I": [[601, 100_000]]}))

        result = client.attack.fill_attack(12345, target_x=700, target_y=710, kingdom_id=0, source_x=5, source_y=6)

        sent = dict(conn(client).request_payloads)
        assert "aci" not in sent
        assert sent["adi"] == {"KID": 0, "SX": 5, "SY": 6, "TX": 700, "TY": 710}
        assert result.waves

    def test_the_stronghold_units_join_the_army(self):
        # AttackDialogUnitPicker adds gui.SHI into the inventory the dialog fills from
        client = self.build([])
        camp_row = [2, 700, 710, -1, 0, -1, -299]
        gui = {"I": [[601, 10]], "SHI": [[601, 100_000]]}
        conn(client).script["adi"] = xt_packet("adi", dict(LIVE_ADI, gaa={"AI": camp_row}, gui=gui))

        result = client.attack.fill_attack(12345, target_x=700, target_y=710, area_type=2)

        placed = sum(
            n
            for wave in result.waves
            for flank in (wave.left, wave.middle, wave.right)
            for wod, n in flank.units
            if wod == 601
        )
        assert placed > 10

    def test_the_army_comes_from_the_pre_calculation(self):
        # CastleAttackInfoVO fills the attack dialog's army from gui.I, so no gui is sent,
        # and a map scan that moved the session off its castle does not matter
        client = self.build([[601, 5]])
        camp_row = [2, 700, 710, -1, 0, -1, -299]
        conn(client).script["adi"] = xt_packet("adi", dict(LIVE_ADI, gaa={"AI": camp_row}, gui={"I": [[601, 100_000]]}))

        result = client.attack.fill_attack(12345, target_x=700, target_y=710, area_type=2)

        assert "gui" not in [command for command, _ in conn(client).request_payloads]
        placed = sum(
            n
            for wave in result.waves
            for flank in (wave.left, wave.middle, wave.right)
            for wod, n in flank.units
            if wod == 601
        )
        assert placed > 5

    def test_a_given_area_type_needs_no_scan_for_the_command(self):
        client = self.build([[601, 100_000]])
        camp_row = [2, 700, 710, -1, 0, -1, -299]
        conn(client).script["adi"] = xt_packet("adi", dict(LIVE_ADI, gaa={"AI": camp_row}, gui={"I": [[601, 100_000]]}))

        result = client.attack.fill_attack(12345, target_x=700, target_y=710, area_type=2)

        # A camp needs no scan for a level either: the count implies it.
        assert "gaa" not in [command for command, _ in conn(client).request_payloads]
        assert result.waves

    def test_a_refused_precalculation_falls_back_to_the_map(self):
        # The server refuses the pre-calculation for anything it will not let
        # this player hit, but the map still describes the tile.
        client = self.build([[601, 100_000]])
        camp_row = [2, 700, 710, -1, 0, -1, -299]
        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [camp_row], "OI": []})

        result = client.attack.fill_attack(12345, target_x=700, target_y=710)

        assert result.waves
        # The scan is castle-scoped work too, so the fill returns home first.
        order = [e for e in conn(client).events if any(c in e for c in ("gaa", "jaa", "gui"))]
        scanned = next(i for i, e in enumerate(order) if "gaa" in e)
        reselected = next(i for i, e in enumerate(order) if "jaa" in e)
        inventory = next(i for i, e in enumerate(order) if "gui" in e)
        assert scanned < reselected < inventory

    def test_a_failed_tile_scan_still_tries_the_pre_calculation_once(self):
        from empire_core.attack.service import _Target

        client = self.build([[601, 100_000]])
        conn(client).script["gaa"] = EmpireTimeoutError("no gaa")
        target = _Target(x=700, y=710)

        client.attack._read_target(target, castle_id=12345, timeout=1.0)

        sent = [command for command, _ in conn(client).request_payloads]
        assert sent.count("gaa") == 1
        assert "aci" in sent

    def test_a_pre_calculation_without_a_row_leaves_the_map_to_supply_it(self):
        from empire_core.attack.service import _Target

        client = self.build([[601, 100_000]])
        outpost_row = [4, 700, 710, 55, 4242, 1, 1, 1, 0, 0, "outpost"]
        conn(client).script["coi"] = xt_packet("coi", {"AB": 1, "MB": 2})
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [outpost_row], "OI": []})
        target = _Target(x=700, y=710, area_type=4, conquer=True)

        client.attack._read_target(target, castle_id=12345, timeout=1.0)

        assert target.row == outpost_row

    def test_a_samurai_camp_starts_at_the_players_own_league(self):
        # The row carries no level: it starts where the player's league band
        # starts and climbs with every defeat the camp has taken.
        client = self.build([[601, 100_000]])
        row = [29, 700, 710, -1, 4, 0, 0, 0, -1, 110, 110, 0]
        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [row], "OI": []})

        result = client.attack.fill_attack(12345, target_x=700, target_y=710)

        # Level 70 sits in the second band, which starts at 81, plus 4 defeats.
        # Which level exactly is pinned in test_combat; here it is that the
        # target fills at all, where it used to have no level to fill for.
        assert result.waves

    def test_a_daimyo_rank_carries_its_level(self):
        client = self.build([[601, 100_000]])
        # Field 4 is the rank, not a victory count: rank 1 is level 81.
        row = [37, 700, 710, -1, 1, 0, 0, 0, -1, 110, 110, 0]
        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [row], "OI": []})

        result = client.attack.fill_attack(12345, target_x=700, target_y=710)

        assert result.waves

    def test_a_scaled_camp_takes_the_difficulty_level(self):
        client = self.build([[601, 100_000]])
        # Field 8 names a difficulty scaling camp, which overrides the rank.
        row = [37, 700, 710, -1, 1, 0, 0, 0, 3, 110, 110, 0]
        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [row], "OI": []})

        result = client.attack.fill_attack(12345, target_x=700, target_y=710)

        assert result.waves

    def test_an_invasion_camp_reports_protection_as_a_percentage(self):
        # Fields 9 to 11 are bonuses already, not building levels: read as
        # levels they would be looked up in the fortification table and lost.
        from empire_core.map.models.items import MapAreaItem

        item = MapAreaItem.from_list([37, 700, 710, -1, 1, 0, 0, 15, -1, 110, 110, 0])

        assert item.is_invasion_camp
        assert (item.base_wall_bonus, item.base_gate_bonus, item.base_moat_bonus) == (110.0, 110.0, 0.0)
        assert MapAreaItem.from_list([1, 700, 710, 900, 4242, 1, 1, 1, 0, 0]).base_wall_bonus is None

    def test_an_invasion_camps_protection_is_divided_by_a_hundred(self):
        # FightScreenHelper.getDefenceBonuses (bundle line 19148) takes baseWallBonus / 100,
        # as fortification_bonuses does for a castle's buildings
        from empire_core.attack.service import _Target
        from empire_core.enums import Flank

        client = self.build([[601, 100_000]])
        assert client.game_data is not None
        target = _Target(x=700, y=710, row=[27, 700, 710, -1, 4, 0, 0, 0, -1, 110, 120, 30])

        defense = client.attack._target_defense(client.game_data, target)

        assert defense is not None
        left, middle = defense[Flank.LEFT], defense[Flank.MIDDLE]
        assert (left.wall_bonus, left.gate_bonus, left.moat_bonus) == pytest.approx((1.1, 0.0, 0.3))
        assert middle.gate_bonus == pytest.approx(1.2)

    def test_an_alien_camps_row_gives_its_protection_and_level(self):
        # A captured red alien camp row; AAlienInvasionMapobjectVO returns fields 6 to 8 as its bonuses
        from empire_core.attack.service import _Target
        from empire_core.enums import Flank

        client = self.build([[601, 100_000]])
        assert client.game_data is not None
        row = [34, 619, 242, 70, -1, 0, 120, 120, 45, 0, -1]
        target = _Target(x=619, y=242, row=row)

        defense = client.attack._target_defense(client.game_data, target)

        assert defense is not None
        left, middle = defense[Flank.LEFT], defense[Flank.MIDDLE]
        assert (left.wall_bonus, middle.gate_bonus, left.moat_bonus) == pytest.approx((1.2, 1.2, 0.45))

        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [row], "OI": []})
        read = _Target(x=619, y=242)
        client.attack._read_target(read, castle_id=12345, timeout=1.0)
        assert (read.row, read.level) == (row, 70)
        assert conn(client).requested.count("gaa") == 1

    def test_the_wolf_king_and_alliance_camps_take_their_rows_protection(self):
        from empire_core.attack.service import _Target
        from empire_core.enums import Flank

        client = self.build([[601, 100_000]])
        assert client.game_data is not None
        for row in (
            [42, 1, 2, 60, 12, 0, 40, 50, 60],
            [35, 1, 2, 60, 8, 100, 500, 20, 6, 3, 40, 50, 60],
            [40, 1, 2, 60, 8, 100, 500, 20, 6, 3, 40, 50, 60],
        ):
            defense = client.attack._target_defense(client.game_data, _Target(x=1, y=2, row=row))
            assert defense is not None
            middle = defense[Flank.MIDDLE]
            assert (middle.wall_bonus, middle.gate_bonus, middle.moat_bonus) == pytest.approx((0.4, 0.5, 0.6)), row

    def test_an_unknown_camp_rank_says_which_rank(self):
        client = self.build([[601, 100_000]])
        # Rank 99 is a daimyo castle the trimmed tables do not describe.
        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet(
            "gaa", {"KID": 0, "AI": [[37, 700, 710, -1, 99, 0, 0, 0, -1, 110, 110, 0]], "OI": []}
        )

        with pytest.raises(ValueError, match="no camp 99 for area type 37"):
            client.attack.fill_attack(12345, target_x=700, target_y=710)

    def test_a_tile_the_map_does_not_describe_says_so(self):
        client = self.build([[601, 100_000]])
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [], "OI": []})

        with pytest.raises(ValueError, match="neither the map nor a pre-calculation has a row for it"):
            client.attack.fill_attack(12345, target_x=700, target_y=710)

    def test_a_target_with_no_level_anywhere_says_so(self):
        client = self.build([[601, 100_000]])
        # An alien camp: not an invasion camp this knows, and no owner record
        # carries a level for it either.
        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet(
            "gaa", {"KID": 0, "AI": [[21, 700, 710, -1, 0, -1, 0, 0, -1, 110, 110, 0]], "OI": []}
        )

        with pytest.raises(ValueError, match="no owner level"):
            client.attack.fill_attack(12345, target_x=700, target_y=710)

    def test_what_is_passed_is_not_re_read(self):
        client = self.build([[601, 100_000]])
        row = [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "small castle"]

        client.attack.fill_attack(
            12345,
            target_x=700,
            target_y=710,
            target_level=13,
            target_owner_legend_level=0,
            target_row=row,
            spy_army=SpyArmy.from_spy_data([[], [], [], [], [], [], []]),
            defending_castellan=Commander.model_validate({"ID": 1}),
            area_bonuses=[],
            general_skill_ids=[],
            legend_skill_ids=[],
        )

        sent = [command for command, _ in conn(client).request_payloads]
        assert "aci" not in sent and "gaa" not in sent

    def test_a_monument_is_sized_for_its_own_level(self):
        from empire_core.enums import MapItemType

        client = self.build([[601, 100_000]])

        low = client.attack.fill_attack(12345, target_level=12, area_type=MapItemType.CASTLE)
        landmark = client.attack.fill_attack(12345, target_level=12, area_type=MapItemType.MONUMENT)

        assert landmark.waves[0].unit_count() > low.waves[0].unit_count()

    def test_a_conquered_target_sizes_the_courtyard_from_the_area(self):
        from empire_core.enums import MapItemType

        client = self.build([[601, 1_000_000]])

        owner = client.attack.fill_attack(12345, target_level=12, area_type=MapItemType.KINGS_TOWER)
        conquered = client.attack.fill_attack(
            12345, target_level=12, area_type=MapItemType.KINGS_TOWER, under_conquer_control=True
        )

        placed = lambda a: sum(p[1] for p in a.yard if p[0] != -1)  # noqa: E731
        # The tower defends at 70 whoever holds it, so its courtyard is larger.
        assert placed(conquered) > placed(owner)

    def test_an_overfull_army_is_refused_before_sending(self):
        from empire_core.combat import WaveCapacity

        client = self.build([[601, 100_000]])
        capacity = WaveCapacity.for_level(70)
        too_big = wave(units=[[601, capacity.flank_soldiers + 50]])

        with pytest.raises(ValueError, match="exceeds what a wave may carry"):
            client.attack.send_attack(500, 510, 700, 710, [too_big], 0, capacity=capacity)

    def test_a_buffed_unit_wins_the_courtyard_too(self):
        # 601 hits harder on paper; a global effect makes 602 the better pick,
        # and the courtyard runs the same pick as a flank.
        from empire_core.gamedata import GameData

        payload = {
            "units": [
                {"wodID": 601, "name": "Barracks", "role": "melee", "meleeAttack": "100", "fightType": "0"},
                {"wodID": 602, "name": "Barracks", "role": "melee", "meleeAttack": "90", "fightType": "0"},
            ],
            "effecttypes": [{"effectTypeID": "148", "name": "attackBonusUnit"}],
            "effects": [{"effectID": "273", "name": "attackBonusUnit", "effectTypeID": "148", "capID": "99"}],
            "globalEffects": [{"globalEffectID": "5", "name": "boost602", "effects": "273&602+50"}],
        }
        client = self.build([[601, 100_000], [602, 100_000]])
        client.game_data = GameData.parse("test", payload)

        plain = client.attack.fill_attack(12345, target_level=13)
        buffed = client.attack.fill_attack(12345, target_level=13, global_effect_ids=[5])

        assert plain.yard[0][0] == 601
        assert buffed.yard[0][0] == 602

    def test_the_row_supplies_the_area_type_a_tool_is_gated_on(self):
        # The ram may only be carried against an area type 2. A castle row is
        # type 1, so it must not appear.
        client = self.build([[601, 100_000], [611, 500]])
        client.game_data.get_tool(611).raw_allowed_to_attack = "0+2"
        row = [1, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "small castle"]

        result = client.attack.fill_attack(12345, target_level=13, target_is_player=True, target_row=row)

        assert placed(result.waves[0].model_dump(by_alias=True)["M"]["T"]) == []

    def test_the_same_tool_is_carried_when_the_row_matches(self):
        client = self.build([[601, 100_000], [611, 500]])
        client.game_data.get_tool(611).raw_allowed_to_attack = "0+1"
        row = [1, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "small castle"]

        result = client.attack.fill_attack(12345, target_level=13, target_is_player=True, target_row=row)

        assert placed(result.waves[0].model_dump(by_alias=True)["M"]["T"]) == [[611, 1]]

    def test_no_game_data_is_an_error(self):
        from empire_core.exceptions import GameDataNotLoadedError

        client = make_client()
        with pytest.raises(GameDataNotLoadedError):
            client.attack.fill_attack(12345, target_level=13)


class TestFillAttackLevelDerivation:
    def test_a_camp_level_follows_from_its_victories(self):
        from empire_core.combat import camp_level
        from empire_core.gamedata import GameData

        client = make_client({"gui": xt_packet("gui", {"I": [[601, 10_000]]})})
        client.game_data = GameData.parse(
            "test",
            {
                "units": [
                    {"wodID": 601, "name": "B", "type": "S", "role": "melee", "meleeAttack": "100", "fightType": "0"}
                ]
            },
        )
        client.state.local_player = stub_player(level=70)

        # 299 victories in the green kingdom is a level 45 camp.
        assert camp_level(299, Kingdom.GREEN) == 45
        # DungeonConst.getKingdomOffset (dll line 19137) takes the kingdom id.
        assert camp_level(299, Kingdom.SANDS) == 45 - 1 + 35
        assert camp_level(299, Kingdom.STORM) == 45 - 1
        result = client.attack.fill_attack(12345, camp_victories=299, camp_kingdom_id=Kingdom.GREEN)

        # Level 45 gives 47 units per flank before bonuses.
        assert placed(result.waves[0].model_dump(by_alias=True)["L"]["U"]) == [[601, 47]]

    def test_neither_level_nor_victories_is_an_error(self):
        from empire_core.gamedata import GameData

        client = make_client()
        client.game_data = GameData.parse("test", {"units": []})

        with pytest.raises(ValueError, match="target_level"):
            client.attack.fill_attack(12345)
