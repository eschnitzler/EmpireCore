"""
The owner record both the alliance member list and the gdi player info send.

AllianceMember (ain, alliance.models.info) and PlayerOwnerInfo (gdi,
player.models.info) subclass PlayerProfileBase.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.enums import AllianceRank
from empire_core.map.models.areas import AllianceEmblem
from empire_core.map.models.owners import OwnerCastlePosition, OwnerCrest, OwnerFaction, owner_positions
from empire_core.protocol.base import BasePayload, enum_or_none, object_or_none
from empire_core.protocol.js import ParseInt, js_loose_equals, js_parse_int, js_parse_int_or_zero, js_truthy


class PlayerProfileBase(BasePayload):
    """
    A player's owner record.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794),
    which both the ain member list and the gdi owner go through
    (``CastleOtherPlayerData.parseOwnerInfo``, bundle line 138996);
    ``WorldMapOwnerInfoVO.parsePosList`` (bundle line 10795) for ``AP`` and ``VP``.

    The protection times count from ``received_at``, as the client counts them from the ``CachedTimer``
    reading ``parseOwnerInfo`` takes (bundle line 138997).
    ``received_at_wall`` is stamped with it, for the ``*_utc`` ends: the wall clock at reading.
    """

    player_id: ParseInt = Field(alias="OID", default=0, description="Player id")
    name: str = Field(alias="N", default="", description="Player name")
    emblem: OwnerCrest | None = Field(alias="E", default=None, description="The player's crest")
    level: ParseInt = Field(alias="L", default=0, description="Level")
    legendary_level: ParseInt = Field(alias="LL", default=0, description="Legendary level")
    beginner_protection_seconds: ParseInt = Field(
        alias="RNP", default=0, description="Seconds of beginner protection left"
    )
    honor: ParseInt = Field(alias="H", default=0, description="Honor points")
    might: ParseInt = Field(alias="MP", default=0, description="Might points")
    top_ranking: ParseInt = Field(alias="TOPX", default=-1, description="Top ranking place")
    is_ruin: bool = Field(alias="R", default=False, description="The player's castle is a ruin")
    alliance_id: int = Field(alias="AID", default=-1, description="Alliance id; -1 when the player is in none")
    alliance_rank: int | None = Field(
        alias="AR", default=None, description="Rank in the alliance, an AllianceRank value; None when unreadable"
    )
    alliance_name: str = Field(alias="AN", default="", description="Alliance name")
    is_searching_alliance: bool = Field(alias="SA", default=False, description="The player is looking for an alliance")
    revenge_protection_seconds: ParseInt = Field(alias="RPT", default=0, description="Seconds of peace protection left")
    castle_positions: list[OwnerCastlePosition] = Field(alias="AP", default_factory=list, description="Castles")
    village_positions: list[OwnerCastlePosition] = Field(alias="VP", default_factory=list, description="Villages")
    has_premium_flag: bool = Field(alias="PF", default=False, description="The player has the premium flag")
    has_vip_flag: bool = Field(alias="VF", default=False, description="The player has the VIP flag")
    is_dummy: bool = Field(alias="DUM", default=False, description="A placeholder record, not a real player")
    achievement_points: ParseInt = Field(alias="AVP", default=0, description="Achievement points")
    relocation_remaining_seconds: int = Field(
        alias="RRD", default=0, description="Seconds until the player's castle relocation ends"
    )
    faction: OwnerFaction | None = Field(alias="FN", default=None, description="Faction event standing")
    alliance_emblem: AllianceEmblem | None = Field(
        alias="aee", default=None, description="The alliance's crest; None outside an alliance"
    )
    title_suffix: int | None = Field(alias="SUF", default=None, description="Suffix title id; None when unsent")
    title_prefix: int | None = Field(alias="PRE", default=None, description="Prefix title id; None when unsent")
    via_refer_a_friend: bool = Field(alias="IRF", default=False, description="The player joined through a referral")
    received_at: float = Field(
        default_factory=time.monotonic, description="When the values were read, in time.monotonic() seconds"
    )
    received_at_wall: float = Field(
        default_factory=time.time, description="When the values were read, in time.time() seconds"
    )

    @field_validator("name", "alliance_name", mode="before")
    @classmethod
    def _text_or_empty(cls, value: Any) -> Any:
        # AN reads as "" unless truthy; N is kept as sent
        return value if isinstance(value, str) else ""

    @field_validator("alliance_rank", mode="before")
    @classmethod
    def _rank(cls, value: Any) -> int | None:
        # parseInt; NaN equals no rank
        return js_parse_int(value)

    @field_validator("alliance_id", mode="before")
    @classmethod
    def _alliance_id(cls, value: Any) -> int:
        # parseInt; NaN, like -1, fails isInAlliance's >= 0
        parsed = js_parse_int(value)
        return -1 if parsed is None else parsed

    @field_validator("is_ruin", mode="before")
    @classmethod
    def _ruin(cls, value: Any) -> bool:
        return js_parse_int(value) == 1

    @field_validator("via_refer_a_friend", mode="before")
    @classmethod
    def _referral(cls, value: Any) -> bool:
        return js_parse_int(value) not in (None, 0)

    @field_validator("is_searching_alliance", "has_premium_flag", "has_vip_flag", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator("is_dummy", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("relocation_remaining_seconds", mode="before")
    @classmethod
    def _relocation(cls, value: Any) -> int:
        return max(0, js_parse_int_or_zero(value))

    @field_validator("emblem", "faction", "alliance_emblem", mode="before")
    @classmethod
    def _block_needs_an_object(cls, value: Any) -> Any:
        # The client only reads keys off these; E and FN are also read only when truthy
        return object_or_none(value)

    @field_validator("title_suffix", "title_prefix", mode="before")
    @classmethod
    def _title_id(cls, value: Any) -> Any:
        return js_parse_int(value)

    @field_validator("castle_positions", "village_positions", mode="before")
    @classmethod
    def _position_rows(cls, value: Any) -> Any:
        return owner_positions(value)

    @model_validator(mode="after")
    def _alliance_crest_only_in_an_alliance(self) -> PlayerProfileBase:
        # fillFromParamObject reads aee.ACCA only for a player in an alliance
        if not self.is_in_alliance or (self.alliance_emblem is not None and self.alliance_emblem.crest is None):
            self.alliance_emblem = None
        return self

    @property
    def is_in_alliance(self) -> bool:
        """
        Whether the player is in an alliance.

        Client: ``WorldMapOwnerInfoVO.isInAlliance`` (bundle line 10834)
        """
        return self.alliance_id >= 0

    @property
    def alliance_rank_enum(self) -> AllianceRank | None:
        """``alliance_rank`` as an :class:`AllianceRank`, None for a value the client does not define."""
        return None if self.alliance_rank is None else enum_or_none(AllianceRank, self.alliance_rank)

    @property
    def is_leader(self) -> bool:
        """
        Whether the player leads their alliance: rank 0.

        Client: ``AllianceInfoVO.allianceLeader`` (bundle line 25986) is the member whose ``allianceRank`` is 0
        """
        return self.is_in_alliance and self.alliance_rank == AllianceRank.LEADER

    @property
    def is_officer(self) -> bool:
        """Whether the player holds a rank between leader and member."""
        rank = self.alliance_rank
        return self.is_in_alliance and rank is not None and AllianceRank.LEADER < rank < AllianceRank.MEMBER

    @property
    def has_bird(self) -> bool:
        """
        Whether the player has peace protection left now; False once it has run out.

        Client: ``WorldMapOwnerInfoVO.isPeaceProtected`` (bundle line 10808)
        """
        return self.remaining_revenge_protection_seconds() > 0

    @property
    def has_beginner_protection(self) -> bool:
        """
        Whether the player has beginner protection left now; False once it has run out.

        Client: ``WorldMapOwnerInfoVO.isNoobProtected`` (bundle line 10806)
        """
        return self.remaining_beginner_protection_seconds() > 0

    @property
    def revenge_protection_end(self) -> float | None:
        """When peace protection ends, in time.monotonic() seconds; None without protection."""
        return self.received_at + self.revenge_protection_seconds if self.revenge_protection_seconds > 0 else None

    @property
    def beginner_protection_end(self) -> float | None:
        """When beginner protection ends, in time.monotonic() seconds; None without protection."""
        return self.received_at + self.beginner_protection_seconds if self.beginner_protection_seconds > 0 else None

    def revenge_protection_end_utc(self) -> datetime | None:
        """When peace protection ends, as a UTC datetime; None without protection.

        Counted from ``received_at_wall``, not from now, so it stays the same
        for the same record.
        """
        return self._utc_end(self.revenge_protection_seconds)

    def beginner_protection_end_utc(self) -> datetime | None:
        """When beginner protection ends, as a UTC datetime; None without protection.

        Counted from ``received_at_wall``, not from now, so it stays the same
        for the same record.
        """
        return self._utc_end(self.beginner_protection_seconds)

    def _utc_end(self, seconds: int) -> datetime | None:
        return datetime.fromtimestamp(self.received_at_wall + seconds, timezone.utc) if seconds > 0 else None

    def remaining_revenge_protection_seconds(self, now: float | None = None) -> float:
        """
        Seconds of peace protection left, 0 when none.

        Client: ``WorldMapOwnerInfoVO.remainingPeaceTime`` (bundle line 10804), counted from the
        ``CachedTimer`` reading ``fillFromParamObject`` keeps (bundle line 10794)
        """
        return self._left(self.revenge_protection_end, now)

    def remaining_beginner_protection_seconds(self, now: float | None = None) -> float:
        """
        Seconds of beginner protection left, 0 when none.

        Client: ``WorldMapOwnerInfoVO.remainingNoobTime`` (bundle line 10802), counted from the
        ``CachedTimer`` reading ``fillFromParamObject`` keeps (bundle line 10794)
        """
        return self._left(self.beginner_protection_end, now)

    @staticmethod
    def _left(end: float | None, now: float | None) -> float:
        return 0.0 if end is None else max(end - (time.monotonic() if now is None else now), 0.0)


__all__ = ["PlayerProfileBase"]
