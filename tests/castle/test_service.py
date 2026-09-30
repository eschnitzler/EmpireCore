"""Tests for the castle service."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.enums import Kingdom
from tests.service_helpers import GOLDEN_GCL, conn, make_client, xt_packet

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
            (2001, "Main Castle", 632, 243, 1),
            (2002, "Outpost North", 630, 244, 4),
        ]
        assert castles[0].position.x == 632
        assert conn(client).request_payloads == [("gcl", {})]

    def test_golden_dcl_payload_parses_resources_and_units(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})

        details = client.castle.get_details(2002)

        assert details is not None
        assert details.castle_id == 2002
        assert (details.wood, details.stone, details.food) == (800, 800, 800)
        assert details.units == {649: 18}
        # The server ignores the payload and lists every castle; the id is matched client-side.
        assert conn(client).request_payloads == [("dcl", {})]

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

    def test_resources_are_parsed(self):
        payload = {"R": {"W": 1, "S": 2, "F": 3, "C": 4, "R": 5}, "SC": {"W": 10}}
        client = make_client({"grc": xt_packet("grc", payload)})

        resources = client.castle.get_resources(12345)

        assert resources is not None
        assert (resources.wood, resources.stone, resources.food, resources.coins, resources.rubies) == (1, 2, 3, 4, 5)

    def test_missing_resources_are_none(self):
        client = make_client({"grc": xt_packet("grc", {})})
        assert client.castle.get_resources(12345) is None

    def test_production_returns_both_rates(self):
        payload = {"P": {"W": 1200.5, "S": 900.0}, "CO": {"F": 300.25}}
        client = make_client({"gpa": xt_packet("gpa", payload)})

        production, consumption = client.castle.get_production(12345)

        assert production is not None and production.wood == 1200.5
        assert consumption is not None and consumption.food == 300.25

    def test_production_without_rates_is_a_none_pair(self):
        client = make_client({"gpa": xt_packet("gpa", {})})
        assert client.castle.get_production(12345) == (None, None)


class TestCastleActions:
    def test_select_sends_castle_and_kingdom(self):
        client = make_client()

        assert client.castle.select(12345, kingdom_id=Kingdom.ICE) is True

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 2})]

    def test_select_waits_for_the_jaa_acknowledgement(self):
        # The server answers a castle jump with 'jaa', never with 'jca'.
        # Waiting on the request command times out on every single call.
        client = make_client({"jaa": xt_packet("jaa")})

        assert client.castle.select(12345) is True
        assert conn(client).requested == ["jaa"]

    def test_select_reports_a_rejected_jump(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})

        assert client.castle.select(12345) is False

    def test_select_rejection_is_logged_against_the_request_command(self, caplog):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})

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
        client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=5, horses_type=3, feathers=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_send_support_without_feathers_keeps_the_horses(self):
        client = make_client()
        client.castle.send_support(12345, 700, 710, [[487, 1]], commander_id=5, horses_type=3)
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
