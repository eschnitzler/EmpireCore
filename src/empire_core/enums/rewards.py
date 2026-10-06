"""Free daily reward constants."""

from enum import Enum


class LoginBonusSpecial(str, Enum):
    """
    A special login bonus, collected instead of a pick: the alliance or the VIP bonus.

    Client: ``CastleDailyLoginBonusDialog.performDailySpecialBonusButtonSelection`` (bundle lines 39230, 39234)
    """

    ALLIANCE = "ALLI"
    VIP = "VIP"
