"""Tests for the castle service."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.enums import Kingdom, Resource
from empire_core.exceptions import CommandError, GameDataNotLoadedError, UnknownCastleError
from empire_core.gamedata import Horse
from tests.service_helpers import (
    COIN_HORSE,
    GOLDEN_GCL,
    RUBY_HORSE,
    StubPlayer,
    StubState,
    conn,
    make_client,
    with_horses,
    xt_packet,
)

GOLDEN_DCL: dict[str, Any] = {
    "PID": 1001,
    "C": [
        {
            "KID": 0,
            "AI": [
                {
                    "AID": 2001,
                    "W": 7000.0,
                    "S": 7000.0,
                    "F": 7000.0,
                    "gpa": {"DW": 2239, "DS": 1952, "DF": 3502},
                    # Unit stacks as positional pairs; the trailing 1-element
                    # entry is the kind of short row the server does send.
                    "AC": [[656, 1], [650, 213], [999]],
                    "B": 1,
                },
                {"AID": 2002, "W": 800.0, "S": 800.0, "F": 800.0, "AC": [[649, 18]], "B": 0},
            ],
        }
    ],
}


# =============================================================================
# CastleService
# =============================================================================


class TestCastleQueries:
    def test_golden_gcl_payload_parses(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})

        castles = client.castle.get_all()

        assert [(c.castle_id, c.castle_name, c.x, c.y, c.castle_type) for c in castles] == [
            (2001, "Main Castle", 512, 256, 1),
            (2002, "Outpost North", 510, 257, 4),
        ]
        assert castles[0].position.x == 512
        assert conn(client).request_payloads == [("gcl", {})]

    def test_golden_dcl_payload_parses_resources_and_units(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})

        details = client.castle.get_details(2002)

        assert details.castle_id == 2002
        assert (details.wood, details.stone, details.food) == (800, 800, 800)
        assert details.units == {649: 18}
        # C2SGetDetailedCastleListVO defaults CD to 1; the id is matched client-side.
        assert conn(client).request_payloads == [("dcl", {"CD": 1})]

    def test_short_unit_row_is_skipped(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})
        details = client.castle.get_details(2001)
        assert details.units == {656: 1, 650: 213}

    def test_a_castle_the_reply_does_not_list_raises(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})
        with pytest.raises(UnknownCastleError) as raised:
            client.castle.get_details(1)
        assert raised.value.castle_id == 1

    def test_a_reply_without_castles_raises(self):
        client = make_client({"dcl": xt_packet("dcl", {})})
        with pytest.raises(UnknownCastleError):
            client.castle.get_details(12345)

    def test_gcl_sends_the_player_id_once_known(self):
        player = StubPlayer()
        player.id = 777
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)}, state=StubState(local_player=player))

        client.castle.get_all()

        assert conn(client).request_payloads == [("gcl", {"PID": 777})]

    def test_resources_are_the_flat_grc_block(self):
        # CastleResourcesVO.parseGRC: AID, KID and the 11 resources at the top level
        payload = {"AID": 12345, "KID": 2, "W": 1.9, "S": 2, "F": 3, "C": 4, "O": 5, "HONEY": "6", "BEEF": 7}
        client = make_client({"grc": xt_packet("grc", payload)}, castles=[(12345, Kingdom.ICE)])

        resources = client.castle.get_resources(12345)

        assert conn(client).request_payloads == [("grc", {"AID": 12345, "KID": 2})]
        assert (resources.castle_id, resources.kingdom_id) == (12345, 2)
        assert (resources.wood, resources.stone, resources.food, resources.coal, resources.oil) == (1, 2, 3, 4, 5)
        assert (resources.honey, resources.beef, resources.mead) == (6, 7, 0)

    def test_production_is_the_joined_castles_gpa_block(self):
        payload = {"P": 80, "DW": 2239, "MRW": 7000, "WM": 110.0, "RFPPA": 0.5, "RS1": 328.0}
        client = make_client({"gpa": xt_packet("gpa", payload)})

        area = client.castle.get_production()

        # C2SGetCastleProductionDataVO sends no fields
        assert conn(client).request_payloads == [("gpa", {})]
        assert (area.population, area.production.wood, area.storage_capacity.wood) == (80, 223.9, 7000)
        assert (area.production_bonus_percent.wood, area.faction_buff, area.barracks_speed) == (110.0, 0.5, 328.0)


class TestCastleActions:
    def test_select_sends_castle_and_its_kingdom_from_the_castle_list(self):
        client = make_client(castles=[(777, Kingdom.GREEN), (12345, Kingdom.ICE)])

        client.castle.select(12345)

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 2})]

    @pytest.mark.parametrize(
        "call",
        [
            lambda c: c.castle.select(12345),
            lambda c: c.castle.join(12345),
            lambda c: c.castle.get_resources(12345),
            lambda c: c.movements.send_resources(12345, 10, 20, {Resource.WOOD: 1}),
            lambda c: c.movements.transfer_units_to_kingdom(12345, Kingdom.ICE, [[620, 1]]),
        ],
    )
    def test_a_castle_not_in_the_castle_list_raises_and_sends_nothing(self, call):
        client = make_client(castles=[(777, Kingdom.ICE)])

        with pytest.raises(UnknownCastleError) as raised:
            call(client)

        assert raised.value.castle_id == 12345
        assert conn(client).request_payloads == []

    def test_select_waits_for_the_jaa_acknowledgement(self):
        # The server answers a castle jump with 'jaa', never with 'jca'.
        # Waiting on the request command times out on every single call.
        client = make_client({"jaa": xt_packet("jaa")}, castles=[(12345, Kingdom.GREEN)])

        client.castle.select(12345)
        assert conn(client).requested == ["jaa"]

    def test_select_reports_a_rejected_jump(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)}, castles=[(12345, Kingdom.GREEN)])

        with pytest.raises(CommandError):
            client.castle.select(12345)

    def test_rename_sends_the_castle_type_and_kingdom_from_the_castle_list(self):
        client = make_client(
            {
                "gcl": xt_packet("gcl", GOLDEN_GCL),
                "arc": xt_packet("arc", {"CID": 2001, "KID": 0, "P": 1}),
            }
        )

        client.castle.rename(2001, "My Fortress", spend_rubies=True)

        assert conn(client).request_payloads[-1] == (
            "arc",
            {"CID": 2001, "N": "My Fortress", "AT": 1, "KID": 0, "P": 1},
        )

    def test_a_rename_costs_rubies_unless_a_premium_account_runs(self):
        # CastleRenameCastleDialog.showLoaded: CHANGE_CASTLE_NAME_C2, 0 while premiumAccountVO.isActive
        stub = StubState(StubPlayer())
        script = {"gcl": xt_packet("gcl", GOLDEN_GCL), "arc": xt_packet("arc", {"CID": 2001, "KID": 0, "P": 1})}
        client = make_client(script, state=stub)
        with pytest.raises(ValueError, match="2500 rubies"):
            client.castle.rename(2001, "My Fortress")
        assert conn(client).request_payloads == []

        stub.boosts = SimpleNamespace(is_premium_active=lambda: True)
        client.castle.rename(2001, "My Fortress")

    def test_naming_a_new_castle_sends_p_0(self):
        client = make_client(
            {
                "gcl": xt_packet("gcl", GOLDEN_GCL),
                "arc": xt_packet("arc", {"CID": 2001, "KID": 0, "P": 0}),
            }
        )

        client.castle.rename(2001, "My Fortress", is_initial_name=True)

        assert conn(client).request_payloads[-1][1]["P"] == 0

    def test_rejected_rename_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL), "arc": xt_packet("arc", error_code=21)})
        with pytest.raises(CommandError):
            client.castle.rename(2001, "nope", spend_rubies=True)

    def test_renaming_a_castle_you_do_not_own_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})
        with pytest.raises(ValueError, match="12345"):
            client.castle.rename(12345, "nope", spend_rubies=True)

    def test_abandon_sends_the_kingdom_from_the_castle_list(self):
        reply = {"CID": 2002, "KID": 0, "AOT": 86400, "CAT": 10800}
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL), "mas": xt_packet("mas", reply)})

        response = client.castle.abandon_castle(2002)

        assert conn(client).request_payloads[-1] == ("mas", {"CID": 2002, "KID": 0})
        assert (response.abandon_seconds, response.cancel_seconds) == (86400, 10800)

    def test_the_kingdoms_main_castle_cannot_be_abandoned(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})
        with pytest.raises(ValueError, match="main castle"):
            client.castle.abandon_castle(2001)
        assert [command for command, _ in conn(client).request_payloads] == ["gcl"]

    def test_abandoning_a_castle_you_do_not_own_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})
        with pytest.raises(UnknownCastleError):
            client.castle.abandon_castle(12345)

    def test_a_refused_abandon_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL), "mas": xt_packet("mas", error_code=140)})
        with pytest.raises(CommandError):
            client.castle.abandon_castle(2002)

    def test_cancel_abandon_sends_the_kingdom_from_the_castle_list(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL), "mac": xt_packet("mac", {"CID": 2002, "KID": 0})})

        client.castle.cancel_abandon(2002)

        assert conn(client).request_payloads[-1] == ("mac", {"CID": 2002, "KID": 0})

    def test_a_refused_cancel_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL), "mac": xt_packet("mac", error_code=21)})
        with pytest.raises(CommandError):
            client.castle.cancel_abandon(2002)

    def test_cancelling_for_a_castle_you_do_not_own_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})
        with pytest.raises(UnknownCastleError):
            client.castle.cancel_abandon(12345)

    def test_send_support_builds_the_documented_payload(self):
        client = make_client()

        client.movements.send_support(12345, 700, 710, {487: 100}, commander_id=5, wait_time=6)

        command, payload = conn(client).request_payloads[0]
        assert command == "cds"
        # C2SCreateDefenceSupportMovementVO's keys, in its order, with no KID
        assert list(payload) == ["SID", "TX", "TY", "LID", "WT", "HBW", "BPC", "PTT", "SD", "A"]
        assert payload["SID"] == 12345
        assert (payload["TX"], payload["TY"]) == (700, 710)
        assert payload["A"] == [[487, 100]]
        assert payload["WT"] == 6
        # A plain commander, no premium commander, no feathers: nothing is spent
        assert (payload["LID"], payload["BPC"], payload["PTT"], payload["HBW"]) == (5, 0, 0, -1)

    def test_send_support_with_feathers_sends_no_horses(self):
        client = make_client()
        client.movements.send_support(
            12345, 700, 710, {487: 1}, commander_id=5, horse_booster_id=Horse.COURSER_STABLE1, feathers=True
        )
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_send_support_without_feathers_keeps_the_horses(self):
        client = with_horses(make_client())
        client.movements.send_support(12345, 700, 710, {487: 1}, commander_id=5, horse_booster_id=COIN_HORSE)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (COIN_HORSE, 0)

    @pytest.mark.parametrize("kwargs", [{"horse_booster_id": RUBY_HORSE}, {"horse_booster_id": 9999}, {"slowdown": 30}])
    def test_a_support_or_troop_send_that_costs_rubies_is_refused(self, kwargs):
        # ACastlePostActionDialog.getTotalCostsC2: the horse's ruby cost and SLOWDOWN_C2_COSTS
        client = with_horses(make_client(castles=[(12345, Kingdom.GREEN)]))
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.movements.send_support(12345, 700, 710, {487: 1}, commander_id=5, **kwargs)
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.movements.send_troops(10, 20, 700, 710, {487: 1}, 5, **kwargs)
        assert conn(client).request_payloads == []

        client.movements.send_support(12345, 700, 710, {487: 1}, commander_id=5, spend_rubies=True, **kwargs)
        client.movements.send_troops(10, 20, 700, 710, {487: 1}, 5, spend_rubies=True, **kwargs)

    def test_a_ruby_horse_paid_with_feathers_costs_no_rubies(self):
        client = make_client()
        client.movements.send_support(
            12345, 700, 710, {487: 1}, commander_id=5, horse_booster_id=RUBY_HORSE, feathers=True
        )

    def test_pricing_a_horse_fails_when_the_game_data_cannot_be_loaded(self):
        client = make_client()
        with pytest.raises(GameDataNotLoadedError, match="could not load the game data"):
            client.movements.send_support(12345, 700, 710, {487: 1}, commander_id=5, horse_booster_id=COIN_HORSE)
        assert conn(client).request_payloads == []

    def test_send_support_with_the_premium_commander(self):
        client = make_client()
        client.movements.send_support(
            12345, 700, 710, {487: 1}, commander_id=-14, use_premium_commander=True, spend_rubies=True
        )
        payload = conn(client).request_payloads[0][1]
        assert (payload["LID"], payload["BPC"]) == (-14, 1)

    def test_out_of_range_wait_time_is_rejected_before_sending(self):
        client = make_client()

        with pytest.raises(ValidationError):
            client.movements.send_support(12345, 700, 710, {487: 1}, commander_id=5, wait_time=13)

        assert conn(client).requested == []
