"""
Citizen judgements: a citizen's case the server opens in your castle, and your verdict.

Commands:
- sjc: A judgement starts (push)
- jjc: Give your verdict; the reply ends the judgement
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field, field_validator

from empire_core.enums import JudgementOption
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import js_parse_int

if TYPE_CHECKING:
    from empire_core.gamedata import Judgement


class JudgementStarted(BaseResponse):
    """
    A citizen judgement started; one already open ends.

    Client: ``SJCCommand.executeCommand`` (bundle line 124681), ``CastleJudgementData.parse_SJC`` and
    ``startNewJudgement`` (bundle lines 134465, 134467), which look ``parseInt(JID)`` up in the ``judgements``
    table and open none for an id it lacks
    """

    command: ClassVar[str] = "sjc"

    judgement_id: EnumOrInt["Judgement"] | None = Field(
        validation_alias="JID", default=None, description="The judgement that started; None when the push names none"
    )

    @field_validator("judgement_id", mode="before")
    @classmethod
    def _judgement(cls, value: Any) -> Any:
        return None if value is None else js_parse_int(value)


class JudgeCitizenRequest(BaseRequest):
    """
    Give your verdict on the open citizen judgement (``jjc``).

    Client: ``C2SJudgeJudgementCitizenVO`` (bundle line 95563), sent by
    ``CastleJudgementChooseOptionDialog.onClick`` (bundle lines 95550-95552)
    """

    command: ClassVar[str] = "jjc"

    option: JudgementOption = Field(validation_alias="CO", description="The verdict")


class JudgeCitizenResponse(BaseResponse):
    """
    The verdict given; the judgement is over.

    Client: ``JJCCommand.executeCommand`` (bundle line 124666), ``CastleJudgementData.parse_JJC`` (bundle line
    134466), which shows the verdict's reward and ends the judgement
    """

    command: ClassVar[str] = "jjc"

    option: EnumOrInt[JudgementOption] = Field(validation_alias="CO", default=0, description="The verdict given")


__all__ = ["JudgeCitizenRequest", "JudgeCitizenResponse", "JudgementStarted"]
