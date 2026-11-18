"""Event packages read from the items, as EventPackageVO.fillFromParamXML reads them."""

from __future__ import annotations

from empire_core.enums import CollectableKind, Rareness
from empire_core.gamedata import GameData, PackageId

CURRENCIES = [{"currencyID": "28", "Name": "LegendaryToken", "JSONKey": "LT"}]

ITEMS = {
    "currencies": CURRENCIES,
    "packages": [
        {"packageID": "10", "packageType": "item", "comment1": "x", "packagePriceC2": "150", "equipmentAmount": "1"},
        {
            "packageID": "11",
            "packageType": "deco",
            "sortOrder": "11",
            "costLegendaryToken": "50",
            "buildingID": "381",
            "buildingAmount": "1",
            "stock": "2",
        },
        {
            "packageID": "12",
            "packageType": "lootBox",
            "costLegendaryToken": "7500",
            "notRebuyable": "1",
            "lootBox": "15+1",
        },
        {
            "packageID": "13",
            "packageType": "resources",
            "fillUpResourceStorage": "1",
            "amountWood": "10000000",
            "amountStone": "10000000",
            "isBannerPackage": "1",
        },
        {
            "packageID": "14",
            "packageType": "gem",
            "costLegendaryToken": "1500",
            "specialGemOfLevelID": "5",
            "gemAmount": "1",
        },
        {
            "packageID": "15",
            "packageType": "item",
            "packagePriceC2": "31250",
            "equipmentIDs": "27",
            "equipmentAmount": "1",
        },
        {"packageID": "16", "packageType": "item", "packagePriceC2": "20", "equipmentIDs": "28", "minLevel": 10},
        {"packageID": "20", "packageType": "packageBundle", "packagePriceC2": "125000", "packageIDs": "15,16,99"},
        {
            "packageID": "21",
            "packageType": "currency",
            "packagePriceWood": "100",
            "packagePriceC1": "20",
            "addLegendaryToken": "5",
            "unitID": "1",
            "unitAmount": "25",
        },
        {
            "packageID": "22",
            "packageType": "xp",
            "packagePriceAquamarine": "5",
            "packagePriceHoney": "2",
            "amountXP": "300",
        },
        {"packageID": "24", "packageType": "unit", "unitID": "1", "unitAmount": "5", "stock": "3"},
        {"packageID": "23", "packageType": "hero", "specialHeroOfRarenessID": "12", "heroAmount": "1"},
    ],
    "events": [{"eventID": "42", "eventType": "Merchant", "packageIDs": "10+11+404"}],
}


def _data() -> GameData:
    return GameData.parse("790.02", ITEMS)


def _kinds(package_id: int) -> list[tuple[CollectableKind, object, float]]:
    return [(c.kind, c.item, c.amount) for c in _data().packages[PackageId(package_id)].rewards]


def test_a_package_without_prices_costs_rubies_0_and_reads_the_client_defaults():
    package = _data().packages[PackageId(23)]

    assert [(c.kind, c.amount) for c in package.costs] == [(CollectableKind.RUBIES, 0)]
    assert (package.min_level, package.max_level, package.min_legend_level, package.max_legend_level) == (0, 99, 0, 950)
    assert (package.stock, package.max_buy_per_click, package.sort_order) == (-1, 1000, 0.0)
    assert not package.is_stock_limited and package.remaining_stock(5) == 1000


def test_goods_prices_come_first_in_the_client_goods_order_then_the_cost_columns():
    data = _data()

    assert [(c.kind, c.amount) for c in data.packages[PackageId(21)].costs] == [
        (CollectableKind.WOOD, 100),
        (CollectableKind.COINS, 20),
    ]
    assert [(c.kind, c.amount) for c in data.packages[PackageId(22)].costs] == [
        (CollectableKind.AQUAMARINE, 5),
        (CollectableKind.HONEY, 2),
    ]
    assert [(c.kind, c.key, c.amount) for c in data.packages[PackageId(11)].costs] == [
        (CollectableKind.CURRENCY, "LT", 50)
    ]


def test_the_rewards_read_the_prefixed_columns_then_the_switch_columns():
    currency, units = _data().packages[PackageId(21)].rewards

    assert (currency.kind, currency.key, currency.amount) == (CollectableKind.CURRENCY, "LT", 5)
    assert (units.kind, units.item, units.amount) == (CollectableKind.UNITS, 1, 25)


def test_a_building_package_places_its_building():
    package = _data().packages[PackageId(11)]

    assert [(c.kind, c.item, c.amount) for c in package.rewards] == [(CollectableKind.BUILDING, 381, 1)]
    assert package.places_building
    assert package.is_stock_limited and package.remaining_stock(1) == 1 and package.remaining_stock(3) == 0


def test_random_equipment_and_gems_only_where_the_row_names_none():
    assert _kinds(10) == [(CollectableKind.RANDOM_REWARD, CollectableKind.EQUIPMENT_RARENESS, 1)]
    assert _kinds(14) == [(CollectableKind.GEM_RANDOM, -5, 1)]
    assert [(k, i, a) for k, i, a in _kinds(15)] == [(CollectableKind.EQUIPMENT_UNIQUE, 27, 1)]
    assert _kinds(23) == [(CollectableKind.HERO_RANDOM, Rareness.HERO_RARE, 1)]


def test_amount_columns_and_xp():
    assert [(k, a) for k, _, a in _kinds(13)] == [(CollectableKind.WOOD, 10000000), (CollectableKind.STONE, 10000000)]
    assert _kinds(22) == [(CollectableKind.XP, None, 300)]


def test_a_loot_box_and_not_rebuyable():
    package = _data().packages[PackageId(12)]

    assert [(c.kind, c.item, c.amount) for c in package.rewards] == [(CollectableKind.LOOT_BOX, 15, 1)]
    assert package.is_stock_limited and package.remaining_stock(0) == 1 and package.remaining_stock(1) == 0


def test_storage_priced_packages_have_a_custom_price():
    data = _data()

    assert data.packages[PackageId(13)].has_custom_price
    assert data.packages[PackageId(13)].is_banner_package
    assert not data.packages[PackageId(11)].has_custom_price


def test_a_bundle_gives_the_rewards_of_the_packages_it_names():
    bundle = _data().packages[PackageId(20)]

    assert bundle.bundle_package_ids == (15, 16, 99)
    assert [(c.kind, c.item) for c in bundle.rewards] == [
        (CollectableKind.EQUIPMENT_UNIQUE, 27),
        (CollectableKind.EQUIPMENT_UNIQUE, 28),
    ]
    assert not bundle.places_building


def test_an_event_names_its_shop_packages():
    assert _data().events[42].package_ids == (10, 11, 404)


def test_the_cache_keeps_the_cost_and_reward_columns(tmp_path):
    _data()._write_cache(tmp_path / "cache.json")

    again = GameData._read_cache(tmp_path / "cache.json", "790.02")

    assert again is not None
    for package_id in (10, 11, 12, 13, 14, 20, 21, 22, 23):
        assert again.packages[PackageId(package_id)] == _data().packages[PackageId(package_id)]
    assert "comment1" not in again._table_rows["packages"][10]


def test_what_the_shop_shows_and_what_may_be_bought_in_bulk():
    data = _data()

    resources, random, building, bundle = (data.packages[PackageId(i)] for i in (13, 10, 11, 20))
    assert random.shown_reward is None and bundle.shown_reward is None
    assert building.shown_reward is not None and building.shown_reward.kind is CollectableKind.BUILDING
    assert not random.may_be_bought_in_bulk() and not building.may_be_bought_in_bulk()
    assert not resources.may_be_bought_in_bulk()
    assert data.packages[PackageId(22)].may_be_bought_in_bulk()
    units = data.packages[PackageId(24)]
    assert units.may_be_bought_in_bulk(bought=1) and not units.may_be_bought_in_bulk(bought=2)
