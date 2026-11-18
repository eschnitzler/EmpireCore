"""Events with a package shop: their game data's packages and those the server adds (BuyPackagesEventVO)."""

from __future__ import annotations

from empire_core.events.models import MercenaryShopEvent, PackageShopEvent, SeasonEvent, event_class
from empire_core.gamedata import GameData
from empire_core.gamedata.ids.events import Event
from empire_core.state.manager import GameState

ITEMS = {
    "packages": [
        {"packageID": "60", "packageType": "resources", "sortOrder": "3"},
        {"packageID": "61", "packageType": "resources", "sortOrder": "1"},
        {"packageID": "62", "packageType": "resources", "sortOrder": "2"},
        {"packageID": "63", "packageType": "unit", "sortOrder": "1"},
    ],
    "events": [
        {"eventID": "42", "eventType": "Merchant", "packageIDs": "60+61+999"},
        {"eventID": "43", "eventType": "UnitDealer", "packageIDs": "63"},
        {"eventID": "76", "eventType": "FactionArmorer", "packageIDs": ""},
    ],
}


def _running(*entries: dict) -> GameState:
    state = GameState()
    state.update_from_packet("sei", {"E": list(entries)})
    return state


def test_the_shops_are_package_shop_events():
    assert event_class(Event.TRAVELING_MERCHANT_EVENT) is PackageShopEvent
    assert event_class(Event.MERCENARY_THORN_KING) is MercenaryShopEvent
    assert event_class(Event.BERIMOND_ARMORER_76) is MercenaryShopEvent
    assert not issubclass(SeasonEvent, PackageShopEvent)


def test_a_shop_sells_its_game_data_packages_and_those_the_server_adds_by_sort_order():
    state = _running({"EID": 42, "RS": 600, "PIDS": "62,abc"})
    event = state.get_event(Event.TRAVELING_MERCHANT_EVENT)

    assert isinstance(event, PackageShopEvent)
    assert event.added_package_ids == (62,)
    data = GameData.parse("790.02", ITEMS)
    assert [package.package_id for package in event.packages(game_data=data)] == [61, 62, 60]


def test_an_entry_without_pids_keeps_the_packages_added_before():
    state = _running({"EID": 42, "RS": 600, "PIDS": "62"})
    state.update_from_packet("sei", {"E": [{"EID": 42, "RS": 500}]})

    event = state.get_event(Event.TRAVELING_MERCHANT_EVENT)
    assert isinstance(event, PackageShopEvent) and event.added_package_ids == (62,)


def test_a_shop_does_not_read_kl():
    event = _running({"EID": 42, "RS": 600, "KL": 1}).get_event(Event.TRAVELING_MERCHANT_EVENT)

    assert event is not None and not event.kingdoms_league_mode


def test_only_the_berimond_armorer_reads_added_packages_among_the_mercenary_shops():
    state = _running({"EID": 43, "RS": 600, "PIDS": "60"}, {"EID": 76, "RS": 600, "PIDS": "60"})

    mercenaries = state.get_event(Event.MERCENARY_THORN_KING)
    armorer = state.get_event(Event.BERIMOND_ARMORER_76)
    assert isinstance(mercenaries, MercenaryShopEvent) and mercenaries.added_package_ids == ()
    assert isinstance(armorer, MercenaryShopEvent) and armorer.added_package_ids == (60,)
    data = GameData.parse("790.02", ITEMS)
    assert [package.package_id for package in mercenaries.packages(game_data=data)] == [63]
    assert [package.package_id for package in armorer.packages(game_data=data)] == [60]
