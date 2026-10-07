"""Collectables read as the client's collectable parser reads them, from captured shapes."""

import logging

import pytest
from pydantic import BaseModel

from empire_core.enums import BoosterId, CollectableKind, Rareness
from empire_core.gamedata import (
    Building,
    Collectable,
    CollectableObject,
    CollectableRows,
    ConstructionItem,
    Currency,
    LootBox,
    Tool,
    Unit,
)

# The login bonus's first day as Skaar's alb sent it
LOGIN_BONUS_REWARDS = {"U": [[664, 5]], "MS2": [1], "C1": [2000], "HF": [240]}


def _short(collectables: tuple[Collectable, ...]) -> list[tuple[CollectableKind, object, object]]:
    return [(c.kind, c.item, c.amount) for c in collectables]


class TestRewardObject:
    def test_the_login_bonus_rewards(self):
        rewards = Collectable.from_object(LOGIN_BONUS_REWARDS)

        assert _short(rewards) == [
            (CollectableKind.UNITS, Unit.KINGSCROSSBOWMAN, 5),
            (CollectableKind.CURRENCY, Currency.SKIP_5_MINUTES, 1),
            (CollectableKind.COINS, None, 2000),
            (CollectableKind.OTHER, None, 1),
        ]
        assert rewards[0].item is Unit.KINGSCROSSBOWMAN and rewards[1].item is Currency.SKIP_5_MINUTES

    def test_a_key_the_client_has_no_type_for_is_kept(self):
        # HF is the hidden food a quest grants; the client's parser has no type for it and drops it
        (hidden_food,) = Collectable.from_object({"HF": [240]})

        assert (hidden_food.kind, hidden_food.key, hidden_food.value) == (CollectableKind.OTHER, "HF", 240)

    def test_the_sort_order_and_a_null_list_are_skipped(self):
        assert _short(Collectable.from_object({"C1": None, "C2": [3], "SO": "C2,C1"})) == [
            (CollectableKind.RUBIES, None, 3)
        ]

    @pytest.mark.parametrize("value", [None, [], "C1", 5])
    def test_anything_but_an_object_is_empty(self, value):
        assert Collectable.from_object(value) == ()


class TestRows:
    def test_mission_rewards(self):
        rows = [["U", [687, 7]], ["U", [626, 3]], ["U", [647, 3]]]

        assert _short(Collectable.from_rows(rows)) == [
            (CollectableKind.UNITS, Unit.KINGSBOWMAN, 7),
            (CollectableKind.UNITS, Tool.GATEHARDENING, 3),
            (CollectableKind.UNITS, Tool.PREMIUMOILSMELTER, 3),
        ]

    def test_goods(self):
        assert _short(Collectable.from_rows([["S", 4]])) == [(CollectableKind.STONE, None, 4)]

    def test_a_third_place_is_the_amount_of_an_item(self):
        assert _short(Collectable.from_rows([["CI", 12, 3]])) == [(CollectableKind.CONSTRUCTION_ITEM, 12, 3)]

    def test_a_list_of_row_lists_is_flattened(self):
        assert _short(Collectable.from_rows([[["W", 5]], [["C2", 1]]])) == [
            (CollectableKind.WOOD, None, 5),
            (CollectableKind.RUBIES, None, 1),
        ]

    def test_an_old_style_list_holds_amounts_in_a_fixed_order(self):
        # wood, stone, food, coins, rubies, coal, oil, glass, then currency 1 (khan tablets)
        assert _short(Collectable.from_rows([0, 5, 0, 100, 0, 0, 0, 0, 3])) == [
            (CollectableKind.STONE, None, 5),
            (CollectableKind.COINS, None, 100),
            (CollectableKind.CURRENCY, Currency.KHAN_TABLETS, 3),
        ]

    @pytest.mark.parametrize("value", [None, [], {"S": 4}, [[1, 2]], [["S"]]])
    def test_unreadable_rows_are_skipped(self, value):
        assert all(c.kind is CollectableKind.STONE for c in Collectable.from_rows(value))


class TestKinds:
    @pytest.mark.parametrize(
        ("key", "entry", "kind", "item", "amount"),
        [
            ("C2", 45, CollectableKind.RUBIES, None, 45),
            ("c2", 45, CollectableKind.RUBIES, None, 45),
            ("MS", ["MS3", 5], CollectableKind.CURRENCY, Currency.SKIP_10_MINUTES, 5),
            ("KT", [1, 7], CollectableKind.CURRENCY, Currency.KHAN_TABLETS, 7),
            ("D", [171, 2], CollectableKind.BUILDING, Building.KEEP_L1, 2),
            ("CI", 1, CollectableKind.CONSTRUCTION_ITEM, ConstructionItem(1), 1),
            ("LB", [1, 4], CollectableKind.LOOT_BOX, LootBox.MYSTERY_BOX_BRONZE_R1, 4),
            ("LB", 1, CollectableKind.LOOT_BOX, LootBox.MYSTERY_BOX_BRONZE_R1, 1),
            ("GE", 3, CollectableKind.EQUIPMENT_RARENESS, Rareness.EPIC, 1),
            ("GE", 12, CollectableKind.HERO_RANDOM, Rareness.HERO_RARE, 1),
            ("GID", 333, CollectableKind.GEM, 333, 1),
            ("GLID", -2, CollectableKind.GEM_RANDOM, 2, 1),
            ("XP", [250], CollectableKind.XP, None, 250),
            ("GT", [7, 2], CollectableKind.GIFT_PACKAGE, 7, 2),
        ],
    )
    def test_each_kind_reads_its_entry(self, key, entry, kind, item, amount):
        collectable = Collectable.from_entry(key, entry)

        assert (collectable.kind, collectable.item, collectable.amount) == (kind, item, amount)

    @pytest.mark.parametrize(
        ("booster", "kind"),
        [
            (21, CollectableKind.XP_BOOSTER),
            (17, CollectableKind.GLORY_BOOSTER),
            (18, CollectableKind.GLORY_BOOSTER),
            (28, CollectableKind.KHAN_MEDAL_POINT_BOOSTER),
            (19, CollectableKind.BOOSTER),
            (0, CollectableKind.BOOSTER),
        ],
    )
    def test_a_booster_with_a_kind_of_its_own(self, booster, kind):
        collectable = Collectable.from_entry("B", {"ID": booster, "D": 3600})

        assert (collectable.kind, collectable.item, collectable.duration_seconds) == (kind, BoosterId(booster), 3600)

    def test_an_unknown_id_is_kept_and_warned_once(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.lenient"):
            first = Collectable.from_entry("U", [987654, 2])
            Collectable.from_entry("U", [987654, 3])

        assert (first.kind, first.item, first.amount) == (CollectableKind.UNITS, 987654, 2)
        assert type(first.item) is int
        assert len([r for r in caplog.records if "987654" in r.getMessage()]) == 1


class TestSendKey:
    @pytest.mark.parametrize(
        ("key", "entry", "expected"),
        [
            ("C1", 100, "C1"),
            ("U", [620, 5], "U"),
            ("MS2", 3, "MS2"),
            ("MS", ["MS2", 3], "MS2"),
            ("B", {"ID": 21, "D": 3600}, "XPB"),
            ("B", {"ID": 17, "D": 3600}, "PG"),
            ("B", {"ID": 0, "D": 3600}, "B"),
            ("GE", 12, "RE"),
            ("GE", 2, "GE"),
            ("w", 5, "W"),
        ],
    )
    def test_the_key_the_client_sends(self, key, entry, expected):
        assert Collectable.from_entry(key, entry).send_key == expected

    def test_an_entry_the_client_has_no_type_for_is_never_sent(self):
        with pytest.raises(ValueError, match="HF"):
            Collectable.from_entry("HF", 240).send_key  # noqa: B018


class TestFields:
    class Rewards(BaseModel):
        rows: CollectableRows = ()
        object: CollectableObject = ()

    def test_model_fields_read_both_layouts(self):
        rewards = self.Rewards.model_validate({"rows": [["S", 4]], "object": {"C1": [5]}})

        assert _short(rewards.rows) == [(CollectableKind.STONE, None, 4)]
        assert _short(rewards.object) == [(CollectableKind.COINS, None, 5)]

    def test_collectables_pass_through(self):
        stone = Collectable.from_entry("S", 4)

        assert self.Rewards(rows=(stone,)).rows == (stone,)

    def test_a_collectable_is_frozen_and_compares_by_value(self):
        stone = Collectable.from_entry("S", 4)

        assert stone == Collectable(kind=CollectableKind.STONE, key="S", amount=4)
        with pytest.raises(ValueError):
            stone.amount = 5  # type: ignore[misc]
