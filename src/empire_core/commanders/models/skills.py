"""
Generals and legend skills: the two attacker-side inputs that size a wave.

A general's unlocked skills widen the flanks; the player's legend skills widen
them further and add waves, but only in a legendary fight. Both are read with
their own command and neither arrives with the commander list.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator, model_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, object_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_loose_equals

from .roster import CommanderRoster, SelectedAbility

if TYPE_CHECKING:
    from empire_core.gamedata import GeneralSkill, LegendSkill, SceatSkill
    from empire_core.gamedata.models import GeneralDef

logger = logging.getLogger(__name__)


def _id_list(value: Any) -> list[Any]:
    """
    An id array as the client walks it: nothing, or not an array, is no ids.

    The client skips only undefined entries; a null one is dropped here too, since it is no id.
    """
    return [entry for entry in value if entry is not None] if isinstance(value, list) else []


class GetGeneralsRequest(BaseRequest):
    """
    Request every general the player owns.

    Command: gie
    Payload: {}

    Client: ``C2SGetGeneralsInfoVO`` (bundle line 56405, no fields)
    """

    command = "gie"


class OwnedGeneral(BasePayload):
    """
    One general, as ``GeneralVO.parseData`` reads it.

    ``skill_ids`` is the useful part: the skills it has unlocked, which is what
    the attack dialog accumulates for the flank and front unit bonuses.

    Client: ``GeneralVO.parseData`` (bundle line 26666)
    """

    general_id: int = Field(alias="GID", default=-1, description="General id")
    experience: int = Field(alias="XP", default=0, description="Experience, 0 when missing")
    star_level: int = Field(
        alias="ST",
        default=0,
        description="Star level; when none is set, derived from fixed_level if that is a multiple of 10",
    )
    is_new: bool = Field(alias="IN", default=False, description="The general is new")
    has_level_up: bool = Field(alias="LU", default=False, description="The general has levelled up")
    skill_ids: tuple[EnumOrInt["GeneralSkill"], ...] = Field(alias="SIDS", default=(), description="Unlocked skills")
    selected_abilities: list[SelectedAbility] = Field(
        alias="GASAIDS", default_factory=list, description="The general's ability slots, filled or empty"
    )
    fixed_level: int = Field(alias="L", default=-1, description="Fixed level; -1 when there is none")
    old_experience: int = Field(alias="OXP", default=0, description="The xp before the last change")
    wins: int = Field(alias="W", default=0, description="Battles won, 0 when missing")
    defeats: int = Field(alias="D", default=0, description="Battles lost, 0 when missing")

    @field_validator("skill_ids", mode="before")
    @classmethod
    def _skill_ids(cls, value: Any) -> Any:
        return _id_list(value)

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
        return js_loose_equals(value, 1)

    @field_validator("selected_abilities", mode="before")
    @classmethod
    def _skip_malformed_slots(cls, value: Any) -> Any:
        # The client indexes each entry; one that is not a pair matches no slot and is ignored.
        return readable_list(SelectedAbility, value)

    @model_validator(mode="after")
    def _star_level_from_fixed_level(self) -> OwnedGeneral:
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
        return [slot.ability_id for slot in self.selected_abilities if slot.ability_id is not None]

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
        return [
            slot.ability_id for slot in self.selected_abilities if slot.slot_id in slots and slot.ability_id is not None
        ]


class AssignGeneralRequest(BaseRequest):
    """
    Assign a general to a commander, or take the commander's general away.

    Command: gla
    Payload: {"LID": commander_id, "GID": general_id}

    Client: ``C2SGeneralAssignLord`` (bundle line 101985)
    """

    command = "gla"

    commander_id: int = Field(
        alias="LID",
        description="The commander to give the general to, from client.commanders.get_commanders()",
    )
    general_id: int = Field(
        alias="GID",
        default=-1,
        description=(
            "The general, an OwnedGeneral.general_id from client.skills.get_generals(); -1 unassigns the "
            "commander's general"
        ),
    )


class AssignGeneralResponse(BaseResponse):
    """
    Reply to a general assignment: the full commander list.

    Command: gla
    Payload: {"gli": {"C": [..], "B": [..]}}

    Client: ``GLACommand.executeCommand`` (bundle line 124218) passes ``gli`` to ``parse_GLI``.
    """

    command = "gla"

    commander_roster: CommanderRoster = Field(
        alias="gli", default_factory=CommanderRoster, description="The commanders and castellans after the change"
    )


class SetGeneralAbilitiesRequest(BaseRequest):
    """
    Choose a general's abilities, one per slot.

    Command: gaae
    Payload: {"GID": general_id, "SAIDS": [[slot_id, ability_id], ..]}

    The ability dialog sends every slot it shows, with -1 for a cleared one.
    The server replies with no body.

    Client: ``C2SGeneralSelectAbilities`` (bundle line 70767),
    ``GeneralsAbilityDialog.onSave`` (bundle line 27846)
    """

    command = "gaae"

    general_id: int = Field(
        alias="GID",
        description=(
            "The general whose abilities are chosen, an OwnedGeneral.general_id from client.skills.get_generals()"
        ),
    )
    abilities: list[SelectedAbility] = Field(
        alias="SAIDS", description="Every slot the dialog shows, each sent as [slot_id, ability_id], -1 for none"
    )


class UnlockGeneralSkillRequest(BaseRequest):
    """
    Unlock a general skill. The skill id names the general, so none is sent.

    Command: guse
    Payload: {"ID": skill_id}

    The server replies with no body.

    Client: ``C2SGeneralUnlockSkillVO`` (bundle line 67469), ``GUSECommand`` (bundle line 124280)
    """

    command = "guse"

    skill_id: int = Field(alias="ID", description="The skill to unlock")


class ResetGeneralSkillsRequest(BaseRequest):
    """
    Reset a general's skill tree.

    Command: grs
    Payload: {"GID": general_id}

    The server replies with no body.

    Client: ``C2SGeneralResetSkills`` (bundle line 67460), ``GRSCommand`` (bundle line 124242)
    """

    command = "grs"

    general_id: int = Field(
        alias="GID",
        description=(
            "The general whose skills are reset, an OwnedGeneral.general_id from client.skills.get_generals()"
        ),
    )


class AddGeneralXpRequest(BaseRequest):
    """
    Feed a general xp items.

    Command: gaxp
    Payload: {"GID": general_id, "CID": currency_id, "AMT": amount}

    The server replies with no body.

    Client: ``C2SGeneralAddXpVO`` (bundle line 74507), ``GAXPCommand`` (bundle line 124176)
    """

    command = "gaxp"

    general_id: int = Field(
        alias="GID",
        description=("The general to give xp to, an OwnedGeneral.general_id from client.skills.get_generals()"),
    )
    currency_id: int = Field(alias="CID", description="The xp item, a currency")
    amount: int = Field(alias="AMT", description="How many of the xp item to use")


class GetGeneralsResponse(BaseResponse):
    """
    Response listing the player's generals.

    Command: gie
    Payload: {"G": [{"GID": .., "SIDS": [skill ids], ..}, ..]}

    Client: ``GIECommand.executeCommand`` (bundle line 124204) hands it to
    ``GeneralsData.parse_GIE`` (bundle line 113069), which updates each general by ``GID``.
    """

    command = "gie"

    generals: list[OwnedGeneral] = Field(alias="G", default_factory=list, description="The player's generals")

    @field_validator("generals", mode="before")
    @classmethod
    def _readable_generals(cls, value: Any) -> Any:
        return readable_list(OwnedGeneral, value, warn=logger, what="generals")

    def skill_ids(self, general_id: int) -> tuple[EnumOrInt["GeneralSkill"], ...]:
        """The skills one general has unlocked, empty when it is not listed."""
        for general in self.generals:
            if general.general_id == general_id:
                return general.skill_ids
        return ()


class GetSkillsRequest(BaseRequest):
    """
    Request the player's own skill lists.

    Command: skl
    Payload: {}

    Client: ``C2SGetSkillListVO`` (bundle line 112219, no fields)
    """

    command = "skl"


class ActivatingSceatSkill(BasePayload):
    """
    A Hall of Legends sceat skill still being activated, an entry of ``SSA``.

    Client: ``CastleLegendSkillData.parse_SKL`` (bundle line 112051)
    """

    skill_id: EnumOrInt["SceatSkill"] | None = Field(
        alias="ID", default=None, description="The sceat skill being activated; None when the entry names none"
    )
    remaining_seconds: ClientInt = Field(alias="RS", default=0, description="Seconds until the skill is active")


class SkillList(BasePayload):
    """
    The player's legend and sceat skills, the ``skl`` block.

    ``SID`` are the legend skills, which apply only in a legendary fight, and
    ``SIDS`` the Hall of Legends sceat skills, which always apply.

    Client: ``CastleLegendSkillData.parse_SKL`` (bundle line 112051)
    """

    legend_skill_ids: tuple[EnumOrInt["LegendSkill"], ...] = Field(
        alias="SID", default=(), description="Legend skills, which apply only in a legendary fight"
    )
    sceat_skill_ids: tuple[EnumOrInt["SceatSkill"], ...] = Field(
        alias="SIDS", default=(), description="Hall of Legends sceat skills, which always apply"
    )
    total_points: ClientInt = Field(alias="SP", default=0, description="Skill points")
    seconds_until_reset: int | float = Field(
        alias="RS", default=0, description="Seconds until the skills can be reset, fractions included"
    )

    reset_count: ClientInt = Field(alias="RC", default=0, description="How many times the skills have been reset")
    activating: list[ActivatingSceatSkill] = Field(
        alias="SSA", default_factory=list, description="Sceat skills still being activated"
    )

    @field_validator("seconds_until_reset", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0

    @field_validator("legend_skill_ids", "sceat_skill_ids", mode="before")
    @classmethod
    def _skill_ids(cls, value: Any) -> Any:
        # parse_SKL walks SID and SIDS only when they are set
        return _id_list(value)

    @field_validator("activating", mode="before")
    @classmethod
    def _readable_entries(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return []
        return [entry for entry in value if isinstance(entry, dict)]


class GetSkillsResponse(BaseResponse, SkillList):
    """
    Response listing the player's legend and sceat skills.

    Command: skl
    Payload: {"SID": [legend skill ids], "SIDS": [sceat skill ids], "SP": total_points,
              "RS": seconds_until_reset, "RC": reset_count, "SSA": [{"ID": .., "RS": ..}, ..]}

    Client: ``SKLCommand.executeCommand`` (bundle line 129742)
    """

    command = "skl"


class ObjectUpdateEvent(BaseResponse):
    """
    An object update pushed by the server.

    Only the skill list is read here; the area update the client also takes
    from it stays in the extra fields.

    Command: ego
    Client: ``EGOCommand.executeCommand`` (bundle line 122801)
    """

    command = "ego"

    skills: SkillList | None = Field(alias="skl", default=None, description="A new skill list, when one was sent")

    @field_validator("skills", mode="before")
    @classmethod
    def _no_skills(cls, value: Any) -> Any:
        # The client parses skl whenever it is truthy, an empty object included
        return object_or_none(value)


__all__ = [
    "OwnedGeneral",
    "SelectedAbility",
    "GetGeneralsRequest",
    "GetGeneralsResponse",
    "AssignGeneralRequest",
    "AssignGeneralResponse",
    "SetGeneralAbilitiesRequest",
    "UnlockGeneralSkillRequest",
    "ResetGeneralSkillsRequest",
    "AddGeneralXpRequest",
    "GetSkillsRequest",
    "GetSkillsResponse",
    "SkillList",
    "ActivatingSceatSkill",
    "ObjectUpdateEvent",
]
