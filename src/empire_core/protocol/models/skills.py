"""
Generals and legend skills: the two attacker-side inputs that size a wave.

A general's unlocked skills widen the flanks; the player's legend skills widen
them further and add waves, but only in a legendary fight. Both are read with
their own command and neither arrives with the commander list.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import Field, ValidationError, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse

if TYPE_CHECKING:
    from empire_core.gamedata.models import GeneralDef

logger = logging.getLogger(__name__)


class GetGeneralsRequest(BaseRequest):
    """
    Request every general the player owns.

    Command: gie
    Payload: {}
    """

    command = "gie"


class SelectedAbility(BasePayload):
    """
    One ability slot of a general: a ``[slot_id, ability_id]`` entry of ``GASAIDS``.

    Client: ``GeneralVO.parseData`` (bundle line 26666) keeps the pairs, and
    ``GeneralVO.getSelectedAbilities`` (bundle line 26769) reads ``[0]`` as the
    slot and ``[1]`` as the ability.
    """

    slot_id: int = Field(description="row[0]: the slot, matched against the general's attack and defense slots")
    ability_id: int = Field(description="row[1]: the ability, -1 for an empty slot")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list) and len(data) >= 2:
            return {"slot_id": data[0], "ability_id": data[1]}
        return data


class General(BasePayload):
    """
    One general, as ``GeneralVO.parseData`` reads it.

    ``skill_ids`` is the useful part: the skills it has unlocked, which is what
    the attack dialog accumulates for the flank and front unit bonuses.

    Client: ``GeneralVO.parseData`` (bundle line 26666)
    """

    general_id: int = Field(alias="GID", default=-1)
    experience: int = Field(alias="XP", default=0)
    star_level: int = Field(
        alias="ST",
        default=0,
        description="Without ST (or with ST 0) and with a fixed level that is a multiple of 10, derived from L",
    )
    is_new: bool = Field(alias="IN", default=False, description="1 == IN")
    has_level_up: bool = Field(alias="LU", default=False, description="1 == LU")
    skill_ids: list[int] = Field(alias="SIDS", default_factory=list)
    selected_abilities: list[SelectedAbility] = Field(
        alias="GASAIDS", default_factory=list, description="The general's ability slots, filled or empty"
    )
    fixed_level: int = Field(alias="L", default=-1, description="L, or -1 when L is missing or 0")
    old_experience: int = Field(alias="OXP", default=0, description="The xp before the last change")
    wins: int = Field(alias="W", default=0)
    defeats: int = Field(alias="D", default=0)

    @field_validator("experience", "old_experience", "wins", "defeats", "star_level", mode="before")
    @classmethod
    def _zero_when_missing(cls, value: Any) -> Any:
        return value or 0

    @field_validator("fixed_level", mode="before")
    @classmethod
    def _no_fixed_level(cls, value: Any) -> Any:
        return value or -1

    @field_validator("is_new", "has_level_up", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        try:
            return float(value) == 1
        except (TypeError, ValueError):
            return False

    @field_validator("selected_abilities", mode="before")
    @classmethod
    def _skip_malformed_slots(cls, value: Any) -> Any:
        # The client indexes each entry; one that is not a pair matches no slot and is ignored.
        if not isinstance(value, list):
            return []
        slots = []
        for entry in value:
            try:
                slots.append(SelectedAbility.model_validate(entry))
            except ValidationError:
                continue
        return slots

    @model_validator(mode="after")
    def _star_level_from_fixed_level(self) -> General:
        """
        Derive the star level from the fixed level when ST is falsy.

        The client computes ``floor((L % 10 == 0 ? L - 1 : this.fixedLevel) / 10)``,
        but ``fixedLevel`` has a setter and no getter (bundle line 26736), so for
        a level that is not a multiple of 10 it gets NaN. Only the multiple-of-10
        branch is applied here; otherwise the star level stays 0.
        """
        if not self.star_level and self.fixed_level > 0 and self.fixed_level % 10 == 0:
            self.star_level = (self.fixed_level - 1) // 10
        return self

    @property
    def ability_ids(self) -> list[int]:
        """
        The abilities this general has selected, one id per filled slot, from either side.

        Client: ``GeneralVO.getSelectedAbilities`` (bundle line 26769) skips a slot whose ability id is not above 0.
        """
        return [slot.ability_id for slot in self.selected_abilities if slot.ability_id > 0]

    def attack_ability_ids(self, general_def: GeneralDef) -> list[int]:
        """
        The abilities selected in this general's attack slots.

        Client: ``GeneralVO.getSelectedAbilities(true)`` (bundle line 26769)
        """
        return self._ability_ids_in(general_def.attack_slots)

    def defense_ability_ids(self, general_def: GeneralDef) -> list[int]:
        """
        The abilities selected in this general's defense slots.

        Client: ``GeneralVO.getSelectedAbilities(false)`` (bundle line 26769)
        """
        return self._ability_ids_in(general_def.defense_slots)

    def _ability_ids_in(self, slots: tuple[int, ...]) -> list[int]:
        return [slot.ability_id for slot in self.selected_abilities if slot.slot_id in slots and slot.ability_id > 0]


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
    "SelectedAbility",
    "GetGeneralsRequest",
    "GetGeneralsResponse",
    "GetSkillsRequest",
    "GetSkillsResponse",
]
