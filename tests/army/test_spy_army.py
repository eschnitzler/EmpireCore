"""The spy report's army block is positional, not a flat list.

CastleSpyArmyInfoVO.parseArmyInfo in the client shifts the ``S`` array in a
fixed order — left, middle, right, keep, stronghold, support, and an optional
reserve — so a flat sum of every position mixes the defending flanks with
support and reserve troops the game never counts together.
"""

import pytest

from empire_core.army import SpyArmy, SpyArmySection, UnitStack


def _army() -> list:
    return [
        [[652, 100], [746, 50]],  # left
        [[602, 200]],  # middle
        [[652, 75]],  # right
        [[746, 400]],  # keep
        [],  # stronghold
        [[602, 25]],  # support
        [[652, 10]],  # reserve
    ]


def parsed(spy_data: list) -> SpyArmy:
    """Parse and narrow: every case below expects a usable report."""
    army = SpyArmy.from_spy_data(spy_data)
    assert army is not None
    return army


class TestPositionalParsing:
    def test_each_position_lands_in_its_own_section(self):
        army = parsed(_army())

        assert army.left == [UnitStack(652, 100), UnitStack(746, 50)]
        assert army.middle == [UnitStack(602, 200)]
        assert army.right == [UnitStack(652, 75)]
        assert army.keep == [UnitStack(746, 400)]
        assert army.stronghold == []
        assert army.support == [UnitStack(602, 25)]
        assert army.reserve == [UnitStack(652, 10)]

    def test_reserve_is_optional(self):
        army = parsed(_army()[:6])

        assert army.reserve == []
        assert army.support == [UnitStack(602, 25)]

    def test_a_short_report_leaves_later_sections_empty(self):
        army = parsed([[[652, 5]]])

        assert army.left == [UnitStack(652, 5)]
        assert army.middle == []
        assert army.keep == []

    def test_empty_report_is_not_an_error(self):
        army = parsed([])

        assert army.total() == 0
        assert army.wall_total() == 0

    @pytest.mark.parametrize("bad", [None, "nonsense", 42])
    def test_unusable_payloads_are_rejected(self, bad):
        assert SpyArmy.from_spy_data(bad) is None

    def test_malformed_stacks_are_skipped_not_fatal(self):
        army = parsed([[[652, 100], "junk", [], [746]], []])

        assert army.left == [UnitStack(652, 100)]


class TestTotals:
    def test_wall_total_counts_only_the_defended_wall(self):
        # left + middle + right: what actually meets an attack on the wall.
        assert parsed(_army()).wall_total() == 425

    def test_total_counts_every_position(self):
        assert parsed(_army()).total() == 860

    def test_sections_are_addressable_for_display(self):
        labeled = [(name, sum(stack.count for stack in stacks)) for name, stacks in parsed(_army()).sections()]

        assert labeled == [
            (SpyArmySection.LEFT, 150),
            (SpyArmySection.MIDDLE, 200),
            (SpyArmySection.RIGHT, 75),
            (SpyArmySection.KEEP, 400),
            (SpyArmySection.STRONGHOLD, 0),
            (SpyArmySection.SUPPORT, 25),
            (SpyArmySection.RESERVE, 10),
        ]

    def test_one_section_is_addressable_by_its_enum(self):
        army = parsed(_army())

        assert army.section(SpyArmySection.KEEP) == [UnitStack(746, 400)]
        assert army.section(SpyArmySection("support")) == [UnitStack(602, 25)]


class TestSections:
    def test_the_enum_iterates_in_wire_order(self):
        assert [section.value for section in SpyArmySection] == [
            "left",
            "middle",
            "right",
            "keep",
            "stronghold",
            "support",
            "reserve",
        ]

    def test_the_wall_is_the_three_flanks(self):
        assert [s for s in SpyArmySection if s.is_wall] == [
            SpyArmySection.LEFT,
            SpyArmySection.MIDDLE,
            SpyArmySection.RIGHT,
        ]

    def test_an_army_stored_by_section_name_rebuilds_in_wire_order(self):
        stored = {section.value: entry for section, entry in zip(SpyArmySection, _army(), strict=True)}

        rebuilt = parsed([stored[section.value] for section in SpyArmySection])

        assert rebuilt == parsed(_army())
