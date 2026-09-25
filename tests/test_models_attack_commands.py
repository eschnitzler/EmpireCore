"""Attack-side request and reply models, checked against the payloads the game client builds."""

import json

from empire_core.protocol.models import (
    AttackPreset,
    AttackWave,
    CreateAttackRequest,
    GetPresetsRequest,
    GetPresetsResponse,
    MinuteSkipDungeonRequest,
    MinuteSkipDungeonResponse,
    PresetArmy,
    SavePresetRequest,
    SkipDungeonCooldownRequest,
    SkipDungeonCooldownResponse,
    WaveFlank,
    parse_response,
)


class TestDungeonCooldownSkips:
    def test_minute_skip_sends_the_client_keys_with_kingdom_as_string(self):
        request = MinuteSkipDungeonRequest(MST="MS2", KID=2, X=100, Y=200)
        payload = request.to_payload()
        assert list(payload.items()) == [("X", 100), ("Y", 200), ("MID", -1), ("NID", -1), ("MST", "MS2"), ("KID", "2")]

    def test_minute_skip_on_a_treasure_map_node(self):
        request = MinuteSkipDungeonRequest(MST="MS1", KID=0, X=5, Y=6, MID=3, NID=12)
        assert request.to_payload()["MID"] == 3
        assert request.to_payload()["NID"] == 12
        assert json.loads(request.to_packet().split("%")[5])["KID"] == "0"

    def test_full_skip_sends_the_client_keys_with_kingdom_as_number(self):
        request = SkipDungeonCooldownRequest(X=100, Y=200, KID=2)
        assert list(request.to_payload().items()) == [("X", 100), ("Y", 200), ("KID", 2), ("MID", -1), ("NID", -1)]

    def test_full_skip_on_a_treasure_map_node(self):
        payload = SkipDungeonCooldownRequest(X=1, Y=2, KID=0, MID=7, NID=4).to_payload()
        assert (payload["MID"], payload["NID"]) == (7, 4)

    def test_replies_carry_the_dungeon_row(self):
        row = [2, 100, 200, -1, 12, 0, 0]
        assert isinstance(parse_response("msd", {"AI": row}), MinuteSkipDungeonResponse)
        assert isinstance(parse_response("sdc", {"AI": row}), SkipDungeonCooldownResponse)
        area = SkipDungeonCooldownResponse.model_validate({"AI": row}).area
        assert area is not None
        assert (area.x, area.y, area.victory_count, area.attack_cooldown_seconds) == (100, 200, 12, 0)
        minute_skip = MinuteSkipDungeonResponse.model_validate({"AI": [2, 1, 2, -1, 3, 540, 0]}).area
        assert minute_skip is not None and minute_skip.attack_cooldown_seconds == 540
        assert not hasattr(SkipDungeonCooldownResponse.model_validate({"AI": row}), "rubies_spent")


# Live capture of a gas reply for an account with one untouched slot
LIVE_GAS = {"S": [{"S": 0, "A": None, "SN": None}]}

# Inputs and outputs of the client's FightPresetVO, run in node
SEVEN_ARRAYS = "[[1,2],[3,4,5,6],[],[10,20,11,21],[12,22],[13,23],[7,8,-1]]"
SIX_ARRAYS = "[[1,2],[],[],[10,20],[],[]]"
WAVE_SAVED_AS = "[[1,2],[],[3,4],[10,20,11,5],[],[12,7]]"


class TestAttackPresets:
    def test_get_presets_sends_an_empty_payload(self):
        assert GetPresetsRequest().to_payload() == {}

    def test_live_reply_with_an_empty_slot(self):
        response = parse_response("gas", LIVE_GAS)
        assert isinstance(response, GetPresetsResponse)
        assert [preset.index for preset in response.presets] == [0]
        assert response.presets[0].name is None
        assert response.presets[0].army() is None

    def test_seven_arrays_carry_support_tools(self):
        preset = GetPresetsResponse.model_validate({"S": [{"S": 2, "SN": "Farm", "A": SEVEN_ARRAYS}]}).presets[0]
        army = preset.army()
        assert army is not None
        assert preset.name == "Farm"
        assert army.support_tools == [7, 8, -1]
        assert army.middle_tools[0] == [1, 2]
        assert army.left_tools[1] == [5, 6]
        assert army.right_tools == []
        assert army.middle_units[1] == [11, 21]

    def test_six_arrays_have_no_support_tools(self):
        army = AttackPreset.model_validate({"S": 0, "A": SIX_ARRAYS}).army()
        assert army is not None
        assert army.support_tools == [-1, -1, -1]

    def test_unparsable_army_reads_as_none(self):
        assert AttackPreset.model_validate({"S": 0, "A": "not json"}).army() is None

    def test_null_entries_are_skipped(self):
        response = GetPresetsResponse.model_validate({"S": [None, {"S": 1}]})
        assert [preset.index for preset in response.presets] == [1]

    def test_save_from_wave_matches_the_client(self):
        wave = AttackWave(
            M=WaveFlank(T=[[1, 2], [-1, 0]], U=[[10, 20], [-1, 0], [11, 5]]),
            L=WaveFlank(T=[[-1, 0]], U=[[-1, 0], [-1, 0]]),
            R=WaveFlank(T=[[3, 4]], U=[[12, 7]]),
        )
        request = SavePresetRequest.create(3, PresetArmy.from_wave(wave))
        assert request.command == "sas"
        assert request.to_payload() == {"S": 3, "A": WAVE_SAVED_AS}

    def test_save_from_a_padded_wave_drops_the_empty_slots(self):
        wave = AttackWave(M=WaveFlank(T=[[-1, 0]] * 3, U=[[10, 20]] + [[-1, 0]] * 5))
        assert PresetArmy.from_wave(wave).to_arrays() == [[], [], [], [10, 20], [], []]

    def test_save_round_trips_through_the_reply(self):
        army = AttackPreset.model_validate({"S": 0, "A": SIX_ARRAYS}).army()
        assert army is not None
        assert SavePresetRequest.create(0, army).to_payload()["A"] == SIX_ARRAYS


class TestAttackRequestShapes:
    def test_cra_keys_follow_the_client_order(self):
        request = CreateAttackRequest(SX=1, SY=2, TX=3, TY=4, A=[AttackWave()])
        # C2SCreateArmyAttackMovementVO initialises SX..CD, then sets A, BKS, AST, RW, ASCT
        assert list(request.to_payload()) == [
            "SX", "SY", "TX", "TY", "KID", "LID", "WT", "HBW", "BPC", "ATT", "AV",
            "LP", "FC", "PTT", "SD", "ICA", "CD", "A", "BKS", "AST", "RW", "ASCT",
        ]  # fmt: skip

    def test_collector_boosters_are_currency_amount_pairs(self):
        # CastleFightScreenVO.addCollectorBooster pushes [boosterKey, amount]
        request = CreateAttackRequest(SX=1, SY=2, TX=3, TY=4, A=[AttackWave()], BKS=[[31, 2], [32, 0]])
        assert request.to_payload()["BKS"] == [[31, 2], [32, 0]]

    def test_wave_keys_follow_the_client_order(self):
        # CastleAttackWaveVO.getWaveInfoObject builds {L, R, M}, each {T, U}
        wave = AttackWave().model_dump(by_alias=True)
        assert list(wave) == ["L", "R", "M"]
        assert list(wave["L"]) == ["T", "U"]


class TestAttackInfoBlocks:
    def test_gaa_gui_and_gli_are_typed(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(
            {
                "gaa": {"AI": [2, 620, 231, -1, 4, 30, 0], "OI": [{"OID": 7, "L": 12, "LL": 3}, "junk"]},
                "gui": {"I": [["10", "4"], [11, 2], [11, 1]], "SHI": [[620, 5], [621, 0]]},
                "gli": {"C": [{"ID": 3, "N": "c"}], "B": [{"ID": 1}]},
            }
        )

        assert info.target_area.area is not None and info.target_area.area.victory_count == 4
        assert [(o.owner_id, o.level, o.legendary_level) for o in info.owner_records()] == [(7, 12, 3)]
        assert info.inventory() == {10: 4, 11: 3}
        assert info.stronghold_inventory() == {620: 5}
        assert [c.commander_id for c in info.commander_roster.commanders] == [3]
        assert [c.commander_id for c in info.commander_roster.castellans] == [1]

    def test_the_castellan_follows_the_client_abe_or_b(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        spied = {"S": [[[10, 1]], [], [], [], [], []], "AS": 5}
        castellan = {"ID": 4, "WID": 2}

        def picked(**blocks: object) -> int | None:
            chosen = GetAttackInfoResponse.model_validate({**spied, **blocks}).defending_castellan()
            return chosen.commander_id if chosen else None

        assert picked(abe={"ID": 9}, B=castellan) == 9
        assert picked(B=castellan) == 4
        assert picked(abe=None, B=castellan) == 4
        # {} is truthy in JavaScript, so the client never falls back to B, and builds no castellan from it
        assert picked(abe={}, B=castellan) is None
        assert picked(abe={"N": "no id"}, B=castellan) is None

    def test_spy_positions_are_read_through_int(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        # fillFromWodAmountArray skips non-arrays and reads int(i[0]), int(i[1])
        info = GetAttackInfoResponse.model_validate({"S": [[[487, "20"], "junk", [488, "x"]], "junk", [[10, 1]]]})

        assert info.spy_data == [[[487, 20], [488, 0]], [], [[10, 1]]]
        army = info.spy_army()
        assert army is not None
        assert [(s.wod_id, s.count) for s in army.left] == [(487, 20), (488, 0)]
        assert [(s.wod_id, s.count) for s in army.right] == [(10, 1)]

    def test_a_null_spy_block_is_no_report(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate({"S": None, "AS": 30, "LS": [5]})

        assert info.spy_army() is None
        assert (info.spy_age_seconds, info.defender_legend_skill_ids) == (-1, [])

    def test_attacker_effects_are_typed(self):
        from empire_core.combat import Bonus
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate({"AE": [[66, [30.0], "CI"], "junk", [67]]})

        assert [(e.effect_id, e.values, e.source) for e in info.attacker_effects] == [(66, [30.0], "CI"), (67, [], "")]
        assert info.attacker_bonuses() == [Bonus(effect_id=66, value=30.0, raw_values=(30.0,))]
