"""Attacks on event maps: Beyond the Horizon attack (abgcam), the Outer Realms attack (cam), treasure
hunts (thm) and daimyo taunts (ldt)."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core import AttackInProgressError
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError, PremiumCommanderCostError
from empire_core.gamedata import CurrencyId, Horse, TreasureMapNodeId
from empire_core.movements import NO_HORSE
from empire_core.protocol.base import parse_response
from empire_core.protocol.models import (
    AttackWave,
    CreateAttackResponse,
    DaimyoTauntRequest,
    DaimyoTauntResponse,
    HorizonAttackRequest,
    HorizonAttackResponse,
    OuterRealmsAttackRequest,
    OuterRealmsAttackResponse,
    TreasureHuntAttackRequest,
    TreasureHuntAttackResponse,
)
from tests.service_helpers import COIN_HORSE, RUBY_HORSE, conn, make_client, wave, with_horses, xt_packet

OWN = [(12345, Kingdom.GREEN, 500, 510)]
ME = 1001


def wrapper(movement_id: int, x: int = 700, y: int = 710) -> dict[str, Any]:
    """A movement wrapper aimed at (x, y), shaped as parseMapMovementArray reads one."""
    return {"M": {"MID": movement_id, "T": 0, "TT": 60, "PT": 0, "OID": ME, "TA": [2, x, y, -1, 1, -211, 0]}}


class TestHorizonAttackModels:
    def test_keys_follow_the_client_order(self):
        request = HorizonAttackRequest(
            commander_id=0, source_x=1, source_y=2, target_x=3, target_y=4, waves=[AttackWave()]
        )
        # The VO initialises SX..ICA, TCK, CD, then sets A, BKS, AST, RW; it has no ASCT
        assert list(request.to_payload()) == [
            "SX", "SY", "TX", "TY", "KID", "LID", "WT", "HBW", "BPC", "ATT", "AV",
            "LP", "FC", "PTT", "SD", "ICA", "TCK", "CD", "A", "BKS", "AST", "RW",
        ]  # fmt: skip
        assert (request.to_payload()["TCK"], request.to_payload()["CD"]) == (0, 99)

    def test_the_reply_is_read_as_a_cra_reply(self):
        reply = parse_response(
            "abgcam", {"AAM": wrapper(41), "O": [{"OID": ME, "N": "me"}, {}], "gcu": {"C1": 5, "C2": 6}}
        )
        assert isinstance(reply, HorizonAttackResponse)
        assert isinstance(reply, CreateAttackResponse)
        assert reply.movement_id == 41
        assert [owner.player_id for owner in reply.owners] == [ME]
        assert reply.currencies is not None and (reply.currencies.coins, reply.currencies.rubies) == (5, 6)

    def test_a_refusal_for_too_few_units_names_the_minimum(self):
        assert HorizonAttackResponse.model_validate({"MS": 40}).minimum_soldiers == 40


class TestHorizonAttack:
    def test_send_attack_sends_abgcam_on_the_horizon(self):
        client = make_client({"abgcam": xt_packet("abgcam", {"AAM": wrapper(41)})}, castles=OWN)

        reply = client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, horizon=True)

        command, payload = conn(client).request_payloads[0]
        assert command == "abgcam"
        assert "ASCT" not in payload
        assert (payload["SX"], payload["TX"], payload["LID"], payload["TCK"]) == (500, 700, 91, 0)
        assert isinstance(reply, HorizonAttackResponse)
        assert reply.movement_id == 41

    def test_send_attack_returns_the_cra_reply(self):
        client = make_client({"cra": xt_packet("cra", {"AAM": wrapper(42)})}, castles=OWN)

        reply = client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91)

        assert type(reply) is CreateAttackResponse
        assert reply.movement_id == 42

    def test_collector_attack_sets_ica(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(
            500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, collector_attack=True,
            horizon=True,
        )  # fmt: skip

        assert conn(client).request_payloads[0][1]["ICA"] == 1

    def test_an_attack_already_on_its_way_raises_with_its_details(self):
        client = make_client({"abgcam": xt_packet("abgcam", {"TS": 30, "AS": 8}, error_code=234)}, castles=OWN)

        with pytest.raises(AttackInProgressError) as caught:
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, horizon=True)

        assert (caught.value.command, caught.value.arrival_seconds, caught.value.army_size) == ("abgcam", 30, 8)

    def test_too_few_units_raises_with_the_minimum_in_the_payload(self):
        client = make_client({"abgcam": xt_packet("abgcam", {"MS": 40}, error_code=100)}, castles=OWN)

        with pytest.raises(CommandError) as caught:
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, horizon=True)

        assert caught.value.payload == {"MS": 40}


class TestOuterRealmsAttack:
    def test_keys_follow_the_client_order(self):
        request = OuterRealmsAttackRequest(
            commander_id=0, source_x=1, source_y=2, target_x=3, target_y=4, waves=[AttackWave()]
        )
        # The VO initialises SX..ICA, CD, then sets A, BKS, AST, RW; it has no ASCT and no TCK
        assert list(request.to_payload()) == [
            "SX", "SY", "TX", "TY", "KID", "LID", "WT", "HBW", "BPC", "ATT", "AV",
            "LP", "FC", "PTT", "SD", "ICA", "CD", "A", "BKS", "AST", "RW",
        ]  # fmt: skip
        assert request.to_payload()["CD"] == 99

    def test_the_reply_is_read_as_a_cra_reply(self):
        reply = parse_response("cam", {"AAM": wrapper(43), "O": [{"OID": ME, "N": "me"}], "gcu": {"C1": 5, "C2": 6}})
        assert isinstance(reply, OuterRealmsAttackResponse)
        assert reply.movement_id == 43
        assert OuterRealmsAttackResponse.model_validate({"MS": 40}).minimum_soldiers == 40

    def test_send_attack_sends_cam_on_the_outer_realms(self):
        client = make_client({"cam": xt_packet("cam", {"AAM": wrapper(43)})}, castles=OWN)

        reply = client.attack.send_attack(
            500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, outer_realms=True
        )

        command, payload = conn(client).request_payloads[0]
        assert command == "cam"
        assert "ASCT" not in payload and "TCK" not in payload
        assert (payload["SX"], payload["TX"], payload["LID"], payload["CD"]) == (500, 700, 91, 99)
        assert isinstance(reply, OuterRealmsAttackResponse)
        assert reply.movement_id == 43

    def test_a_collector_attack_still_sends_ica_0(self):
        client = make_client(castles=OWN)

        client.attack.send_attack(
            500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, collector_attack=True,
            outer_realms=True,
        )  # fmt: skip

        assert conn(client).request_payloads[0][1]["ICA"] == 0

    def test_both_servers_at_once_are_refused(self):
        client = make_client(castles=OWN)

        with pytest.raises(ValueError, match="not both"):
            client.attack.send_attack(
                500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, horizon=True,
                outer_realms=True,
            )  # fmt: skip
        assert conn(client).request_payloads == []

    def test_an_attack_already_on_its_way_raises_with_its_details(self):
        client = make_client({"cam": xt_packet("cam", {"TS": 30, "AS": 8}, error_code=234)}, castles=OWN)

        with pytest.raises(AttackInProgressError) as caught:
            client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], commander_id=91, outer_realms=True)

        assert (caught.value.command, caught.value.arrival_seconds, caught.value.army_size) == ("cam", 30, 8)


class TestTreasureHuntModels:
    def test_keys_follow_the_client_order(self):
        request = TreasureHuntAttackRequest(
            commander_id=7, horse_booster_id=-1, use_premium_commander=0, map_id=3, node_id=TreasureMapNodeId(12),
            feathers=1, waves=[AttackWave()],
        )  # fmt: skip
        # C2SCreateTreasureHuntMovementVO initialises LID, BT, BPC, MID, NID, PTT, then sets A
        assert list(request.to_payload().items())[:6] == [
            ("LID", 7), ("BT", -1), ("BPC", 0), ("MID", 3), ("NID", 12), ("PTT", 1),
        ]  # fmt: skip
        assert list(request.to_payload())[-1] == "A"

    def test_the_horse_is_a_horse_and_none_goes_as_minus_one(self):
        horse = TreasureHuntAttackRequest(
            commander_id=7, horse_booster_id=Horse.WARHORSE_STABLE1, map_id=3, node_id=TreasureMapNodeId(12)
        )
        assert horse.horse_booster_id is Horse.WARHORSE_STABLE1 and horse.to_payload()["BT"] == 1002
        default = TreasureHuntAttackRequest(commander_id=7, map_id=3, node_id=TreasureMapNodeId(12))
        assert default.horse_booster_id == NO_HORSE and default.to_payload()["BT"] == -1

    def test_the_reply_carries_the_movement_currencies_and_units(self):
        reply = parse_response(
            "thm",
            {"TM": wrapper(51), "gcu": {"C1": 10, "C2": 2}, "gui": {"I": [[487, 9]], "TU": [], "SHI": [], "HI": []}},
        )
        assert isinstance(reply, TreasureHuntAttackResponse)
        assert reply.movement_id == 51
        assert reply.currencies is not None and reply.currencies.coins == 10
        assert reply.unit_inventory is not None
        assert dict(reply.unit_inventory.units) == {487: 9}

    def test_an_unreadable_movement_costs_only_itself(self):
        reply = TreasureHuntAttackResponse.model_validate({"TM": {"M": "junk"}, "gcu": {"C1": 1}})
        assert (reply.movement, reply.movement_id) == (None, None)
        assert reply.currencies is not None


class TestTreasureHuntAttack:
    def test_sends_the_complete_waves_with_the_map_and_node(self):
        client = with_horses(make_client({"thm": xt_packet("thm", {"TM": wrapper(51)})}))

        reply = client.attack.send_treasure_hunt_attack(
            3, TreasureMapNodeId(12), [wave(units=[[487, 5]]), wave()], commander_id=7, horse_booster_id=COIN_HORSE
        )

        command, payload = conn(client).request_payloads[0]
        assert command == "thm"
        assert (payload["MID"], payload["NID"], payload["LID"], payload["BT"], payload["PTT"]) == (
            3,
            12,
            7,
            COIN_HORSE,
            0,
        )
        assert len(payload["A"]) == 1
        assert reply.movement_id == 51

    def test_feathers_send_no_horse(self):
        client = make_client()

        client.attack.send_treasure_hunt_attack(
            3,
            TreasureMapNodeId(12),
            [wave(units=[[487, 5]])],
            7,
            horse_booster_id=Horse.WARHORSE_STABLE1,
            feathers=True,
        )

        payload = conn(client).request_payloads[0][1]
        assert (payload["BT"], payload["PTT"]) == (-1, 1)

    def test_a_horse_that_costs_rubies_needs_spend_rubies(self):
        client = with_horses(make_client())

        with pytest.raises(ValueError, match="spend_rubies"):
            client.attack.send_treasure_hunt_attack(
                3, TreasureMapNodeId(12), [wave(units=[[487, 5]])], 7, horse_booster_id=RUBY_HORSE
            )

        assert conn(client).request_payloads == []

    def test_the_premium_commander_needs_consent(self):
        client = make_client()

        with pytest.raises(PremiumCommanderCostError):
            client.attack.send_treasure_hunt_attack(
                3, TreasureMapNodeId(12), [wave(units=[[487, 5]])], -14, use_premium_commander=True
            )

        assert conn(client).request_payloads == []

    def test_waves_without_units_are_refused_before_sending(self):
        client = make_client()

        with pytest.raises(ValueError, match="no units"):
            client.attack.send_treasure_hunt_attack(3, TreasureMapNodeId(12), [wave()], 7)

        assert conn(client).request_payloads == []

    def test_is_paced_with_send_attack(self, monkeypatch):
        client = make_client(castles=OWN)
        client.config.attack_send_interval = 4.0
        clock = [100.0]
        slept: list[float] = []
        monkeypatch.setattr("empire_core.attack.pacing.time.monotonic", lambda: clock[0])
        monkeypatch.setattr(
            "empire_core.attack.pacing.sleep_unless_cancelled", lambda seconds, cancel: slept.append(seconds)
        )

        client.attack.send_attack(500, 510, 700, 710, [wave(units=[[487, 1]])], 3)
        clock[0] = 101.0
        client.attack.send_treasure_hunt_attack(3, TreasureMapNodeId(12), [wave(units=[[487, 5]])], 7)

        assert slept == [3.0]

    def test_cant_start_new_armies_raises(self):
        # THMCommand drops this code without a message; the library still raises it
        client = make_client({"thm": xt_packet("thm", None, error_code=90)})

        with pytest.raises(CommandError):
            client.attack.send_treasure_hunt_attack(3, TreasureMapNodeId(12), [wave(units=[[487, 5]])], 7)


class TestDaimyoTaunt:
    def test_keys_follow_the_client_order(self):
        request = DaimyoTauntRequest(township_x=40, township_y=50, samurai_medal_boosters=2, shogun_point_boosters=1)
        assert list(request.to_payload().items()) == [("TX", 40), ("TY", 50), ("SMK", 2), ("SPK", 1)]

    def test_the_whole_reply_is_the_movement(self):
        reply = parse_response("ldt", wrapper(61, 40, 50))
        assert isinstance(reply, DaimyoTauntResponse)
        assert reply.movement.movement_id == 61

    def test_taunt_returns_the_attack_it_started(self):
        client = make_client({"ldt": xt_packet("ldt", wrapper(61, 40, 50))})

        reply = client.attack.taunt_daimyo(40, 50, samurai_medal_boosters=3)

        assert conn(client).request_payloads[0] == ("ldt", {"TX": 40, "TY": 50, "SMK": 3, "SPK": 0})
        assert reply.movement.movement_id == 61

    def test_negative_boosters_are_refused_before_sending(self):
        client = make_client()

        with pytest.raises(ValueError):
            client.attack.taunt_daimyo(40, 50, shogun_point_boosters=-1)

        assert conn(client).request_payloads == []

    def test_a_refusal_raises(self):
        client = make_client({"ldt": xt_packet("ldt", None, error_code=21)})

        with pytest.raises(CommandError):
            client.attack.taunt_daimyo(40, 50)


def test_collector_booster_ids_are_currencies():
    request = HorizonAttackRequest(
        commander_id=0, source_x=1, source_y=2, target_x=3, target_y=4,
        collector_booster={CurrencyId.SAMURAI_MEDAL_BOOSTER: 2},
    )  # fmt: skip
    assert request.to_payload()["BKS"] == [[31, 2]]
