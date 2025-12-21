"""
Models for quests and achievements.
"""

from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field


class Quest(BaseModel):
    """Represents a game quest."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    QID: int = Field(default=-1)  # Quest ID
    P: List[int] = Field(default_factory=list)  # Progress

    @property
    def quest_id(self) -> int:
        return self.QID

    @property
    def progress(self) -> List[int]:
        return self.P


class QuestReward(BaseModel):
    """Quest reward."""

    model_config = ConfigDict(extra="ignore")

    type: str  # "U" for units, "F" for food, etc.
    value: Any  # Depends on type


class DailyQuest(BaseModel):
    """Daily quest with progress and rewards."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    PQL: int = Field(default=0)  # Player Quest Level?
    RDQ: List[Quest] = Field(default_factory=list)  # Running Daily Quests
    FDQ: List[int] = Field(default_factory=list)  # Finished Daily Quests
    RS: List[List[Any]] = Field(default_factory=list)  # Rewards

    @property
    def level(self) -> int:
        return self.PQL

    @property
    def active_quests(self) -> List[Quest]:
        return self.RDQ

    @property
    def finished_quests(self) -> List[int]:
        return self.FDQ

    @property
    def rewards(self) -> List[List[Any]]:
        return self.RS
