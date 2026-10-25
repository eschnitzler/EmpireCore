"""
The officers' school: its training programs, offered and running.

Commands:
- gtp: The programs on offer, the one running and the reroll and prolong counts
- atp: Start an offered program
- ptp: Prolong the program running
- rtp: Reroll the offered programs
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field, field_serializer, field_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_truthy

from .account import OfficerBonus

if TYPE_CHECKING:
    from empire_core.gamedata import CurrencyId


class TrainingProgram(BasePayload):
    """
    A training program as ``gtp`` sends it: one on offer, or the one running.

    Not a response model: its ``E`` is the program's bonus, not an error code.

    Client: ``OfficersSchoolData.parseOfficerEffectVO`` (bundle line 144737), which reads the program's row
    of the ``officersSchoolEffects`` table by ``TE``; ``OfficersSchoolEffectVO.getCost`` (bundle line 144773)
    prices slot 1 in coins, slot 2 in the day's event currency and slot 3 in rubies
    """

    program_id: ClientInt = Field(
        validation_alias="TE", default=0, description="The program's row in the officers' school effects table"
    )
    slot_id: ClientInt = Field(validation_alias="S", default=0, description="The offer slot the program is in")
    duration_seconds: ClientNumber = Field(validation_alias="D", default=0, description="Seconds the program runs")
    bonus: OfficerBonus | None = Field(
        validation_alias="E", default=None, description="The bonus the program gives; None for none"
    )

    @field_validator("bonus", mode="before")
    @classmethod
    def _bonus(cls, value: Any) -> Any:
        return value if isinstance(value, OfficerBonus) or (isinstance(value, list) and value) else None


def _program_or_none(value: Any) -> Any:
    return value if js_truthy(value) else None


class GetTrainingProgramsRequest(BaseRequest):
    """
    Ask for the officers' school's training programs (``gtp``).

    Client: ``C2SGetTrainingProgramInfoVO`` (bundle line 85724), sent as ``OfficersSchoolDialogList`` shows
    (bundle line 85651)
    """

    command: ClassVar[str] = "gtp"


class TrainingProgramsResponse(BaseResponse):
    """
    The officers' school's training programs: those on offer, the one running and today's counts.

    Client: ``GTPCommand.executeCommand`` (bundle line 126183), ``OfficersSchoolData.parse_GTP``
    (bundle line 144715)
    """

    command: ClassVar[str] = "gtp"

    running: TrainingProgram | None = Field(
        validation_alias="AT", default=None, description="The program running; None when none runs"
    )
    offered: tuple[TrainingProgram, ...] = Field(
        validation_alias="TP", default=(), description="The programs on offer, by slot"
    )
    prolong_count: ClientInt = Field(
        validation_alias="PC", default=0, description="How often the running program was prolonged"
    )
    event_currency_rerolls: ClientInt = Field(
        validation_alias="RCSC", default=0, description="Rerolls paid in the event currency so far"
    )
    ruby_rerolls: ClientInt = Field(validation_alias="RCHC", default=0, description="Rerolls paid in rubies so far")
    event_currency: EnumOrInt["CurrencyId"] = Field(
        validation_alias="CT",
        default=0,
        description="The event currency slot 2's program and the cheaper reroll cost today",
    )

    @field_validator("running", mode="before")
    @classmethod
    def _running(cls, value: Any) -> Any:
        return _program_or_none(value)

    @field_validator("offered", mode="before")
    @classmethod
    def _offered(cls, value: Any) -> Any:
        return readable_list(TrainingProgram, value)


class ActivateTrainingProgramRequest(BaseRequest):
    """
    Start the training program on offer in a slot (``atp``).

    Client: ``C2SActivateTrainingProgramVO`` (bundle line 85787), sent by
    ``OfficersSchoolEffectItem.onConfirmBuy`` (bundle line 85774)
    """

    command: ClassVar[str] = "atp"

    slot_id: int = Field(validation_alias="S", description="The offer slot of the program to start")


class ActivateTrainingProgramResponse(BaseResponse):
    """The reply to ``atp``, which carries nothing the client reads. Client: ``ATPCommand`` (bundle line 126151)"""

    command: ClassVar[str] = "atp"


class ProlongTrainingProgramRequest(BaseRequest):
    """
    Prolong the training program running, for rubies (``ptp``).

    Client: ``C2SProlongTrainingProgramVO`` (bundle line 85732), sent by ``OfficersSchoolDialogList.onBuyProlong``
    (bundle line 85691); ``OfficersSchoolData.getC2ProlongCosts`` (bundle line 144743) prices it in rubies
    """

    command: ClassVar[str] = "ptp"


class ProlongTrainingProgramResponse(BaseResponse):
    """The reply to ``ptp``, which carries nothing the client reads. Client: ``PTPCommand`` (bundle line 126194)"""

    command: ClassVar[str] = "ptp"


class RerollTrainingProgramsRequest(BaseRequest):
    """
    Replace the training programs on offer, except those kept (``rtp``).

    Client: ``C2SRerollTrainingProgramsVO`` (bundle line 144760), sent by ``OfficersSchoolData.sendReroll``
    (bundle line 144706) with the slots locked against the reroll; ``OfficersSchoolDialogList`` prices the
    reroll in the event currency, or in rubies for the premium one (``OfficersSchoolDialogList.softRerollCosts``,
    ``hardRerollCosts``, bundle lines 85711-85714; ``onClick``, bundle lines 85679-85681)
    """

    command: ClassVar[str] = "rtp"

    premium: bool = Field(
        validation_alias="P", default=False, description="The reroll is paid in rubies, not the event currency"
    )
    kept_slot_ids: list[int] = Field(
        validation_alias="LS", default_factory=list, description="The offer slots whose programs stay"
    )

    @field_serializer("premium")
    def _flag(self, value: bool) -> int:
        return int(value)


class RerollTrainingProgramsResponse(BaseResponse):
    """The reply to ``rtp``, which carries nothing the client reads. Client: ``RTPCommand`` (bundle line 126207)"""

    command: ClassVar[str] = "rtp"


__all__ = [
    "ActivateTrainingProgramRequest",
    "ActivateTrainingProgramResponse",
    "GetTrainingProgramsRequest",
    "ProlongTrainingProgramRequest",
    "ProlongTrainingProgramResponse",
    "RerollTrainingProgramsRequest",
    "RerollTrainingProgramsResponse",
    "TrainingProgram",
    "TrainingProgramsResponse",
]
