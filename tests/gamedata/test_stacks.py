"""Units and tools by amount, read and written as the client's containers and inventories do."""

import logging

import pytest
from pydantic import BaseModel

from empire_core.gamedata import (
    EMPTY_SLOT,
    CurrencyAmounts,
    CurrencyId,
    SupportToolSlots,
    Tool,
    Unit,
    WodAmount,
    WodAmounts,
    WodAmountSlots,
)
from empire_core.protocol.base import json_text


class Army(BaseModel):
    slots: WodAmountSlots = ()
    inventory: WodAmounts = {}
    support: SupportToolSlots = ()
    boosters: CurrencyAmounts = {}


class TestSlots:
    def test_each_slot_is_kept_in_order_duplicates_and_empty_ones_too(self):
        # CastleFightItemContainer.getSlotList writes one pair per slot, [-1, 0] for an empty one
        army = Army.model_validate({"slots": [[601, 10], [-1, 0], [601, 5], [1, 2]]})

        assert army.slots == (
            WodAmount(Unit.SWORDMAN, 10),
            EMPTY_SLOT,
            WodAmount(Unit.SWORDMAN, 5),
            WodAmount(Tool.NOMAD_TABLET_BOOST, 2),
        )
        assert json_text(army.model_dump()["slots"]) == "[[601,10],[-1,0],[601,5],[1,2]]"

    def test_a_pair_reads_through_the_clients_int(self):
        # fillFromParamArray reads int(i.shift()) twice and ignores the rest
        army = Army.model_validate({"slots": [["601", "10"], [601, 2.9], [601, 3, 99]]})

        assert army.slots == ((601, 10), (601, 2), (601, 3))

    def test_an_empty_slot_logs_no_unknown_id(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.lenient"):
            army = Army.model_validate({"slots": [[-1, 0]]})

        assert army.slots[0].item is None
        assert not caplog.records

    def test_a_pair_unpacks_like_the_list_it_came_from(self):
        unit, amount = Army.model_validate({"slots": [[601, 10]]}).slots[0]

        assert (unit, amount) == (Unit.SWORDMAN, 10)

    def test_count_fails_loudly_instead_of_being_tuple_count(self):
        # A port from the old UnitCount/UnitStack .count must not compare a bound method
        slot = WodAmount(Unit.SWORDMAN, 10)

        with pytest.raises(AttributeError, match=r"\.amount"):
            _ = slot.count
        assert slot.amount == 10 and slot == (601, 10) and hash(slot) == hash((601, 10))

    def test_a_mapping_is_one_slot_per_entry(self):
        slots = WodAmount.slots({Unit.SWORDMAN: 10, Tool.NOMAD_TABLET_BOOST: 1})

        assert slots == ((601, 10), (1, 1))
        assert Army.model_validate({"slots": {Unit.SWORDMAN: 10}}).slots == ((601, 10),)
        assert WodAmount.slots(slots) == slots


class TestInventory:
    def test_an_id_sent_twice_adds_up_and_nothing_is_dropped_below_one(self):
        # UnitInventoryDictionary: addUnit clamps at 0, changeUnitAmount adds, setUnit drops <= 0
        army = Army.model_validate({"inventory": [[601, 10], [601, 5], [652, 0], [1, -3], "x"]})

        assert army.inventory == {Unit.SWORDMAN: 15}
        assert all(isinstance(unit, Unit) for unit in army.inventory)

    def test_a_mapping_is_taken_as_it_is(self):
        assert Army.model_validate({"inventory": {601: 3}}).inventory == {Unit.SWORDMAN: 3}


class TestSupportTools:
    def test_an_empty_slot_is_none_here_and_minus_one_on_the_wire(self):
        # toolsSupportWodIds pushes -1 for an empty slot
        army = Army.model_validate({"support": [-1, 1, -1]})

        assert army.support == (None, Tool.NOMAD_TABLET_BOOST, None)
        assert army.model_dump(exclude_none=True)["support"] == [-1, 1, -1]


class TestCurrencyAmounts:
    def test_rows_by_currency_id_round_trip(self):
        # CastleFightScreenVO.addCollectorBooster pushes [currency_id, amount], a 0 amount included
        army = Army.model_validate({"boosters": [[31, 2], [32, 0]]})

        assert army.boosters == {CurrencyId.SAMURAI_MEDAL_BOOSTER: 2, CurrencyId.SHOGUN_POINTS_BOOSTER: 0}
        assert army.model_dump()["boosters"] == [[31, 2], [32, 0]]
