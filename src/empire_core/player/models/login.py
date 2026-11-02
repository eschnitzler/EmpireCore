"""
Your player sections of the login data (``gbd``), each also pushed on its own.

Commands:
- gpi: who you are
- gxp: level and XP
- gcu: coins and rubies
- vip: VIP status
- gho: honor and ranking points
- gal: your alliance membership
- sce: special currencies
- glu: a level-up
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import AliasChoices, ConfigDict, Field, field_validator, model_validator

from empire_core.gamedata import EnumOrStr
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import BaseResponse, CurrencyBlock, CurrencyTotals, object_or_none
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals, js_number, js_parse_int

if TYPE_CHECKING:
    from empire_core.gamedata import Currency


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


class ExperienceResponse(BaseResponse):
    """
    Your level and XP: the ``gxp`` login section, pushed as they change.

    The client ignores the ``LL``, ``XPFCL`` and ``XPTNL`` the server sends alongside and computes
    the legend level and the level's XP range from these two; so does ``client.state``.

    Command: gxp, as a login section of ``gbd``, a push, and inside a ``glu``.

    Client: ``GXPCommand.executeCommand`` (bundle line 129719), ``CastleUserData.parse_GXP`` (bundle
    line 9878), which reads ``int(e.XP)`` and ``LVL`` as sent
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gxp"

    xp: ClientInt = Field(validation_alias="XP", default=0, description="Your total XP")
    level: int | None = Field(
        validation_alias="LVL",
        default=None,
        description=(
            "Your level; 70 is the cap before legend levels. None when the server sent nothing parseInt"
            " reads as a number, which the client stores as it came"
        ),
    )

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: Any) -> Any:
        return js_parse_int(value)


class CurrencyResponse(BaseResponse, CurrencyTotals):
    """
    Your coins and rubies: the ``gcu`` login section, pushed as they change.

    Command: gcu, as a login section of ``gbd``, a push, and inside many replies (see ``CurrencyBlock``).

    Client: ``GCUCommand.exec`` (bundle line 129491), ``CurrencyData.parseGCU`` (bundle line 141240)
    """

    command = "gcu"


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


class HonorResponse(BaseResponse):
    """
    Your honor and ranking points: the ``gho`` login section, pushed as they change.

    Command: gho, as a login section of ``gbd`` and a push.

    Client: ``GHOCommand.executeCommand`` (bundle line 129559), ``CastleUserData.parse_GHO`` (bundle
    line 9875), which reads both through ``int()``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gho"

    honor: ClientInt = Field(validation_alias="H", default=0, description="Your honor")
    ranking_points: ClientInt = Field(validation_alias="RP", default=0, description="Your ranking points")


class Alliance(BaseResponse):
    """
    Your alliance membership: the ``gal`` login section, pushed when you join or leave.

    An ``alliance_id`` of 0 or less means no alliance; the client then forgets its alliance
    and chat, and so does ``client.state``.

    Command: gal, as a login section of ``gbd`` and a push.

    Client: ``GALCommand.executeCommand`` (bundle line 129393), ``CastleUserData.parse_GAL`` (bundle
    line 9876), which reads ``AID``, ``R`` and ``ACF`` through ``int()``, ``AN`` as sent and
    ``1 == parseInt(e.SA)``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gal"

    alliance_id: ClientInt = Field(validation_alias="AID", default=0, description="The alliance; 0 or less for none")
    rank: ClientInt = Field(validation_alias="R", default=0, description="Your rank in the alliance")
    # The client reads AN; live servers send N
    name: str = Field(validation_alias=AliasChoices("AN", "N"), default="", description="The alliance's name")
    current_fame: ClientInt = Field(validation_alias="ACF", default=0, description="The alliance's current fame")
    is_searching: bool = Field(validation_alias="SA", default=False, description="You are looking for an alliance")

    @field_validator("name", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        return value if isinstance(value, str) else ""

    @field_validator("is_searching", mode="before")
    @classmethod
    def _searching_flag(cls, value: Any) -> bool:
        return js_parse_int(value) == 1

    @property
    def is_member(self) -> bool:
        """Whether you are in an alliance: ``alliance_id`` above 0."""
        return self.alliance_id > 0


class SpecialCurrenciesResponse(BaseResponse):
    """
    Your special currencies: the ``sce`` login section, pushed as they change.

    The payload is a list of ``[currency_key, amount]`` pairs. A key the generated ``Currency``
    enum lacks stays a str (the client ignores keys its item data lacks).

    Command: sce, as a login section of ``gbd`` and a push.

    Client: ``SCECommand.exec`` (bundle line 129774), ``CurrencyData.parseSCE`` (bundle line
    141231), which sets ``int(amount)`` on the currency with that key
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "sce"

    amounts: dict[EnumOrStr["Currency"], int] = Field(default_factory=dict, description="Amount per currency")

    @model_validator(mode="before")
    @classmethod
    def _pairs(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        from empire_core.gamedata import Currency

        amounts: dict[Any, int] = {}
        for entry in data:
            if isinstance(entry, list) and entry:
                amounts[known(Currency, str(entry[0]))] = js_int(entry[1] if len(entry) > 1 else None)
        return {"amounts": amounts}


class LevelUpResponse(BaseResponse):
    """
    A level-up: your new currencies and XP, and the level the client's dialog shows.

    Command: glu, a push.

    Client: ``GLUCommand.executeCommand`` (bundle line 129619), which hands ``gcu`` to
    ``CurrencyData.parseGCU`` and then ``gxp`` to ``CastleUserData.parse_GXP``; ``int(L)`` and
    ``1 == LL`` only drive the level-up dialog and tracking
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "glu"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", default=None, description="Coins and rubies after the level-up"
    )
    experience: ExperienceResponse | None = Field(
        validation_alias="gxp", default=None, description="Level and XP after the level-up"
    )
    level: ClientInt = Field(validation_alias="L", default=0, description="The level reached, as the dialog shows it")
    is_legend_level_up: bool = Field(
        validation_alias="LL", default=False, description="The level-up is a legend level (1 == LL)"
    )

    @field_validator("experience", mode="before")
    @classmethod
    def _experience(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("is_legend_level_up", mode="before")
    @classmethod
    def _legend_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)
