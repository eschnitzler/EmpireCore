"""
Account sections of the login data, and the pushes and replies that bring them again.

Commands:
- drt: seconds until the daily reset
- gatp: the officers' school training program running now
- bie: the global effects a booster event boosts
- pgl: your gift packages and how many you may still send

The timed models count from ``received_at``, as the client counts from its timer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseResponse, TimedPayload, TimedResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber

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
        serialization_alias="STR",
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

    slot_id: ClientInt = Field(
        validation_alias="S", serialization_alias="S", default=-1, description="The program's slot, -1 for none"
    )
    bonus: OfficerBonus | None = Field(
        validation_alias="E", serialization_alias="E", default=None, description="The program's bonus; None for none"
    )
    seconds: ClientNumber = Field(
        validation_alias="RS",
        serialization_alias="RS",
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
        validation_alias="GE", serialization_alias="GE", default=(), description="The boosted global effects"
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

    package_id: ClientInt = Field(default=0, description="The event package's id")
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

    gifts: tuple[PlayerGift, ...] = Field(
        validation_alias="G", serialization_alias="G", default=(), description="The gift packages you hold"
    )
    sendable_amount: ClientNumber = Field(
        validation_alias="RA",
        serialization_alias="RA",
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


__all__ = [
    "BoostedGlobalEffectsResponse",
    "DailyResetResponse",
    "OfficerBonus",
    "OfficerTraining",
    "PlayerGift",
    "PlayerGiftsResponse",
]
