"""
Player protocol models.

Commands:
- gdi: Get detailed player info (including castle list with capture info)
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse
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
# Player Owner Info
# =============================================================================


class PlayerOwnerInfo(BaseResponse):
    """
    Owner info from the gdi response's O object.

    Contains basic player information.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_id: int = Field(alias="OID", default=0)
    name: str = Field(alias="N", default="")
    alliance_id: int = Field(alias="AID", default=0)
    alliance_name: str = Field(alias="AN", default="")
    level: int = Field(alias="L", default=0)


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
        "O": {"OID": ..., "N": ..., "AN": ..., ...},
        "gcl": {"C": [{"KID": ..., "AI": [{"AI": [...]}]}]}
    }

    The gcl.C array contains castle/location info per kingdom.
    Each location has an AI array where:
    - Index 0: Location type (1=Castle, 3=Capital, 4=Outpost, 22=Metro)
    - Index 3: Location ID
    - Index 14: Capturer ID for Capital/Metro
    - Index 15: Capturer ID for Outpost
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

    def get_location_captures(self) -> list[LocationCapture]:
        """
        Extract locations that are being captured.

        Parses the gcl.C array to find locations with active captures.

        Returns:
            List of LocationCapture objects for locations being captured.
        """
        captures = []
        worlds = self.raw_castle_list.get("C", [])

        for world in worlds:
            try:
                kingdom = Kingdom(world.get("KID", 0))
            except ValueError:
                # Skip unknown kingdoms
                continue

            locations = world.get("AI", [])

            for loc_wrapper in locations:
                # Each location is wrapped: {"AI": [type, ?, ?, loc_id, ...]}
                location = loc_wrapper.get("AI", []) if isinstance(loc_wrapper, dict) else []
                if not location or len(location) < 4:
                    continue

                loc_type = location[0]
                loc_type_name = get_location_type_name(loc_type)

                # Only process capturable location types
                if loc_type_name not in ("Outpost", "Capital", "Metro"):
                    continue

                loc_id = location[3]

                # Capturer ID position depends on location type
                if loc_type_name == "Outpost":
                    capturer_id = location[15] if len(location) > 15 else -1
                else:  # Capital or Metro
                    capturer_id = location[14] if len(location) > 14 else -1

                # Only include if being captured
                if capturer_id != -1:
                    captures.append(
                        LocationCapture(
                            location_id=loc_id,
                            location_type=loc_type,
                            location_type_name=loc_type_name,
                            kingdom=kingdom,
                            capturer_id=capturer_id,
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
    "LocationCapture",
    "LOCATION_TYPES",
    "get_location_type_name",
]
