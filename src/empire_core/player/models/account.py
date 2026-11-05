"""
Account sections of the login data, and the pushes and replies that bring them again.

Commands:
- gpi: who you are
- vip: VIP status
- drt: seconds until the daily reset
- gatp: the officers' school training program running now
- bie: the global effects a booster event boosts
- pgl: your gift packages and how many you may still send
- gpg: send another player a gift package
- DTS: whether your food production is frozen

The timed models count from ``received_at``, as the client counts from its timer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, Field, field_validator, model_validator

from empire_core.gamedata import EnumOrInt, PackageId
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, TimedPayload, TimedResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_loose_equals, js_number

if TYPE_CHECKING:
    from empire_core.gamedata import Effect, GlobalEffect


class DailyResetResponse(TimedResponse):
    """
    When the daily reset comes.

    Command: drt, as a login section of ``gbd`` only.

    Client: ``CastleTimerData.parse_DRT`` and ``timeTillDailyResetInSec`` (bundle lines 112810-112811)
    """

    command = "drt"

    seconds: ClientNumber = Field(
        validation_alias="STR",
        default=0,
        description="Seconds until the daily reset when the values were read",
    )

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until the daily reset, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now))


class OfficerBonus(BasePayload):
    """
    The bonus a training program gives: an effect and its values, ``[effect_id, [value, ...]]``.

    Client: ``OfficersSchoolEffectVO.setBonusVOByValueArray`` (bundle line 144678), which looks the
    effect up by id and reads the values with ``BonusVO.parseFromValueArray``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    effect: EnumOrInt["Effect"] = Field(description="The effect")
    values: tuple[int | float, ...] = Field(default=(), description="The effect's values, in the effect's order")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            values = data[1] if len(data) > 1 else []
            return {"effect": data[0] if data else None, "values": values if isinstance(values, list) else [values]}
        return data


class OfficerTraining(TimedPayload):
    """
    The officers' school training program running now.

    Not a response model: its ``E`` is the program's bonus, not an error code.

    Command: gatp, as a login section of ``gbd`` and a reply; a ``gtp`` updates it.

    Client: ``GATPCommand`` (bundle line 126126), ``OfficersSchoolData.parse_GATP`` (bundle line 144606),
    ``OfficersSchoolEffectVO.setBonusVOByValueArray`` and ``setActiveTime`` (bundle lines 144678, 144681),
    ``OfficersSchoolData.getBonusByEffectType`` (bundle line 144634)
    """

    slot_id: ClientInt = Field(validation_alias="S", default=-1, description="The program's slot, -1 for none")
    bonus: OfficerBonus | None = Field(
        validation_alias="E", default=None, description="The program's bonus; None for none"
    )
    seconds: ClientNumber = Field(
        validation_alias="RS",
        default=-1,
        description="Seconds the program runs when the values were read, -1 for none",
    )

    @field_validator("bonus", mode="before")
    @classmethod
    def _bonus(cls, value: Any) -> Any:
        # setBonusVOByValueArray reads the bonus only from a non-empty list
        return value if isinstance(value, OfficerBonus) or (isinstance(value, list) and value) else None

    @property
    def is_set(self) -> bool:
        """Whether the client takes this as a running program: a slot with time left, or a bonus."""
        return (self.slot_id > -1 and self.seconds > 0) or self.bonus is not None

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds the program still runs, 0 at least; its bonus counts only while this is above 0."""
        return max(0.0, self.seconds - self._elapsed(now))


class BoostedGlobalEffectsResponse(BaseResponse):
    """
    The global effects the running global effect booster event makes stronger.

    The running global effects themselves come with the global effects event, not here.

    Command: bie, as a login section of ``gbd`` and a push.

    Client: ``BIECommand`` (bundle line 122579), ``GlobalEffectData.parse_GIE`` (bundle line 143676), which
    skips a block without ``GE``, and ``isEffectBoosted`` (bundle line 143643)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "bie"

    global_effect_ids: tuple[EnumOrInt["GlobalEffect"], ...] = Field(
        validation_alias="GE", default=(), description="The boosted global effects"
    )

    @field_validator("global_effect_ids", mode="before")
    @classmethod
    def _listed(cls, value: Any) -> Any:
        # isEffectBoosted looks ids up in the list; anything but a list holds none
        return value if isinstance(value, list | tuple) else ()


class PlayerGift(BasePayload):
    """
    One gift package you hold: ``[package_id, amount]``.

    Client: ``PlayerGiftVO.parseFromArray`` (bundle line 52178)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    package_id: Annotated[PackageId, BeforeValidator(js_int)] = Field(
        default=PackageId(0), description="The package, a packages row of the game data"
    )
    amount: ClientInt = Field(default=0, description="How many you hold")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return dict(zip(("package_id", "amount"), data, strict=False))
        return data


class PlayerGiftsResponse(BaseResponse):
    """
    Your gift packages, to send to other players, and how many you may still send.

    Command: pgl, as a login section of ``gbd`` and a reply.

    Client: ``PGLCommand`` (bundle line 127961), ``PlayerGiftData.parse_PGL`` (bundle line 113571), which skips a
    block without ``G``; ``sendablePackageAmount`` (bundle line 113613), read at bundle line 44174
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "pgl"

    gifts: tuple[PlayerGift, ...] = Field(validation_alias="G", default=(), description="The gift packages you hold")
    sendable_amount: ClientNumber = Field(
        validation_alias="RA",
        default=0,
        description="Gift packages you may still send; none at 0 or less",
    )

    @field_validator("gifts", mode="before")
    @classmethod
    def _gifts(cls, value: Any) -> Any:
        return tuple(readable_list(PlayerGift, value, accept=lambda entry: isinstance(entry, list)))

    @property
    def can_send(self) -> bool:
        """Whether you may send another gift package."""
        return self.sendable_amount > 0


class SendGiftPackagesRequest(BaseRequest):
    """
    Send another player gift packages you hold (``gpg``).

    Client: ``GPGCommandVO`` (bundle line 68352), built as ``(RID, PID, A)`` by
    ``CastlePlayerGiftSliderGiveDialog.onBtnOkClick`` (bundle line 68336)
    """

    command = "gpg"

    receiver_id: int = Field(validation_alias="RID", description="The player who gets the gift")
    package_id: PackageId = Field(validation_alias="PID", description="The package, a PlayerGift.package_id you hold")
    amount: int = Field(validation_alias="A", description="How many of the package to send")


class SendGiftPackagesResponse(BaseResponse):
    """
    The reply to ``gpg``, which carries nothing the client reads; ``TOO_MANY_PACKAGES_SENT_TODAY`` refuses
    past the day's limit.

    Client: ``GPGCommand.executeCommand`` (bundle line 127957)
    """

    command = "gpg"


class FoodProductionStatus(BaseResponse):
    """
    Whether your food production is frozen: the client then shows food, mead and beef production and
    consumption as frozen.

    Command: DTS, as a login section of ``gbd`` and a push.

    Client: ``DTSCommand.executeCommand`` (bundle line 129363), ``CastleUserData.parse_DTS`` (bundle line 9925),
    ``GBDCommand.exec`` (bundle line 129430)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "DTS"

    frozen: bool = Field(validation_alias="DTS", default=False, description="Whether food production is frozen")

    @field_validator("frozen", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


__all__ = [
    "BoostedGlobalEffectsResponse",
    "DailyResetResponse",
    "FoodProductionStatus",
    "OfficerBonus",
    "OfficerTraining",
    "PlayerGift",
    "PlayerGiftsResponse",
    "SendGiftPackagesRequest",
    "SendGiftPackagesResponse",
]


class PlayerIdentityResponse(BaseResponse):
    """
    Who you are: the ``gpi`` login section, pushed again when it changes.

    Command: gpi, as a login section of ``gbd`` and a push.

    ``E`` is your email here, not an error code, so ``error_code`` stays 0.

    Client: ``GPICommand.executeCommand`` (bundle line 129683), ``CastleUserData.parse_GPI`` (bundle
    line 9873), reading ``CommKeys.USER_ID`` (``UID``), ``TARGET_PLAYER_ID`` (``PID``), ``PLAYER_NAME``
    (``PN``), ``EMAIL_2`` (``E``), ``HAS_CONFIRMED_EMAIL`` (``V``), ``ADMIN_SECURITY_LEVEL`` (``CL``)
    and ``CTAC``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gpi"

    error_code: int = Field(default=0, exclude=True, description="Always 0; the E of a gpi is the email")
    user_id: ClientInt = Field(validation_alias="UID", default=0, description="Your account id")
    player_id: ClientInt = Field(validation_alias="PID", default=0, description="Your player id")
    name: str = Field(validation_alias="PN", default="", description="Your player name")
    email: str = Field(validation_alias="E", default="", description='Your email; empty when the server sends "-1"')
    email_confirmed: bool = Field(
        validation_alias="V",
        default=False,
        description="Your email is confirmed (1 == V); an unconfirmed one counts as temporary",
    )
    is_cheater: bool = Field(validation_alias="CL", default=False, description="Your admin security level is above 0")
    accepted_terms: bool = Field(
        validation_alias="CTAC", default=False, description="You accepted the terms and conditions (CTAC > 0)"
    )

    @field_validator("name", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        return value if isinstance(value, str) else ""

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value: Any) -> Any:
        # parse_GPI: "-1" != e.E ? e.E : "", with JavaScript's loose comparison
        return "" if not isinstance(value, str) or js_loose_equals(value, -1) else value

    @field_validator("email_confirmed", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("is_cheater", "accepted_terms", mode="before")
    @classmethod
    def _above_zero(cls, value: Any) -> bool:
        return js_number(value) > 0


class VipStatusResponse(BaseResponse):
    """
    Your VIP status: the ``vip`` login section, pushed as it changes.

    Command: vip, as a login section of ``gbd``, a push, and inside an ``sbp`` reply.

    Client: ``VIPCommand.exec`` (bundle line 129988), ``CastleVIPData.parse_VIP`` (bundle line 47542),
    which reads each key through ``int()`` and keeps no VIP time for a ``VRS`` of 0 or less
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "vip"

    vip_points: ClientInt = Field(validation_alias="VP", default=0, description="Your VIP points")
    vip_level: ClientInt = Field(validation_alias="VRL", default=0, description="The highest VIP level you reached")
    vip_seconds_left: ClientInt = Field(
        validation_alias="VRS", default=0, description="Seconds of VIP time left when sent; 0 without VIP time"
    )
    used_premium_commanders: ClientInt = Field(
        validation_alias="UPG",
        default=0,
        description="Premium commanders used today from the VIP level's free ones",
    )

    @field_validator("vip_seconds_left")
    @classmethod
    def _no_vip_time(cls, value: int) -> int:
        return max(0, value)
