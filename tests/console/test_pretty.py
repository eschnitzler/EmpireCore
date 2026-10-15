from enum import Enum

from pydantic import BaseModel

from empire_core.console.pretty import pretty


class Colour(Enum):
    RED = 1


class Inner(BaseModel):
    x: int
    colour: Colour


class Outer(BaseModel):
    name: str
    inners: list[Inner]
    tags: dict[str, int]


def test_short_values_stay_on_one_line():
    assert pretty(Inner(x=1, colour=Colour.RED)) == "Inner(x=1, colour=Colour.RED)"


def test_long_values_break_over_indented_lines():
    value = Outer(name="n" * 30, inners=[Inner(x=i, colour=Colour.RED) for i in range(3)], tags={"a": 1})
    assert pretty(value, width=60) == (
        "Outer(\n"
        "    name='nnnnnnnnnnnnnnnnnnnnnnnnnnnnnn',\n"
        "    inners=[\n"
        "        Inner(x=0, colour=Colour.RED),\n"
        "        Inner(x=1, colour=Colour.RED),\n"
        "        Inner(x=2, colour=Colour.RED),\n"
        "    ],\n"
        "    tags={'a': 1},\n"
        ")"
    )


def test_long_lists_are_cut():
    text = pretty(list(range(100)), width=40, max_items=5)
    assert "… 95 more" in text and "99" not in text
