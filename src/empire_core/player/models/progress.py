"""
The player's progress, as the login data and its pushes send it.

Commands:
- rei: research
- boi: boosters, the premium account and production slots (bfs: the festival)
- gmu: might points
- ufa: glory points
- ufp: Berimond (faction) points
- uar: top-X title ranks, the island title and the displayed title systems
- vli: achievements
- gri: relocation

Each model is read once and never changes; the times in it count from ``received_at``.
"""

from __future__ import annotations

import math
import time
from typing import Annotated, Any

from pydantic import BeforeValidator, ConfigDict, Field, field_validator

from empire_core.enums import TitleSystem
from empire_core.protocol.base import BasePayload, BaseResponse, object_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals, js_number_or_none, js_parse_int

PERMANENT_BOOSTER_DURATION = 2147483647
"""``BoosterConst.PERMANENT_BOOSTER_DURATION`` (dll): a booster's ``RT`` when it never runs out"""


def _number(value: Any) -> int | float:
    # The client multiplies these by 1000; NaN ends up as no time left
    number = js_number_or_none(value)
    return 0 if number is None else number


def _numbers(value: Any) -> tuple[int | float, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(entry for entry in value if isinstance(entry, (int, float)) and not isinstance(entry, bool))


def _ints(value: Any) -> tuple[int, ...]:
    return tuple(entry for entry in _numbers(value) if isinstance(entry, int))


Seconds = Annotated[int | float, BeforeValidator(_number)]
Numbers = Annotated[tuple[int | float, ...], BeforeValidator(_numbers)]
Ints = Annotated[tuple[int, ...], BeforeValidator(_ints)]
ParsedInt = Annotated[int | None, BeforeValidator(js_parse_int)]


def _title_system(value: str) -> TitleSystem | None:
    try:
        return TitleSystem(value)
    except ValueError:
        return None


class _Read(BasePayload):
    model_config = ConfigDict(frozen=True)

    received_at: float = Field(
        default_factory=time.monotonic, description="When the values were read, in time.monotonic() seconds"
    )

    def _elapsed(self, now: float | None) -> float:
        return (time.monotonic() if now is None else now) - self.received_at


class _ReadResponse(BaseResponse, _Read):
    pass


class ResearchInfoResponse(_ReadResponse):
    """
    Your research: what is finished and what runs now.

    Command: rei, as a login section of ``gbd``, a push, and inside the ``res`` and ``msr`` replies.

    Client: ``CastleResearchData.parse_REI`` (bundle line 139330), ``remainingResearchTimeInSeconds``
    and ``isSomeResearchActive`` (bundle lines 139337-139338)
    """

    command = "rei"

    bought_research_ids: Ints = Field(alias="BR", default=(), description="Finished research ids")
    current_research_id: ClientInt = Field(alias="ARID", default=0, description="The research running now, -1 for none")
    research_seconds: Seconds = Field(
        alias="ARRT", default=0, description="Seconds left on the running research when the values were read"
    )

    def remaining_research_seconds(self, now: float | None = None) -> int:
        """Whole seconds left on the running research, 0 when none runs."""
        return js_int(max(self.research_seconds - self._elapsed(now), 0))

    def is_research_active(self, now: float | None = None) -> bool:
        """Whether a research runs: an id other than -1 with time left."""
        return self.current_research_id != -1 and self.remaining_research_seconds(now) > 0


class Booster(_Read):
    """
    One booster of a ``boi``'s ``BO`` list.

    Client: ``CastleHeroDefaultBoosterShopVO.parseServerInfo`` (bundle line 8677), ``remainingTimeInSeconds``
    and ``isActive`` (bundle lines 8678-8682); the subclasses that read ``B`` (bundle lines 90338, 90365,
    90670, 90864)
    """

    booster_id: ClientInt = Field(alias="ID", default=0, description="The booster's id")
    level: ClientInt = Field(alias="L", default=0, description="The booster's level")
    seconds: ClientInt = Field(
        alias="RT", default=0, description="Seconds left when the values were read; PERMANENT_BOOSTER_DURATION for ever"
    )
    purchase_count: int | float | None = Field(
        alias="PC", default=None, description="How many times in a row it was bought; None when not sent"
    )
    bonus_percent: ClientInt | None = Field(alias="B", default=None, description="Its bonus in percent, if it has one")

    @field_validator("purchase_count", mode="before")
    @classmethod
    def _count(cls, value: Any) -> Any:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @property
    def is_permanent(self) -> bool:
        """Whether the booster never runs out."""
        return self.seconds == PERMANENT_BOOSTER_DURATION

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds left, -1 at least; infinite for a permanent booster."""
        if self.is_permanent:
            return math.inf
        return max(-1.0, self.seconds - self._elapsed(now))

    def is_active(self, now: float | None = None) -> bool:
        """A permanent booster with a level, or one whose time has not run out."""
        return self.level > 0 if self.is_permanent else self.remaining_seconds(now) >= 0


class Festival(_Read):
    """
    The running festival: a ``boi``'s ``bfs``, or a ``bfs`` reply.

    Client: ``FestivalVO.fillFromParamObject`` and ``parseDuration`` (bundle lines 90214-90215)
    """

    festival_type: ClientInt = Field(alias="T", default=0, description="The festival's id, -1 for none")
    seconds: Seconds = Field(alias="RT", default=0, description="Seconds left when the values were read")

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds left, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now))

    def is_active(self, now: float | None = None) -> bool:
        """Whether the festival still runs."""
        return self.remaining_seconds(now) > 0


class BoosterInfoResponse(_ReadResponse):
    """
    Your boosters, premium account, production slots and festival.

    A ``boi`` lists only some boosters; the client keeps the others as they were, and
    ``client.state.get_boosts()`` does the same.

    Command: boi, as a login section of ``gbd``, a push, and inside the replies to buying a booster
    (``bcs``, ``bds``, ``bis``, ``bms``, ``brs``, ``ovs``, ``ups``, ``btx``).

    Client: ``CastlePremiumBoostData.parse_BOI`` (bundle line 15202), ``PremiumAccountVO.parseServerInfo``,
    ``isActive``, ``remainingTimeInSeconds`` and ``premiumAccountType`` (bundle lines 90230-90234),
    ``parse_bfs`` (bundle line 15218)
    """

    command = "boi"

    boosters: tuple[Booster, ...] = Field(alias="BO", default=(), description="The boosters this packet lists")
    premium_seconds: Seconds = Field(
        alias="PA", default=0, description="Seconds of premium account left when the values were read"
    )
    premium_type: Any = Field(alias="PT", default=-1, description="The premium account's type, -1 for none")
    unit_slots: Numbers = Field(
        alias="SU", default=(), description="Unit production slots: above 0 bought, below 0 permanent"
    )
    tool_slots: Numbers = Field(
        alias="ST", default=(), description="Tool production slots: above 0 bought, below 0 permanent"
    )
    festival: Festival | None = Field(alias="bfs", default=None, description="The festival; None when not sent")

    @field_validator("boosters", mode="before")
    @classmethod
    def _boosters(cls, value: Any) -> Any:
        return tuple(readable_list(Booster, value, accept=lambda entry: isinstance(entry, dict)))

    @field_validator("festival", mode="before")
    @classmethod
    def _festival(cls, value: Any) -> Any:
        return object_or_none(value)

    def premium_remaining_seconds(self, now: float | None = None) -> float:
        """Seconds of premium account left, 0 when it is not active."""
        return max(0.0, self.premium_seconds - self._elapsed(now))

    def is_premium_active(self, now: float | None = None) -> bool:
        """Whether the premium account runs."""
        return self.premium_remaining_seconds(now) > 0

    def premium_account_type(self, now: float | None = None) -> Any:
        """The premium account's type while it runs, else -1."""
        return self.premium_type if self.is_premium_active(now) else -1

    @property
    def bought_unit_slots(self) -> int:
        """Unit production slots bought."""
        return sum(1 for slot in self.unit_slots if slot > 0)

    @property
    def permanent_unit_slots(self) -> int:
        """Permanent unit production slots."""
        return sum(1 for slot in self.unit_slots if slot < 0)

    @property
    def bought_tool_slots(self) -> int:
        """Tool production slots bought."""
        return sum(1 for slot in self.tool_slots if slot > 0)

    @property
    def permanent_tool_slots(self) -> int:
        """Permanent tool production slots."""
        return sum(1 for slot in self.tool_slots if slot < 0)

    def booster(self, booster_id: int) -> Booster | None:
        """One booster, None when it is not listed."""
        return next((booster for booster in self.boosters if booster.booster_id == booster_id), None)


class MightPointsResponse(_ReadResponse):
    """
    Your might points.

    Command: gmu, as a login section of ``gbd`` and a push. The client reads one only
    when it has both ``MP`` and ``HMP``.

    Client: ``MightData.parse_GMU`` (bundle line 113517)
    """

    command = "gmu"

    might_points: ParsedInt = Field(alias="MP", default=None, description="Might points; None when unreadable")
    building_might: ParsedInt = Field(
        alias="TSBM", default=None, description="Might points from buildings; None when unreadable"
    )
    highest_might_points: ParsedInt = Field(
        alias="HMP", default=None, description="The most might points ever reached; None when unreadable"
    )


class GloryPointsResponse(_ReadResponse):
    """
    Your glory points, which give the glory titles.

    Command: ufa, as a login section of ``gbd`` and a push.

    Client: ``CastleTitleData.parseUFA`` (bundle line 21038), which ``parseInt``\\ s a string and keeps a number
    """

    command = "ufa"

    glory_points: int | float | None = Field(alias="CF", default=None, description="Glory points")
    highest_glory_points: int | float | None = Field(alias="HF", default=None, description="The most glory points ever")

    @field_validator("glory_points", "highest_glory_points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> Any:
        if isinstance(value, str):
            return js_parse_int(value)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class FactionPointsResponse(_ReadResponse):
    """
    Your Berimond (faction) points, which give the Berimond titles.

    Command: ufp, a push. The client ignores the copy in ``gbd``.

    Client: ``UFPCommand`` (bundle line 121010), ``CastleTitleData.parseUFP`` (bundle line 21039)
    """

    command = "ufp"

    faction_points: ParsedInt = Field(alias="CFP", default=None, description="Berimond points; None when unreadable")
    highest_faction_points: ParsedInt = Field(
        alias="HFP", default=None, description="The most Berimond points ever; None when unreadable"
    )


class TopTitleRanking(_Read):
    """
    One title system's top-X standing: a ``uar``'s ``FTM`` (glory) or ``BTM`` (Berimond).

    Client: ``CastleTitleData.parseUAR`` (bundle line 21022)
    """

    top_rank: ClientInt = Field(
        alias="CTXT", default=0, description="Your rank for the system's top-X titles, -1 or 0 for none"
    )
    reset_seconds: Seconds = Field(alias="RS", default=0, description="Seconds until the top-X titles reset")
    thresholds: tuple[int, ...] = Field(
        alias="NTFP", default=(), description="The points the top-X titles need, highest title first"
    )
    top_player_id: Any = Field(alias="TOID", default=None, description="The player holding the system's top title")

    @field_validator("thresholds", mode="before")
    @classmethod
    def _thresholds(cls, value: Any) -> Any:
        return tuple(js_int(entry) for entry in value) if isinstance(value, list) else ()


class IslandTitle(BasePayload):
    """A ``uar``'s ``ITM``. Client: ``CastleTitleData.parseIslandDataFromServer`` (bundle line 21023)"""

    model_config = ConfigDict(frozen=True)

    title_id: Any = Field(alias="TID", default=-1, description="Your Storm Islands title, -1 for none")

    @property
    def held_title_id(self) -> int:
        """The title id when it is above -1, else -1."""
        tid = self.title_id
        return tid if isinstance(tid, int) and not isinstance(tid, bool) and tid > -1 else -1


class AllianceCityTitle(BasePayload):
    """A ``uar``'s ``ATM``. Client: ``CastleTitleData.parseAllianceCityDataFromServer`` (bundle line 21026)"""

    model_config = ConfigDict(frozen=True)

    title_id: Any = Field(alias="TID", default=None, description="The alliance city title")
    player_id: Any = Field(alias="PID", default=None, description="The player holding it")


class TitleRanksResponse(_ReadResponse):
    """
    Your top-X title ranks, Storm Islands title and the title systems your name shows.

    Command: uar, as a login section of ``gbd`` and a push.

    Client: ``CastleTitleData.parseUAR`` (bundle line 21022)
    """

    command = "uar"

    glory: TopTitleRanking = Field(alias="FTM", default_factory=TopTitleRanking, description="The glory system")
    faction: TopTitleRanking = Field(alias="BTM", default_factory=TopTitleRanking, description="The Berimond system")
    island_title: IslandTitle = Field(alias="ITM", default_factory=IslandTitle, description="Your Storm Islands title")
    alliance_city_title: AllianceCityTitle | None = Field(
        alias="ATM", default=None, description="The alliance city title; None when not sent"
    )
    prefix_system: Any = Field(alias="PFX", default=None, description="The title system shown before your name")
    suffix_system: Any = Field(alias="SFX", default=None, description="The title system shown after your name")

    @field_validator("glory", "faction", "island_title", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, BasePayload)) else {}

    @field_validator("alliance_city_title", mode="before")
    @classmethod
    def _city(cls, value: Any) -> Any:
        return object_or_none(value)

    @property
    def prefix_title_system(self) -> TitleSystem | None:
        """``prefix_system`` as a :class:`TitleSystem`, None for any other value."""
        return _title_system(self.prefix_system) if isinstance(self.prefix_system, str) else None

    @property
    def suffix_title_system(self) -> TitleSystem | None:
        """``suffix_system`` as a :class:`TitleSystem`, None for any other value."""
        return _title_system(self.suffix_system) if isinstance(self.suffix_system, str) else None


class AchievementProgress(BasePayload):
    """
    One achievement's progress, an entry of a ``vli``'s ``RA``.

    Client: ``CastleAchievementData.parse_RA`` (bundle line 29838), ``AchievementVO.setProgress`` (bundle line 92889)
    """

    model_config = ConfigDict(frozen=True)

    achievement_id: ClientInt = Field(alias="AID", default=0, description="The achievement's id")
    progress: Numbers = Field(
        alias="P", default=(), description="Progress per condition, in condition order; -1 for a condition done"
    )


class AchievementsResponse(_ReadResponse):
    """
    Your achievement points, finished achievements and progress.

    A ``vli`` adds to what the client knows: finished achievements stay finished, and an
    achievement it does not list keeps its progress. ``client.state.get_achievements()`` does the same.

    Command: vli, as a login section of ``gbd`` and a push.

    Client: ``CastleAchievementData.parse_vli``, ``parse_RA`` and ``parse_FA`` (bundle lines 29837-29842)
    """

    command = "vli"

    achievement_points: ClientInt = Field(alias="AVP", default=0, description="Achievement points")
    finished_achievement_ids: Ints = Field(alias="FA", default=(), description="Finished achievements")
    progress: tuple[AchievementProgress, ...] = Field(
        alias="RA", default=(), description="Progress of the achievements this packet lists"
    )

    @field_validator("progress", mode="before")
    @classmethod
    def _progress(cls, value: Any) -> Any:
        return tuple(readable_list(AchievementProgress, value, accept=lambda entry: isinstance(entry, dict)))


class RelocationInfoResponse(_ReadResponse):
    """
    Your castle relocations: how many, the one running and the cooldown.

    Command: gri, as a login section of ``gbd`` and a push.

    Client: ``CastleUserData.parse_GRI`` (bundle line 9910), ``remainingRelocationDuration`` and
    ``remainingRelocationCooldown``
    """

    command = "gri"

    relocation_count: ClientInt = Field(alias="RLC", default=0, description="Relocations made")
    relocation_seconds: Seconds = Field(
        alias="RD", default=0, description="Seconds left on the running relocation when the values were read"
    )
    relocation_mode: Any = Field(
        alias="JM", default=None, description="The relocation's mode; its time counts only while this is 0"
    )
    cooldown_seconds: Seconds = Field(
        alias="RMC", default=0, description="Seconds until you may relocate again, when the values were read"
    )
    destination_x: ClientInt = Field(alias="DX", default=0, description="The relocation's destination X")
    destination_y: ClientInt = Field(alias="DY", default=0, description="The relocation's destination Y")

    def remaining_relocation_seconds(self, now: float | None = None) -> float:
        """Seconds left on the running relocation, 0 when none runs."""
        if not js_loose_equals(self.relocation_mode, 0):
            return 0
        return max(0.0, self.relocation_seconds - self._elapsed(now))

    def remaining_cooldown_seconds(self, now: float | None = None) -> float:
        """Seconds until you may relocate again, 0 at least."""
        return max(0.0, self.cooldown_seconds - self._elapsed(now))


__all__ = [
    "PERMANENT_BOOSTER_DURATION",
    "AchievementProgress",
    "AchievementsResponse",
    "AllianceCityTitle",
    "Booster",
    "BoosterInfoResponse",
    "FactionPointsResponse",
    "Festival",
    "GloryPointsResponse",
    "IslandTitle",
    "MightPointsResponse",
    "RelocationInfoResponse",
    "ResearchInfoResponse",
    "TitleRanksResponse",
    "TopTitleRanking",
]
