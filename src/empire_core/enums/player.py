"""Player progress constants."""

from enum import Enum, IntEnum


class TitleSystem(str, Enum):
    """
    A title system: the ``type`` of a title in the items data, and a ``uar``'s ``PFX`` and ``SFX``.

    Client: ``ClientConstTitle.GLORY_TITLE``, ``BRAVERY_TITLE`` and ``ISLAND_TITLE`` (bundle line 6767)
    """

    GLORY = "FAME"
    FACTION = "FACTION"
    ISLAND = "ISLE"


class PremiumAccountType(IntEnum):
    """
    The premium account's type, a ``boi``'s ``PT``.

    Client: ``PremiumConst.PREMIUM_ACCOUNT_*`` (dll line 19628), compared with ``PT`` in
    ``TaxConst.getCollectorC2Costs`` (dll line 19779); ``PT`` also indexes the three-entry
    ``PremiumConst.FACTOR_*`` arrays (dll lines 19622-19625, bundle line 90238)
    """

    BRONZE = 0
    SILVER = 1
    GOLD = 2


class MercenaryMissionState(IntEnum):
    """
    Where a mercenary mission stands, an ``mpe`` mission's ``S``.

    Client: ``CastleMercenaryData.MISSION_STATE_DEFAULT`` to ``MISSION_STATE_COLLECTED`` (bundle line 28881)
    """

    OPEN = 0
    STARTED = 1
    COLLECTABLE = 2
    COLLECTED = 3


class MercenaryMissionRarity(IntEnum):
    """
    A mercenary mission's rarity, an ``mpe`` mission's ``Q``.

    Client: ``CastleMercenaryMissionItemVO.RARITY_FREE`` to ``RARITY_LEGENDARY`` (bundle line 81149)
    """

    FREE = 0
    COMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4


class MysteryBoxKey(IntEnum):
    """
    The key a mystery box is opened with, a currency id: an ``ole``'s ``CID`` and ``UKI``.

    The common key is not counted and never runs out; the others are spent one per box.

    Client: ``ClientConstCurrency.ID_MYSTERY_BOX_KEY_*`` (bundle line 1920; the common key is ``5e3``),
    ``RewardHubMainDialogMysteryBoxes.getSelectedKeyID`` (bundle line 92162),
    ``MysteryBoxOpeningDialog.updateKeyAmount`` (bundle line 124875)
    """

    COMMON = 5000
    RARE = 5001
    EPIC = 5002
    LEGENDARY = 5003


class Hero(IntEnum):
    """
    The hero you pick for the tutorial's quest character, the ``HID`` of ``hdc``.

    Client: ``TutorialConst.TUTORIAL_HERO_0_ID`` to ``TUTORIAL_HERO_2_ID`` (dll line 19886),
    ``CastleChooseHeroDialog.onClick`` (bundle line 42416)
    """

    YOUNG_KNIGHT = 801
    OLD_KNIGHT = 802
    FEMALE_WARRIOR = 803


class CoatOfArmsBackground(IntEnum):
    """
    How a coat of arms splits its background into its two colours, its ``BGT``.

    Client: ``ClientConstCrest.BACKGROUND_TYPE_*`` (bundle line 12240)
    """

    PLAIN = 0
    TWO_HORIZONTAL = 1
    TWO_VERTICAL = 2
    FOUR_X = 3


class SymbolLayout(IntEnum):
    """
    Where a coat of arms shows its symbols, its ``SPT``.

    ``NONE`` shows no symbol and ``ONE_CENTERED`` only the first.

    Client: ``ClientConstCrest.SYMBOL_POSITION_*`` (bundle line 12240)
    """

    NONE = 0
    ONE_CENTERED = 1
    TWO_HORIZONTAL = 2
    TWO_VERTICAL = 3
    FOUR_X = 4


class VerificationLink(IntEnum):
    """
    Which verification link ``rsm`` sends again, its ``T``.

    Client: ``PlayerConst.RESEND_MAIL_ACCOUNT_VERIFICATION`` (dll line 19599);
    ``OptionsDialogAccountDetails.onSendAgainEmail`` (bundle line 72747) sends it while the email address is
    unverified and 1 otherwise, while an email change waits for verification
    """

    ACCOUNT_VERIFICATION = 0
    EMAIL_CHANGE = 1
