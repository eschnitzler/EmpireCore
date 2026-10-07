"""Tests for the attack service."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.combat import WaveCapacity
from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError, AttackBelowMinimumError, CommandError, UnknownCastleError
from empire_core.protocol.models import AttackType, Commander, CreateAttackRequest, CreateAttackResponse, MapItemType
from tests.service_helpers import LIVE_ADI, conn, make_client, placed, stub_player, wave, xt_packet

OWN = [(12345, Kingdom.GREEN, 500, 510)]

# Live capture of an ali reply for a kings tower, owner record trimmed and scrubbed.
LIVE_ALI: dict[str, Any] = dict(
    LIVE_ADI,
    gaa={
        "AI": [23, 630, 240, 4758767, 6537608, 0, -1, "630:240"],
        "OI": [
            {"OID": 6537608, "DUM": False, "N": "player", "L": 70, "LL": 950, "R": 0, "AID": 3318, "AN": "alliance"}
        ],
    },
)


class TestCreateAttackReply:
    # Live capture of a cra reply for a robber baron camp, names scrubbed.
    LIVE = {
        "AAM": {
            "M": {
                "MID": 93337642,
                "PT": 0,
                "TT": 71,
                "D": 0,
                "TID": -210,
                "T": 0,
                "HBW": -1,
                "KID": 0,
                "TA": [2, 623, 235, -1, 1, -2606959, 0],
                "SID": 17743261,
                "OID": 17743261,
                "SA": [1, 624, 234, 16654597, 17743261, 1, 1, 1, 1, 0, "castle", 0, 0, -1, -1, -1, 0, 0, [], 0],
            },
            "UM": {"PWD": 0, "TWD": 0, "L": {"ID": 0, "WID": 2, "VIS": 0, "N": "", "GID": -1, "EQ": [], "AE": []}},
            "FA": {"L": [[10, 2]], "M": [], "R": [], "RW": []},
            "AST": [],
            "ATT": 0,
            "ASCT": 0,
            "FC": 0,
        },
        "O": [{}, {"OID": 17743261, "DUM": False, "N": "player", "L": 9, "AID": -1}],
    }

    def test_the_owner_records_are_kept(self):
        reply = CreateAttackResponse.model_validate(self.LIVE)

        assert reply.movement_id == 93337642
        # parseOwnerInfo skips a record without an OID, so the {} goes.
        assert [(o.player_id, o.level, o.alliance_id) for o in reply.owners] == [(17743261, 9, -1)]
        # None of the live replies carried gcu.
        assert reply.currencies is None

    def test_the_movement_is_typed(self):
        reply = CreateAttackResponse.model_validate(self.LIVE)

        movement = reply.attack_movement
        assert movement is not None
        assert (movement.movement.target_id, movement.movement.total_time) == (-210, 71)
        assert movement.full_army is not None and movement.full_army.left == [[10, 2]]
        assert reply.leader is not None and reply.leader.commander_id == 0

    def test_the_currencies_are_kept(self):
        # CurrencyData.parseGCU reads C1 and C2.
        reply = CreateAttackResponse.model_validate(dict(self.LIVE, gcu={"C1": 1200, "C2": 30}))

        assert reply.currencies is not None
        assert (reply.currencies.coins, reply.currencies.rubies) == (1200, 30)

    def test_an_unreadable_owner_record_costs_only_itself(self):
        reply = CreateAttackResponse.model_validate({"O": ["junk", {"OID": 5, "L": "x"}, {"OID": 6}]})

        assert [o.player_id for o in reply.owners] == [6]

    def test_attack_in_progress_explains_itself(self):
        from empire_core.protocol.errors import GGEError
        from empire_core.protocol.models import CreateAttackRequest

        client = make_client({"cra": xt_packet("cra", {"TS": 95, "AS": 40}, error_code=234)}, castles=OWN)
        request = CreateAttackRequest(
            commander_id=0, source_x=1, source_y=2, target_x=3, target_y=4, waves=[wave(units=[[487, 1]])]
        )

        with pytest.raises(CommandError) as raised:
            client.send(request, wait=True)

        assert raised.value.error is GGEError.ATTACK_IN_PROGRESS
        reply = CreateAttackResponse.model_validate(raised.value.payload)
        assert (reply.arrival_seconds, reply.army_size) == (95, 40)


class TestAttackService:
    def test_an_attack_already_on_its_way_raises_with_its_details(self):
        from empire_core import AttackInProgressError

        client = make_client({"cra": xt_packet("cra", {"TS": 95, "AS": 120}, error_code=234)}, castles=OWN)

        with pytest.raises(AttackInProgressError) as caught:
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91)

        assert (caught.value.arrival_seconds, caught.value.army_size) == (95, 120)
        assert conn(client).request_payloads[0][1]["FC"] == 0

    def test_send_anyway_sets_fc(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, send_anyway=True)

        assert conn(client).request_payloads[0][1]["FC"] == 1

    def test_the_source_kingdom_is_read_from_the_castle_at_the_source_position(self):
        client = make_client(castles=[(12345, Kingdom.GREEN, 1, 2), (1, Kingdom.ICE, 500, 510)])

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91)

        assert conn(client).request_payloads[0][1]["KID"] == Kingdom.ICE

    def test_a_source_position_not_yours_raises_and_sends_nothing(self):
        client = make_client(castles=[(12345, Kingdom.GREEN, 1, 2)])

        with pytest.raises(UnknownCastleError) as raised:
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91)

        assert raised.value.position == (500, 510)
        assert conn(client).request_payloads == []

    def test_a_source_position_yours_in_two_kingdoms_needs_the_kingdom(self):
        client = make_client(castles=[(1, Kingdom.GREEN, 500, 510), (1, Kingdom.STORM, 500, 510)])
        args = (500, 510, 700, 710, [wave(units=[[487, 1]])])

        with pytest.raises(AmbiguousCastleError) as raised:
            client.attack.send_attack(*args, commander_id=91)
        client.attack.send_attack(*args, commander_id=91, kingdom_id=Kingdom.STORM)

        assert raised.value.kingdoms == [Kingdom.GREEN, Kingdom.STORM]
        assert [payload["KID"] for _, payload in conn(client).request_payloads] == [Kingdom.STORM]

    def test_a_given_source_kingdom_needs_no_castle_list(self):
        client = make_client(castles=[])

        client.attack.send_attack(
            500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, kingdom_id=Kingdom.SANDS
        )

        assert conn(client).request_payloads[0][1]["KID"] == Kingdom.SANDS

    def test_other_rejections_still_return_false(self):
        client = make_client({"cra": xt_packet("cra", None, error_code=219)}, castles=OWN)

        assert client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91) is False

    def test_send_attack_builds_the_client_payload(self):
        client = make_client(castles=OWN)

        sent = client.attack.send_attack(
            source_x=500,
            source_y=510,
            target_x=700,
            target_y=710,
            waves=[wave(units=[[487, 100]], tools=[[301, 5]])],
            kingdom_id=Kingdom.ICE,
            commander_id=91,
        )

        assert sent is True
        command, payload = conn(client).request_payloads[0]
        assert command == "cra"
        assert (payload["SX"], payload["SY"]) == (500, 510)
        assert (payload["TX"], payload["TY"]) == (700, 710)
        assert payload["KID"] == 2
        assert payload["LID"] == 91
        assert payload["A"] == [
            {"L": {"T": [[301, 5]], "U": [[487, 100]]}, "M": {"T": [], "U": []}, "R": {"T": [], "U": []}}
        ]
        assert payload["CD"] == 99
        assert payload["ATT"] == AttackType.ATTACK

    def test_the_courtyard_wave_rides_in_rw(self):
        client = make_client(castles=OWN)
        yard = [[487, 300], [601, 200]] + [[-1, 0]] * 6

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 0, yard_wave=yard)

        # Every slot goes out, empty ones included.
        assert conn(client).request_payloads[0][1]["RW"] == yard

    def test_no_courtyard_wave_sends_an_empty_rw(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 0)

        assert conn(client).request_payloads[0][1]["RW"] == []

    def test_commander_must_be_chosen_explicitly(self):
        # Every id gli reports leads an attack, 0 included, so there is no safe
        # value to default to.
        client = make_client(castles=OWN)
        with pytest.raises(TypeError):
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])])  # type: ignore[call-arg]

    def test_commander_is_sent_as_lid(self):
        client = make_client(castles=OWN)
        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 0)
        assert conn(client).request_payloads[0][1]["LID"] == 0

    def test_empty_waves_are_dropped_like_the_client_does(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]]), wave(tools=[[301, 5]]), wave()], 3)

        # A wave carrying only tools has no units, so the client never sends it.
        assert conn(client).request_payloads[0][1]["A"] == [
            {"L": {"T": [], "U": [[487, 1]]}, "M": {"T": [], "U": []}, "R": {"T": [], "U": []}}
        ]

    def test_attack_without_any_units_is_rejected_before_sending(self):
        client = make_client(castles=OWN)

        with pytest.raises(ValueError, match="no units"):
            client.attack.send_attack(500, 510, 700, 710, [wave()], 3)

        assert conn(client).requested == []

    def test_too_few_units_are_refused_before_sending(self):
        # Live: 1 unit on a level 16 castle came back as error 100 with MS 8
        client = make_client(castles=OWN)

        with pytest.raises(AttackBelowMinimumError) as caught:
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 3, min_soldiers=8)

        assert (caught.value.minimum, caught.value.soldiers, caught.value.attack) == (8, 1, None)
        assert conn(client).requested == []

    def test_the_minimum_comes_from_the_capacity(self):
        client = make_client(castles=OWN)

        with pytest.raises(AttackBelowMinimumError):
            client.attack.send_attack(
                500, 510, 700, 710, [wave(units=[[487, 7]])], 3, capacity=WaveCapacity.for_level(16)
            )

        assert conn(client).requested == []

    def test_the_minimum_counts_every_wave_but_not_the_courtyard(self):
        client = make_client(castles=OWN)

        with pytest.raises(AttackBelowMinimumError):
            client.attack.send_attack(
                500, 510, 700, 710, [wave(units=[[487, 7]])], 3, yard_wave=[[487, 50]], min_soldiers=8
            )
        assert client.attack.send_attack(
            500, 510, 700, 710, [wave(units=[[487, 4]]), wave(units=[[487, 4]])], 3, min_soldiers=8
        )

    def test_the_servers_refusal_of_too_few_units_is_false(self):
        client = make_client({"cra": xt_packet("cra", {"MS": 8}, error_code=100)}, castles=OWN)

        assert client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 3) is False

    def test_feathers_force_the_horse_field_to_minus_one(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 3, horse_booster_id=2, feathers=True)

        payload = conn(client).request_payloads[0][1]
        assert (payload["PTT"], payload["HBW"]) == (1, -1)

    def test_horses_survive_without_feathers(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 3, horse_booster_id=2, feathers=False)

        payload = conn(client).request_payloads[0][1]
        assert (payload["PTT"], payload["HBW"]) == (0, 2)

    def test_conquer_attack_type(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(
            500,
            510,
            700,
            710,
            [wave(units=[[487, 1]])],
            3,
            attack_type=AttackType.CONQUER,
        )

        assert conn(client).request_payloads[0][1]["ATT"] == 7

    def test_accepted_attack_reports_the_movement(self):
        # Shape captured from a live cra response.
        payload = {"AAM": {"M": {"MID": 5001, "TT": 132, "TA": [2, 510, 256, -1, 297, -900, 0]}}}
        client = make_client({"cra": xt_packet("cra", payload)}, castles=OWN)

        response = client.request(
            CreateAttackRequest(
                source_x=509,
                source_y=255,
                target_x=510,
                target_y=256,
                kingdom_id=Kingdom.GREEN,
                commander_id=1,
                waves=[wave(units=[[211, 5]])],
            ),
            CreateAttackResponse,
        )

        assert response.movement_id == 5001

    def test_response_without_a_movement_has_no_id(self):
        client = make_client({"cra": xt_packet("cra", {})}, castles=OWN)
        response = client.request(
            CreateAttackRequest(
                commander_id=0, source_x=1, source_y=1, target_x=2, target_y=2, waves=[wave(units=[[211, 1]])]
            ),
            CreateAttackResponse,
        )
        assert response.movement_id is None

    def test_fill_waves_needs_game_data(self):
        from empire_core.exceptions import GameDataNotLoadedError

        client = make_client(castles=OWN)

        with pytest.raises(GameDataNotLoadedError):
            client.attack.fill_waves(12345)

    def test_tools_are_drawn_from_the_same_inventory(self):
        # Tools live in the same gui inventory as units; filtering them out of
        # the pool made every wave tool-less regardless of the strategies.
        from empire_core.gamedata import GameData

        payload = {
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
            ]
        }
        client = make_client({"gui": xt_packet("gui", {"I": [[601, 5000], [611, 500]]})}, castles=OWN)
        client.game_data = GameData.parse("test", payload)
        client.state.local_player = stub_player(level=70)

        from empire_core.combat import DefenderFlankEffects, Flank

        waves = client.attack.fill_waves(
            12345,
            level=13,
            defense={
                f: DefenderFlankEffects(gate_bonus=0.30) for f in (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT, Flank.YARD)
            },
        )

        assert placed(waves[0].model_dump(by_alias=True)["M"]["T"]) == [[611, 1]]

    def test_a_commanders_own_equipment_widens_the_flanks(self):
        from empire_core.gamedata import GameData

        payload = {
            "units": [{"wodID": 601, "name": "Barracks", "role": "melee", "meleeAttack": "100", "fightType": "0"}],
            "effecttypes": [{"effectTypeID": "28", "name": "attackUnitAmountFlank"}],
            "effects": [{"effectID": "500", "name": "flankUnits", "effectTypeID": "28", "capID": "99"}],
        }
        client = make_client({"gui": xt_packet("gui", {"I": [[601, 100_000]]})}, castles=OWN)
        client.game_data = GameData.parse("test", payload)
        client.state.local_player = stub_player(level=70)
        # An equipped item worth +30% units on each side flank.
        commander = Commander.model_validate({"ID": 7, "EQ": [[1, 1, 2, 5, -1, [[500, [30.0]]], -1, -1, 0, -1, -1, 1]]})

        plain = client.attack.fill_waves(12345, level=13)
        widened = client.attack.fill_waves(12345, level=13, commander=commander)

        left = plain[0].model_dump(by_alias=True)["L"]["U"][0][1]
        wider = widened[0].model_dump(by_alias=True)["L"]["U"][0][1]
        assert wider > left
        # 20% of 73 attackers, then +30%: ceil(14.6 * 1.3).
        assert (left, wider) == (15, 19)

    def test_fill_waves_sizes_itself_from_the_target_level(self):
        from empire_core.gamedata import GameData

        payload = {
            "units": [{"wodID": 601, "name": "Barracks", "type": "Swordsman", "role": "melee", "meleeAttack": "100"}]
        }
        inventory = {"I": [[601, 10_000], [107, 50]], "U": [], "T": []}
        client = make_client({"gui": xt_packet("gui", inventory)}, castles=OWN)
        client.game_data = GameData.parse("test", payload)
        # Level 13 unlocks a second wave and 73 attackers per wave.
        client.state.local_player = stub_player(level=70)

        # A level 13 target: 73 attackers per wave, and the attacker's own
        # level decides that there are four waves.
        waves = client.attack.fill_waves(12345, level=13)

        assert len(waves) == 4
        assert waves[0].unit_count() == 73
        # 107 is a boost item in the inventory and must not be sent as an army.
        assert all(
            wod_id == 601
            for wave in waves
            for flank in wave.model_dump(by_alias=True).values()
            for wod_id, _count in placed(flank["U"])
        )

    def test_fill_waves_without_a_target_level_is_an_error_not_a_guess(self):
        # The attacker's own level would be the wrong answer, so there is no
        # default to fall back on.
        from empire_core.gamedata import GameData

        client = make_client({"gui": xt_packet("gui", {"I": [[601, 10]]})}, castles=OWN)
        client.game_data = GameData.parse("test", {"units": []})
        client.state.local_player = stub_player(level=70)

        with pytest.raises(ValueError, match="level"):
            client.attack.fill_waves(12345)

    def test_rejected_attack_is_false(self):
        client = make_client({"cra": xt_packet("cra", error_code=21)}, castles=OWN)
        assert client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 3) is False


class TestAttackInfo:
    """The aci pre-calculation, shaped as the live server sends it."""

    PAYLOAD = {
        "SCID": 2005,
        "TX": 512,
        "TY": 256,
        "KID": 0,
        "E": {"BGT": 0, "BGC1": 1644825, "IS": 1},
        "HAWL": 0,
        "AE": [[111, [40.0], "AB"], [66, [30.0], "CI"], [426, [10.0], "GE"]],
        "gaa": {"KID": 0, "AI": [1, 512, 256, 2001, 1001, 2, 2, 2, 1, 0, "Château Nord"]},
        "gui": {"I": [[211, 5323], [601, 100], [107, 0]]},
        "gli": {"C": [{"ID": 1, "GID": 101}], "B": [{"ID": 0}]},
    }

    def test_parses_the_live_shape(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(self.PAYLOAD)

        assert info.source_castle_id == 2005
        assert (info.target_x, info.target_y) == (512, 256)
        # The crest under "E" must not read as an error code.
        assert info.error_code == 0

    def test_target_row_and_inventory(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(self.PAYLOAD)

        assert info.target_row()[:3] == [1, 512, 256]
        # Zero counts are dropped, as everywhere else.
        assert info.inventory() == {211: 5323, 601: 100}

    def test_scoped_attacker_effects_resolve(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(self.PAYLOAD)

        bonuses = info.attacker_bonuses()

        # The construction item's flank bonus arrives tagged CI.
        assert any(b.effect_id == 66 and b.value == 30.0 for b in bonuses)

    def test_empty_payload_is_not_an_error(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate({})

        assert info.target_row() == []
        assert info.inventory() == {}

    SPIED = {
        "SCID": 2005,
        "KID": 0,
        "AE": [],
        "S": [[[601, 50]], [], [], [], [], []],
        "AS": 1800,
        "abe": {"ID": 7, "WID": 1},
        "B": {"ID": 3, "WID": 1},
        "LS": [101, 102],
        "MB": 25,
        "KTB": 10,
        "gaa": {"AI": [1, 512, 256, 900, 4242, 1, 1, 1, 0, 0, "small castle"], "OI": [{"OID": 4242, "L": 46}, {}]},
        "gui": {"I": [[601, 100]], "SHI": [[620, 4], [620, 1], [621, 0]]},
    }

    def test_as_is_the_spy_report_age(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(self.SPIED)

        assert info.spy_age_seconds == 1800
        assert info.defender_legend_skill_ids == (101, 102)
        assert (info.morality, info.kings_tower_bonus) == (25, 10)

    def test_abe_is_the_castellan_before_b(self):
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(self.SPIED)
        without_abe = GetAttackInfoResponse.model_validate({k: v for k, v in self.SPIED.items() if k != "abe"})

        castellan = info.defending_castellan()
        fallback = without_abe.defending_castellan()
        assert castellan is not None and castellan.commander_id == 7
        assert fallback is not None and fallback.commander_id == 3

    def test_an_empty_spy_army_means_no_spy_report(self):
        # parseArmyInfo reads AS, the castellan and LS only when S is not empty.
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(dict(self.SPIED, S=[]))

        assert info.spy_age_seconds == -1
        assert info.spy_army() is None
        assert info.defending_castellan() is None
        assert info.defender_legend_skill_ids == ()

    def test_stronghold_inventory_and_owner_records(self):
        # Repeated ids add up and a zero is dropped, as UnitInventoryDictionary does.
        from empire_core.protocol.models import GetAttackInfoResponse

        info = GetAttackInfoResponse.model_validate(self.SPIED)

        assert info.stronghold_inventory() == {620: 5}
        assert [(r.owner_id, r.level) for r in info.owner_records()] == [(4242, 46), (None, 0)]
        assert GetAttackInfoResponse.model_validate({}).kings_tower_bonus == 0

    def test_service_sends_the_documented_payload(self):
        client = make_client(castles=OWN)

        client.attack.get_attack_info(512, 256, 509, 255, kingdom_id=Kingdom.GREEN)

        command, payload = conn(client).request_payloads[0]
        assert command == "aci"
        assert (payload["TX"], payload["TY"]) == (512, 256)
        assert (payload["SX"], payload["SY"]) == (509, 255)


class TestTargetPrecalculation:
    """Each kind of target answers its own pre-calculation command."""

    @pytest.mark.parametrize(
        ("area_type", "command", "keys"),
        [
            # CastleStartAttackDialog.attackCastle / C2SGetAttackCastleInfosVO
            (1, "aci", {"TX", "TY", "SX", "SY", "KID"}),
            (4, "aci", {"TX", "TY", "SX", "SY", "KID"}),
            # attackDungeon / C2SGetAttackDungeonInfosVO
            (2, "adi", {"KID", "SX", "SY", "TX", "TY"}),
            (25, "adi", {"KID", "SX", "SY", "TX", "TY"}),
            (37, "adi", {"KID", "SX", "SY", "TX", "TY"}),
            # attackBossDungeon / C2SAttackInfoBossDungeonVO
            (11, "abi", {"KID", "SX", "SY", "TX", "TY"}),
            # attackLandmark / C2SAttackInfoLandmarkVO
            (23, "ali", {"KID", "TX", "TY", "SX", "SY"}),
            (26, "ali", {"KID", "TX", "TY", "SX", "SY"}),
            (28, "ali", {"KID", "TX", "TY", "SX", "SY"}),
            # attackVillage / C2SAttackInfoVillageVO
            (10, "avi", {"KID", "TX", "TY"}),
            # attackIsland / C2SAttackInfoIslandVO
            (24, "aii", {"KID", "TX", "TY"}),
        ],
    )
    def test_the_command_follows_the_area_type(self, area_type, command, keys):
        client = make_client(castles=OWN)

        client.attack.get_attack_info(700, 710, 5, 6, kingdom_id=Kingdom.SANDS, area_type=area_type)

        sent_command, payload = conn(client).request_payloads[0]
        assert sent_command == command
        assert set(payload) == keys
        assert (payload["TX"], payload["TY"], payload["KID"]) == (700, 710, 1)

    @pytest.mark.parametrize(("area_type", "command"), [(4, "coi"), (3, "cci"), (22, "cti")])
    def test_a_conquest_asks_the_conquer_info(self, area_type, command):
        client = make_client(castles=OWN)

        client.attack.get_attack_info(700, 710, 5, 6, kingdom_id=Kingdom.GREEN, area_type=area_type, conquer=True)

        assert conn(client).request_payloads[0] == (command, {"KID": 0, "TX": 700, "TY": 710})

    @pytest.mark.parametrize(
        ("area_type", "conquer"),
        # 7: treasure dungeons are pre-calculated with tai from the treasure-map screens, never adi
        [(41, False), (14, False), (0, False), (9, False), (15, False), (1, True), (7, False)],
    )
    def test_an_unmodelled_target_is_refused_before_sending(self, area_type, conquer):
        client = make_client(castles=OWN)

        with pytest.raises(ValueError, match=f"area type {area_type}"):
            client.attack.get_attack_info(700, 710, 5, 6, area_type=area_type, conquer=conquer)

        assert conn(client).request_payloads == []

    def test_the_live_adi_reply(self):
        from empire_core.protocol.models import GetDungeonAttackInfoResponse

        client = make_client({"adi": xt_packet("adi", LIVE_ADI)}, castles=OWN)

        info = client.attack.get_attack_info(620, 231, 620, 233, area_type=MapItemType.DUNGEON)

        assert isinstance(info, GetDungeonAttackInfoResponse)
        assert info.source_castle_id == 2003
        assert info.home_workshop_level == 1
        assert info.target_row() == [2, 620, 231, -1, 0, -1, 0]
        assert info.inventory() == {10: 10, 614: 2, 611: 1, 651: 300, 649: 300, 648: 300}
        assert info.spy_army() is None and info.spy_age_seconds == -1

    def test_the_live_ali_reply_carries_owner_records(self):
        from empire_core.protocol.models import GetLandmarkAttackInfoResponse

        info = GetLandmarkAttackInfoResponse.model_validate(LIVE_ALI)

        assert info.target_row()[:3] == [23, 630, 240]
        assert [record.owner_id for record in info.owner_records()] == [6537608]

    def test_an_outpost_conquest_reads_its_barons(self):
        from empire_core.protocol.models import GetOutpostConquerInfoResponse

        info = GetOutpostConquerInfoResponse.model_validate(dict(LIVE_ADI, AB=1, MB=2))

        assert (info.available_barons, info.max_barons) == (1, 2)
        assert not hasattr(info, "morality")
