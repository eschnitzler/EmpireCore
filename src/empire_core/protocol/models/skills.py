"""
Generals and legend skills: the two attacker-side inputs that size a wave.

A general's unlocked skills widen the flanks; the player's legend skills widen
them further and add waves, but only in a legendary fight. Both are read with
their own command and neither arrives with the commander list.
"""

from __future__ import annotations

import logging

from pydantic import Field

from .base import BasePayload, BaseRequest, BaseResponse

logger = logging.getLogger(__name__)


class GetGeneralsRequest(BaseRequest):
    """
    Request every general the player owns.

    Command: gie
    Payload: {}
    """

    command = "gie"


class General(BasePayload):
    """
    One general, as ``GeneralVO.parseData`` reads it.

    ``skill_ids`` is the useful part: the skills it has unlocked, which is what
    the attack dialog accumulates for the flank and front unit bonuses.
    """

    general_id: int = Field(alias="GID", default=-1)
    experience: int = Field(alias="XP", default=0)
    star_level: int = Field(alias="ST", default=0)
    skill_ids: list[int] = Field(alias="SIDS", default_factory=list)
    ability_ids: list[int] = Field(alias="GASAIDS", default_factory=list)
    fixed_level: int = Field(alias="L", default=-1)
    wins: int = Field(alias="W", default=0)
    defeats: int = Field(alias="D", default=0)


class GetGeneralsResponse(BaseResponse):
    """
    Response listing the player's generals.

    Command: gie
    Payload: {"G": [{"GID": .., "SIDS": [skill ids], ..}, ..]}
    """

    command = "gie"

    generals: list[General] = Field(alias="G", default_factory=list)

    def skill_ids(self, general_id: int) -> list[int]:
        """The skills one general has unlocked, empty when it is not listed."""
        for general in self.generals:
            if general.general_id == general_id:
                return general.skill_ids
        return []


class GetSkillsRequest(BaseRequest):
    """
    Request the player's own skill lists.

    Command: skl
    Payload: {}
    """

    command = "skl"


class GetSkillsResponse(BaseResponse):
    """
    Response listing the player's legend and sceat skills.

    Command: skl
    Payload: {"SID": [legend skill ids], "SIDS": [sceat skill ids],
              "SP": total_points, "RS": seconds_until_reset}

    ``parse_SKL`` reads exactly these: ``SID`` are the legend skills, which
    apply only in a legendary fight, and ``SIDS`` the Hall of Legends sceat
    skills, which always apply.
    """

    command = "skl"

    legend_skill_ids: list[int] = Field(alias="SID", default_factory=list)
    sceat_skill_ids: list[int] = Field(alias="SIDS", default_factory=list)
    total_points: int = Field(alias="SP", default=0)
    seconds_until_reset: int = Field(alias="RS", default=0)


__all__ = [
    "General",
    "GetGeneralsRequest",
    "GetGeneralsResponse",
    "GetSkillsRequest",
    "GetSkillsResponse",
]
