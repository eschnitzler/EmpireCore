"""
The castle and world tables, read as the client reads them: the real items 790.06 rows
(tests/data/castle_tables.json) and synthetic edge cases.
"""

import json
from pathlib import Path

import pytest

from empire_core.enums import CollectableKind, Kingdom
from empire_core.enums.map import _KINGDOM_NAMES
from empire_core.gamedata import (
    Building,
    CurrencyId,
    FusionForgeId,
    GameData,
    SceatSkill,
    TreasureMapId,
    Unit,
)

REAL = json.loads((Path(__file__).parents[1] / "data" / "castle_tables.json").read_text())

TABLES = {
    "kingdoms": "kingdoms",
    "kingdom_villages": "villages",
    "expansions": "expansions",
    "resources": "resources",
    "mine_types": "mineTypes",
    "landmarks": "landmarks",
    "wishing_well_levels": "wishingwells",
    "catalysts": "catalysts",
    "forge_minute_skips": "forgeMinuteSkips",
    "fusion_cost_sequences": "fusionCostSequences",
    "fusion_shops": "fusionShops",
    "officers_school_currencies": "officersSchoolCurrencies",
    "officers_school_unit_pairs": "officersSchoolUnitPairs",
}


@pytest.fixture(scope="module")
def real() -> GameData:
    return GameData.parse("790.06", REAL)


def parse(**tables: object) -> GameData:
    return GameData.parse("0.01", dict(tables))


@pytest.mark.parametrize(("attribute", "items_table"), TABLES.items())
def test_every_real_row_reads(real: GameData, attribute: str, items_table: str) -> None:
    assert len(getattr(real, attribute)) == len(REAL[items_table])


def test_every_table_survives_the_cache(real: GameData, tmp_path: Path) -> None:
    cache_file = tmp_path / "items.json"
    real._write_cache(cache_file)
    cached = GameData._read_cache(cache_file, "790.06")
    assert cached is not None
    for attribute in TABLES:
        assert dict(getattr(cached, attribute)) == dict(getattr(real, attribute)), attribute


def test_every_real_slum_reads(real: GameData) -> None:
    assert len(real.slums) == len(REAL["slums"])


class TestKingdoms:
    def test_a_real_kingdom(self, real: GameData) -> None:
        ice = real.kingdoms[Kingdom.ICE]
        assert ice.name == "Icecream"
        assert (ice.min_level, ice.min_premium_unlock_level) == (25, 18)
        assert ice.required_kingdom_id is Kingdom.GREEN
        assert (ice.unit_travel_tax_percent, ice.goods_travel_tax_percent) == (30, 20)
        assert (ice.village_cap_wood, ice.village_cap_coal) == (5, 0)
        assert ice.beginner_protection_seconds == 172800

    def test_a_missing_nan_column_is_none(self, real: GameData) -> None:
        berimond = real.kingdoms[Kingdom.BERIMOND]
        assert berimond.max_villages is None
        assert berimond.goods_travel_tax_percent is None
        assert berimond.village_cap_coal == 0
        assert real.kingdoms[Kingdom.GREEN].required_kingdom_id == -1

    def test_the_hand_written_names_match_the_table(self, real: GameData) -> None:
        assert {kingdom: row.name for kingdom, row in real.kingdoms.items()} == _KINGDOM_NAMES

    def test_villages(self, real: GameData) -> None:
        sands = real.kingdom_villages[Kingdom.SANDS]
        assert (sands.wall_id, sands.gate_id, sands.keep_id) == (
            Building.CASTLEWALL_L3,
            Building.BASIC_L3_452,
            Building.KEEP_L3,
        )
        assert sands.moat_id == -1
        assert (sands.peasants, sands.guards, sands.food_boost, sands.iron_boost) == (200, 40, 30, 0)
        assert Kingdom.GREEN not in real.kingdom_villages

    def test_unreadable_village_columns(self) -> None:
        row = parse(villages=[{"kID": "2", "wallWodId": "x", "productivityCoalBoost": "y"}]).kingdom_villages[2]
        assert (row.wall_id, row.peasants, row.coal_boost) == (None, None, 0)


class TestSlums:
    def test_a_real_slum_level(self, real: GameData) -> None:
        slum = real.slum(Kingdom.ICE, 1)
        assert slum is not None
        assert (slum.part_price_id, slum.package_ids) == (15, (100, 2793))
        first, storm = real.slum(Kingdom.ICE, 0), real.slum(Kingdom.STORM, 1)
        assert first is not None and first.part_price_id is None
        assert storm is not None and len(storm.package_ids) == 19
        assert real.slum(Kingdom.ICE, 5) is None

    def test_the_level_reads_with_the_clients_int(self) -> None:
        rows = parse(slums=[{"kID": "2", "slumLevel": "3x"}, {"kID": "1", "slumLevel": "2"}]).slums
        assert [row.level for row in rows] == [0, 2]

    def test_slums_survive_the_cache(self, real: GameData, tmp_path: Path) -> None:
        cache_file = tmp_path / "items.json"
        real._write_cache(cache_file)
        cached = GameData._read_cache(cache_file, "790.06")
        assert cached is not None
        assert cached.slums == real.slums


class TestExpansions:
    def test_the_price_for_a_space_and_level(self, real: GameData) -> None:
        sands = real.expansion(Kingdom.SANDS, 3)
        fire = real.expansion(Kingdom.FIRE, 3)
        assert sands is not None and sands is fire
        assert sands.cost_rubies == 600
        assert [(cost.kind, cost.amount) for cost in sands.costs] == [
            (CollectableKind.WOOD, 4093),
            (CollectableKind.STONE, 4093),
        ]
        assert sands.locked_by_skill_id is None

    def test_rubies_are_not_among_the_costs(self, real: GameData) -> None:
        assert all(cost.kind is not CollectableKind.RUBIES for row in real.expansions.values() for cost in row.costs)

    def test_a_skill_locked_expansion(self, real: GameData) -> None:
        locked = real.expansion(Kingdom.GREEN, 17)
        assert locked is not None
        assert locked.locked_by_skill_id is SceatSkill.ONWARDS_AND_OUTWARDS_L1
        assert {cost.amount for cost in locked.costs} == {500, 2500}

    def test_a_season_map_space(self, real: GameData) -> None:
        thorn_king = real.expansion(TreasureMapId.THORN_KING_NORMAL, 1)
        assert thorn_king is not None
        assert thorn_king.space_ids[0] is TreasureMapId.THORN_KING_NORMAL
        assert (thorn_king.expansion_id, thorn_king.cost_rubies) == (74, 200)

    def test_past_the_last_level(self, real: GameData) -> None:
        assert real.expansion(Kingdom.GREEN, 1000) is None

    def test_space_ids_skip_empty_parts(self) -> None:
        row = parse(expansions=[{"expansionID": "1", "spaceIDs": "1,,3", "expansionLevel": "2"}]).expansions[1]
        assert row.space_ids == (Kingdom.SANDS, Kingdom.FIRE)


def test_resources_name_their_kinds(real: GameData) -> None:
    assert [row.kind for row in real.resources.values()][:3] == [
        CollectableKind.COINS,
        CollectableKind.RUBIES,
        CollectableKind.WOOD,
    ]
    assert all(row.kind is not CollectableKind.OTHER for row in real.resources.values())
    assert parse(resources=[{"resourceID": "5", "name": "nothing"}]).resources[5].kind is CollectableKind.OTHER


class TestMineTypes:
    def test_ruby_and_coin_mines(self, real: GameData) -> None:
        ruby, coin = real.mine_types[1], real.mine_types[2]
        assert (ruby.kind, ruby.amount_per_collect, ruby.total_amount) == (CollectableKind.RUBIES, 250, 250 * 360)
        assert (coin.kind, coin.amount_per_collect, coin.total_amount) == (CollectableKind.COINS, 500, 500 * 30)

    def test_an_influence_mine(self, real: GameData) -> None:
        mine = real.mine_types[28]
        assert (mine.influence_per_minute, mine.max_influence_points, mine.reduction_display) == (850, 100000, 75)
        assert (mine.kind, mine.amount_per_collect) == (CollectableKind.COINS, 0)

    def test_rubies_set_the_kind_and_coins_the_amount(self) -> None:
        mine = parse(mineTypes=[{"mineTypeID": "3", "amountPerCollectC1": "5", "amountPerCollectC2": "7"}]).mine_types[
            3
        ]
        assert (mine.kind, mine.amount_per_collect) == (CollectableKind.RUBIES, 5)


def test_landmarks(real: GameData) -> None:
    assert real.landmarks[1].is_default
    assert real.landmarks[1].prebuilt_castle_id == 0
    assert (real.landmarks[2].prebuilt_castle_id, real.landmarks[2].default_level) == (37, 11)


class TestWishingWell:
    def test_levels(self, real: GameData) -> None:
        first, last = real.wishing_well_levels[0], real.wishing_well_levels[10]
        assert (first.wishing_well_id, first.entry_rubies, first.upgrade_id, first.downgrade_id) == (601, None, 602, -1)
        assert (last.entry_rubies, last.lucky_pennies, last.waiting_seconds, last.upgrade_id) == (2000, 1, 72000, -1)
        assert (real.wishing_well_levels[1].cost_wood, real.wishing_well_levels[2].cost_wood) == (500, None)

    def test_a_row_without_a_level_is_left_out(self) -> None:
        assert (
            len(parse(wishingwells=[{"wodID": 601, "level": "x"}, {"wodID": 602, "level": "1"}]).wishing_well_levels)
            == 1
        )


class TestFusionForge:
    def test_catalysts(self, real: GameData) -> None:
        catalyst = real.catalysts[CurrencyId.DC80]
        assert catalyst.forge_id is FusionForgeId.DECORATIONS
        assert (catalyst.tier, catalyst.max_fusion_level, catalyst.dust_gained, catalyst.deprecated) == (
            80,
            800,
            160,
            False,
        )
        assert real.catalysts[100001].deprecated

    def test_catalyst_defaults(self) -> None:
        catalyst = parse(catalysts=[{"currencyID": "7", "deprecated": "x", "tier": "y"}]).catalysts[7]
        assert (catalyst.forge_id, catalyst.deprecated, catalyst.tier) == (-1, True, 0)

    def test_minute_skips(self, real: GameData) -> None:
        assert [row.currency_id for row in real.forge_minute_skips.values()] == [
            CurrencyId.SKIP_5_HOURS,
            CurrencyId.SKIP_24_HOURS,
        ]

    @pytest.mark.parametrize(("target_level", "step"), [(1, 1), (4, 4), (5, 1), (8, 4), (10, 2)])
    def test_the_cost_cycle(self, real: GameData, target_level: int, step: int) -> None:
        row = real.fusion_cost_step(FusionForgeId.DECORATIONS, target_level)
        assert row is not None
        assert row.step == step

    def test_cost_kinds(self, real: GameData) -> None:
        assert [row.cost_kind for row in real.fusion_cost_sequences.values()] == [
            CollectableKind.IRON,
            CollectableKind.COAL,
            CollectableKind.OIL,
            CollectableKind.GLASS,
        ]

    def test_a_forge_without_a_cycle(self, real: GameData) -> None:
        assert real.fusion_cost_step(99, 3) is None

    def test_shops(self, real: GameData) -> None:
        assert real.fusion_shops[1].package_ids == (90000, 90005)
        assert parse(fusionShops=[{"id": "3", "packageIDs": "4++x+5"}]).fusion_shops[3].package_ids == (4, 5)


class TestOfficersSchool:
    def test_currencies_read_by_name(self, real: GameData) -> None:
        assert [row.currency_id for row in real.officers_school_currencies.values()] == [
            CurrencyId.KHAN_TABLETS,
            CurrencyId.SAMURAI_TOKENS,
            CurrencyId.KHAN_MEDALS,
        ]

    def test_an_unknown_currency_is_left_out(self) -> None:
        data = parse(officersSchoolCurrencies=[{"id": "1", "currency": "Nothing"}])
        assert 1 not in data.officers_school_currencies

    def test_unit_pairs(self, real: GameData) -> None:
        pair = real.officers_school_unit_pairs[1]
        assert pair.unit_ids == (Unit.ELITEMACE, Unit.ELITECROSSBOWMAN)
        assert pair.unlock_building_id is Building.OFFICERS_SCHOOL_L1

    def test_the_first_pair_naming_a_unit_unlocks_it(self, real: GameData) -> None:
        assert real.officers_school_unlock_building(Unit.ELITEMACE) is Building.OFFICERS_SCHOOL_L1
        assert real.officers_school_unlock_building(664) == 1791
        assert real.officers_school_unlock_building(1) is None
