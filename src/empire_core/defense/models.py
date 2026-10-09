"""
Defense protocol models.

Commands:
- dfc: Read a castle's keep, wall and moat setup
- dfk: Set the keep's tools and unit settings
- dfw: Set the wall's tools and unit split
- dfm: Set the moat's tools
- sdi: Defense of a castle you could send support to
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import Field, ValidatorFunctionWrapHandler, field_validator, model_validator

from empire_core.army.models.units import UnitInventory
from empire_core.army.spy_army import SpyArmyBlock
from empire_core.commanders.models.roster import Castellan, CommanderRoster
from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt, UnitOrTool, WodAmountSlots
from empire_core.movements.models import MovementArea
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, read_or_none
from empire_core.protocol.js import ClientInt, js_int, row_is_at

if TYPE_CHECKING:
    from empire_core.gamedata import Unit

logger = logging.getLogger(__name__)


# =============================================================================
# DFC - Read a castle's defense setup
# =============================================================================


class GetDefenseRequest(BaseRequest):
    """
    Read the defense setup of one of your castles.

    Command: dfc
    Payload: {"CX": castle_x, "CY": castle_y, "AID": area_id, "KID": kingdom}

    ``KID`` is -1 unless a kingdom is given: the VO defaults it to -1, and
    every call site passes -1 or leaves it out.

    Client: ``C2SDefenceCompleteVO`` (bundle line 32769); every call site
    passes the castle's ``absAreaPos`` and ``objectId``, with ``KID`` -1 or
    omitted (``CastleDefenceDialog.updateDefenceData``, bundle line 15978)
    """

    command = "dfc"

    castle_x: int = Field(validation_alias="CX", serialization_alias="CX", description="Castle map x")
    castle_y: int = Field(validation_alias="CY", serialization_alias="CY", description="Castle map y")
    area_id: int = Field(
        validation_alias="AID",
        serialization_alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    kingdom_id: Kingdom | None = Field(
        validation_alias="KID",
        serialization_alias="KID",
        default=None,
        description="The castle's kingdom; None for none",
    )

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _no_kingdom(cls, value: Any) -> Any:
        return None if value == -1 else value

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        if self.kingdom_id is None:
            payload["KID"] = -1
        return payload

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a dfc reply is about this castle: its area row ``A``, when sent, lies at ``CX``/``CY``.

        Client: ``DFCCommand`` (bundle line 123480) through ``parse_DFC`` (bundle line
        134243), which reads the castle from ``A`` with ``parseWorldMapArea``.
        """
        row = payload.get("A") if isinstance(payload, dict) else None
        return not isinstance(row, list) or row_is_at(row, self.castle_x, self.castle_y)


class WallSection(BasePayload):
    """
    One wall section's setup as the ``dfw`` reply carries it; a missing
    number reads as 0, as the client's ``int()`` gives.

    Client: ``CastleDefenceData.parse_DFW`` (bundle line 134250)
    """

    slots: WodAmountSlots = Field(
        validation_alias="S", serialization_alias="S", default=(), description="Wall tool slots"
    )
    unit_percent: ClientInt = Field(
        validation_alias="UP",
        serialization_alias="UP",
        default=0,
        description="Share of the wall's units on this section",
    )
    unit_composition: ClientInt = Field(
        validation_alias="UC", serialization_alias="UC", default=0, description="Unit composition of this section"
    )


class WallDefense(BaseResponse):
    """
    The wall setup: the ``dfw`` reply, also nested in ``dfc``.

    Command: dfw
    Client: ``DFWCommand.executeCommand`` (bundle line 123525),
    ``CastleDefenceData.parse_DFW`` (bundle line 134250)
    """

    command = "dfw"

    left: WallSection = Field(
        validation_alias="L", serialization_alias="L", default_factory=WallSection, description="Left wall section"
    )
    middle: WallSection = Field(
        validation_alias="M", serialization_alias="M", default_factory=WallSection, description="Middle wall section"
    )
    right: WallSection = Field(
        validation_alias="R", serialization_alias="R", default_factory=WallSection, description="Right wall section"
    )
    unit_count: ClientInt = Field(
        validation_alias="U", serialization_alias="U", default=0, description="Units on the wall"
    )
    unit_slot_count: ClientInt = Field(
        validation_alias="US", serialization_alias="US", default=0, description="Units the wall can hold"
    )
    defense: ClientInt = Field(
        validation_alias="D", serialization_alias="D", default=0, description="Wall defence, as a whole number"
    )


class KeepDefense(BaseResponse):
    """
    The keep setup: the ``dfk`` reply, also nested in ``dfc``.

    Command: dfk
    Client: ``DFKCommand.executeCommand`` (bundle line 123495),
    ``CastleDefenceData.parse_DFK`` (bundle line 134251)
    """

    command = "dfk"

    slots: WodAmountSlots = Field(
        validation_alias="S", serialization_alias="S", default=(), description="Keep tool slots"
    )
    support_tool_slots: WodAmountSlots = Field(
        validation_alias="STS", serialization_alias="STS", default=(), description="Keep support-tool slots"
    )
    alliance_unit_yard_limit: ClientInt = Field(
        validation_alias="AUYL", serialization_alias="AUYL", default=0, description="Alliance unit yard limit"
    )
    unit_yard_limit: ClientInt = Field(
        validation_alias="UYL", serialization_alias="UYL", default=0, description="Unit yard limit"
    )
    unit_count: ClientInt = Field(
        validation_alias="U", serialization_alias="U", default=0, description="Units in the keep"
    )
    unit_composition: ClientInt = Field(
        validation_alias="UC", serialization_alias="UC", default=0, description="Keep unit composition"
    )
    min_attacking_units_for_tools: ClientInt = Field(
        validation_alias="MAUCT",
        serialization_alias="MAUCT",
        default=0,
        description="Minimum attacking units before the keep's tools are used",
    )

    @property
    def keep_unit_slot_count(self) -> int:
        """
        Units the keep can hold: ``UYL - AUYL``.

        The client makes it unlimited on special servers and in daimyo
        townships, which this reply cannot tell.
        """
        return self.unit_yard_limit - self.alliance_unit_yard_limit


class MoatDefense(BaseResponse):
    """
    The moat setup: the ``dfm`` reply, also nested in ``dfc``.

    Command: dfm
    Client: ``DFMCommand.executeCommand`` (bundle line 123510),
    ``CastleDefenceData.parse_DFM`` (bundle line 134252)
    """

    command = "dfm"

    left_slots: WodAmountSlots = Field(
        validation_alias="LS", serialization_alias="LS", default=(), description="Left moat slots"
    )
    middle_slots: WodAmountSlots = Field(
        validation_alias="MS", serialization_alias="MS", default=(), description="Middle moat slots"
    )
    right_slots: WodAmountSlots = Field(
        validation_alias="RS", serialization_alias="RS", default=(), description="Right moat slots"
    )
    defense: ClientInt = Field(
        validation_alias="D", serialization_alias="D", default=0, description="Moat defence, as a whole number"
    )


class GetDefenseResponse(BaseResponse):
    """
    A castle's whole defense setup.

    Command: dfc
    Client: ``DFCCommand.executeCommand`` (bundle line 123480),
    ``CastleDefenceData.parse_DFC`` (bundle line 134243). The server also
    sends ``MDS`` and ``RDS``, which the client does not read.
    """

    command = "dfc"

    unit_inventory: UnitInventory = Field(
        validation_alias="gui",
        serialization_alias="gui",
        default_factory=UnitInventory,
        description="The castle's unit inventory",
    )
    area: MovementArea | None = Field(
        validation_alias="A", serialization_alias="A", default=None, description="The castle's map row"
    )
    home_defense_workshop_level: int | None = Field(
        validation_alias="HDWL",
        serialization_alias="HDWL",
        default=None,
        description="Defense workshop level, which unlocks the keep's support-tool slots",
    )
    wall: WallDefense | None = Field(
        validation_alias="dfw", serialization_alias="dfw", default=None, description="Wall setup"
    )
    keep: KeepDefense | None = Field(
        validation_alias="dfk", serialization_alias="dfk", default=None, description="Keep setup"
    )
    moat: MoatDefense | None = Field(
        validation_alias="dfm", serialization_alias="dfm", default=None, description="Moat setup"
    )
    range_priority: tuple[EnumOrInt["Unit"], ...] = Field(
        validation_alias="PR",
        serialization_alias="PR",
        default=(),
        description="The ranged units in the order the castle places them on the wall",
    )
    melee_priority: tuple[EnumOrInt["Unit"], ...] = Field(
        validation_alias="PM",
        serialization_alias="PM",
        default=(),
        description="The melee units in the order the castle places them on the wall",
    )
    gate_defense: ClientInt = Field(
        validation_alias="GD", serialization_alias="GD", default=0, description="Gate defence, as a whole number"
    )
    castellan: Castellan | None = Field(
        validation_alias="L",
        serialization_alias="L",
        default=None,
        description="The castle's castellan; None when there is none",
    )
    listed_castellan_id: ClientInt = Field(
        default=-1, exclude=True, description="The listed castellan's id; -1 when none is listed"
    )

    @model_validator(mode="before")
    @classmethod
    def _castellan_id_from_l(cls, data: Any) -> Any:
        # Client: parse_DFC does e.L && (this._lordID = int(e.L.ID)), and {} is truthy
        if isinstance(data, dict) and isinstance(data.get("L"), dict):
            data = {**data, "listed_castellan_id": js_int(data["L"].get("ID"))}
        return data

    @field_validator("castellan", mode="wrap")
    @classmethod
    def _castellan_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Castellan | None:
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the castellan of a dfc reply")

    @property
    def castellan_id(self) -> int:
        """The castellan's id, ``int(L.ID)``; -1 when none is set, as the client starts from."""
        return self.castellan.commander_id if self.castellan else self.listed_castellan_id

    def inventory(self) -> dict[UnitOrTool, int]:
        """The castle's units as ``{Unit or Tool: amount}``, the only inventory ``parse_DFC`` reads."""
        return dict(self.unit_inventory.units)


# =============================================================================
# DFK / DFW / DFM - Change the keep, wall and moat setup
# =============================================================================


class ChangeKeepDefenseRequest(BaseRequest):
    """
    Set the keep's tools, support tools and unit settings.

    The client builds the slot lists from its keep containers, one pair per
    slot; start from the ``dfc`` reply's ``dfk`` lists. Fields follow the
    client's key order.

    Command: dfk
    Client: ``C2SDefenceKeepVO`` (bundle line 66597), built by
    ``CastleDefenceDialog.sendKeepData`` (bundle line 16041), which sends an
    empty ``STS`` when there is no support-tool container
    """

    command = "dfk"

    castle_x: int = Field(validation_alias="CX", serialization_alias="CX", description="Castle map x")
    castle_y: int = Field(validation_alias="CY", serialization_alias="CY", description="Castle map y")
    area_id: int = Field(
        validation_alias="AID",
        serialization_alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    min_attacking_units_for_tools: int = Field(
        validation_alias="MAUCT",
        serialization_alias="MAUCT",
        default=0,
        description="Minimum attacking units before the keep's tools are used",
    )
    unit_composition: int = Field(
        validation_alias="UC", serialization_alias="UC", default=50, description="Keep unit composition"
    )
    slots: WodAmountSlots = Field(validation_alias="S", serialization_alias="S", description="Keep tool slots")
    support_tool_slots: WodAmountSlots = Field(
        validation_alias="STS", serialization_alias="STS", default=(), description="Keep support-tool slots"
    )


class WallSectionSetup(BasePayload):
    """
    One wall section in a ``dfw`` request; the client has no defaults.

    Client: ``C2SDefenceWallVO`` (bundle line 66616)
    """

    slots: WodAmountSlots = Field(validation_alias="S", serialization_alias="S", description="Wall tool slots")
    unit_percent: int = Field(
        validation_alias="UP", serialization_alias="UP", description="Share of the wall's units on this section"
    )
    unit_composition: int = Field(
        validation_alias="UC", serialization_alias="UC", description="Unit composition of this section"
    )


class ChangeWallDefenseRequest(BaseRequest):
    """
    Set the wall's tools and unit split per section.

    Every section needs its slots, unit percent and unit composition; the
    client has no defaults for them. Start from the ``dfc`` reply's ``dfw``.

    Command: dfw
    Client: ``C2SDefenceWallVO`` (bundle line 66616), built by
    ``CastleDefenceDialog.sendWallData`` (bundle line 16045)
    """

    command = "dfw"

    castle_x: int = Field(validation_alias="CX", serialization_alias="CX", description="Castle map x")
    castle_y: int = Field(validation_alias="CY", serialization_alias="CY", description="Castle map y")
    area_id: int = Field(
        validation_alias="AID",
        serialization_alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    left: WallSectionSetup = Field(validation_alias="L", serialization_alias="L", description="Left wall section")
    middle: WallSectionSetup = Field(validation_alias="M", serialization_alias="M", description="Middle wall section")
    right: WallSectionSetup = Field(validation_alias="R", serialization_alias="R", description="Right wall section")


class ChangeMoatDefenseRequest(BaseRequest):
    """
    Set the moat's tools.

    Start from the ``dfc`` reply's ``dfm`` lists.

    Command: dfm
    Client: ``C2SDefenceMoatVO`` (bundle line 66607), built by
    ``CastleDefenceDialog.sendMoatData`` (bundle line 16049)
    """

    command = "dfm"

    castle_x: int = Field(validation_alias="CX", serialization_alias="CX", description="Castle map x")
    castle_y: int = Field(validation_alias="CY", serialization_alias="CY", description="Castle map y")
    area_id: int = Field(
        validation_alias="AID",
        serialization_alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    left_slots: WodAmountSlots = Field(validation_alias="LS", serialization_alias="LS", description="Left moat slots")
    middle_slots: WodAmountSlots = Field(
        validation_alias="MS", serialization_alias="MS", description="Middle moat slots"
    )
    right_slots: WodAmountSlots = Field(validation_alias="RS", serialization_alias="RS", description="Right moat slots")


# =============================================================================
# SDI - Support Defence Info
# =============================================================================


class GetSupportDefenseRequest(BaseRequest):
    """
    Get the defense of a castle you could send support to, before sending it.

    Command: sdi
    Payload: {"TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y}

    The client sends it from the Support button, which it shows for a castle
    of another member of your alliance (and a few other areas, such as your
    own outposts), never for your own castle; the server answers your own
    castle with NO_SELF_DESTRUCTION (92). Read your own castle with ``dfc``.

    Client: ``C2SSupportDefenceInfoVO`` (bundle line 72078), sent by
    ``CastleStartAttackDialog.supportDefence`` (bundle line 14833);
    ``CastleMapobjectVO.canBeSupported`` (bundle line 18918),
    ``OutpostMapobjectVO.canBeSupported`` (bundle line 18820)
    """

    command = "sdi"

    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Map x of the castle to support")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Map y of the castle to support")
    source_x: int = Field(
        validation_alias="SX", serialization_alias="SX", description="Map x of your castle the support would leave from"
    )
    source_y: int = Field(
        validation_alias="SY", serialization_alias="SY", description="Map y of your castle the support would leave from"
    )


class GetSupportDefenseResponse(BaseResponse):
    """
    Defense information for an alliance member's castle.

    Command: sdi
    Payload::

        {"SCID": source_castle_id,
         "S": [left, middle, right, keep, stronghold, support, reserve],
         "AS": spy_age_seconds, "B": {castellan}, "abe": {castellan}, "LS": [...],
         "gaa": {"AI": [...], "OI": [...]},
         "gui": {"I": [[wod_id, count], ...], "SHI": [...]},
         "gli": {"C": [...], "B": [...]},
         "UYL": yard_limit, "AUYL": alliance_yard_limit, "UWL": wall_limit}

    The client reads ``S``, ``AS``, the castellan and ``LS`` into the same
    ``CastleSpyArmyInfoVO`` a spy report and an attack pre-calculation use. It
    takes the castellan from ``abe`` when the target is an alliance
    battleground tower and from ``B`` otherwise.

    Client: ``SDICommand.executeCommand`` (bundle line 122352), which passes
    ``gli`` to ``CastleLordData.parse_GLI``;
    ``CastleSupportDefenceVO.fillFromParamObject`` (bundle line 140066);
    ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699).
    """

    command = "sdi"

    castle_id: int = Field(validation_alias="SCID", serialization_alias="SCID", default=0)
    defense_positions: SpyArmyBlock = Field(
        validation_alias="S",
        serialization_alias="S",
        default=None,
        description="The castle's defenders by the position they hold; None when the reply lists none",
    )
    castellan: Castellan | None = Field(
        validation_alias="B",
        serialization_alias="B",
        default=None,
        description="The castle's castellan, without its equipment; None when there is none",
    )
    tower_castellan: Castellan | None = Field(
        validation_alias="abe",
        serialization_alias="abe",
        default=None,
        description="The castellan of an alliance battleground tower, in place of castellan",
    )
    unit_inventory: UnitInventory = Field(
        validation_alias="gui",
        serialization_alias="gui",
        default_factory=UnitInventory,
        description="Your own units and tools, and your stronghold units",
    )
    commander_roster: CommanderRoster = Field(
        validation_alias="gli",
        serialization_alias="gli",
        default_factory=CommanderRoster,
        description="Your commanders and castellans",
    )

    yard_limit: int = Field(
        validation_alias="UYL",
        serialization_alias="UYL",
        default=0,
        description="Courtyard unit limit, the alliance share (available_yard_limit) included",
    )
    available_yard_limit: int = Field(
        validation_alias="AUYL",
        serialization_alias="AUYL",
        default=0,
        description="The share of the courtyard limit open to alliance support",
    )
    wall_limit: int = Field(validation_alias="UWL", serialization_alias="UWL", default=0, description="Wall unit limit")

    @field_validator("castellan", "tower_castellan", mode="wrap")
    @classmethod
    def _castellan_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> Castellan | None:
        # Client: LordFactory.createLord returns null for an empty entry
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the castellan of an sdi reply")

    def get_max_defense(self) -> int:
        """
        Get the maximum defense capacity for this castle.

        UYL (yard_limit) represents the total capacity including
        courtyard limit plus room for alliance support.

        Returns:
            Maximum number of troops that can defend this castle.
        """
        return self.yard_limit


__all__ = [
    # DFC - Get Defense
    "GetDefenseRequest",
    "GetDefenseResponse",
    "WallSection",
    "WallSectionSetup",
    "WallDefense",
    "KeepDefense",
    "MoatDefense",
    # DFK - Keep Defense
    "ChangeKeepDefenseRequest",
    # DFW - Wall Defense
    "ChangeWallDefenseRequest",
    # DFM - Moat Defense
    "ChangeMoatDefenseRequest",
    # SDI - Support Defense Info
    "GetSupportDefenseRequest",
    "GetSupportDefenseResponse",
]
