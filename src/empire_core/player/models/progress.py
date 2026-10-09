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
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, Field, field_validator

from empire_core.enums import PremiumAccountType, TitleSystem
from empire_core.gamedata import EnumOrInt, EnumOrStr
from empire_core.protocol.base import BasePayload, TimedPayload, TimedResponse, object_or_none, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_loose_equals, js_parse_int

if TYPE_CHECKING:
    from empire_core.gamedata import Achievement, Research, Title

PERMANENT_BOOSTER_DURATION = 2147483647
"""``BoosterConst.PERMANENT_BOOSTER_DURATION`` (dll): a booster's ``RT`` when it never runs out"""


def _numbers(value: Any) -> tuple[int | float, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(entry for entry in value if isinstance(entry, (int, float)) and not isinstance(entry, bool))


def _ints(value: Any) -> tuple[int, ...]:
    return tuple(entry for entry in _numbers(value) if isinstance(entry, int))


Numbers = Annotated[tuple[int | float, ...], BeforeValidator(_numbers)]
Ints = Annotated[tuple[int, ...], BeforeValidator(_ints)]
ParsedInt = Annotated[int | None, BeforeValidator(js_parse_int)]


class ResearchInfoResponse(TimedResponse):
    """
    Your research: what is finished and what runs now.

    Command: rei, as a login section of ``gbd``, a push, and inside the ``res`` and ``msr`` replies.

    Client: ``CastleResearchData.parse_REI`` (bundle line 139330), ``remainingResearchTimeInSeconds``
    and ``isSomeResearchActive`` (bundle lines 139337-139338)
    """

    command = "rei"

    bought_research_ids: Annotated[tuple[EnumOrInt["Research"], ...], BeforeValidator(_ints)] = Field(
        validation_alias="BR", serialization_alias="BR", default=(), description="Finished researches"
    )
    current_research_id: ClientInt = Field(
        validation_alias="ARID",
        serialization_alias="ARID",
        default=0,
        description="The research running now, -1 for none",
    )
    research_seconds: ClientNumber = Field(
        validation_alias="ARRT",
        serialization_alias="ARRT",
        default=0,
        description="Seconds left on the running research when the values were read",
    )

    def remaining_research_seconds(self, now: float | None = None) -> int:
        """Whole seconds left on the running research, 0 when none runs."""
        return js_int(max(self.research_seconds - self._elapsed(now), 0))

    def is_research_active(self, now: float | None = None) -> bool:
        """Whether a research runs: an id other than -1 with time left."""
        return self.current_research_id != -1 and self.remaining_research_seconds(now) > 0


class Booster(TimedPayload):
    """
    One booster of a ``boi``'s ``BO`` list.

    Client: ``CastleHeroDefaultBoosterShopVO.parseServerInfo`` (bundle line 8677), ``remainingTimeInSeconds``
    and ``isActive`` (bundle lines 8678-8682); the subclasses that read ``B`` (bundle lines 90338, 90365,
    90670, 90864)
    """

    booster_id: ClientInt = Field(
        validation_alias="ID", serialization_alias="ID", default=0, description="The booster's id"
    )
    level: ClientInt = Field(
        validation_alias="L", serialization_alias="L", default=0, description="The booster's level"
    )
    seconds: ClientInt = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=0,
        description="Seconds left when the values were read; PERMANENT_BOOSTER_DURATION for ever",
    )
    purchase_count: int | float | None = Field(
        validation_alias="PC",
        serialization_alias="PC",
        default=None,
        description="How many times in a row it was bought; None when not sent",
    )
    bonus_percent: ClientInt | None = Field(
        validation_alias="B", serialization_alias="B", default=None, description="Its bonus in percent, if it has one"
    )

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


class Festival(TimedPayload):
    """
    The running festival: a ``boi``'s ``bfs``, or a ``bfs`` reply.

    Client: ``FestivalVO.fillFromParamObject`` and ``parseDuration`` (bundle lines 90214-90215)
    """

    festival_type: ClientInt = Field(
        validation_alias="T", serialization_alias="T", default=0, description="The festival's id, -1 for none"
    )
    seconds: ClientNumber = Field(
        validation_alias="RT", serialization_alias="RT", default=0, description="Seconds left when the values were read"
    )

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds left, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now))

    def is_active(self, now: float | None = None) -> bool:
        """Whether the festival still runs."""
        return self.remaining_seconds(now) > 0


class BoosterInfoResponse(TimedResponse):
    """
    Your boosters, premium account, production slots and festival.

    A ``boi`` lists only some boosters; the client keeps the others as they were, and
    ``client.state.get_boosts()`` does the same.

    Command: boi, as a login section of ``gbd``, a push, and inside the replies to buying a booster
    (``bcs``, ``bds``, ``bis``, ``bms``, ``brs``, ``ovs``, ``ups``, ``btx``).

    Client: ``CastlePremiumBoostData.parse_BOI`` (bundle line 15202), ``PremiumAccountVO.parseServerInfo``,
    ``isActive``, ``remainingTimeInSeconds`` and ``premiumAccountType`` (bundle lines 90230-90235),
    ``parse_bfs`` (bundle line 15218)
    """

    command = "boi"

    boosters: tuple[Booster, ...] = Field(
        validation_alias="BO", serialization_alias="BO", default=(), description="The boosters this packet lists"
    )
    premium_seconds: ClientNumber = Field(
        validation_alias="PA",
        serialization_alias="PA",
        default=0,
        description="Seconds of premium account left when the values were read",
    )
    premium_type: EnumOrInt[PremiumAccountType] | None = Field(
        validation_alias="PT",
        serialization_alias="PT",
        default=None,
        description="The premium account's type; None when the packet names none",
    )
    unit_slots: Numbers = Field(
        validation_alias="SU",
        serialization_alias="SU",
        default=(),
        description="Unit production slots: above 0 bought, below 0 permanent",
    )
    tool_slots: Numbers = Field(
        validation_alias="ST",
        serialization_alias="ST",
        default=(),
        description="Tool production slots: above 0 bought, below 0 permanent",
    )
    festival: Festival | None = Field(
        validation_alias="bfs", serialization_alias="bfs", default=None, description="The festival; None when not sent"
    )

    @field_validator("boosters", mode="before")
    @classmethod
    def _boosters(cls, value: Any) -> Any:
        return tuple(readable_list(Booster, value, accept=lambda entry: isinstance(entry, dict)))

    @field_validator("festival", mode="before")
    @classmethod
    def _festival(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("premium_type", mode="before")
    @classmethod
    def _premium_type(cls, value: Any) -> Any:
        # PremiumAccountVO starts at _accountType=-1, which names no account (bundle line 90229)
        return None if value is None or js_loose_equals(value, -1) else value

    def premium_remaining_seconds(self, now: float | None = None) -> float:
        """Seconds of premium account left, 0 when it is not active."""
        return max(0.0, self.premium_seconds - self._elapsed(now))

    def is_premium_active(self, now: float | None = None) -> bool:
        """Whether the premium account runs."""
        return self.premium_remaining_seconds(now) > 0

    def premium_account_type(self, now: float | None = None) -> PremiumAccountType | int | None:
        """The premium account's type while it runs, else None."""
        return self.premium_type if self.is_premium_active(now) else None

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


class MightPointsResponse(TimedResponse):
    """
    Your might points.

    Command: gmu, as a login section of ``gbd`` and a push. The client reads one only
    when it has both ``MP`` and ``HMP``.

    Client: ``MightData.parse_GMU`` (bundle line 113517)
    """

    command = "gmu"

    might_points: ParsedInt = Field(
        validation_alias="MP", serialization_alias="MP", default=None, description="Might points; None when unreadable"
    )
    building_might: ParsedInt = Field(
        validation_alias="TSBM",
        serialization_alias="TSBM",
        default=None,
        description="Might points from buildings; None when unreadable",
    )
    highest_might_points: ParsedInt = Field(
        validation_alias="HMP",
        serialization_alias="HMP",
        default=None,
        description="The most might points ever reached; None when unreadable",
    )


class GloryPointsResponse(TimedResponse):
    """
    Your glory points, which give the glory titles.

    Command: ufa, as a login section of ``gbd`` and a push.

    Client: ``CastleTitleData.parseUFA`` (bundle line 21038), which ``parseInt``\\ s a string and keeps a number
    """

    command = "ufa"

    glory_points: int | float | None = Field(
        validation_alias="CF", serialization_alias="CF", default=None, description="Glory points"
    )
    highest_glory_points: int | float | None = Field(
        validation_alias="HF", serialization_alias="HF", default=None, description="The most glory points ever"
    )

    @field_validator("glory_points", "highest_glory_points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> Any:
        if isinstance(value, str):
            return js_parse_int(value)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class FactionPointsResponse(TimedResponse):
    """
    Your Berimond (faction) points, which give the Berimond titles.

    Command: ufp, a push. The client ignores the copy in ``gbd``.

    Client: ``UFPCommand`` (bundle line 121010), ``CastleTitleData.parseUFP`` (bundle line 21039)
    """

    command = "ufp"

    faction_points: ParsedInt = Field(
        validation_alias="CFP",
        serialization_alias="CFP",
        default=None,
        description="Berimond points; None when unreadable",
    )
    highest_faction_points: ParsedInt = Field(
        validation_alias="HFP",
        serialization_alias="HFP",
        default=None,
        description="The most Berimond points ever; None when unreadable",
    )


class TopTitleRanking(TimedPayload):
    """
    One title system's top-X standing: a ``uar``'s ``FTM`` (glory) or ``BTM`` (Berimond).

    Client: ``CastleTitleData.parseUAR`` (bundle line 21022)
    """

    top_rank: ClientInt = Field(
        validation_alias="CTXT",
        serialization_alias="CTXT",
        default=0,
        description="Your rank for the system's top-X titles, -1 or 0 for none",
    )
    reset_seconds: ClientNumber = Field(
        validation_alias="RS", serialization_alias="RS", default=0, description="Seconds until the top-X titles reset"
    )
    thresholds: tuple[int, ...] = Field(
        validation_alias="NTFP",
        serialization_alias="NTFP",
        default=(),
        description="The points the top-X titles need, highest title first",
    )
    top_player_id: int | None = Field(
        validation_alias="TOID",
        serialization_alias="TOID",
        default=None,
        description="The player holding the system's top title; None when not sent",
    )

    @field_validator("thresholds", mode="before")
    @classmethod
    def _thresholds(cls, value: Any) -> Any:
        return tuple(js_int(entry) for entry in value) if isinstance(value, list) else ()

    @field_validator("top_player_id", mode="before")
    @classmethod
    def _player_id(cls, value: Any) -> Any:
        # assignTop1PlayerID stores TOID as sent (bundle line 21042); the client compares player ids with ==
        return None if value is None else js_parse_int(value)


class IslandTitle(BasePayload):
    """A ``uar``'s ``ITM``. Client: ``CastleTitleData.parseIslandDataFromServer`` (bundle lines 21023-21027)"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    title_id: EnumOrInt["Title"] | None = Field(
        validation_alias="TID",
        serialization_alias="TID",
        default=None,
        description="Your Storm Islands title; None for none",
    )

    @field_validator("title_id", mode="before")
    @classmethod
    def _held(cls, value: Any) -> Any:
        # Client: TID > -1 names a title
        return value if isinstance(value, int) and not isinstance(value, bool) and value > -1 else None

    @property
    def held_title_id(self) -> int:
        """The title id, -1 for none."""
        return -1 if self.title_id is None else self.title_id


class AllianceCityTitle(BasePayload):
    """A ``uar``'s ``ATM``. Client: ``CastleTitleData.parseAllianceCityDataFromServer`` (bundle lines 21028-21036)"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    title_id: EnumOrInt["Title"] | None = Field(
        validation_alias="TID",
        serialization_alias="TID",
        default=None,
        description="The alliance city title; None for none",
    )
    player_id: int | None = Field(
        validation_alias="PID",
        serialization_alias="PID",
        default=None,
        description="The player holding it; None when not sent",
    )

    @field_validator("title_id", mode="before")
    @classmethod
    def _title(cls, value: Any) -> Any:
        # Client: _allPossibleTitles.get(e.TID), keyed by the int title ids
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @field_validator("player_id", mode="before")
    @classmethod
    def _player_id(cls, value: Any) -> Any:
        # Client: e.PID==userData.playerID (bundle line 21035)
        return None if value is None else js_parse_int(value)


class TitleRanksResponse(TimedResponse):
    """
    Your top-X title ranks, Storm Islands title and the title systems your name shows.

    Command: uar, as a login section of ``gbd`` and a push.

    Client: ``CastleTitleData.parseUAR`` (bundle line 21022)
    """

    command = "uar"

    glory: TopTitleRanking = Field(
        validation_alias="FTM",
        serialization_alias="FTM",
        default_factory=TopTitleRanking,
        description="The glory system",
    )
    faction: TopTitleRanking = Field(
        validation_alias="BTM",
        serialization_alias="BTM",
        default_factory=TopTitleRanking,
        description="The Berimond system",
    )
    island_title: IslandTitle = Field(
        validation_alias="ITM",
        serialization_alias="ITM",
        default_factory=IslandTitle,
        description="Your Storm Islands title",
    )
    alliance_city_title: AllianceCityTitle | None = Field(
        validation_alias="ATM",
        serialization_alias="ATM",
        default=None,
        description="The alliance city title; None when not sent",
    )
    prefix_system: EnumOrStr[TitleSystem] | None = Field(
        validation_alias="PFX",
        serialization_alias="PFX",
        default=None,
        description="The title system shown before your name; None when not sent",
    )
    suffix_system: EnumOrStr[TitleSystem] | None = Field(
        validation_alias="SFX",
        serialization_alias="SFX",
        default=None,
        description="The title system shown after your name; None when not sent",
    )

    @field_validator("glory", "faction", "island_title", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, BasePayload)) else {}

    @field_validator("alliance_city_title", mode="before")
    @classmethod
    def _city(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("prefix_system", "suffix_system", mode="before")
    @classmethod
    def _system(cls, value: Any) -> Any:
        # parseUAR stores PFX and SFX as sent and compares them with the title system names (bundle line 21143)
        return value if isinstance(value, str) else None


class AchievementProgress(BasePayload):
    """
    One achievement's progress, an entry of a ``vli``'s ``RA``.

    Client: ``CastleAchievementData.parse_RA`` (bundle line 29838), ``AchievementVO.setProgress`` (bundle line 92889)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    achievement_id: ClientInt = Field(
        validation_alias="AID", serialization_alias="AID", default=0, description="The achievement's id"
    )
    progress: Numbers = Field(
        validation_alias="P",
        serialization_alias="P",
        default=(),
        description="Progress per condition, in condition order; -1 for a condition done",
    )


class AchievementsResponse(TimedResponse):
    """
    Your achievement points, finished achievements and progress.

    A ``vli`` adds to what the client knows: finished achievements stay finished, and an
    achievement it does not list keeps its progress. ``client.state.get_achievements()`` does the same.

    Command: vli, as a login section of ``gbd`` and a push.

    Client: ``CastleAchievementData.parse_vli``, ``parse_RA`` and ``parse_FA`` (bundle lines 29837-29842)
    """

    command = "vli"

    achievement_points: ClientInt = Field(
        validation_alias="AVP", serialization_alias="AVP", default=0, description="Achievement points"
    )
    finished_achievement_ids: Annotated[tuple[EnumOrInt["Achievement"], ...], BeforeValidator(_ints)] = Field(
        validation_alias="FA", serialization_alias="FA", default=(), description="Finished achievements"
    )
    progress: tuple[AchievementProgress, ...] = Field(
        validation_alias="RA",
        serialization_alias="RA",
        default=(),
        description="Progress of the achievements this packet lists",
    )

    @field_validator("progress", mode="before")
    @classmethod
    def _progress(cls, value: Any) -> Any:
        return tuple(readable_list(AchievementProgress, value, accept=lambda entry: isinstance(entry, dict)))


class RelocationInfoResponse(TimedResponse):
    """
    Your castle relocations: how many, the one running and the cooldown.

    Command: gri, as a login section of ``gbd`` and a push.

    Client: ``CastleUserData.parse_GRI`` (bundle line 9910), ``remainingRelocationDuration`` and
    ``remainingRelocationCooldown``
    """

    command = "gri"

    relocation_count: ClientInt = Field(
        validation_alias="RLC", serialization_alias="RLC", default=0, description="Relocations made"
    )
    relocation_seconds: ClientNumber = Field(
        validation_alias="RD",
        serialization_alias="RD",
        default=0,
        description="Seconds left on the running relocation when the values were read",
    )
    relocation_mode: int | None = Field(
        validation_alias="JM",
        serialization_alias="JM",
        default=None,
        description=(
            "The relocation's mode: its time counts only while this is 0, and the client redraws the map"
            " at OX/OY for 1; None when not sent"
        ),
    )
    cooldown_seconds: ClientNumber = Field(
        validation_alias="RMC",
        serialization_alias="RMC",
        default=0,
        description="Seconds until you may relocate again, when the values were read",
    )
    destination_x: ClientInt = Field(
        validation_alias="DX", serialization_alias="DX", default=0, description="The relocation's destination X"
    )
    destination_y: ClientInt = Field(
        validation_alias="DY", serialization_alias="DY", default=0, description="The relocation's destination Y"
    )

    @field_validator("relocation_mode", mode="before")
    @classmethod
    def _mode(cls, value: Any) -> Any:
        # parse_GRI compares 0==e.JM, GRICommand 1==int(JM); neither names the values (bundle lines 9910, 129650)
        return None if value is None else js_int(value)

    def remaining_relocation_seconds(self, now: float | None = None) -> float:
        """Seconds left on the running relocation, 0 when none runs."""
        if self.relocation_mode != 0:
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
