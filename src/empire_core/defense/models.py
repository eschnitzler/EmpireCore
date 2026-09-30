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
from typing import Any

from pydantic import Field, ValidatorFunctionWrapHandler, field_validator, model_validator

from empire_core.army.models.units import SpyPositions, UnitInventory
from empire_core.commanders.models.roster import Castellan, CommanderRoster
from empire_core.enums import Kingdom
from empire_core.movements.models import MovementArea
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, read_or_none
from empire_core.protocol.js import ClientInt, js_int, row_is_at

logger = logging.getLogger(__name__)


Slot = list[int]
"""One container slot: ``[wod_id, amount]``, ``[-1, 0]`` when empty."""


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

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(
        alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    kingdom_id: Kingdom | None = Field(alias="KID", default=None, description="The castle's kingdom; None for none")

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

    slots: list[Slot] = Field(alias="S", default_factory=list, description="Wall tool slots")
    unit_percent: ClientInt = Field(alias="UP", default=0, description="Share of the wall's units on this section")
    unit_composition: ClientInt = Field(alias="UC", default=0, description="Unit composition of this section")


class WallDefense(BaseResponse):
    """
    The wall setup: the ``dfw`` reply, also nested in ``dfc``.

    Command: dfw
    Client: ``DFWCommand.executeCommand`` (bundle line 123525),
    ``CastleDefenceData.parse_DFW`` (bundle line 134250)
    """

    command = "dfw"

    left: WallSection = Field(alias="L", default_factory=WallSection, description="Left wall section")
    middle: WallSection = Field(alias="M", default_factory=WallSection, description="Middle wall section")
    right: WallSection = Field(alias="R", default_factory=WallSection, description="Right wall section")
    unit_count: ClientInt = Field(alias="U", default=0, description="Units on the wall")
    unit_slot_count: ClientInt = Field(alias="US", default=0, description="Units the wall can hold")
    defense: ClientInt = Field(alias="D", default=0, description="Wall defence, as a whole number")


class KeepDefense(BaseResponse):
    """
    The keep setup: the ``dfk`` reply, also nested in ``dfc``.

    Command: dfk
    Client: ``DFKCommand.executeCommand`` (bundle line 123495),
    ``CastleDefenceData.parse_DFK`` (bundle line 134251)
    """

    command = "dfk"

    slots: list[Slot] = Field(alias="S", default_factory=list, description="Keep tool slots")
    support_tool_slots: list[Slot] = Field(alias="STS", default_factory=list, description="Keep support-tool slots")
    alliance_unit_yard_limit: ClientInt = Field(alias="AUYL", default=0, description="Alliance unit yard limit")
    unit_yard_limit: ClientInt = Field(alias="UYL", default=0, description="Unit yard limit")
    unit_count: ClientInt = Field(alias="U", default=0, description="Units in the keep")
    unit_composition: ClientInt = Field(alias="UC", default=0, description="Keep unit composition")
    min_attacking_units_for_tools: ClientInt = Field(
        alias="MAUCT",
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

    left_slots: list[Slot] = Field(alias="LS", default_factory=list, description="Left moat slots")
    middle_slots: list[Slot] = Field(alias="MS", default_factory=list, description="Middle moat slots")
    right_slots: list[Slot] = Field(alias="RS", default_factory=list, description="Right moat slots")
    defense: ClientInt = Field(alias="D", default=0, description="Moat defence, as a whole number")


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
        alias="gui",
        default_factory=UnitInventory,
        description="The castle's unit inventory",
    )
    area: MovementArea | None = Field(alias="A", default=None, description="The castle's map row")
    home_defense_workshop_level: int | None = Field(
        alias="HDWL",
        default=None,
        description="Defense workshop level, which unlocks the keep's support-tool slots",
    )
    wall: WallDefense | None = Field(alias="dfw", default=None, description="Wall setup")
    keep: KeepDefense | None = Field(alias="dfk", default=None, description="Keep setup")
    moat: MoatDefense | None = Field(alias="dfm", default=None, description="Moat setup")
    range_priority: list[int] = Field(alias="PR", default_factory=list, description="Ranged unit priority")
    melee_priority: list[int] = Field(alias="PM", default_factory=list, description="Melee unit priority")
    gate_defense: ClientInt = Field(alias="GD", default=0, description="Gate defence, as a whole number")
    castellan: Castellan | None = Field(
        alias="L",
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

    def inventory(self) -> dict[int, int]:
        """The castle's units as ``{wod_id: amount}``, the only inventory ``parse_DFC`` reads."""
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

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(
        alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    min_attacking_units_for_tools: int = Field(
        alias="MAUCT",
        default=0,
        description="Minimum attacking units before the keep's tools are used",
    )
    unit_composition: int = Field(alias="UC", default=50, description="Keep unit composition")
    slots: list[Slot] = Field(alias="S", description="Keep tool slots")
    support_tool_slots: list[Slot] = Field(alias="STS", default_factory=list, description="Keep support-tool slots")


class WallSectionSetup(BasePayload):
    """
    One wall section in a ``dfw`` request; the client has no defaults.

    Client: ``C2SDefenceWallVO`` (bundle line 66616)
    """

    slots: list[Slot] = Field(alias="S", description="Wall tool slots")
    unit_percent: int = Field(alias="UP", description="Share of the wall's units on this section")
    unit_composition: int = Field(alias="UC", description="Unit composition of this section")


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

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(
        alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    left: WallSectionSetup = Field(alias="L", description="Left wall section")
    middle: WallSectionSetup = Field(alias="M", description="Middle wall section")
    right: WallSectionSetup = Field(alias="R", description="Right wall section")


class ChangeMoatDefenseRequest(BaseRequest):
    """
    Set the moat's tools.

    Start from the ``dfc`` reply's ``dfm`` lists.

    Command: dfm
    Client: ``C2SDefenceMoatVO`` (bundle line 66607), built by
    ``CastleDefenceDialog.sendMoatData`` (bundle line 16049)
    """

    command = "dfm"

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(
        alias="AID",
        description="The castle's id: CastleInfo.castle_id from client.castle.get_all() or Castle.id",
    )
    left_slots: list[Slot] = Field(alias="LS", description="Left moat slots")
    middle_slots: list[Slot] = Field(alias="MS", description="Middle moat slots")
    right_slots: list[Slot] = Field(alias="RS", description="Right moat slots")


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

    target_x: int = Field(alias="TX", description="Map x of the castle to support")
    target_y: int = Field(alias="TY", description="Map y of the castle to support")
    source_x: int = Field(alias="SX", description="Map x of your castle the support would leave from")
    source_y: int = Field(alias="SY", description="Map y of your castle the support would leave from")


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

    castle_id: int = Field(alias="SCID", default=0)
    defense_positions: SpyPositions = Field(
        alias="S",
        default_factory=list,
        description="Defenders as [wod_id, amount] pairs per position: left, middle, right, keep, "
        "stronghold, support, then an optional reserve",
    )
    castellan: Castellan | None = Field(
        alias="B",
        default=None,
        description="The castle's castellan, without its equipment; None when there is none",
    )
    tower_castellan: Castellan | None = Field(
        alias="abe",
        default=None,
        description="The castellan of an alliance battleground tower, in place of castellan",
    )
    unit_inventory: UnitInventory = Field(
        alias="gui",
        default_factory=UnitInventory,
        description="Your own units and tools, and your stronghold units",
    )
    commander_roster: CommanderRoster = Field(
        alias="gli",
        default_factory=CommanderRoster,
        description="Your commanders and castellans",
    )

    # Capacity limits
    yard_limit: int = Field(alias="UYL", default=0)  # Total yard/courtyard limit
    available_yard_limit: int = Field(alias="AUYL", default=0)  # Available yard space
    wall_limit: int = Field(alias="UWL", default=0)  # Wall limit

    @field_validator("castellan", "tower_castellan", mode="wrap")
    @classmethod
    def _castellan_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> Castellan | None:
        # Client: LordFactory.createLord returns null for an empty entry
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the castellan of an sdi reply")

    def get_total_defenders(self) -> int:
        """
        Calculate total number of defending troops.

        Returns:
            Total count of all units across all defense positions.
        """
        return sum(count for position in self.defense_positions for _, count in position)

    def get_max_defense(self) -> int:
        """
        Get the maximum defense capacity for this castle.

        UYL (yard_limit) represents the total capacity including
        courtyard limit plus room for alliance support.

        Returns:
            Maximum number of troops that can defend this castle.
        """
        return self.yard_limit

    def get_units_by_position(self) -> list[dict[int, int]]:
        """
        Get unit counts grouped by defense position.

        Returns:
            One dict per position, each mapping unit_id -> count for that position.
        """
        result = []
        for position in self.defense_positions:
            units: dict[int, int] = {}
            for unit_id, count in position:
                units[unit_id] = units.get(unit_id, 0) + count
            result.append(units)
        return result


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
