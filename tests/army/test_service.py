"""Tests for the army service."""

from __future__ import annotations

import pytest

from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError, CommandError, GameDataNotLoadedError, UnknownCastleError
from empire_core.gamedata import GameData, Tool, Unit
from empire_core.protocol.models import ProductionListId, SlotType
from tests.service_helpers import conn, make_client, xt_packet

OWN = [(12345, Kingdom.GREEN)]

# 620 and 649 cost no rubies; 700 costs rubies, 702 on a temporary server, and 701 heals for them
ITEMS = {
    "units": [
        {"wodID": "620", "name": "Barracks", "type": "Swordsman"},
        {"wodID": "649", "name": "Workshop", "type": "Ladder", "slotTypes": "1"},
        {"wodID": "700", "name": "Eventunit", "type": "Elite", "costC2": "1337"},
        {"wodID": "701", "name": "Barracks", "type": "Veteran", "healingCostC2": "5"},
        {"wodID": "702", "name": "Eventtool", "type": "Ram", "slotTypes": "1", "tempServerCostC2": "50"},
    ]
}


def army_client(script=None, castles=OWN):
    client = make_client(script, castles=castles)
    client.game_data = GameData.parse("test", ITEMS)
    return client


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

        assert response.units == {107: 86058, 178: 38712}
        assert response.in_production == {105: 12}
        assert response.stronghold == {646: 500}
        assert response.hospital == {627: 7}
        assert all(isinstance(unit, (Unit, Tool)) for unit in response.units)

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

        assert list(units.items()) == [(487, 100), (488, 20), (301, 5)]
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

    def test_a_list_the_castle_cannot_produce_reads_as_empty(self):
        # The server answers {} for such a list (seen live: auxiliaries on a castle without that building)
        client = make_client({"spl": xt_packet("spl", {})}, castles=OWN)

        production = client.army.get_production_list(12345, ProductionListId.AUXILIARIES)

        assert production.queue == []

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
                    12345, ProductionListId.TOOLS, 649, 20, spend_rubies=True, private_offer_id=88
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
                lambda s: s.double_production_slot(
                    12345, ProductionListId.SOLDIERS, SlotType.QUEUE, 2, spend_rubies=True
                ),
                "bou",
                {"LID": 0, "S": 2, "AID": 12345, "SID": 0, "ST": "queue"},
            ),
            (lambda s: s.heal_units(12345, 620, 12), "hru", {"U": 620, "A": 12}),
            (lambda s: s.cancel_heal(12345, 1), "hcs", {"S": 1}),
            (lambda s: s.skip_heal(12345, 2, spend_rubies=True), "hss", {"S": 2}),
            (lambda s: s.dismiss_wounded(12345, 620, 5), "hdu", {"U": 620, "A": 5}),
            (
                lambda s: s.dismiss_wounded_units(12345, {620: 5, 621: 3}),
                "hdu",
                {"UT": [{"U": 620, "A": 5}, {"U": 621, "A": 3}]},
            ),
            (lambda s: s.heal_all(12345, 417, spend_rubies=True), "hra", {"C2": 417}),
            (lambda s: s.heal_all(12345, 0), "hra", {"C2": 0}),
            (lambda s: s.heal_units(12345, 701, 3, spend_rubies=True), "hru", {"U": 701, "A": 3}),
            (
                lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 700, 1, spend_rubies=True),
                "bup",
                {"LID": 0, "WID": 700, "AMT": 1, "PO": -1, "PWR": 1, "SK": 73, "SID": 0, "AID": 12345},
            ),
        ],
    )
    def test_actions_join_the_castle_then_send_the_client_payload(self, call, command, expected):
        client = army_client()

        assert call(client.army) is True

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 0}), (command, expected)]
        assert list(conn(client).request_payloads[-1][1]) == list(expected)

    def test_the_castle_kingdom_goes_into_bup_and_bou(self):
        client = army_client(castles=[(777, Kingdom.GREEN), (12345, Kingdom.ICE)])

        client.army.produce_units(12345, ProductionListId.SOLDIERS, 620, 1)
        client.army.double_production_slot(12345, ProductionListId.SOLDIERS, SlotType.PRODUCTION, 0, spend_rubies=True)

        sent = conn(client).request_payloads
        assert sent[0] == ("jaa", {"CID": 12345, "KID": 2})
        assert (sent[1][1]["SID"], sent[3][1]["SID"]) == (2, 2)

    @pytest.mark.parametrize(
        "call,command",
        [
            (lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 620, 1), "bup"),
            (lambda s: s.heal_units(12345, 620, 1), "hru"),
            (lambda s: s.dismiss_wounded(12345, 620, 1), "hdu"),
            (lambda s: s.heal_all(12345, 10, spend_rubies=True), "hra"),
        ],
    )
    def test_rejected_actions_are_false(self, call, command):
        client = army_client({command: xt_packet(command, error_code=21)})
        assert call(client.army) is False

    @pytest.mark.parametrize(
        "call",
        [
            lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 700, 1),
            lambda s: s.produce_units(12345, ProductionListId.TOOLS, 702, 1),
            lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 999, 1),
            lambda s: s.double_production_slot(12345, ProductionListId.SOLDIERS, SlotType.PRODUCTION, 0),
            lambda s: s.heal_units(12345, 701, 1),
            lambda s: s.heal_units(12345, 999, 1),
            lambda s: s.heal_all(12345, 417),
            lambda s: s.skip_heal(12345, 0),
        ],
    )
    def test_a_call_that_spends_rubies_is_refused_before_anything_is_sent(self, call):
        client = army_client()

        with pytest.raises(ValueError, match="spend_rubies=True"):
            call(client.army)
        assert conn(client).request_payloads == []

    @pytest.mark.parametrize(
        "call",
        [
            lambda s: s.produce_units(12345, ProductionListId.SOLDIERS, 620, 1),
            lambda s: s.heal_units(12345, 620, 1),
        ],
    )
    def test_pricing_a_unit_needs_the_game_data(self, call):
        client = make_client(castles=OWN)

        with pytest.raises(GameDataNotLoadedError):
            call(client.army)
        assert conn(client).request_payloads == []

    def test_a_castle_not_in_the_castle_list_raises_before_joining(self):
        client = army_client(castles=[(777, Kingdom.ICE)])

        with pytest.raises(UnknownCastleError):
            client.army.heal_units(12345, 620, 1)
        assert conn(client).request_payloads == []

    def test_an_id_repeated_across_your_kingdoms_raises_before_joining(self):
        client = army_client(castles=[(12345, Kingdom.STORM), (12345, Kingdom.BERIMOND)])

        with pytest.raises(AmbiguousCastleError):
            client.army.produce_units(12345, ProductionListId.SOLDIERS, 620, 1)

        assert conn(client).request_payloads == []

    def test_a_refused_join_sends_no_action(self):
        client = army_client({"jaa": xt_packet("jaa", error_code=21)})

        with pytest.raises(CommandError):
            client.army.heal_units(12345, 620, 1)
        assert [command for command, _ in conn(client).request_payloads] == ["jaa"]
