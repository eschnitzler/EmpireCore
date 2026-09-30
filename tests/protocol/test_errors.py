"""GGEError against the client's ERROR enum (dll line 20067); currency 1 and 2 are named coins and rubies."""

import pytest

from empire_core.protocol.errors import GGEError


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("NOT_ENOUGH_COINS", 10),
        ("NOT_ENOUGH_RUBIES", 11),
        ("ALLI_NOT_ENOUGH_COINS", 115),
        ("ALLI_NOT_ENOUGH_RUBIES", 116),
        ("WRONG_AMOUNT_OF_BOUGHT_RUBIES", 336),
        ("RUBY_CONFIRMATION_REQUIRED", 440),
        ("LOGIN_COOLDOWN_ACTIVE", 453),
        ("QUEST_IN_PROGRESS", 454),
        ("QUEST_IN_COOLDOWN", 455),
        ("NOT_ENOUGH_QUEST_TRIES", 456),
        ("QUEST_NOT_IN_COOLDOWN", 457),
        ("INVALID_ALLIANCE_REWARD_ID", 458),
        ("QUEST_IN_PROGRESS_BY_OTHER_PLAYER", 459),
        ("RAID_BOSS_NOT_IN_POOL", 460),
        ("RAID_ALREADY_IN_PROGRESS", 461),
        ("RAID_BOSS_LOCKED", 462),
        ("RAID_NO_ACTIVE_BOSS", 463),
        ("NO_FREE_EMBLEM", 2000),
        ("AGE_CHECK_FAILED_TIME_OF_DAY", 10000),
    ],
)
def test_names_and_codes_match_the_client(name, code):
    assert GGEError[name] == code
    assert GGEError.from_code(code).name == name


def test_the_old_cooldown_name_is_gone():
    assert "LOGIN_COOLDOWN" not in GGEError.__members__


def test_login_cooldown_is_a_cooldown():
    assert GGEError.LOGIN_COOLDOWN_ACTIVE.is_cooldown
    assert GGEError.COOLING_DOWN.is_cooldown
    assert not GGEError.QUEST_IN_COOLDOWN.is_cooldown
