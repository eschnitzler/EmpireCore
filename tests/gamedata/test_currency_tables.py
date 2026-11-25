"""The currency and price tables, read as the client reads them.

``tests/data/currency_tables.json`` holds the whole tables of items 790.06; the expected values come from the
client's own parsers and lookups run in node over that file.
"""

import json
from pathlib import Path

import pytest

from empire_core.enums import CollectableKind, MessageType, RerollType
from empire_core.gamedata import MINUTE_SKIPS, Currency, CurrencyId, GameData
from empire_core.gamedata.collectables import MINUTE_SKIP_FIRST_ID
from empire_core.messages.models import MessagesSentToday

ITEMS = json.loads((Path(__file__).parents[1] / "data" / "currency_tables.json").read_text())
DATA = GameData.parse("790.06", ITEMS)


def parse(**tables: object) -> GameData:
    return GameData.parse("test", {**ITEMS, **tables})


class TestCurrencyTypes:
    def test_every_row_reads_its_range(self):
        ranges = [[row.type_id, *row.currency_id_range] for row in DATA.currency_types.values()]
        assert ranges == [
            [1, 1000, 1999],
            [2, 30000, 39999],
            [3, 1, 999],
            [4, 100001, 199999],
            [6, 2000, 2999],
            [7, 3000, 4999],
            [8, 5000, 5999],
            [9, 10000, 11000],
            [10, 7000, 7100],
            [11, 6000, 6100],
            [12, 9998, 9999],
            [13, 8000, 8100],
        ]
        assert DATA.currency_types[MINUTE_SKIPS].type_name == "MinuteSkip"

    def test_a_range_holds_both_ends(self):
        skips = DATA.currency_types[MINUTE_SKIPS]
        assert [skips.contains(currency_id) for currency_id in (999, 1000, 1999, 2000)] == [False, True, True, False]

    def test_minute_skips_by_the_table(self):
        assert DATA.is_minute_skip(CurrencyId.SKIP_24_HOURS)
        assert not DATA.is_minute_skip(5000)

    def test_the_minute_skip_keys_start_where_the_table_does(self):
        assert DATA.currency_types[MINUTE_SKIPS].currency_id_range[0] == MINUTE_SKIP_FIRST_ID

    @pytest.mark.parametrize("text", ["", "5", "a-b"])
    def test_a_range_without_both_ends_holds_nothing(self, text):
        row = parse(currencyTypes=[{"typeID": "1", "currencyIDRange": text}]).currency_types[MINUTE_SKIPS]
        assert not row.contains(5)

    def test_without_a_minute_skip_type_the_check_raises(self):
        with pytest.raises(KeyError):
            parse(currencyTypes=[]).is_minute_skip(1001)


class TestPerCurrencyTables:
    def test_caps(self):
        assert len(DATA.currency_caps) == 12
        sceat = DATA.currency_caps[CurrencyId.SCEAT]
        assert (sceat.soft_cap, sceat.hard_cap) == (99999, 125000)

    def test_rarenesses(self):
        assert len(DATA.currency_rarenesses) == 26
        assert DATA.currency_rarenesses[5003].rareness == 4

    def test_minute_skips(self):
        minutes = {int(row.currency_id): row.minutes for row in DATA.minute_skips.values()}
        assert minutes == {1001: 1, 1002: 5, 1003: 10, 1004: 30, 1005: 60, 1006: 300, 1007: 1440}

    def test_hidden_currencies(self):
        assert sorted(map(int, DATA.hidden_currencies)) == [46, 81, 91, 110]

    def test_a_missing_value_reads_as_minus_1(self):
        data = parse(currencyCaps=[{"currencyID": "64"}], currencyRarenesses=[{"currencyID": "64", "rareness": ""}])
        assert (data.currency_caps[64].soft_cap, data.currency_caps[64].hard_cap) == (-1, -1)
        assert data.currency_rarenesses[64].rareness == -1

    def test_a_negative_currency_is_left_out(self):
        assert len(parse(currencyCaps=[{"currencyID": "-1", "softCap": "5"}]).currency_caps) == 0


class TestRerollCosts:
    def test_a_row_reads_its_prices(self):
        row = DATA.reroll_costs[1]
        assert (row.reroll_type, row.reroll_count, row.cost_coins, row.cost_rubies) == (
            RerollType.ALIEN_CAMP,
            1,
            24000,
            1200,
        )
        assert [(cost.kind, cost.item, cost.amount) for cost in row.costs] == [
            (CollectableKind.CURRENCY, Currency.KHAN_TABLETS, 100),
            (CollectableKind.CURRENCY, Currency.KHAN_MEDALS, 15),
            (CollectableKind.CURRENCY, Currency.SAMURAI_TOKENS, 100),
            (CollectableKind.CURRENCY, Currency.GOLD_PIECES, 80),
            (CollectableKind.CURRENCY, Currency.SILVER_PIECES, 300),
        ]

    def test_a_missing_price_reads_as_minus_1(self):
        assert DATA.reroll_costs[41].cost_coins == -1

    @pytest.mark.parametrize(
        ("reroll_type", "free", "ids"),
        [
            (RerollType.ALIEN_CAMP, 0, [20, 1, 2, 5, 6, 7, 20, 20, 20]),
            (RerollType.TRAINING_PROGRAMS, 5, [26, 21, 22, 25, 26, 26, 26, 26, 26]),
            (RerollType.TRAINING_PROGRAM_PROLONG, 0, [45, 41, 42, 45, 45, 45, 45, 45, 45]),
        ],
    )
    def test_prices_by_count_and_free_rerolls(self, reroll_type, free, ids):
        counts = [0, 1, 2, 5, 6, 7, 20, 21, 99]
        assert [DATA.reroll_cost(reroll_type, count).reroll_cost_id for count in counts] == ids
        assert DATA.free_soft_rerolls(reroll_type) == free

    def test_a_type_without_prices_raises(self):
        with pytest.raises(ValueError, match="no reroll prices"):
            DATA.reroll_cost(RerollType.CHARGE_CAMP_EFFECT, 1)

    def test_alien_prices_go_by_position(self):
        soft = [DATA.alien_reroll_cost(n, rubies=False).reroll_cost_id for n in (0, 1, 19, 20, 25)]
        ruby = [DATA.alien_reroll_cost(n, rubies=True).reroll_cost_id for n in (0, 1, 19)]
        assert (soft, ruby) == ([1, 2, 20, 20, 20], [1, 2, 20])

    def test_a_ruby_alien_reroll_past_the_last_price_raises(self):
        with pytest.raises(ValueError, match="after 20 rerolls"):
            DATA.alien_reroll_cost(20, rubies=True)

    def test_unsorted_rows(self):
        rows = [
            {"id": "1", "type": "alien", "rerollCount": "3", "c2Cost": "30"},
            {"id": "2", "type": "alien", "rerollCount": "1", "c2Cost": "10"},
            {"id": "3", "type": "alien", "rerollCount": "2", "c2Cost": "20"},
        ]
        data = parse(rerollCosts=rows)
        assert data.reroll_cost(RerollType.ALIEN_CAMP, 5).reroll_cost_id == 1
        assert data.reroll_cost(RerollType.ALIEN_CAMP, 2).reroll_cost_id == 3
        assert data.alien_reroll_cost(1, rubies=True).reroll_cost_id == 2

    def test_an_event_currency_price_is_not_free(self):
        rows = [
            {"id": "1", "type": "officersSchool", "rerollCount": "1", "c1Cost": "0", "costKhanTablet": "0"},
            {"id": "2", "type": "officersSchool", "rerollCount": "2", "c1Cost": "0", "costKhanTablet": "5"},
        ]
        assert parse(rerollCosts=rows).free_soft_rerolls(RerollType.TRAINING_PROGRAMS) == 1


class TestAlienRerollChances:
    def test_each_kind_by_units(self):
        soft = DATA.alien_reroll_odds(rubies=False)
        ruby = DATA.alien_reroll_odds(rubies=True)
        assert [row.added_units for row in soft] == list(range(20, 501, 20))
        assert [row.added_units for row in ruby] == list(range(520, 1001, 20))
        assert (soft[0].chance, soft[9].chance, ruby[24].chance) == (0.625, 6.25, 0.625)
        assert sum(row.chance for row in soft) == sum(row.chance for row in ruby) == 100

    def test_rows_are_sorted_by_units(self):
        rows = [
            {"alienRerollChancesID": "1", "amountUnits": "40", "chance": "1", "isSoftCurrency": "1"},
            {"alienRerollChancesID": "2", "amountUnits": "20", "chance": "2", "isSoftCurrency": "1"},
            {"alienRerollChancesID": "3", "amountUnits": "30", "chance": "3", "isHardCurrency": "1"},
        ]
        data = parse(alienRerollChances=rows)
        assert [row.chance_id for row in data.alien_reroll_odds(rubies=False)] == [2, 1]
        assert [row.chance_id for row in data.alien_reroll_odds(rubies=True)] == [3]

    def test_a_row_without_units_is_left_out(self):
        rows = [{"alienRerollChancesID": "1", "chance": "5", "isSoftCurrency": "1"}]
        assert parse(alienRerollChances=rows).alien_reroll_odds(rubies=False) == []


class TestMessageRestrictions:
    def test_every_row(self):
        rows = [
            [row.restriction_id, row.message_type, row.daily_limit, row.min_level, row.min_level_special_server]
            for row in DATA.message_restrictions.values()
        ]
        assert rows == [[1, 2, 75, 16, 1], [2, 22, 350, 1, 1], [3, 36, 50, 1, 1]]

    def test_by_message_type(self):
        restriction = DATA.message_restriction(MessageType.USER_OUT)
        assert restriction is not None
        assert restriction.daily_limit == 75
        assert restriction.required_level() == 16
        assert restriction.required_level(special_server=True) == 1
        newsletter = DATA.message_restriction(MessageType.ALLIANCE_NEWSLETTER)
        assert newsletter is not None
        assert newsletter.restriction_id == 2
        assert DATA.message_restriction(99) is None

    def test_parse_int_of_the_value_or_its_default(self):
        rows = [
            {"messageRestrictionID": "1", "messageType": "2", "minLevel": 0},
            {"messageRestrictionID": "2", "messageType": "22", "minLevel": "0", "minLevelGlobalServer": ""},
            {"messageRestrictionID": "3", "minLevel": "x"},
        ]
        first, second, third = parse(messageRestrictions=rows).message_restrictions.values()
        assert (first.min_level, first.daily_limit) == (-1, None)
        assert (second.min_level, second.min_level_special_server) == (0, 1)
        assert (third.message_type, third.min_level) == (None, None)

    def test_the_first_row_of_a_type_counts(self):
        rows = [
            {"messageRestrictionID": "1", "messageType": "2", "dailyLimitPerPlayer": "5"},
            {"messageRestrictionID": "2", "messageType": "2", "dailyLimitPerPlayer": "9"},
        ]
        restriction = parse(messageRestrictions=rows).message_restriction(MessageType.USER_OUT)
        assert restriction is not None
        assert restriction.daily_limit == 5

    def test_the_limit_against_the_messages_sent_today(self):
        restriction = DATA.message_restriction(MessageType.USER_OUT)
        assert restriction is not None
        assert not MessagesSentToday.model_validate({"MTC": [[2, 74], [22, 400]]}).limit_reached(restriction)
        assert MessagesSentToday.model_validate({"MTC": [[2, 75]]}).limit_reached(restriction)
        assert not MessagesSentToday.model_validate({}).limit_reached(restriction)

    def test_without_a_limit_it_is_never_reached(self):
        rows = [{"messageRestrictionID": "1", "messageType": "2"}]
        restriction = parse(messageRestrictions=rows).message_restrictions[1]
        assert not MessagesSentToday.model_validate({"MTC": [[2, 10**6]]}).limit_reached(restriction)
