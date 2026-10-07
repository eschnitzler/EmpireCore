"""Lenient id fields keep an id the enum lacks as its plain value, warned once."""

import logging
import subprocess
import sys

import pytest
from pydantic import BaseModel, ValidationError

from empire_core.enums import Kingdom
from empire_core.gamedata import Currency, EnumOrInt, EnumOrStr, GameDataId, QuestId


class Ids(BaseModel):
    kingdom: EnumOrInt[Kingdom] = Kingdom.GREEN
    quests: tuple[EnumOrInt["QuestId"], ...] = ()
    currency: EnumOrStr[Currency] | None = None


def test_a_known_id_is_its_member():
    ids = Ids.model_validate({"kingdom": 2, "quests": [3047, "3600"], "currency": "KT"})

    assert ids.kingdom is Kingdom.ICE and ids.currency is Currency.KHAN_TABLETS
    assert ids.quests == (QuestId.BUY_RUBIES, QuestId.SPEND_CURRENCY1)


def test_an_unknown_id_is_kept_and_warned_once(caplog):
    with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.lenient"):
        first = Ids.model_validate({"kingdom": 4711, "currency": "NOT_A_KEY"})
        Ids.model_validate({"kingdom": 4711})

    assert (first.kingdom, first.currency) == (4711, "NOT_A_KEY")
    assert type(first.kingdom) is int
    assert len([record for record in caplog.records if "4711" in record.getMessage()]) == 1


@pytest.mark.parametrize("value", [None, True, "x", 1.5, [1]])
def test_anything_but_an_id_fails(value):
    with pytest.raises(ValidationError):
        Ids.model_validate({"kingdom": value})


def test_members_go_on_the_wire_as_their_values():
    ids = Ids(kingdom=Kingdom.ICE, quests=(QuestId.BUY_RUBIES, 9), currency=Currency.KHAN_TABLETS)

    assert ids.model_dump(mode="json") == {"kingdom": 2, "quests": [3047, 9], "currency": "KT"}


def test_an_enum_named_by_a_string_loads_only_when_a_value_arrives():
    code = (
        "import sys\n"
        "from pydantic import BaseModel\n"
        "from empire_core.gamedata import EnumOrInt\n"
        "class M(BaseModel):\n"
        "    quest: EnumOrInt['QuestId']\n"
        "assert 'empire_core.gamedata.ids.quests' not in sys.modules\n"
        "assert M(quest=3047).quest.name == 'BUY_RUBIES'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_a_game_data_id_keeps_an_unknown_id_without_a_warning(caplog):
    class Row(BaseModel):
        quest: GameDataId["QuestId"]

    with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.lenient"):
        row = Row.model_validate({"quest": "4712"})

    assert row.quest == 4712 and type(row.quest) is int
    assert Row.model_validate({"quest": 3047}).quest is QuestId.BUY_RUBIES
    assert not caplog.records
