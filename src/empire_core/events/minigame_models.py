"""The event minigames: the Wheels of Fortune, the gachas, the colossus, imperial patronage, the marauders' contest,
the Traveling Knights and Shady Lady events, the fortune teller, the world cup vote and the collector currency."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BeforeValidator, Field

from empire_core.enums import Kingdom
from empire_core.enums.events import GachaRarity, WheelOfFortuneType, WorldCupVote
from empire_core.gamedata import Collectable, CollectableRows, EnumOrInt, RewardId
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock
from empire_core.protocol.js import ClientInt, js_int, js_number, js_truthy
from empire_core.ranking.event_models import GetColossusHighscoreResponse

_Truthy = Annotated[bool, BeforeValidator(js_truthy)]


def _first_int(value: Any) -> int | None:
    return js_int(value[0]) if isinstance(value, list) and value else None


def _truthy_int(value: Any) -> int | None:
    return js_int(value) if js_truthy(value) else None


def _truthy_number(value: Any) -> float | None:
    return js_number(value) if js_truthy(value) else None


_FirstInt = Annotated[int | None, BeforeValidator(_first_int)]
"""The first of a list's values through ``int()``, as ``AScoreEventVO.setRankAndPoints`` (bundle line 15052) reads
it; None without one."""

_SetInt = Annotated[int | None, BeforeValidator(_truthy_int)]
"""A value through ``int()``, None when it is 0 or missing, which the client then does not apply."""

_SetNumber = Annotated[float | None, BeforeValidator(_truthy_number)]


# =============================================================================
# Wheel of Fortune
# =============================================================================


class WheelOfFortuneSpinRequest(BaseRequest):
    """
    Spin a Wheel of Fortune, paid in Wheel of Fortune tickets (or a free spin).

    Client: ``C2SLuckyWheelSpinVO`` (bundle line 59783), sent by ``CastleLuckyWheelDialog.startSpin`` and
    ``CastleLuckWheelSalesDaysDialog.startSpin`` (bundle lines 116661, 117919)
    """

    command: ClassVar[str] = "lws"

    wheel: WheelOfFortuneType = Field(
        default=WheelOfFortuneType.WHEEL_OF_FORTUNE, validation_alias="LWET", description="The wheel to spin"
    )


class WheelOfFortuneChangeModeRequest(BaseRequest):
    """
    Switch the Wheel of Fortune between its normal and its pro mode.

    Client: ``C2SLuckyWheelChangeModeVO`` (bundle line 116687), ``CastleLuckyWheelDialog.changeMode`` (bundle
    line 116666)
    """

    command: ClassVar[str] = "lwm"


class WheelOfFortuneBuyJackpotRequest(BaseRequest):
    """
    Spin the Wheel of Fortune for a guaranteed jackpot, paid in rubies and tickets.

    Client: ``C2SLuckyWheelBuyJackpotVO`` (bundle line 116678), ``CastleLuckyWheelDialog.clickedBuyJackpot``
    (bundle line 116659); ``LuckyWheelData.jackpotC2Price`` (bundle line 17639)
    """

    command: ClassVar[str] = "lwj"


class WheelOfFortuneIncreaseWinClassRequest(BaseRequest):
    """
    Raise the Wheel of Fortune's win class at once, paid in rubies.

    Client: ``C2SLuckyWheelIncreasePrizeClass`` (bundle line 59775),
    ``CastleLuckyWheelIncreaseWinClassDialog.clickedAccept`` (bundle line 117107);
    ``LuckyWheelData.increaseWinClassC2`` (bundle line 17628)
    """

    command: ClassVar[str] = "lwc"


class WheelOfFortuneStatus(BaseResponse):
    """
    The wheel's state as every Wheel of Fortune reply carries it.

    Client: ``LuckyWheelData.parseBasics`` (bundle line 17570)
    """

    has_visited_pro_mode: _Truthy = Field(
        default=False, validation_alias="HVPM", description="Whether you opened the pro mode"
    )
    has_free_spin: _Truthy = Field(default=False, validation_alias="HFS", description="Whether a free spin is waiting")
    pro_mode: _Truthy = Field(default=False, validation_alias="PMA", description="Whether the pro mode is on")
    win_class: ClientInt = Field(default=0, validation_alias="CWC", description="The wheel's current win class")
    win_class_progress: float = Field(
        default=0.0, validation_alias="WCP", description="The spins made towards the next win class"
    )
    jackpot_set_id: ClientInt = Field(default=0, validation_alias="JSID", description="The next jackpot set")
    jackpot_spin_set_id: ClientInt = Field(
        default=0, validation_alias="JHID", description="The jackpot set of the next jackpot spin"
    )


class WheelOfFortuneSpinResponse(WheelOfFortuneStatus):
    """
    A spin's outcome and the wheel after it.

    Client: ``LWSCommand.executeCommand`` (bundle line 128141), ``LuckyWheelData.parseLWS`` (bundle line 17566)
    """

    command: ClassVar[str] = "lws"

    wheel: EnumOrInt[WheelOfFortuneType] = Field(
        default=WheelOfFortuneType.WHEEL_OF_FORTUNE, validation_alias="LWET", description="The wheel that was spun"
    )
    winning_category: ClientInt = Field(default=0, validation_alias="WC", description="The wheel's slice that won")
    rewards: CollectableRows = Field(default=(), validation_alias="R", description="What the spin won")
    own_rank: _FirstInt = Field(default=None, validation_alias="OR", description="Your rank in the event")
    own_points: _FirstInt = Field(default=None, validation_alias="OP", description="Your points in the event")


class WheelOfFortuneBuyJackpotResponse(WheelOfFortuneSpinResponse):
    """
    A jackpot spin's outcome and the wheel after it.

    Client: ``LWJCommand.executeCommand`` (bundle line 128105), ``LuckyWheelData.parseLWJ`` (bundle line 17565)
    """

    command: ClassVar[str] = "lwj"


class WheelOfFortuneChangeModeResponse(BaseResponse):
    """
    The jackpot sets after a mode change; the mode itself flips.

    Client: ``LWMCommand.executeCommand`` (bundle line 128122), ``LuckyWheelData.parseLWM`` (bundle line 17564)
    """

    command: ClassVar[str] = "lwm"

    jackpot_set_id: ClientInt = Field(default=0, validation_alias="JSID", description="The next jackpot set")
    jackpot_spin_set_id: ClientInt = Field(
        default=0, validation_alias="JHID", description="The jackpot set of the next jackpot spin"
    )


class WheelOfFortuneIncreaseWinClassResponse(WheelOfFortuneStatus):
    """
    The wheel after its win class was raised.

    Client: ``LWCCommand.executeCommand`` (bundle line 128090), ``LuckyWheelData.parseLWC`` (bundle line 17569)
    """

    command: ClassVar[str] = "lwc"


# =============================================================================
# Gacha
# =============================================================================


class GachaSpinRequest(BaseRequest):
    """
    Pull a gacha event's chest one or more times, paid with the gacha's price per pull.

    Client: ``C2SGachaSpinVO`` (bundle line 104048), ``GachaComponentPull.onClick`` (bundle line 57102), which
    sends the pulls picked
    """

    command: ClassVar[str] = "dge"

    event_id: int = Field(validation_alias="EID", description="The gacha event")
    pulls: int = Field(default=1, ge=1, validation_alias="AMT", description="How many pulls")
    reserved: Literal[0] = Field(default=0, validation_alias="OB", description="Always 0")


class GachaPull(BasePayload):
    """
    One pull's rewards and their rarity.

    Client: ``GachaComponentRewards.onSpin`` (bundle line 57167)
    """

    rewards: CollectableRows = Field(default=(), validation_alias="RR", description="What the pull gave")
    rarity: EnumOrInt[GachaRarity] = Field(default=GachaRarity.COMMON, validation_alias="R", description="Its rarity")


class GachaUpdate(BaseResponse):
    """
    A gacha event's score and free chest, as a pull or a free chest reports them; a value that is 0 or missing
    leaves the event's own.

    Client: ``AGachaEventVO.parseGachaEvent`` (bundle line 15379)
    """

    free_chest_seconds: _SetNumber = Field(
        default=None, validation_alias="FCRT", description="Seconds until the free chest comes back"
    )
    own_points: _SetInt = Field(default=None, validation_alias="OP", description="Your pulls in the event")
    own_rank: _SetInt = Field(default=None, validation_alias="OR", description="Your rank in the event")


class GachaSpinResponse(GachaUpdate):
    """
    The pulls' rewards and the event after them.

    Client: ``DGECommand.executeCommand`` (bundle line 124175)
    """

    command: ClassVar[str] = "dge"

    gacha_id: ClientInt = Field(
        default=0, validation_alias="ID", description="The row of the game data's gachas table pulled from"
    )
    pulls: tuple[GachaPull, ...] = Field(default=(), validation_alias="LTR", description="Each pull's rewards")


class GachaFreeChestResponse(GachaUpdate):
    """
    A free gacha chest the server opened for you; the client never asks for one.

    Client: ``CFCCommand.executeCommand`` (bundle line 124161)
    """

    command: ClassVar[str] = "cfc"

    event_id: ClientInt = Field(validation_alias="EID", description="The gacha event")


class GachaInfoResponse(BaseResponse):
    """
    A gacha info push; the client reads nothing from it and never asks for one.

    Client: ``GDECommand.executeCommand`` (bundle line 124189)
    """

    command: ClassVar[str] = "gde"


# =============================================================================
# Colossus
# =============================================================================


class ColossusDepositRequest(BaseRequest):
    """
    Donate wood and stone from a castle to the colossus.

    Client: ``C2SColossusDepositResourcesVO`` (bundle line 115335), ``CastleColossusDonateDialog.onDonate``
    (bundle line 59308)
    """

    command: ClassVar[str] = "cde"

    castle_id: int = Field(validation_alias="SCID", description="The donating castle")
    kingdom: Kingdom = Field(validation_alias="SKID", description="The donating castle's kingdom")
    stone: int = Field(default=0, ge=0, validation_alias="DS", description="Stone to donate")
    wood: int = Field(default=0, ge=0, validation_alias="DW", description="Wood to donate")


class ColossusCoinDepositRequest(BaseRequest):
    """
    Donate coins to the coin colossus.

    Client: ``C2SColossusCoinDepositResourcesVO`` (bundle line 115326), ``CastleCoinColossusDonateDialog.onDonate``
    (bundle line 59272)
    """

    command: ClassVar[str] = "ccd"

    coins: int = Field(ge=1, validation_alias="DC", description="Coins to donate")


class ColossusDepositResponse(BaseResponse):
    """
    The colossus board after a donation; the castle's ``grc`` stays in the extra fields.

    Client: ``CDECommand.executeCommand`` (bundle line 127690), ``CastleSpecialEventData.parse_CHE`` (bundle
    line 139832)
    """

    command: ClassVar[str] = "cde"

    highscore: GetColossusHighscoreResponse | None = Field(
        default=None, validation_alias="che", description="Your points and the donors' board"
    )


class ColossusCoinDepositResponse(ColossusDepositResponse):
    """
    The coin colossus board and your coins after a donation.

    Client: ``CCDCommand.executeCommand`` (bundle line 127672)
    """

    command: ClassVar[str] = "ccd"

    currency: CurrencyBlock = Field(default=None, validation_alias="gcu", description="Coins and rubies after it")


# =============================================================================
# Imperial Patronage
# =============================================================================


class DonationItemAmount(BasePayload):
    """
    One donation item and the amount to give of it.

    Client: ``DonationEventDialogDonate.onDonate`` (bundle line 115642)
    """

    donation_item_id: int = Field(validation_alias="DII", description="The donation item, a donationItems row")
    amount: int = Field(ge=1, validation_alias="DIA", description="How much of it to give")


class DonateItemsRequest(BaseRequest):
    """
    Give donation items to imperial patronage.

    Client: ``C2SDonatePointTypeVO`` (bundle line 115702), ``DonationEventDialogDonate.onDonate`` (bundle
    line 115642), which leaves out the items with no amount
    """

    command: ClassVar[str] = "ddi"

    items: tuple[DonationItemAmount, ...] = Field(validation_alias="DIV", description="The items given")


class GetImperialPatronageProgressRequest(BaseRequest):
    """
    Ask for the points you have earned per donation item.

    Client: ``C2SGetDonationPointTypeVO`` (bundle line 115568), sent as ``DonationEventDialog`` opens (bundle
    line 39780)
    """

    command: ClassVar[str] = "gdti"


class DonationItemPoints(BasePayload):
    """
    The points one donation item has earned you.

    Client: ``CastleDonationEventData.parseGDTI`` (bundle line 58869)
    """

    donation_item_id: ClientInt = Field(validation_alias="DII", description="The donation item, a donationItems row")
    points: ClientInt = Field(default=0, validation_alias="DIP", description="The points it has earned")


class ImperialPatronageProgressResponse(BaseResponse):
    """
    The points you have earned per donation item.

    Client: ``GDTICommand.executeCommand`` (bundle line 123604), ``CastleDonationEventData.parseGDTI`` (bundle
    line 58869)
    """

    command: ClassVar[str] = "gdti"

    items: tuple[DonationItemPoints, ...] = Field(validation_alias="DIS", description="Each item's points")


class DonateItemsResponse(ImperialPatronageProgressResponse):
    """
    The points you have earned per donation item, after a donation.

    Client: ``DDICommand.executeCommand`` (bundle line 123589)
    """

    command: ClassVar[str] = "ddi"


# =============================================================================
# Marauders' contest
# =============================================================================


class BuyMaraudersContestPackageRequest(BaseRequest):
    """
    Hand resource packages from a castle to the marauders for contest points.

    Client: ``C2SBuyBeggingKnightsPackageVO`` (bundle line 114933), sent with each selected amount divided by the
    event's package size (bundle line 114916)
    """

    command: ClassVar[str] = "bkp"

    castle_id: int = Field(validation_alias="SCID", description="The giving castle")
    kingdom: Kingdom = Field(validation_alias="SKID", description="The giving castle's kingdom")
    wood_packages: int = Field(default=0, ge=0, validation_alias="WP", description="Wood packages")
    stone_packages: int = Field(default=0, ge=0, validation_alias="SP", description="Stone packages")
    food_packages: int = Field(default=0, ge=0, validation_alias="FP", description="Food packages")


class BuyMaraudersContestPackageResponse(BaseResponse):
    """
    The acknowledgement of a marauders' package; the client then asks for its points.

    Client: ``BKPCommand.executeCommand`` (bundle line 128233)
    """

    command: ClassVar[str] = "bkp"


# =============================================================================
# Traveling Knights event
# =============================================================================


class BuyArtifactPieceRequest(BaseRequest):
    """
    Buy pieces of a Traveling Knights event's artifact with rubies.

    Client: ``C2SBuyArtifactPieceVO`` (bundle line 114775), ``CastleArtifactBuyPieceDialog`` (bundle lines
    114756, 114762), which sends the event's first kingdom
    """

    command: ClassVar[str] = "sap"

    pieces: int = Field(ge=1, validation_alias="A", description="How many pieces to buy")
    event_id: int = Field(validation_alias="EID", description="The Traveling Knights event")
    kingdom: Kingdom = Field(validation_alias="KID", description="The event's kingdom")


class ArtifactFoundResponse(BaseResponse):
    """
    The pieces of an artifact found so far; pushed when you find one, the client never asks.

    Client: ``SAFCommand.executeCommand`` (bundle line 127599), ``CastleSpecialEventData.handleArtifactPartFound``
    (bundle line 139892)
    """

    command: ClassVar[str] = "saf"

    event_id: ClientInt = Field(validation_alias="EID", description="The Traveling Knights event")
    parts_found: ClientInt = Field(default=0, validation_alias="PF", description="The pieces you have")


class BuyArtifactPieceResponse(ArtifactFoundResponse):
    """
    The pieces of an artifact you have, and your rubies, after a purchase.

    Client: ``SAPCommand.executeCommand`` (bundle line 127614)
    """

    command: ClassVar[str] = "sap"

    currency: CurrencyBlock = Field(default=None, validation_alias="gcu", description="Coins and rubies after it")


# =============================================================================
# Shady Lady
# =============================================================================


class ValidateShadyLadyTargetRequest(BaseRequest):
    """
    Have the server check your Shady Lady target, and pick a new one when it is gone.

    Client: ``C2SBountyHunterValidateOrResetTargetVO`` (bundle line 115038), sent as
    ``CastleBountyhunterEventDialog`` opens (bundle line 114986)
    """

    command: ClassVar[str] = "brt"


class ValidateShadyLadyTargetResponse(BaseResponse):
    """
    The acknowledgement of a target check; a new target comes in a ``sei``.

    Client: ``BRTCommand.executeCommand`` (bundle line 127629), which reads nothing
    """

    command: ClassVar[str] = "brt"


class SkipShadyLadyTargetRequest(BaseRequest):
    """
    Skip your Shady Lady target for another, paid in rubies.

    Client: ``C2SBountyHunterBuySkipTargetVO`` (bundle line 115030), ``CastleBountyhunterEventDialog.onClick``
    (bundle line 115004); ``BountyhunterEventVO.parseEventXmlNode`` reads its ``targetSkipCostC2`` (bundle line
    114944)
    """

    command: ClassVar[str] = "bst"


class SkipShadyLadyTargetResponse(BaseResponse):
    """
    Your rubies after a skip; the new target's ``sei`` stays in the extra fields and updates the event.

    Client: ``BSTCommand.executeCommand`` (bundle line 127642)
    """

    command: ClassVar[str] = "bst"

    currency: CurrencyBlock = Field(default=None, validation_alias="gcu", description="Coins and rubies after it")


# =============================================================================
# Fortune teller
# =============================================================================


class FortuneTellerReadingRequest(BaseRequest):
    """
    Buy a fortune teller reading, priced in rubies by how many you had today.

    Client: ``C2SBuyFortuneTellerPackageVO`` (bundle line 116188), ``FortuneTellerEventDialog.onClick`` (bundle
    line 59613); the price is the reading's ``c2Cost`` (``FortuneTellerClassVO.parseXML``, bundle line 145167)
    """

    command: ClassVar[str] = "ftl"


class FortuneTellerReadingResponse(BaseResponse):
    """
    The reading's reward.

    Client: ``FTLCommand.executeCommand`` (bundle line 127942), ``CastleFortuneTellerData.parseFTL`` (bundle line
    145157), which shows the first reward
    """

    command: ClassVar[str] = "ftl"

    reward_ids: tuple[RewardId, ...] = Field(default=(), validation_alias="RIDS", description="The rewards drawn")
    rewards: tuple[Collectable, ...] = Field(default=(), description="What the rewards drawn give")


# =============================================================================
# World cup
# =============================================================================


class VoteWorldCupRequest(BaseRequest):
    """
    Bet on a world cup match's outcome.

    Client: ``C2SVoteWorldCupVO`` (bundle line 104734), ``CastleWorldCupDialogNotVotedState.sendVote`` (bundle
    line 104723)
    """

    command: ClassVar[str] = "vwc"

    vote: WorldCupVote = Field(validation_alias="V", description="The outcome bet on")


class VoteWorldCupResponse(BaseResponse):
    """
    Your bet and the rubies counted towards it.

    Client: ``VWCCommand.executeCommand`` (bundle line 128541), ``WorldCupEventVO.parse_VWC`` (bundle line 24586)
    """

    command: ClassVar[str] = "vwc"

    vote: EnumOrInt[WorldCupVote] = Field(
        default=-1, validation_alias="V", description="The outcome bet on; -1 before you bet"
    )
    rubies_spent: ClientInt = Field(
        default=0, validation_alias="CC2", description="Rubies spent in the event, which must reach the bet's price"
    )


# =============================================================================
# Collector events
# =============================================================================


class GetCollectorCurrencyRequest(BaseRequest):
    """
    Ask how much of the collector event's currency a player holds.

    Client: ``C2SGetPlayerCollectorCurrencyVO`` (bundle line 134035),
    ``CastleCollectorEventData.getPlayerCollectorAmount`` (bundle line 134000)
    """

    command: ClassVar[str] = "pcc"

    player_id: int = Field(validation_alias="PID", description="The player")


class CollectorCurrencyResponse(BaseResponse):
    """
    How much of the collector event's currency a player holds.

    Client: ``PCCCommand.executeCommand`` (bundle line 127657), ``CastleCollectorEventData.parse_PCC`` (bundle
    line 134004)
    """

    command: ClassVar[str] = "pcc"

    player_id: ClientInt = Field(validation_alias="PID", description="The player")
    amount: ClientInt = Field(default=0, validation_alias="CCA", description="The currency they hold")


__all__ = [
    "ArtifactFoundResponse",
    "BuyArtifactPieceRequest",
    "BuyArtifactPieceResponse",
    "BuyMaraudersContestPackageRequest",
    "BuyMaraudersContestPackageResponse",
    "CollectorCurrencyResponse",
    "ColossusCoinDepositRequest",
    "ColossusCoinDepositResponse",
    "ColossusDepositRequest",
    "ColossusDepositResponse",
    "DonateItemsRequest",
    "DonateItemsResponse",
    "DonationItemAmount",
    "DonationItemPoints",
    "ImperialPatronageProgressResponse",
    "FortuneTellerReadingRequest",
    "FortuneTellerReadingResponse",
    "GachaFreeChestResponse",
    "GachaInfoResponse",
    "GachaPull",
    "GachaSpinRequest",
    "GachaSpinResponse",
    "GachaUpdate",
    "GetCollectorCurrencyRequest",
    "GetImperialPatronageProgressRequest",
    "WheelOfFortuneBuyJackpotRequest",
    "WheelOfFortuneBuyJackpotResponse",
    "WheelOfFortuneChangeModeRequest",
    "WheelOfFortuneChangeModeResponse",
    "WheelOfFortuneIncreaseWinClassRequest",
    "WheelOfFortuneIncreaseWinClassResponse",
    "WheelOfFortuneSpinRequest",
    "WheelOfFortuneSpinResponse",
    "WheelOfFortuneStatus",
    "SkipShadyLadyTargetRequest",
    "SkipShadyLadyTargetResponse",
    "ValidateShadyLadyTargetRequest",
    "ValidateShadyLadyTargetResponse",
    "VoteWorldCupRequest",
    "VoteWorldCupResponse",
]
