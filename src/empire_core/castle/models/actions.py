"""Castle actions.

Commands:
- jca: Join a castle (answered as jaa)
- jaa: Join an area by its position
- arc: Rename castle
- mas: Abandon a castle
- mac: Cancel abandoning a castle
- rst: Relocate castle
- laa: Leave the joined area
- gtwara: The joined area is gone, back to the world map
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.base import BaseRequest, BaseResponse, enum_or_none
from empire_core.protocol.js import js_int, js_same_number, row_is_at
from empire_core.protocol.text import encode_json_text

from .brewery import BreweryProductionResponse
from .collect import MineStatusList, ResourceCartInfo
from .details import CastleProductionArea
from .objects import CastleBuildings, block_or_none
from .resources import CastleResources
from .storage import DecorationStorages
from .updates import AreaBooster, SlumLevel

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
        validation_alias="CID",
        description=(
            "The castle to join, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")


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

    x: int = Field(validation_alias="PX", description="Map x")
    y: int = Field(validation_alias="PY", description="Map y")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The kingdom it lies in")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a jaa reply is for this area: its ``KID`` and, when sent, the joined area's row position.

        Client: ``JAACommand`` (bundle line 130190) switches to the reply's ``KID``;
        ``AreaFactory.parseAreaInfo`` (bundle line 130226) reads the area from
        ``gca.A`` with ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line
        5343), whose parser for every area type takes the position from ``A[1]``
        and ``A[2]`` (``BasicMapobjectVO``, ``InteractiveMapobjectVO``,
        ``CapitalMapobjectVO``, ``MetropolMapobjectVO``, ``FactionCampMapobjectVO``
        and the rest, bundle lines 3631-76548). A treasure camp (``T`` 8) is the
        exception: its area is not read from ``A``, so its reply is not checked
        for position.
        """
        if not isinstance(payload, dict):
            return False
        if "KID" in payload and not js_same_number(payload["KID"], self.kingdom_id):
            return False
        if js_same_number(payload.get("T"), MapItemType.TREASURE_CAMP):
            return True
        area = payload.get("gca")
        row = area.get("A") if isinstance(area, dict) else None
        return not isinstance(row, list) or row_is_at(row, self.x, self.y)


class SelectCastleResponse(BaseResponse):
    """
    The joined area's state, the ``jaa`` the server answers a join with.

    Command: jaa, the answer to both ``jca`` and a ``jaa`` by position; the
    client reads both with the same code.
    Payload: {"KID": kingdom_id, "T": area_type, "gca": {...}, "grc": {...}, "gpa": {...}, ...}

    A block that cannot be read is None, so it does not cost the rest. The
    other blocks (``spl0`` to ``spl3``, ``gui``, ``uap``, ``hin``, ``crai``) are kept as sent.

    Client: ``JAACommand.executeCommand`` (bundle line 130190),
    ``AreaDataUpdater.parseJAA`` (bundle line 131496)
    """

    command = "jaa"

    kingdom_id: int = Field(validation_alias="KID", default=0, description="The joined area's kingdom")
    area_type: MapItemType | None = Field(
        validation_alias="T",
        default=None,
        description="The joined area's type; None for one MapItemType lacks",
    )
    buildings: CastleBuildings | None = Field(
        validation_alias="gca",
        default=None,
        description="The area's buildings; None when the reply has none",
    )
    resources: CastleResources | None = Field(
        validation_alias="grc",
        default=None,
        description="The area's resources; None when the reply has none",
    )
    production_area: CastleProductionArea | None = Field(
        validation_alias="gpa",
        default=None,
        description="The area's production area; None when the reply has none",
    )
    slum_level: SlumLevel | None = Field(
        validation_alias="csl",
        default=None,
        description="The area's slum level; None when the reply has none",
    )
    area_booster: AreaBooster | None = Field(
        validation_alias="gab",
        default=None,
        description="The area's builder discount; None when the reply has none",
    )
    mines: MineStatusList | None = Field(
        validation_alias="gsm",
        default=None,
        description="The area's mines; None when the reply has none",
    )
    resource_carts: ResourceCartInfo | None = Field(
        validation_alias="rci",
        default=None,
        description="The area's resource carts; None when the reply has none",
    )
    brewery: BreweryProductionResponse | None = Field(
        validation_alias="abpi",
        default=None,
        description="The castle's brewery production; None when the reply has none",
    )
    storages: DecorationStorages = Field(
        validation_alias="sin", default_factory=list, description="The decoration storages the reply names"
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

    @field_validator("slum_level", mode="before")
    @classmethod
    def _slum_level(cls, value: Any) -> SlumLevel | None:
        return block_or_none(SlumLevel, value)

    @field_validator("area_booster", mode="before")
    @classmethod
    def _area_booster(cls, value: Any) -> AreaBooster | None:
        return block_or_none(AreaBooster, value)

    @field_validator("mines", mode="before")
    @classmethod
    def _mines(cls, value: Any) -> MineStatusList | None:
        return block_or_none(MineStatusList, value)

    @field_validator("resource_carts", mode="before")
    @classmethod
    def _resource_carts(cls, value: Any) -> ResourceCartInfo | None:
        return block_or_none(ResourceCartInfo, value)

    @field_validator("brewery", mode="before")
    @classmethod
    def _brewery(cls, value: Any) -> BreweryProductionResponse | None:
        # JAACommand (bundle line 130249) parses the first entry
        return block_or_none(BreweryProductionResponse, value[0]) if isinstance(value, list) and value else None


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
        validation_alias="CID",
        description="The castle to rename, a CastleInfo.castle_id from client.castle.get_all()",
    )
    is_rename: int = Field(
        validation_alias="P",
        default=1,
        description="1 to rename, 0 to name a newly acquired castle such as a monument",
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    castle_type: MapItemType = Field(validation_alias="AT", description="The castle's area type")
    castle_name: str = Field(validation_alias="N", description="The new name")

    @field_serializer("castle_name")
    def _encoded_name(self, value: str) -> str:
        return encode_json_text(value)

    def accepts_reply(self, payload: Any) -> bool:
        """Whether an arc reply is about this castle: its ``CID``, and its ``KID`` when sent, are the ones asked for.

        Client: ``ARCCommand.executeCommand`` (bundle line 124966) looks the renamed
        castle up by the reply's ``CID`` and ``KID`` (bundle line 124968).
        """
        if not isinstance(payload, dict) or not js_same_number(payload.get("CID"), self.castle_id):
            return False
        return "KID" not in payload or js_same_number(payload["KID"], self.kingdom_id)


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

    castle_id: int = Field(validation_alias="CID", description="The renamed castle")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    is_rename: int = Field(validation_alias="P", default=1, description="1 for a rename, 0 for a first naming")


# =============================================================================
# MAS / MAC - Abandon Castle
# =============================================================================


class AbandonCastleRequest(BaseRequest):
    """
    Start abandoning one of your castles.

    Command: mas
    Payload: {"CID": castle_id, "KID": kingdom_id}

    The castle is given up after ``OutpostConst.ABANDON_TIME`` (86400 s),
    and the abandon may be cancelled within ``ABANDON_CANCEL_TIME`` (10800 s).

    Client: ``C2SAbandonOutpostStartVO`` (bundle line 104735), sent by
    ``CastleManagementDialog.onAbandonOutpost`` (bundle line 24630);
    ``OutpostConst`` (dll line 19530)
    """

    command = "mas"

    castle_id: int = Field(
        validation_alias="CID",
        description="The castle to abandon, a CastleInfo.castle_id from client.castle.get_all()",
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a mas reply is about this castle: its ``CID``, and its ``KID`` when sent.

        Client: ``CastleUserData.parse_MAS`` (bundle line 9893) looks the castle up by ``CID`` and ``KID``.
        """
        if not isinstance(payload, dict) or not js_same_number(payload.get("CID"), self.castle_id):
            return False
        return "KID" not in payload or js_same_number(payload["KID"], self.kingdom_id)


class AbandonCastleResponse(BaseResponse):
    """
    The castle being abandoned and its timers.

    Command: mas
    Payload: {"CID": castle_id, "KID": kingdom_id, "AOT": seconds, "CAT": seconds}

    Client: ``MASCommand.executeCommand`` (bundle line 125051),
    ``CastleUserData.parse_MAS`` (bundle line 9893)
    """

    command = "mas"

    castle_id: int = Field(validation_alias="CID", description="The castle being abandoned")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    abandon_seconds: int = Field(validation_alias="AOT", default=-1, description="Seconds until it is abandoned")
    cancel_seconds: int = Field(validation_alias="CAT", default=-1, description="Seconds left to cancel the abandon")

    _timers = field_validator("abandon_seconds", "cancel_seconds", mode="before")(js_int)


class CancelAbandonCastleRequest(BaseRequest):
    """
    Cancel abandoning one of your castles.

    Command: mac
    Payload: {"CID": castle_id, "KID": kingdom_id}

    The client offers it only while the castle's ``CAT`` is above 0.

    Client: ``C2SAbandonOutpostCancelVO`` (bundle line 104726), sent by
    ``CastleManagementDialog.onCancelAbandoning`` (bundle line 24629)
    """

    command = "mac"

    castle_id: int = Field(
        validation_alias="CID",
        description="The castle to keep, a CastleInfo.castle_id from client.castle.get_all()",
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a mac reply is about this castle: its ``CID``, and its ``KID`` when sent.

        Client: ``CastleUserData.parse_MAC`` (bundle line 9896) looks the castle up by ``CID`` and ``KID``.
        """
        if not isinstance(payload, dict) or not js_same_number(payload.get("CID"), self.castle_id):
            return False
        return "KID" not in payload or js_same_number(payload["KID"], self.kingdom_id)


class CancelAbandonCastleResponse(BaseResponse):
    """
    The castle kept; the client sets both its abandon timers to -1.

    Command: mac
    Payload: {"CID": castle_id, "KID": kingdom_id}

    Client: ``MACCommand.executeCommand`` (bundle line 125037),
    ``CastleUserData.parse_MAC`` (bundle line 9896)
    """

    command = "mac"

    castle_id: int = Field(validation_alias="CID", description="The castle kept")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")


# =============================================================================
# RST - Relocate Castle
# =============================================================================


class RelocateCastleRequest(BaseRequest):
    """
    Start a relocation to a new position.

    Command: rst
    Payload: {"PX": x, "PY": y}

    The client sends only the position: no castle id and no kingdom. It relocates the main castle in
    the green kingdom.

    Client: ``C2SStartRelocationVO`` (bundle line 109671), sent by
    ``CastleRelocateDialog.onClick`` (bundle line 109656)
    """

    command = "rst"

    x: int = Field(validation_alias="PX", description="Map x of the new position")
    y: int = Field(validation_alias="PY", description="Map y of the new position")


class RelocateCastleResponse(BaseResponse):
    """
    The relocation started.

    Command: rst

    Client: ``RSTCommand.executeCommand`` (bundle line 126855) reads nothing from the reply
    """

    command = "rst"


# =============================================================================
# LAA - Leave Area
# =============================================================================


class LeaveAreaRequest(BaseRequest):
    """
    Leave the area you joined last.

    Command: laa
    Payload: {}

    The client registers no handler for an ``laa`` reply.

    Client: ``C2SLeaveAreaVO`` (bundle line 108588), sent by ``CastleKingdomOverviewScreen.show``
    (bundle line 108518)
    """

    command = "laa"


# =============================================================================
# GTWARA - Go To World map After Remove Area
# =============================================================================


class LeftRemovedAreaResponse(BaseResponse):
    """
    The area you were in is gone, and the client goes back to the world map.

    Command: gtwara, pushed

    Client: ``GTWARACommand.executeCommand`` (bundle line 127296) reads nothing and runs
    ``SwitchToWorldmapCommand``
    """

    command = "gtwara"


__all__ = [
    "AbandonCastleRequest",
    "AbandonCastleResponse",
    "CancelAbandonCastleRequest",
    "CancelAbandonCastleResponse",
    "JoinAreaRequest",
    "LeaveAreaRequest",
    "LeftRemovedAreaResponse",
    "SelectCastleRequest",
    "SelectCastleResponse",
    "RenameCastleRequest",
    "RenameCastleResponse",
    "RelocateCastleRequest",
    "RelocateCastleResponse",
]
