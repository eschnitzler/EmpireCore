"""Tests for the castle service."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError, UnknownCastleError
from tests.service_helpers import GOLDEN_GCL, StubPlayer, StubState, conn, make_client, xt_packet

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

        assert details is not None
        assert details.castle_id == 2002
        assert (details.wood, details.stone, details.food) == (800, 800, 800)
        assert details.units == {649: 18}
        # C2SGetDetailedCastleListVO defaults CD to 1; the id is matched client-side.
        assert conn(client).request_payloads == [("dcl", {"CD": 1})]

    def test_short_unit_row_is_skipped(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})
        details = client.castle.get_details(2001)
        assert details is not None
        assert details.units == {656: 1, 650: 213}

    def test_unknown_castle_is_none(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})
        assert client.castle.get_details(1) is None

    def test_missing_castle_block_is_none(self):
        client = make_client({"dcl": xt_packet("dcl", {})})
        assert client.castle.get_details(12345) is None

    def test_gcl_sends_the_player_id_once_known(self):
        player = StubPlayer()
        player.id = 777  # type: ignore[attr-defined]
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

        assert client.castle.select(12345) is True

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 2})]

    @pytest.mark.parametrize(
        "call",
        [
            lambda c: c.select(12345),
            lambda c: c.join(12345),
            lambda c: c.get_resources(12345),
            lambda c: c.send_resources(12345, 10, 20, {"W": 1}),
            lambda c: c.transfer_units_to_kingdom(12345, Kingdom.ICE, [[620, 1]]),
        ],
    )
    def test_a_castle_not_in_the_castle_list_raises_and_sends_nothing(self, call):
        client = make_client(castles=[(777, Kingdom.ICE)])

        with pytest.raises(UnknownCastleError) as raised:
            call(client.castle)

        assert raised.value.castle_id == 12345
        assert conn(client).request_payloads == []

    @pytest.mark.parametrize(
        "call",
        [
            lambda c: c.select(1),
            lambda c: c.join(1),
            lambda c: c.get_resources(1),
            lambda c: c.send_resources(1, 10, 20, {"W": 1}),
            lambda c: c.transfer_units_to_kingdom(1, Kingdom.GREEN, [[620, 1]]),
        ],
    )
    def test_an_id_repeated_across_your_kingdoms_raises_and_sends_nothing(self, call):
        client = make_client(castles=[(1, Kingdom.STORM), (1, Kingdom.BERIMOND)])

        with pytest.raises(AmbiguousCastleError) as raised:
            call(client.castle)

        assert (raised.value.castle_id, raised.value.kingdoms) == (1, [Kingdom.STORM, Kingdom.BERIMOND])
        assert "repeats across your kingdoms" in str(raised.value)
        assert conn(client).request_payloads == []

    def test_details_of_an_id_listed_in_two_kingdoms_raise(self):
        dcl = {"C": [{"KID": 4, "AI": [{"AID": 1, "W": 4}]}, {"KID": 10, "AI": [{"AID": 1, "W": 10}]}]}
        client = make_client({"dcl": xt_packet("dcl", dcl)})

        with pytest.raises(AmbiguousCastleError):
            client.castle.get_details(1)

    def test_rename_of_an_id_listed_in_two_kingdoms_raises_and_sends_no_rename(self):
        row = [1, 10, 20, 1, 1001, 1, 1, 1, 0, 0, "Keep"]
        gcl = {"PID": 1001, "C": [{"KID": 4, "AI": [{"AI": row}]}, {"KID": 10, "AI": [{"AI": row}]}]}
        client = make_client({"gcl": xt_packet("gcl", gcl)})

        with pytest.raises(AmbiguousCastleError):
            client.castle.rename(1, "New")

        assert [command for command, _ in conn(client).request_payloads] == ["gcl"]

    def test_select_waits_for_the_jaa_acknowledgement(self):
        # The server answers a castle jump with 'jaa', never with 'jca'.
        # Waiting on the request command times out on every single call.
        client = make_client({"jaa": xt_packet("jaa")}, castles=[(12345, Kingdom.GREEN)])

        assert client.castle.select(12345) is True
        assert conn(client).requested == ["jaa"]

    def test_select_reports_a_rejected_jump(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)}, castles=[(12345, Kingdom.GREEN)])

        assert client.castle.select(12345) is False

    def test_select_rejection_is_logged_against_the_request_command(self, caplog):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)}, castles=[(12345, Kingdom.GREEN)])

        with caplog.at_level(logging.WARNING, logger="empire_core.services.base"):
            client.castle.select(12345)

        assert "jca" in caplog.text

    def test_rename_sends_the_castle_type_and_kingdom_from_the_castle_list(self):
        client = make_client(
            {
                "gcl": xt_packet("gcl", GOLDEN_GCL),
                "arc": xt_packet("arc", {"CID": 2001, "KID": 0, "P": 1}),
            }
        )

        assert client.castle.rename(2001, "My Fortress") is True

        assert conn(client).request_payloads[-1] == (
            "arc",
            {"CID": 2001, "N": "My Fortress", "AT": 1, "KID": 0, "P": 1},
        )

    def test_naming_a_new_castle_sends_p_0(self):
        client = make_client(
            {
                "gcl": xt_packet("gcl", GOLDEN_GCL),
                "arc": xt_packet("arc", {"CID": 2001, "KID": 0, "P": 0}),
            }
        )

        assert client.castle.rename(2001, "My Fortress", is_initial_name=True) is True

        assert conn(client).request_payloads[-1][1]["P"] == 0

    def test_rejected_rename_is_false(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL), "arc": xt_packet("arc", error_code=21)})
        assert client.castle.rename(2001, "nope") is False

    def test_renaming_a_castle_you_do_not_own_raises(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})
        with pytest.raises(ValueError, match="12345"):
            client.castle.rename(12345, "nope")

    def test_send_support_builds_the_documented_payload(self):
        client = make_client()

        assert client.castle.send_support(12345, 700, 710, [[487, 100]], commander_id=5, wait_time=6) is True

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
        client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=5, horse_booster_id=3, feathers=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_send_support_without_feathers_keeps_the_horses(self):
        client = make_client()
        client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=5, horse_booster_id=3)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (3, 0)

    def test_send_support_with_the_premium_commander(self):
        client = make_client()
        client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=-14, use_premium_commander=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["LID"], payload["BPC"]) == (-14, 1)

    def test_out_of_range_wait_time_is_rejected_before_sending(self):
        client = make_client()

        with pytest.raises(ValidationError):
            client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=5, wait_time=13)

        assert conn(client).requested == []
