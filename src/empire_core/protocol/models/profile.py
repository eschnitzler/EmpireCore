"""
Shared player profile payload fields.

Both the alliance member list (ain response, alliance.py) and the detailed
player info owner object (gdi response, player.py) return the same ~20-field
player profile structure. PlayerProfileBase holds the common fields and
derived properties; AllianceMember and PlayerOwnerInfo subclass it and only
declare their genuinely divergent fields locally.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from pydantic import Field

from .base import BasePayload

if TYPE_CHECKING:
    from .alliance import MemberCastle


class PlayerProfileBase(BasePayload):
    """
    Common player profile fields shared by AllianceMember and PlayerOwnerInfo.

    Server field mapping:
    - OID: Player/Object ID
    - N: Player Name
    - L: Level
    - LL: Legendary Level
    - H: Honor (or unknown metric)
    - AR: Alliance Rank (0=member, 8=leader, etc.)
    - CF: Castle count (main castles)
    - HF: Total castles including outposts
    - MP: Might/Power points
    - DUM: Is dummy/inactive account
    - AVP: Avatar points
    - PRE: Title prefix
    - SUF: Title suffix
    - TOPX: Top ranking (-1 if unranked)
    - SA: Special ability/status
    - VF: VIP flag
    - PF: Premium flag
    - RRD: Resource request date
    - TI: Title index
    - RPT: Revenge protection time remaining (seconds) — bird
    - AID: Alliance ID
    - AN: Alliance Name
    - AP: Castle positions [[kingdom, area_id, x, y, castle_type], ...]
    - VP: Village positions

    The "E" alias (emblem) is declared on the subclasses because its type
    differs between them.
    """

    player_id: int = Field(alias="OID", default=0)
    name: str = Field(alias="N", default="")
    level: int = Field(alias="L", default=0)
    legendary_level: int = Field(alias="LL", default=0)
    h_field: int = Field(alias="H", default=0)  # Unknown metric, NOT online status
    alliance_rank: int = Field(alias="AR", default=0)
    castle_count: int = Field(alias="CF", default=0)
    total_castles: int = Field(alias="HF", default=0)
    might: int = Field(alias="MP", default=0)
    is_dummy: bool = Field(alias="DUM", default=False)
    avatar_points: int = Field(alias="AVP", default=0)
    title_prefix: int = Field(alias="PRE", default=0)
    title_suffix: int = Field(alias="SUF", default=-1)
    top_ranking: int = Field(alias="TOPX", default=-1)
    alliance_id: int = Field(alias="AID", default=0)
    alliance_name: str = Field(alias="AN", default="")
    special_ability: int = Field(alias="SA", default=0)
    vip_flag: int = Field(alias="VF", default=0)
    premium_flag: int = Field(alias="PF", default=0)
    resource_request_date: int = Field(alias="RRD", default=0)
    title_index: int = Field(alias="TI", default=-1)
    revenge_protection_seconds: int = Field(alias="RPT", default=0)

    # Castle positions (raw - can be parsed with MemberCastle.from_list)
    castle_positions: list = Field(alias="AP", default_factory=list)
    village_positions: list = Field(alias="VP", default_factory=list)

    @property
    def honor(self) -> int:
        """Get the player's honor points (H field)."""
        return self.h_field

    @property
    def castles(self) -> list["MemberCastle"]:
        """Parse castle positions into MemberCastle objects."""
        # Imported here to avoid a circular import (alliance.py imports this module)
        from .alliance import MemberCastle

        return [MemberCastle.from_list(pos) for pos in self.castle_positions]

    @property
    def is_leader(self) -> bool:
        """Check if the player is alliance leader (AR=8)."""
        return self.alliance_rank == 8

    @property
    def is_officer(self) -> bool:
        """Check if the player is an officer (AR > 0 and < 8)."""
        return 0 < self.alliance_rank < 8

    @property
    def has_bird(self) -> bool:
        """Check if the player has revenge protection (bird) active."""
        return self.revenge_protection_seconds > 0

    @property
    def bird_end_time(self) -> datetime | None:
        """
        Calculate when bird protection ends.

        Returns:
            Timezone-aware datetime (UTC) when bird expires, or None if no bird active.

        Note:
            This is calculated relative to when the data was fetched,
            so it should be used soon after fetching.
        """
        if self.revenge_protection_seconds <= 0:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=self.revenge_protection_seconds)


__all__ = ["PlayerProfileBase"]
