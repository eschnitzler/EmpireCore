"""Tests for the defense service."""

from __future__ import annotations

import pytest

from empire_core.defense.models import GetDefenseResponse, GetSupportDefenseResponse, MoatDefense
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError
from tests.defense.test_models import LIVE_DFC
from tests.service_helpers import conn, make_client, xt_packet


class TestGetSupportDefenseInfo:
    def test_source_defaults_to_the_first_own_castle(self):
        castles = [(1, Kingdom.GREEN, 100, 200), (2, Kingdom.GREEN, 300, 400)]
        client = make_client({"sdi": xt_packet("sdi", {"S": []})}, castles=castles)

        response = client.defense.get_support_defense_info(640, 655)

        assert isinstance(response, GetSupportDefenseResponse)
        assert conn(client).request_payloads == [("sdi", {"TX": 640, "TY": 655, "SX": 100, "SY": 200})]

    def test_explicit_source_is_sent_as_given(self):
        client = make_client({"sdi": xt_packet("sdi", {"S": []})}, castles=[])

        client.defense.get_support_defense_info(640, 655, source_x=1, source_y=2)

        assert conn(client).request_payloads == [("sdi", {"TX": 640, "TY": 655, "SX": 1, "SY": 2})]

    def test_no_source_and_no_castle_raises(self):
        client = make_client(castles=[])

        with pytest.raises(ValueError):
            client.defense.get_support_defense_info(640, 655)


class TestGetOwnDefense:
    def test_dfc_is_sent_for_the_castle_with_no_kingdom(self):
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC)})

        response = client.defense.get_own_defense(635, 242, 16655114)

        assert isinstance(response, GetDefenseResponse)
        assert conn(client).request_payloads == [("dfc", {"CX": 635, "CY": 242, "AID": 16655114, "KID": -1})]
        assert response.wall is not None
        assert response.keep is not None

    def test_a_given_kingdom_is_sent(self):
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC)})

        client.defense.get_own_defense(635, 242, 16655114, kingdom=Kingdom.ICE)

        assert conn(client).request_payloads == [("dfc", {"CX": 635, "CY": 242, "AID": 16655114, "KID": 2})]

    def test_a_rejection_raises(self):
        client = make_client({"dfc": xt_packet("dfc", error_code=92)})

        with pytest.raises(CommandError):
            client.defense.get_own_defense(635, 242, 16655114)


class TestSetDefense:
    """Read-modify-write: the setters take the shapes get_own_defense returns."""

    def test_set_keep_sends_the_read_keep(self):
        reply = {**LIVE_DFC["dfk"], "S": [[651, 20], [-1, 0], [-1, 0]]}
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC), "dfk": xt_packet("dfk", reply)})
        keep = client.defense.get_own_defense(635, 242, 16655114).keep
        assert keep is not None
        keep.slots[0] = [651, 20]
        keep.unit_composition = 70

        stored = client.defense.set_keep(635, 242, 16655114, keep)

        command, payload = conn(client).request_payloads[1]
        assert command == "dfk"
        # C2SDefenceKeepVO initialises CX, CY, AID, MAUCT, UC before it sets S and STS
        assert list(payload.items()) == [
            ("CX", 635),
            ("CY", 242),
            ("AID", 16655114),
            ("MAUCT", 0),
            ("UC", 70),
            ("S", [[651, 20], [-1, 0], [-1, 0]]),
            ("STS", [[-1, 0], [-1, 0], [-1, 0]]),
        ]
        assert stored.slots[0] == [651, 20]

    def test_set_wall_sends_each_section(self):
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC), "dfw": xt_packet("dfw", LIVE_DFC["dfw"])})
        wall = client.defense.get_own_defense(635, 242, 16655114).wall
        assert wall is not None

        stored = client.defense.set_wall(635, 242, 16655114, wall)

        command, payload = conn(client).request_payloads[1]
        assert command == "dfw"
        assert list(payload) == ["CX", "CY", "AID", "L", "M", "R"]
        assert list(payload["L"].items()) == [("S", []), ("UP", 25), ("UC", 50)]
        assert payload["M"] == {"S": [[-1, 0]], "UP": 50, "UC": 50}
        assert payload["R"] == {"S": [], "UP": 25, "UC": 50}
        assert stored.unit_slot_count == 20

    def test_set_moat_sends_the_three_lists(self):
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC), "dfm": xt_packet("dfm", LIVE_DFC["dfm"])})
        moat = client.defense.get_own_defense(635, 242, 16655114).moat
        assert moat is not None

        client.defense.set_moat(635, 242, 16655114, moat)

        command, payload = conn(client).request_payloads[1]
        assert command == "dfm"
        assert list(payload.items()) == [
            ("CX", 635),
            ("CY", 242),
            ("AID", 16655114),
            ("LS", [[-1, 0]]),
            ("MS", [[-1, 0]]),
            ("RS", [[-1, 0]]),
        ]

    def test_a_rejected_setter_raises(self):
        client = make_client({"dfm": xt_packet("dfm", error_code=92)})
        with pytest.raises(CommandError):
            client.defense.set_moat(635, 242, 16655114, MoatDefense())
