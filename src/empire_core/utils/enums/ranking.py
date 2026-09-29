"""Highscore list types and categories."""

from enum import IntEnum


class RankingType(IntEnum):
    """
    Known LT (List Type) values.
    Corresponds to Event IDs or Metric IDs.
    """

    # Core Alliance Metrics
    ALLIANCE_HONOR = 10
    ALLIANCE_MIGHT = 11
    DOMINION_POINTS = 12
    CARGO_POINTS = 13

    # Core Player Metrics
    PLAYER_HONOR = 5
    PLAYER_MIGHT = 6
    LEGEND_LEVEL = 7
    ACHIEVEMENTS = 1

    # Events
    FOREIGN_INVASION = 71
    BLOODCROWS = 72
    SAMURAI = 80
    NOMAD = 85
    BERIMOND = 113
    SHAPESHIFTER = 60
    HORIZON = 134
    OUTER_REALMS = 63


class RankingCategory(IntEnum):
    """
    Common LID (List ID) values.
    Corresponds to level brackets or sub-categories.
    """

    LEVEL_70 = 6  # Standard for most events (Level 70 bracket)
    LEGENDARY_TOP = 5
    GLOBAL = 1
