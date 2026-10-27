"""The brewery (abpi, bfl), private villages (bpv, upv, rpv), the dialog reads (sub, gctb, fce), the tax bribe
(btx), the mission refresh (rmm), the reads behind pushes (csp, nec, irc, rei) and the gca and sea pushes."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.castle import (
    BreweryProductionResponse,
    BribeTaxCollectorRequest,
    BuildingRow,
    BuyPrivateVillageRequest,
    CastleBuildingsPushed,
    GetBreweryProductionRequest,
    PrivateVillage,
    RefreshMercenaryMissionRequest,
    RemovePrivateVillageRequest,
    SelectCastleResponse,
    SetBreweryProductionRequest,
    SetMeadPriorityRequest,
    ShowUpgradableBuildingsRequest,
    ShowUpgradableBuildingsResponse,
    TransportationBuildingsResponse,
    UpgradePrivateVillageRequest,
)
from empire_core.castle.models.brewery import BreweryStops, MeadShare
from empire_core.enums import Kingdom, TaxStatus
from empire_core.events import SeasonEventResponse
from empire_core.exceptions import CommandError, UnknownCastleError
from empire_core.gamedata import Building, PrivateVillageType
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

BREWERY = BuildingRow.from_list([1959, 42, 3, 4, 0, 0, 0, 100, 100, 100, 0, 0, 0, 0, 0])
ABPI: dict[str, Any] = {"PA": {"MEAD": 40}, "MS": {"F": 100, "HONEY": 5}, "SRPF": 0, "bfl": {"PPOT": 1}}


class TestBrewery:
    def test_requests_send_the_client_keys(self):
        get = GetBreweryProductionRequest(kingdom_id=Kingdom.ICE, castle_id=7, wod_id=1959, object_id=42)
        assert get.to_payload() == {"KID": 2, "AID": 7, "WID": 1959, "OID": 42}
        assert get.wod_id is Building.RELIC_BREWERY_L1
        set_ = SetBreweryProductionRequest(
            kingdom_id=Kingdom.ICE,
            castle_id=7,
            wod_id=1959,
            object_id=42,
            share=MeadShare(mead_percent=40),
            stops=BreweryStops(food=100, honey=5),
        )
        assert set_.to_payload() == {
            "KID": 2,
            "AID": 7,
            "WID": 1959,
            "OID": 42,
            "PA": {"MEAD": 40},
            "MS": {"F": 100, "HONEY": 5},
        }
        prio = SetMeadPriorityRequest(kingdom_id=Kingdom.GREEN, castle_id=7, enabled=True)
        assert prio.to_payload() == {"KID": 0, "AID": 7, "PPOT": 1}

    def test_the_reply_reads_the_production(self):
        reply = parse_response("abpi", ABPI)
        assert isinstance(reply, BreweryProductionResponse)
        assert reply.share.mead_percent == 40
        assert (reply.stops.food, reply.stops.honey) == (100, 5)
        assert reply.mead_priority.enabled and not reply.production_frozen

    def test_a_join_reads_the_first_brewery_entry(self):
        reply = SelectCastleResponse.model_validate({"KID": 0, "abpi": [ABPI]})
        assert reply.brewery is not None and reply.brewery.share.mead_percent == 40
        assert SelectCastleResponse.model_validate({"KID": 0, "abpi": []}).brewery is None

    def test_service_sends_the_castle_and_the_brewery(self):
        client = make_client({"abpi": [xt_packet("abpi", ABPI), xt_packet("abpi", ABPI)]}, castles=[(7, Kingdom.ICE)])

        client.castle.get_brewery_production(7, BREWERY)
        client.castle.set_brewery_production(7, BREWERY, 40, stop_at_food=100, stop_at_honey=5)
        client.castle.set_mead_priority(7, False)

        assert conn(client).request_payloads == [
            ("abpi", {"KID": 2, "AID": 7, "WID": 1959, "OID": 42}),
            ("abpi", {"KID": 2, "AID": 7, "WID": 1959, "OID": 42, "PA": {"MEAD": 40}, "MS": {"F": 100, "HONEY": 5}}),
            ("bfl", {"KID": 2, "AID": 7, "PPOT": 0}),
        ]

    def test_an_unknown_castle_sends_nothing(self):
        client = make_client(castles=[(7, Kingdom.ICE)])
        with pytest.raises(UnknownCastleError):
            client.castle.get_brewery_production(8, BREWERY)
        assert conn(client).request_payloads == []


WOOD_L1 = PrivateVillageType.ICE_PRIVATE_WOOD_VILLAGE_L1


class TestPrivateVillages:
    def test_requests_send_the_client_keys(self):
        assert BuyPrivateVillageRequest(village_type_id=WOOD_L1).to_payload() == {"XID": 41}
        upgrade = UpgradePrivateVillageRequest(village_type_id=WOOD_L1, village_id=90)
        assert upgrade.to_payload() == {"XID": 41, "VID": 90}
        assert upgrade.village_type_id is WOOD_L1
        assert RemovePrivateVillageRequest(village_id=90).to_payload() == {"VID": 90}

    def test_the_type_carries_its_kingdom_resource_and_level(self):
        assert (WOOD_L1.kingdom_id, WOOD_L1.resource, WOOD_L1.level) == (Kingdom.ICE, "wood", 1)

    def test_service(self):
        client = make_client()
        client.castle.buy_private_village(WOOD_L1)
        village = PrivateVillage.model_validate({"VID": 90, "XID": 41})
        client.castle.upgrade_private_village(village)
        client.castle.remove_private_village(village)
        assert conn(client).request_payloads == [
            ("bpv", {"XID": 41}),
            ("upv", {"XID": 41, "VID": 90}),
            ("rpv", {"VID": 90}),
        ]

    def test_a_refused_buy_raises(self):
        client = make_client({"bpv": xt_packet("bpv", error_code=21)})
        with pytest.raises(CommandError):
            client.castle.buy_private_village(WOOD_L1)


class TestLookups:
    def test_upgradable_buildings(self):
        request = ShowUpgradableBuildingsRequest(wod_id=101)
        assert request.to_payload() == {"WOD": 101, "PSU": True} and request.wod_id is Building.WOODCUTTER_L2
        reply = parse_response("sub", {"WOD": 101, "UD": [[2, 7, 42], [0, 8]], "BE": 1})
        assert isinstance(reply, ShowUpgradableBuildingsResponse)
        first, second = reply.buildings
        assert (first.kingdom, first.castle_id, first.object_id) == (Kingdom.ICE, 7, 42)
        assert (second.kingdom, second.castle_id, second.object_id) == (Kingdom.GREEN, 8, -1)
        assert reply.building_exists and reply.wod_id == Building(101)

    def test_transportation_buildings(self):
        reply = parse_response("gctb", {"BL": [[101, 2], [450, 1]]})
        assert isinstance(reply, TransportationBuildingsResponse)
        assert [(b.wod_id, b.amount) for b in reply.buildings] == [(Building(101), 2), (Building(450), 1)]

    def test_service(self):
        client = make_client(
            {
                "sub": xt_packet("sub", {"WOD": 101, "UD": [], "BE": 0}),
                "gctb": xt_packet("gctb", {"BL": [[101, 2]]}),
                "fce": xt_packet("fce", {"FRM": 25}),
            }
        )

        upgradable = client.castle.get_upgradable_buildings(Building.WOODCUTTER_L2, prime_sale_upgrade=False)
        transported = client.castle.get_transportation_buildings()
        discount = client.castle.get_feast_cost_reduction()

        assert conn(client).request_payloads == [("sub", {"WOD": 101, "PSU": False}), ("gctb", {}), ("fce", {})]
        assert upgradable.buildings == [] and not upgradable.building_exists
        assert transported[0].amount == 2
        assert discount == 25


class TestTaxBribe:
    BTX: dict[str, Any] = {"gcu": {"C1": 90, "C2": 10}, "txi": {"TX": {"TT": 2, "RT": 5400, "EM": 100}}}

    def test_the_request_sends_the_offer(self):
        assert BribeTaxCollectorRequest().to_payload() == {"PO": -1}

    def test_a_bribe_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.castle.bribe_tax_collector()
        assert conn(client).request_payloads == []

    def test_a_bribe_returns_the_tax(self):
        client = make_client({"btx": xt_packet("btx", self.BTX)})
        reply = client.castle.bribe_tax_collector(spend_rubies=True)
        assert conn(client).request_payloads == [("btx", {"PO": -1})]
        assert reply.tax_info is not None and reply.tax_info.tax.status is TaxStatus.COLLECTING


def mission(mission_id: int, state: int, rd: float = 0) -> dict[str, Any]:
    return {"ID": mission_id, "R": [["C1", 500]], "D": 3600, "P": 120, "Q": 1, "S": state, "RD": rd}


class TestMissionRefresh:
    def test_the_request_sends_the_mission(self):
        assert RefreshMercenaryMissionRequest(mission_id=4).to_payload() == {"MID": 4}

    def test_a_refresh_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.castle.refresh_mission(4)
        assert conn(client).request_payloads == []

    def test_an_open_mission_is_refreshed_while_one_runs(self):
        missions = {"NM": 600, "M": [mission(4, 0), mission(5, 1, rd=600)]}
        client = make_client({"mpe": xt_packet("mpe", missions)})

        client.castle.refresh_mission(4, spend_rubies=True)

        assert conn(client).request_payloads == [("mpe", {"MID": -1}), ("rmm", {"MID": 4})]

    @pytest.mark.parametrize(
        ("missions", "mission_id"),
        [
            # the client shows refresh only on an open mission
            ([mission(4, 1, rd=600)], 4),
            # and disables it while a mission waits to be collected
            ([mission(4, 0), mission(5, 2)], 4),
            ([mission(4, 0)], 9),
        ],
    )
    def test_refresh_refuses_what_the_client_would_not_send(self, missions: list[dict[str, Any]], mission_id: int):
        client = make_client({"mpe": xt_packet("mpe", {"NM": 600, "M": missions})})
        with pytest.raises(ValueError):
            client.castle.refresh_mission(mission_id, spend_rubies=True)
        assert conn(client).request_payloads == [("mpe", {"MID": -1})]


class TestPushReads:
    def test_the_reads_send_nothing_but_the_command_and_feed_the_state(self):
        client = make_client(
            {
                "csp": xt_packet("csp", {"C": 12}),
                "nec": xt_packet("nec", {"NCRS": 600, "LECT": -1}),
                "irc": xt_packet("irc", {"G": [["W", 50]], "EG": 0}),
                "rei": xt_packet("rei", {"BR": [1, 2], "ARID": -1, "ARRT": 0}),
            },
            state=GameState(),  # type: ignore[arg-type]
        )
        conn(client).on_packet = client._on_packet

        space = client.castle.get_construction_item_space()
        expiry = client.castle.get_construction_item_expiry()
        pool = client.castle.collect_resource_citizen()
        research = client.castle.get_research()

        assert conn(client).request_payloads == [("csp", {}), ("nec", {}), ("irc", {}), ("rei", {})]
        assert space.space_left == 12 and expiry.next_expiry_seconds == 600
        assert len(pool.goods) == 1 and research.current_research_id == -1
        assert client.castle.construction_item_space == space
        assert client.castle.research.bought_research_ids == research.bought_research_ids


class TestPushes:
    def test_a_gca_reads_the_owner_and_the_buildings(self):
        reply = parse_response("gca", {"O": {"OID": 1001, "N": "me"}, "gca": {"CI": []}})
        assert isinstance(reply, CastleBuildingsPushed)
        assert reply.owner is not None and reply.owner.owner_id == 1001
        assert reply.buildings is not None and reply.buildings.construction_items == ()

    def test_a_gca_replaces_the_joined_castles_construction_items(self):
        client = make_client(state=GameState())  # type: ignore[arg-type]
        pushed: list[CastleBuildingsPushed] = []
        client.castle.on_castle_buildings(pushed.append)
        client._on_packet(xt_packet("gca", {"O": {"OID": 1001}, "gca": {"CI": []}}))
        assert pushed == [] and client.state.get_placed_construction_items() is None

        client._on_packet(xt_packet("jaa", {"KID": 0, "gca": {"A": [1, 3, 4, 7, 1001]}}))
        client._on_packet(xt_packet("gca", {"O": {"OID": 1001}, "gca": {"CI": []}}))

        assert client.state.get_placed_construction_items() == ()
        assert [push.owner.owner_id for push in pushed if push.owner is not None] == [1001]

    def test_a_season_event_packet_is_read(self):
        assert isinstance(parse_response("sea", {}), SeasonEventResponse)
