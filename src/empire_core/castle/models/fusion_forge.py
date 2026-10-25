"""The decoration fusion forge, which fuses a stored decoration into a placed one.

Commands:
- ffi: the fusion forges' level and energy
- ffl: level a fusion forge up
- fsr: refill a fusion forge's energy for rubies
- fcc: assemble or disassemble fusion catalysts
- gtd: the placed decorations a fusion can target
- dff: fuse a decoration into another
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, model_validator

from empire_core.enums import CatalystConversion, Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt

if TYPE_CHECKING:
    from empire_core.gamedata import Building, CurrencyId

DECORATION_FORGE_ID = 1
"""The decoration fusion forge, the one fusion forge the client opens.

Client: ``FusionConst.DECORATION_FORGE_ID`` (dll line 19373)
"""


class FusionForge(BasePayload):
    """
    A fusion forge's level and energy.

    Client: ``FusionForgeVO.parseServerObject`` (bundle line 142197)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    forge_id: ClientInt = Field(validation_alias="FID", description="The fusion forge")
    level: ClientInt = Field(validation_alias="FL", default=-1, description="The forge's level")
    energy: ClientInt = Field(validation_alias="FE", default=0, description="The energy fusions spend")
    recharge_progress_seconds: ClientInt = Field(
        validation_alias="FRS",
        default=0,
        description="Seconds into the current energy recharge interval, as of the packet",
    )
    used_minute_skips: ClientInt = Field(validation_alias="FUM", default=0, description="Minute skips used on it")
    used_ruby_refills: ClientInt = Field(
        validation_alias="FUPS",
        default=0,
        description="Energy refills bought with rubies, which raise the next one's price",
    )


class GetFusionForgesRequest(BaseRequest):
    """
    Ask for fusion forges' level and energy.

    Command: ffi
    Payload: {"FIDS": [forge_id, ...]}

    Client: ``C2SGetFusionForgeInfoEventVO`` (bundle line 61701), sent for every fusion system after the
    login data (``FusionForgeData.onGbdArrived``, bundle line 142012) and for one forge when its next
    recharge is due (``FusionForgeVO.requestDataFromServer``, bundle line 142199)
    """

    command = "ffi"

    forge_ids: tuple[int, ...] = Field(validation_alias="FIDS", description="The fusion forges asked for")


class FusionForgesResponse(BaseResponse):
    """
    Fusion forges' level and energy.

    Command: ffi
    Payload: {"FI": [forge, ...]}

    Client: ``FFICommand.executeCommand`` (bundle line 124120), ``FusionForgeData.parseFFI`` (bundle line 141989)
    """

    command = "ffi"

    forges: tuple[FusionForge, ...] = Field(validation_alias="FI", default=(), description="The forges sent")


class LevelUpFusionForgeRequest(BaseRequest):
    """
    Level a fusion forge up for decoration dust.

    Command: ffl
    Payload: {"FID": forge_id}

    Client: ``C2SLevelUpFusionForgeEventVO`` (bundle line 78287), sent by
    ``DecorationForgeUpgradeDialog.onLevelUpButtonClicked`` (bundle line 78274); the price is
    ``FusionForgeVO.getCostForForgeLevelUp`` (bundle line 142209)
    """

    command = "ffl"

    forge_id: int = Field(validation_alias="FID", description="The fusion forge")


class LevelUpFusionForgeResponse(BaseResponse):
    """
    A fusion forge's new level.

    Command: ffl
    Payload: {"FID": forge_id, "FL": level}

    Client: ``FFLCommand.executeCommand`` (bundle line 124135), ``DecorationForgeUpgradeDialog.showPopover``
    (bundle line 78263)
    """

    command = "ffl"

    forge_id: ClientInt = Field(validation_alias="FID", description="The fusion forge")
    level: ClientInt = Field(validation_alias="FL", description="Its level now")


class RefillFusionForgeRequest(BaseRequest):
    """
    Refill a fusion forge's energy for rubies.

    Command: fsr
    Payload: {"FID": forge_id, "FSRP": 1}

    Client: ``C2SSkipFusionRechargeEventVO`` (bundle line 77974), sent with ``FSRP`` 1 by
    ``DecorationForgeRechargeEnergyDialog`` (bundle line 35619) at
    ``FusionForgeVO.getC2PriceForEnergyPremiumSkip`` (bundle line 142206)
    """

    command = "fsr"

    forge_id: int = Field(validation_alias="FID", description="The fusion forge")
    with_rubies: bool = Field(validation_alias="FSRP", default=True, description="Always True: refilled for rubies")

    @field_serializer("with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class RefillFusionForgeResponse(BaseResponse):
    """
    The energy a fusion forge's refill added.

    Command: fsr
    Payload: {"FID": forge_id, "FE": energy}

    Client: ``FSRCommand.executeCommand`` (bundle line 124150), ``DecorationForgeRechargeEnergyDialog.showPopover``
    (bundle line 35609), which shows ``FE`` as the energy added
    """

    command = "fsr"

    forge_id: ClientInt = Field(validation_alias="FID", description="The fusion forge")
    energy: ClientInt = Field(validation_alias="FE", default=0, description="The energy added")


class ConvertCatalystRequest(BaseRequest):
    """
    Assemble fusion catalysts, or disassemble them into decoration dust.

    Command: fcc
    Payload: {"FID": forge_id, "FCCD": direction, "FCID": catalyst_id, "FCCA": amount}

    Client: ``C2SFusionCatalystConversionEventVO`` (bundle line 78022), sent by
    ``ADecorationForgeCatalystConversionDialogInfoBox.onConfirmButtonClicked`` (bundle line 48367)
    """

    command = "fcc"

    forge_id: int = Field(validation_alias="FID", description="The fusion forge")
    direction: CatalystConversion = Field(validation_alias="FCCD", description="Assemble or disassemble")
    catalyst_id: EnumOrInt["CurrencyId"] = Field(validation_alias="FCID", description="The catalyst, a currency")
    amount: int = Field(validation_alias="FCCA", description="How many catalysts")


class ConvertCatalystResponse(BaseResponse):
    """
    The catalysts converted.

    Command: fcc
    Payload: {"FID": forge_id, "FCCD": direction, "FCID": catalyst_id, "FCCA": amount}

    Client: ``FCCCommand.executeCommand`` (bundle line 124105),
    ``DecorationForgeCatalystConversionDialog.showPopover`` (bundle line 35564)
    """

    command = "fcc"

    forge_id: ClientInt = Field(validation_alias="FID", description="The fusion forge")
    direction: CatalystConversion = Field(validation_alias="FCCD", description="Assembled or disassembled")
    catalyst_id: EnumOrInt["CurrencyId"] = Field(validation_alias="FCID", description="The catalyst, a currency")
    amount: ClientInt = Field(validation_alias="FCCA", description="How many catalysts")


class FusionDecoration(BasePayload):
    """
    A decoration as a fusion names it.

    Client: ``ADecoBuildingVO.parseServerInfoShort`` (bundle line 11889), ``CustomDecoBuildingVO``
    (bundle line 82354) for ``DP``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    wod_id: EnumOrInt["Building"] = Field(validation_alias="WID", description="The decoration's building type")
    object_id: int = Field(validation_alias="OID", default=-1, description="Its object id where it is placed")
    fusion_xp: ClientInt = Field(validation_alias="FXP", default=0, description="Its fusion experience")
    unique_id: int = Field(validation_alias="UID", default=-1, description="Its unique id; -1 for none")
    decoration_points: ClientInt | None = Field(
        validation_alias="DP", default=None, description="A custom decoration's points; None for others"
    )


_DECORATION_KEYS = ("WID", "OID", "FXP", "UID", "DP")


class FusionTargetArea(BasePayload):
    """
    The decorations placed in one of your areas that a fusion can target.

    Client: ``DecoStorageTempDecoVO.parseServerObject`` (bundle line 141479)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    castle_id: ClientInt = Field(validation_alias="AID", description="The area")
    kingdom: Kingdom = Field(validation_alias="KID", description="Its kingdom")
    decorations: tuple[FusionDecoration, ...] = Field(validation_alias="A", default=(), description="The decorations")


class GetFusionTargetsRequest(BaseRequest):
    """
    Ask for the placed decorations a fusion can target.

    Command: gtd
    Payload: {}

    Client: ``C2SGetTargetDecosInAreaEventVO`` (bundle line 141470), sent by ``DecoStorageData.requestGTD``
    (bundle line 141447)
    """

    command = "gtd"


class FusionTargetsResponse(BaseResponse):
    """
    The placed decorations a fusion can target, per area.

    Command: gtd
    Payload: [{"AID": castle_id, "KID": kingdom, "A": [decoration, ...]}, ...]

    Client: ``GTDCommand.executeCommand`` (bundle line 124606), ``DecoStorageData.parseGTD`` (bundle line 141438)
    """

    command = "gtd"

    areas: tuple[FusionTargetArea, ...] = Field(default=(), description="Your areas with their decorations")

    @model_validator(mode="before")
    @classmethod
    def _areas(cls, value: Any) -> Any:
        return {"areas": value} if isinstance(value, list) else value


class FuseDecorationRequest(BaseRequest):
    """
    Fuse a stored decoration into a placed one, which gains its fusion experience.

    Command: dff
    Payload: {"FCID": catalyst_id, "FFFP": 0 or 1, "FSUID": source_unique_id, "FSWID": source_wod_id,
    "FTOID": target_object_id, "FTSID": target_kingdom, "FTAID": target_castle_id, "FTUID": target_unique_id,
    "FTWID": target_wod_id}

    Client: ``C2SDecoForgeFuseEventVO`` (bundle line 77863), sent by
    ``DecorationForgeMainDialog.onFuseButtonClicked`` (bundle line 35455) with ``FFFP`` 1 for the
    premium fusion, which pays rubies for the fusion currency
    """

    command = "dff"

    catalyst_id: EnumOrInt["CurrencyId"] = Field(validation_alias="FCID", description="The catalyst, a currency")
    pay_with_rubies: bool = Field(
        validation_alias="FFFP", default=False, description="The premium fusion, paid in rubies"
    )
    source_unique_id: int = Field(validation_alias="FSUID", description="The stored decoration's unique id")
    source_wod_id: EnumOrInt["Building"] = Field(validation_alias="FSWID", description="Its building type")
    target_object_id: int = Field(validation_alias="FTOID", description="The placed decoration's object id")
    target_kingdom: Kingdom = Field(validation_alias="FTSID", description="Its area's kingdom")
    target_castle_id: int = Field(validation_alias="FTAID", description="Its area")
    target_unique_id: int = Field(validation_alias="FTUID", description="Its unique id")
    target_wod_id: EnumOrInt["Building"] = Field(validation_alias="FTWID", description="Its building type")

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class FuseDecorationResponse(BaseResponse):
    """
    The decoration a fusion grew, and where it stands.

    Command: dff
    Payload: {"WID": wod_id, "OID": object_id, "FXP": xp, "UID": unique_id, "SID": kingdom, "AID": castle_id,
    "BFXP": bonus_xp}

    Client: ``DFFCommand.executeCommand`` (bundle line 124090), ``FusionForgeData.parseDFF`` (bundle line 141997)
    builds the decoration with ``parseServerInfoShort`` and a ``DecorationForgeSelectResultVO``
    (bundle line 23014) from ``SID`` and ``AID``
    """

    command = "dff"

    decoration: FusionDecoration = Field(description="The target decoration after the fusion")
    kingdom: Kingdom = Field(validation_alias="SID", description="Its area's kingdom")
    castle_id: ClientInt = Field(validation_alias="AID", description="Its area")
    bonus_xp: ClientInt = Field(
        validation_alias="BFXP", default=0, description="The bonus fusion experience on top; 0 for none"
    )

    @model_validator(mode="before")
    @classmethod
    def _decoration(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "decoration" in value:
            return value
        return {**value, "decoration": {key: value[key] for key in _DECORATION_KEYS if key in value}}


__all__ = [
    "DECORATION_FORGE_ID",
    "ConvertCatalystRequest",
    "ConvertCatalystResponse",
    "FuseDecorationRequest",
    "FuseDecorationResponse",
    "FusionDecoration",
    "FusionForge",
    "FusionForgesResponse",
    "FusionTargetArea",
    "FusionTargetsResponse",
    "GetFusionForgesRequest",
    "GetFusionTargetsRequest",
    "LevelUpFusionForgeRequest",
    "LevelUpFusionForgeResponse",
    "RefillFusionForgeRequest",
    "RefillFusionForgeResponse",
]
