"""Game data and helpers shared by the combat tests."""

from empire_core.gamedata import GameData, UnitStats


def placed(slots: list[list[int]]) -> list[list[int]]:
    """A wave container's filled slots; fill_wave pads the rest with [-1, 0]."""
    return [slot for slot in slots if slot[0] != -1]


def unit_of(game: GameData, wod_id: int) -> UnitStats:
    """The unit, insisting it is there - a missing row is a failure, not a None."""
    unit = game.get_unit(wod_id)
    assert unit is not None, f"no unit {wod_id} in the parsed data"
    return unit


# Live rows: 211 is a ranged MeadRanger, 601 a melee unit, 646 a defense tool.
PAYLOAD = {
    "units": [
        {
            "wodID": 211,
            "name": "Barracks",
            "type": "MeadRanger",
            "role": "ranged",
            "rangeAttack": "270",
            "meleeDefence": "25",
            "rangeDefence": "42",
        },
        {
            "wodID": 601,
            "name": "Barracks",
            "type": "Swordsman",
            "role": "melee",
            "meleeAttack": "100",
            "meleeDefence": "60",
            "rangeDefence": "20",
        },
        {
            "wodID": 646,
            "name": "Dworkshop",
            "type": "Premiumstakes",
            "typ": "Defence",
            "slotTypes": "4,9",
            "moatBonus": "80",
        },
    ],
    "dungeons": [
        {
            "countVictories": "-6",
            "kID": "0",
            "lordID": "-21",
            "unitsM": "601+10#211+5",
            "toolM": "646+2",
            "unitsL": "601+2",
        },
    ],
}


def data() -> GameData:
    return GameData.parse("test", PAYLOAD)


# =============================================================================
# Solver: soldier fill
# =============================================================================

SOLVER_PAYLOAD = {
    "units": [
        # A defensive unit with a real attack value: fightType decides, not the
        # attack number, so this must never be picked.
        {
            "wodID": 604,
            "name": "Barracks",
            "type": "Halberd",
            "role": "melee",
            "meleeAttack": "17",
            "meleeDefence": "135",
            "rangeDefence": "50",
            "fightType": "1",
        },
        # Melee: 100 attack. Ranged: 270 attack. A ruby-healed and a mead unit
        # for the filters, and a pure defender that must never be picked.
        {
            "wodID": 601,
            "name": "Barracks",
            "type": "Swordsman",
            "role": "melee",
            "meleeAttack": "100",
            "meleeDefence": "60",
            "rangeDefence": "20",
        },
        {
            "wodID": 211,
            "name": "Barracks",
            "type": "MeadRanger",
            "role": "ranged",
            "rangeAttack": "270",
            "meleeDefence": "25",
            "rangeDefence": "42",
            "meadSupply": "2",
        },
        {
            "wodID": 700,
            "name": "Barracks",
            "type": "RubyKnight",
            "role": "melee",
            "meleeAttack": "500",
            "healingCostC2": "10",
        },
        {"wodID": 800, "name": "Barracks", "type": "Wall", "role": "melee", "meleeDefence": "900"},
    ],
}


def solver_data() -> GameData:
    return GameData.parse("test", SOLVER_PAYLOAD)
