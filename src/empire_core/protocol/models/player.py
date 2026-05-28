"""
Player protocol models.

Commands:
- gdi: Get detailed player info (including castle list with capture info)
- wsp: World search player (search by name)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import ConfigDict, Field

from .base import BasePayload, BaseRequest, BaseResponse
from .map import Kingdom

# =============================================================================
# Location Types
# =============================================================================

LOCATION_TYPES = {
    0: "Empty",
    1: "Castle",
    2: "Dungeon",
    3: "Capital",
    4: "Outpost",
    7: "Treasure Dungeon",
    12: "Castle",  # Colored kingdom castle (KID 1-4)
    15: "Camp",
    22: "Metro",
    26: "Monument",
    28: "Laboratory",
}


def get_location_type_name(type_id: int) -> str:
    """Get the human-readable name for a location type."""
    return LOCATION_TYPES.get(type_id, f"Unknown ({type_id})")


# =============================================================================
# Location Capture Info
# =============================================================================


class LocationCapture(BaseResponse):
    """
    Information about a location being captured.

    Extracted from the gdi response's gcl.C[].AI[] arrays.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    location_id: int = 0
    location_type: int = 0
    location_type_name: str = ""
    x: int = 0
    y: int = 0
    kingdom: Kingdom = Kingdom.GREEN
    capturer_id: int = -1  # Player ID of who is capturing, -1 if none

    @property
    def is_being_captured(self) -> bool:
        """Check if this location is being captured."""
        return self.capturer_id != -1


# =============================================================================
# Player Castle (gcl parsed)
# =============================================================================


class PlayerCastle(BasePayload):
    """
    A castle/location from the gdi response's gcl.C[].AI[] arrays.

    AI array format (confirmed from packet examples):
    [type, x, y, location_id, owner_id, lvl1, lvl2, lvl3, lvl4, lvl5,
     name, ?, ?, ?, capturer_id_capital, capturer_id_outpost, kingdom, ...]

    Index reference:
    - 0:  castle_type (1=Castle, 3=Capital, 4=Outpost, 12=?, 15=Camp, 22=Metro)
    - 1:  x
    - 2:  y
    - 3:  location_id (area_id)
    - 4:  owner_id
    - 10: name
    - 14: capturer_id (Capital/Metro)
    - 15: capturer_id (Outpost)
    - 16: kingdom (KID)
    """

    kingdom: int = 0
    location_id: int = 0
    x: int = 0
    y: int = 0
    castle_type: int = 0
    owner_id: int = 0
    name: str = ""
    capturer_id: int = -1

    @property
    def castle_type_name(self) -> str:
        """Human-readable castle type."""
        return get_location_type_name(self.castle_type)

    @property
    def is_being_captured(self) -> bool:
        """Check if this location is currently being captured."""
        return self.capturer_id != -1

    @classmethod
    def from_list(cls, data: list, kingdom: int = 0) -> "PlayerCastle":
        """Parse from a gcl.C[].AI[] array entry."""
        if not data or len(data) < 4:
            return cls(kingdom=kingdom)

        castle_type = data[0] if len(data) > 0 else 0
        x = data[1] if len(data) > 1 else 0
        y = data[2] if len(data) > 2 else 0
        location_id = data[3] if len(data) > 3 else 0
        owner_id = data[4] if len(data) > 4 else 0
        name = data[10] if len(data) > 10 else ""

        # Capturer ID position depends on type
        type_name = get_location_type_name(castle_type)
        if type_name == "Outpost":
            capturer_id = data[15] if len(data) > 15 else -1
        elif type_name in ("Capital", "Metro"):
            capturer_id = data[14] if len(data) > 14 else -1
        else:
            capturer_id = -1

        # Kingdom can also be read from index 16 if present (overrides passed-in kingdom)
        if len(data) > 16 and isinstance(data[16], int):
            kingdom = data[16]

        return cls(
            kingdom=kingdom,
            location_id=location_id,
            x=x,
            y=y,
            castle_type=castle_type,
            owner_id=owner_id,
            name=name,
            capturer_id=capturer_id,
        )


# =============================================================================
# Player Owner Info
# =============================================================================


class PlayerOwnerInfo(BaseResponse):
    """
    Owner info from the gdi response's O object.

    Field mapping (confirmed from packet examples):
    - OID: Player ID
    - N: Player name
    - AID: Alliance ID
    - AN: Alliance name
    - L: Level
    - LL: Legendary level
    - H: Honor (or unknown metric)
    - AVP: Avatar points
    - CF: Castle count (main castles)
    - HF: Total castles including outposts
    - MP: Might/power points
    - PRE: Title prefix ID
    - SUF: Title suffix ID
    - TOPX: Global ranking (-1 if unranked)
    - DUM: Dummy/inactive account flag
    - AR: Alliance rank
    - SA: Special ability/status
    - VF: VIP flag
    - PF: Premium flag
    - RRD: Resource request date
    - TI: Title index
    - RPT: Revenge protection time remaining (seconds) — bird
    - AP: Castle positions [[kingdom, area_id, x, y, castle_type], ...]
    - VP: Village positions (usually empty)
    - E: Emblem configuration
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_id: int = Field(alias="OID", default=0)
    name: str = Field(alias="N", default="")
    alliance_id: int = Field(alias="AID", default=0)
    alliance_name: str = Field(alias="AN", default="")
    level: int = Field(alias="L", default=0)
    legendary_level: int = Field(alias="LL", default=0)
    h_field: int = Field(alias="H", default=0)
    avatar_points: int = Field(alias="AVP", default=0)
    castle_count: int = Field(alias="CF", default=0)
    total_castles: int = Field(alias="HF", default=0)
    might: int = Field(alias="MP", default=0)
    title_prefix: int = Field(alias="PRE", default=0)
    title_suffix: int = Field(alias="SUF", default=-1)
    top_ranking: int = Field(alias="TOPX", default=-1)
    is_dummy: bool = Field(alias="DUM", default=False)
    alliance_rank: int = Field(alias="AR", default=0)
    special_ability: int = Field(alias="SA", default=0)
    vip_flag: int = Field(alias="VF", default=0)
    premium_flag: int = Field(alias="PF", default=0)
    resource_request_date: int = Field(alias="RRD", default=0)
    title_index: int = Field(alias="TI", default=-1)
    revenge_protection_seconds: int = Field(alias="RPT", default=0)
    castle_positions: list = Field(alias="AP", default_factory=list)
    village_positions: list = Field(alias="VP", default_factory=list)

    # Emblem — imported inline to avoid circular import at module level
    emblem: dict | None = Field(alias="E", default=None)

    @property
    def honor(self) -> int:
        """Get player's honor (H field)."""
        return self.h_field

    @property
    def castles(self) -> list:
        """Parse AP castle positions. Returns list of MemberCastle objects."""
        from .alliance import MemberCastle

        return [MemberCastle.from_list(pos) for pos in self.castle_positions]

    @property
    def has_bird(self) -> bool:
        """Check if player has revenge protection (bird) active."""
        return self.revenge_protection_seconds > 0

    @property
    def bird_end_time(self) -> datetime | None:
        """
        Calculate when bird protection ends.

        Returns:
            Timezone-aware datetime (UTC) when bird expires, or None if no bird.

        Note:
            Calculated relative to when gdi data was fetched — use promptly.
        """
        if self.revenge_protection_seconds <= 0:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=self.revenge_protection_seconds)

    @property
    def is_leader(self) -> bool:
        """Check if player is alliance leader (AR=8)."""
        return self.alliance_rank == 8

    @property
    def is_officer(self) -> bool:
        """Check if player is an officer (AR > 0 and < 8)."""
        return 0 < self.alliance_rank < 8


# =============================================================================
# GDI - Get Detailed Player Info
# =============================================================================


class GetPlayerInfoRequest(BaseRequest):
    """
    Get detailed player information including castle list.

    Command: gdi
    Payload: {"PID": player_id}

    Returns owner info (O) and castle list (gcl.C) with capture status.
    """

    command = "gdi"

    player_id: int = Field(alias="PID")


class GetPlayerInfoResponse(BaseResponse):
    """
    Response containing detailed player information.

    Command: gdi
    Response format: {
        "O": { ...player fields... },
        "gcl": {"PID": ..., "C": [{"KID": ..., "AI": [{"AI": [...]}]}]}
    }

    The gcl.C array contains castle/location info per kingdom.
    Each location AI array:
    - Index 0:  location type (1=Castle, 3=Capital, 4=Outpost, 15=Camp, 22=Metro)
    - Index 1:  x
    - Index 2:  y
    - Index 3:  location ID
    - Index 4:  owner player ID
    - Index 10: name
    - Index 14: capturer ID (Capital/Metro)
    - Index 15: capturer ID (Outpost)
    - Index 16: kingdom ID
    """

    command = "gdi"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    owner: PlayerOwnerInfo | None = Field(alias="O", default=None)
    raw_castle_list: dict = Field(alias="gcl", default_factory=dict)

    @property
    def player_id(self) -> int:
        """Get player ID from owner info."""
        return self.owner.player_id if self.owner else 0

    @property
    def player_name(self) -> str:
        """Get player name from owner info."""
        return self.owner.name if self.owner else ""

    @property
    def alliance_id(self) -> int:
        """Get alliance ID from owner info."""
        return self.owner.alliance_id if self.owner else 0

    @property
    def alliance_name(self) -> str:
        """Get alliance name from owner info."""
        return self.owner.alliance_name if self.owner else ""

    @property
    def has_bird(self) -> bool:
        """Check if player has revenge protection (bird) active."""
        return self.owner.has_bird if self.owner else False

    @property
    def bird_end_time(self) -> datetime | None:
        """When bird protection ends (UTC), or None."""
        return self.owner.bird_end_time if self.owner else None

    def get_castles(self) -> list[PlayerCastle]:
        """
        Parse gcl.C into a flat list of PlayerCastle objects.

        Returns:
            All castles/outposts/locations across all kingdoms.
        """
        castles = []
        worlds = self.raw_castle_list.get("C", [])

        for world in worlds:
            kingdom = world.get("KID", 0)
            locations = world.get("AI", [])

            for loc_wrapper in locations:
                location = loc_wrapper.get("AI", []) if isinstance(loc_wrapper, dict) else []
                if not location:
                    continue
                # Handle nested list (e.g. [[10, 127, ...]])
                if location and isinstance(location[0], list):
                    location = location[0]
                castles.append(PlayerCastle.from_list(location, kingdom=kingdom))

        return castles

    def get_location_captures(self) -> list[LocationCapture]:
        """
        Extract locations that are being captured.

        Returns:
            List of LocationCapture objects for locations with active captures.
        """
        captures = []
        for castle in self.get_castles():
            if castle.is_being_captured:
                try:
                    kingdom = Kingdom(castle.kingdom)
                except ValueError:
                    continue
                captures.append(
                    LocationCapture(
                        location_id=castle.location_id,
                        location_type=castle.castle_type,
                        location_type_name=castle.castle_type_name,
                        x=castle.x,
                        y=castle.y,
                        kingdom=kingdom,
                        capturer_id=castle.capturer_id,
                    )
                )
        return captures

    def get_all_captures_by_location(self) -> dict[int, int]:
        """
        Get a mapping of location_id -> capturer_id for all captures.

        Returns:
            Dict mapping location_id to the player_id who is capturing it.
        """
        return {cap.location_id: cap.capturer_id for cap in self.get_location_captures()}


__all__ = [
    "GetPlayerInfoRequest",
    "GetPlayerInfoResponse",
    "PlayerOwnerInfo",
    "PlayerCastle",
    "LocationCapture",
    "LOCATION_TYPES",
    "get_location_type_name",
    "SearchPlayerRequest",
    "SearchPlayerResponse",
    "SearchPlayerResult",
]


# =============================================================================
# WSP - World Search Player
# =============================================================================


class SearchPlayerRequest(BaseRequest):
    command = "wsp"

    player_name: str = Field(alias="PN")


class SearchPlayerResult(BaseResponse):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_id: int = Field(alias="OID", default=0)
    name: str = Field(alias="N", default="")
    level: int = Field(alias="L", default=0)
    alliance_id: int = Field(alias="AID", default=0)


class SearchPlayerResponse(BaseResponse):
    command = "wsp"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    raw_gaa: dict = Field(alias="gaa", default_factory=dict)

    def get_player(self) -> SearchPlayerResult | None:
        owner_info = self.raw_gaa.get("OI", [])
        if owner_info and len(owner_info) > 0:
            return SearchPlayerResult.model_validate(owner_info[0])
        return None
