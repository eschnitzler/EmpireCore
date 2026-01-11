"""
Search protocol models for GGE.

Commands:
- hgh: Search/highscore command for players and alliances
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import BaseRequest, BaseResponse, GGECommand


class SearchType:
    """Search types for hgh command."""

    ALLIANCE = 11  # Search alliances by name


class SearchListType:
    """List types for search results."""

    ALLIANCE_RESULTS = 6  # Alliance search results


class AllianceSearchResult:
    """A single alliance from search results."""

    def __init__(self, raw: list) -> None:
        """
        Parse alliance from raw array.

        Array format: [alliance_id, name, member_count, leader_id, leader_name, ?, ?, emblem_id?]
        """
        self.alliance_id: int = raw[0] if len(raw) > 0 else 0
        self.name: str = raw[1] if len(raw) > 1 else ""
        self.member_count: int = raw[2] if len(raw) > 2 else 0
        self.leader_id: int = raw[3] if len(raw) > 3 else 0
        self.leader_name: str = raw[4] if len(raw) > 4 else ""

    def __repr__(self) -> str:
        return f"AllianceSearchResult(id={self.alliance_id}, name='{self.name}', members={self.member_count})"


class SearchAllianceRequest(BaseRequest):
    """
    Search for alliances by name.

    Command: hgh
    """

    command: ClassVar[str] = GGECommand.HGH

    search_type: int = Field(default=SearchType.ALLIANCE, alias="LT")
    list_type: int = Field(default=SearchListType.ALLIANCE_RESULTS, alias="LID")
    search_value: str = Field(alias="SV")

    @classmethod
    def create(cls, search_term: str) -> "SearchAllianceRequest":
        """Create an alliance search request."""
        return cls(SV=search_term)


class SearchAllianceResponse(BaseResponse):
    """
    Response containing alliance search results.

    Command: hgh
    """

    command: ClassVar[str] = GGECommand.HGH

    # Raw list data from response
    L: list = Field(default_factory=list)

    @property
    def results(self) -> list[AllianceSearchResult]:
        """Parse and return alliance search results."""
        results = []
        for raw in self.L:
            if isinstance(raw, list) and len(raw) >= 3 and isinstance(raw[2], list):
                # Format: [rank, score, [alliance_id, name, member_count, ...]]
                results.append(AllianceSearchResult(raw[2]))
            elif isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[1], list):
                # Format: [score, [alliance_id, name, member_count, ...]]
                results.append(AllianceSearchResult(raw[1]))
            elif isinstance(raw, list):
                # Fallback: direct format [alliance_id, name, member_count, ...]
                results.append(AllianceSearchResult(raw))
        return results

    @property
    def count(self) -> int:
        """Number of results found."""
        return len(self.L)


__all__ = [
    "SearchType",
    "SearchListType",
    "AllianceSearchResult",
    "SearchAllianceRequest",
    "SearchAllianceResponse",
]
