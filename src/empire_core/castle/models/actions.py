"""Castle actions.

Commands:
- jca: Join a castle (answered as jaa)
- jaa: Join an area by its position
- arc: Rename castle
- rst: Relocate castle
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.base import BaseRequest, BaseResponse, enum_or_none
from empire_core.protocol.js import js_int
from empire_core.protocol.text import encode_json_text

from .details import CastleProductionArea
from .objects import CastleBuildings, block_or_none
from .resources import CastleResources

# =============================================================================
# JCA - Jump to Castle / Select Castle
# =============================================================================


class SelectCastleRequest(BaseRequest):
    """
    Join a castle, making it the session's active castle.

    Command: jca (answered as 'jaa')
    Payload: {"CID": castle_id, "KID": kingdom_id}

    Castle-scoped reads such as ``gui`` answer for the joined castle.

    Client: ``C2SJoinCastleVO`` (bundle line 5841); its ``MY_CASTLE`` is -1
    """

    command = "jca"
    response_command = "jaa"

    castle_id: int = Field(
        alias="CID",
        description=(
            "The castle to join, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")


class JoinAreaRequest(BaseRequest):
    """
    Join an area by its position rather than by castle id.

    Command: jaa
    Payload: {"PX": x, "PY": y, "KID": kingdom_id}

    The client joins a map object this way only when it may visit it and it
    is not a castle: ``JoinAreaAndSavePositionCommand`` sends ``jca`` for a
    ``CastleMapobjectVO`` (main and kingdom castles) and ``jaa`` for anything
    else. Its callers pass either your own areas from the castle lists or,
    from a double click on the world map or the ring menu's visit button,
    an object whose ``canBeVisited`` is true: outposts, capitals and
    metropolises, and faction camps that are not destroyed. Every other
    object (NPC camps, dungeons, kings towers, villages, monuments and the
    rest) says false, and the client never joins it; a live server answered
    INVALID_POSITION (6) for NPC camps and a kings tower. ``ARCCommand``
    also joins a kingdom castle by position after its first naming, and a
    live server accepted that too. Joining another
    player's outpost is what the client allows; whether the server accepts it
    is unverified.

    Client: ``C2SJoinAreaVO`` (bundle line 56128), whose key order the fields
    follow; sent by ``JoinAreaAndSavePositionCommand.execute`` (bundle line
    100892) and ``ARCCommand.executeCommand`` (bundle line 124969);
    ``CastleWorldMapScreen.onDoubleClickCastle`` (bundle line 39601) and
    ``ButtonVisitCastleComponent`` (bundle line 110159) check
    ``canBeVisited``, on ``InteractiveMapobjectVO`` (bundle line 3678),
    ``OutpostMapobjectVO`` (bundle line 18829), ``CastleMapobjectVO``
    (bundle line 18924) and ``FactionCampMapobjectVO`` (bundle line 21538)
    """

    command = "jaa"

    x: int = Field(alias="PX", description="Map x")
    y: int = Field(alias="PY", description="Map y")
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom it lies in")


class SelectCastleResponse(BaseResponse):
    """
    The joined area's state, the ``jaa`` the server answers a join with.

    Command: jaa, the answer to both ``jca`` and a ``jaa`` by position; the
    client reads both with the same code.
    Payload: {"KID": kingdom_id, "T": area_type, "gca": {...}, "grc": {...}, "gpa": {...}, ...}

    A block that cannot be read is None, so it does not cost the rest. The
    other blocks (``csl``, ``gab``, ``gsm``, ``spl0`` to ``spl3``, ``gui``,
    ``uap``, ``hin``, ``sin``, ``rci``, ``abpi``, ``crai``) are kept as sent.

    Client: ``JAACommand.executeCommand`` (bundle line 130190),
    ``AreaDataUpdater.parseJAA`` (bundle line 131496)
    """

    command = "jaa"

    kingdom_id: int = Field(alias="KID", default=0, description="The joined area's kingdom")
    area_type: MapItemType | None = Field(
        alias="T", default=None, description="The joined area's type; None for one MapItemType lacks"
    )
    buildings: CastleBuildings | None = Field(
        alias="gca", default=None, description="The area's buildings; None when the reply has none"
    )
    resources: CastleResources | None = Field(
        alias="grc", default=None, description="The area's resources; None when the reply has none"
    )
    production_area: CastleProductionArea | None = Field(
        alias="gpa", default=None, description="The area's production area; None when the reply has none"
    )

    @field_validator("area_type", mode="before")
    @classmethod
    def _area_type(cls, value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool):
            return enum_or_none(MapItemType, value)
        return None

    _kingdom = field_validator("kingdom_id", mode="before")(js_int)

    @field_validator("buildings", mode="before")
    @classmethod
    def _buildings(cls, value: Any) -> CastleBuildings | None:
        return block_or_none(CastleBuildings, value)

    @field_validator("resources", mode="before")
    @classmethod
    def _resources(cls, value: Any) -> CastleResources | None:
        return block_or_none(CastleResources, value)

    @field_validator("production_area", mode="before")
    @classmethod
    def _production_area(cls, value: Any) -> CastleProductionArea | None:
        return block_or_none(CastleProductionArea, value)


# =============================================================================
# ARC - Rename Castle
# =============================================================================


class RenameCastleRequest(BaseRequest):
    """
    Rename a castle.

    Command: arc
    Payload: {"CID": castle_id, "P": 0 or 1, "KID": kingdom_id, "AT": area_type, "N": name}

    The keys follow the client's order: the constructor initialises CID, P, KID
    and AT before it sets N, which it encodes as it encodes any text it sends.

    Client: ``C2SRenameCastleVO`` (bundle line 42424)
    """

    command = "arc"

    castle_id: int = Field(
        alias="CID", description="The castle to rename, a CastleInfo.castle_id from client.castle.get_all()"
    )
    is_rename: int = Field(
        alias="P", default=1, description="1 to rename, 0 to name a newly acquired castle such as a monument"
    )
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    castle_type: MapItemType = Field(alias="AT", description="The castle's area type")
    castle_name: str = Field(alias="N", description="The new name")

    @field_serializer("castle_name")
    def _encoded_name(self, value: str) -> str:
        return encode_json_text(value)


class RenameCastleResponse(BaseResponse):
    """
    Response to castle rename.

    Command: arc
    Payload: {"CID": castle_id, "KID": kingdom_id, "P": 0 or 1}

    Client: ``ARCCommand.executeCommand`` (bundle line 124966), which looks the
    castle up by CID and KID, and joins a kingdom castle's area again after a
    first naming (P 0)
    """

    command = "arc"

    castle_id: int = Field(alias="CID", description="The renamed castle")
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    is_rename: int = Field(alias="P", default=1, description="1 for a rename, 0 for a first naming")


# =============================================================================
# RST - Relocate Castle
# =============================================================================


class RelocateCastleRequest(BaseRequest):
    """
    Start a relocation to a new position.

    Command: rst
    Payload: {"PX": x, "PY": y}

    The client sends only the position: no castle id and no kingdom.

    Client: ``C2SStartRelocationVO`` (bundle line 109634), sent by
    ``CastleRelocateDialog.onClick`` (bundle line 109619)
    """

    command = "rst"

    x: int = Field(alias="PX", description="Map x of the new position")
    y: int = Field(alias="PY", description="Map y of the new position")


class RelocateCastleResponse(BaseResponse):
    """
    Response to castle relocation.

    Command: rst

    Client: ``RSTCommand.executeCommand`` (bundle line 126817)
    """

    command = "rst"


__all__ = [
    "JoinAreaRequest",
    "SelectCastleRequest",
    "SelectCastleResponse",
    "RenameCastleRequest",
    "RenameCastleResponse",
    "RelocateCastleRequest",
    "RelocateCastleResponse",
]
