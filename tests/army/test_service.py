"""Tests for the army service."""

from __future__ import annotations

import pytest

from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError, CommandError, UnknownCastleError
from empire_core.protocol.models import ProductionListId, SlotType
from tests.service_helpers import conn, make_client, xt_packet

OWN = [(12345, Kingdom.GREEN)]

# =============================================================================
# ArmyService
# =============================================================================


class TestArmyService:
    def test_get_units_reads_the_live_inventory_array(self):
        # A live gui response carries the inventory as [[wod_id, count], ...]
        # under I, with U and T empty.
        payload = {
            "U": [],
            "T": [],
            "I": [[107, 86058], [178, 38712], [242, 0]],
            "TU": [[105, 12]],
            "SHI": [[646, 500]],
            "HI": [[627, 7]],
        }
        client = make_client({"gui": xt_packet("gui", payload)}, castles=OWN)

        response = client.army.get_units_response(12345)

        assert [(u.unit_id, u.count) for u in response.get_inventory()] == [
            (107, 86058),
            (178, 38712),
        ]
        assert [(u.unit_id, u.count) for u in response.get_in_production()] == [(105, 12)]
        assert [(u.unit_id, u.count) for u in response.get_stronghold()] == [(646, 500)]
        assert [(u.unit_id, u.count) for u in response.get_hospital()] == [(627, 7)]

    def test_a_refused_join_raises_instead_of_reading_another_castle(self):
        script = {"jaa": xt_packet("jaa", error_code=21), "gui": xt_packet("gui", {"I": [[1, 1]]})}
        client = make_client(script, castles=OWN)

        with pytest.raises(CommandError):
            client.army.get_units(12345)
        assert "gui" not in [command for command, _ in conn(client).request_payloads]

    def test_get_units_joins_the_castle_and_reads_i(self):
        # parse_GUI reads I, TU, SHI and HI; U and T are not read
        payload = {"U": [{"UID": 1, "C": 1}], "I": [[487, 100], [488, 20], [301, 5]]}
        client = make_client({"gui": xt_packet("gui", payload)}, castles=OWN)

        units = client.army.get_units(12345)

        assert [(u.unit_id, u.count) for u in units] == [(487, 100), (488, 20), (301, 5)]
        # gui names no castle (C2SGetUnitInventoryVO), so the castle is joined first
        assert [command for command, _ in conn(client).request_payloads] == ["jaa", "gui"]
        assert conn(client).request_payloads[-1] == ("gui", {})

    def test_production_list_joins_the_castle_and_reads_the_spl_block(self):
        payload = {"LID": 1, "QS": [{"P": {"WID": 649, "TUA": 20}, "SI": {"RUT": -1}}], "PS": {}, "RM": 0, "TCT": 0}
        client = make_client({"spl": xt_packet("spl", payload)}, castles=OWN)

        production = client.army.get_production_list(12345, ProductionListId.TOOLS)

        assert [(s.position, s.wod_id, s.amount) for s in production.queue] == [(0, 649, 20)]
        assert production.current.is_free
        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 0}), ("spl", {"LID": 1})]

    @pytest.mark.parametrize(
        "call,command,expected",
        [
            (
                lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 620, 150),
                "bup",
                {"LID": 0, "WID": 620, "AMT": 150, "PO": -1, "PWR": 0, "SK": 73, "SID": 0, "AID": 12345},
            ),
            (
                lambda s: s.produce_units(12345, ProductionListId.TOOLS, 649, 20, private_offer_id=88),
                "bup",
                {"LID": 1, "WID": 649, "AMT": 20, "PO": -1, "PWR": 0, "SK": 73, "SID": 0, "AID": 12345},
            ),
            (
                lambda s: s.produce_units(
                    12345, ProductionListId.TOOLS, 649, 20, pay_with_rubies=True, private_offer_id=88
                ),
                "bup",
                {"LID": 1, "WID": 649, "AMT": 20, "PO": 88, "PWR": 1, "SK": 73, "SID": 0, "AID": 12345},
            ),
            (lambda s: s.dismiss_units(12345, 620, 30), "dup", {"WID": 620, "A": 30, "S": 0}),
            (lambda s: s.dismiss_units(12345, 620, 30, from_stronghold=True), "dup", {"WID": 620, "A": 30, "S": 1}),
            (
                lambda s: s.cancel_production(12345, ProductionListId.SOLDIERS, SlotType.PRODUCTION, 0),
                "mcu",
                {"LID": 0, "S": 0, "ST": "production"},
            ),
            (
                lambda s: s.double_production_slot(12345, ProductionListId.SOLDIERS, SlotType.QUEUE, 2),
                "bou",
                {"LID": 0, "S": 2, "AID": 12345, "SID": 0, "ST": "queue"},
            ),
            (lambda s: s.heal_units(12345, 620, 12), "hru", {"U": 620, "A": 12}),
            (lambda s: s.cancel_heal(12345, 1), "hcs", {"S": 1}),
            (lambda s: s.skip_heal(12345, 2), "hss", {"S": 2}),
            (lambda s: s.dismiss_wounded(12345, 620, 5), "hdu", {"U": 620, "A": 5}),
            (
                lambda s: s.dismiss_wounded_units(12345, {620: 5, 621: 3}),
                "hdu",
                {"UT": [{"U": 620, "A": 5}, {"U": 621, "A": 3}]},
            ),
            (lambda s: s.heal_all(12345, 417), "hra", {"C2": 417}),
        ],
    )
    def test_actions_join_the_castle_then_send_the_client_payload(self, call, command, expected):
        client = make_client(castles=OWN)

        assert call(client.army) is True

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 0}), (command, expected)]
        assert list(conn(client).request_payloads[-1][1]) == list(expected)

    def test_the_castle_kingdom_goes_into_bup_and_bou(self):
        client = make_client(castles=[(777, Kingdom.GREEN), (12345, Kingdom.ICE)])

        client.army.produce_units(12345, ProductionListId.SOLDIERS, 620, 1)
        client.army.double_production_slot(12345, ProductionListId.SOLDIERS, SlotType.PRODUCTION, 0)

        sent = conn(client).request_payloads
        assert sent[0] == ("jaa", {"CID": 12345, "KID": 2})
        assert (sent[1][1]["SID"], sent[3][1]["SID"]) == (2, 2)

    @pytest.mark.parametrize(
        "call,command",
        [
            (lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 620, 1), "bup"),
            (lambda s: s.heal_units(12345, 620, 1), "hru"),
            (lambda s: s.dismiss_wounded(12345, 620, 1), "hdu"),
            (lambda s: s.heal_all(12345, 10), "hra"),
        ],
    )
    def test_rejected_actions_are_false(self, call, command):
        client = make_client({command: xt_packet(command, error_code=21)}, castles=OWN)
        assert call(client.army) is False

    def test_a_castle_not_in_the_castle_list_raises_before_joining(self):
        client = make_client(castles=[(777, Kingdom.ICE)])

        with pytest.raises(UnknownCastleError):
            client.army.heal_units(12345, 620, 1)
        assert conn(client).request_payloads == []

    def test_an_id_repeated_across_your_kingdoms_raises_before_joining(self):
        client = make_client(castles=[(12345, Kingdom.STORM), (12345, Kingdom.BERIMOND)])

        with pytest.raises(AmbiguousCastleError):
            client.army.produce_units(12345, ProductionListId.SOLDIERS, 620, 1)

        assert conn(client).request_payloads == []

    def test_a_refused_join_sends_no_action(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)}, castles=OWN)

        with pytest.raises(CommandError):
            client.army.heal_units(12345, 620, 1)
        assert [command for command, _ in conn(client).request_payloads] == ["jaa"]
