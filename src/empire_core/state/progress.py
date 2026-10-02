"""The player's progress: research, boosts, might, points, titles, achievements, relocation and plague monks."""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from empire_core.player.models.progress import (
    AchievementProgress,
    AchievementsResponse,
    BoosterInfoResponse,
    FactionPointsResponse,
    Festival,
    GloryPointsResponse,
    MightPointsResponse,
    RelocationInfoResponse,
    ResearchInfoResponse,
    TitleRanksResponse,
)
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_truthy
from empire_core.spy.models import PlagueMonkInfoResponse
from empire_core.state.base import StateBase

logger = logging.getLogger(__name__)

_M = TypeVar("_M", bound=BaseModel)
_PROGRESS_SECTIONS = ("rei", "boi", "gmu", "ufa", "uar", "vli", "gri", "cpi")


def _read(model: type[_M], body: Any, what: str) -> _M | None:
    return read_or_none(model.model_validate, body, warn=logger, what=what) if isinstance(body, dict) else None


class ProgressState(StateBase):
    def _parse_progress(self, data: dict[str, Any]) -> set[str]:
        """Apply the progress sections of a gbd, or the one a push or reply carries; return those not applied.

        Client: ``GBDCommand.exec`` (bundle line 129381) calls ``parseUFA``, ``parseUAR``,
        ``parse_BOI``, ``parse_GMU``, ``parse_vli``, ``parse_REI``, ``parse_GRI`` and ``parse_CPI``;
        it never reads the gbd's ``ufp``
        """
        applied: set[str] = set()
        if "rei" in data and (research := _read(ResearchInfoResponse, data["rei"], "the research")) is not None:
            self.research = research
            applied.add("rei")
        if "boi" in data and self._apply_boosts(data["boi"]):
            applied.add("boi")
        gmu = data.get("gmu")
        if isinstance(gmu, dict) and "MP" in gmu and "HMP" in gmu:
            if (might := _read(MightPointsResponse, gmu, "the might points")) is not None:
                self.might = might
                applied.add("gmu")
        if "ufa" in data and (glory := _read(GloryPointsResponse, data["ufa"], "the glory points")) is not None:
            self.glory_points = glory
            applied.add("ufa")
        if "uar" in data and self._apply_title_ranks(data["uar"]):
            applied.add("uar")
        if "vli" in data and self._apply_achievements(data["vli"]):
            applied.add("vli")
        if js_truthy(gri := data.get("gri")):
            if (relocation := _read(RelocationInfoResponse, gri, "the relocation info")) is not None:
                self.relocation = relocation
                applied.add("gri")
        if js_truthy(cpi := data.get("cpi")):
            if (monks := _read(PlagueMonkInfoResponse, cpi, "the plague monks")) is not None:
                self.plague_monks = monks
                applied.add("cpi")
        return {section for section in _PROGRESS_SECTIONS if section in data} - applied

    def _apply_boosts(self, body: Any) -> bool:
        """Read a ``boi`` over the boosters known: one it does not list keeps its values, a falsy ``bfs`` the festival.

        Client: ``CastlePremiumBoostData.parse_BOI`` and ``parse_bfs`` (bundle lines 15202, 15218)
        """
        boosts = _read(BoosterInfoResponse, body, "the boosters")
        if boosts is None:
            return False
        previous = self.boosts
        if previous is not None:
            listed = {booster.booster_id: booster for booster in boosts.boosters}
            kept = tuple(listed.pop(booster.booster_id, booster) for booster in previous.boosters)
            update: dict[str, Any] = {"boosters": (*kept, *listed.values())}
            if boosts.festival is None:
                update["festival"] = previous.festival
            boosts = boosts.model_copy(update=update)
        self.boosts = boosts
        return True

    def _handle_bfs(self, data: Any) -> None:
        """Handle the reply to starting a festival: its ``T`` and ``RT`` are the festival.

        Client: ``BFSCommand`` (bundle line 122569) passes the reply to ``parse_bfs`` (bundle line 15218)
        """
        if not js_truthy(data) or (festival := _read(Festival, data, "the festival")) is None:
            return
        boosts = self.boosts if self.boosts is not None else BoosterInfoResponse()
        self.boosts = boosts.model_copy(update={"festival": festival})

    def _handle_ufp(self, data: Any) -> None:
        """Handle a ``ufp`` push: your Berimond points.

        Client: ``UFPCommand`` (bundle line 121010), ``CastleTitleData.parseUFP`` (bundle line 21039)
        """
        if (points := _read(FactionPointsResponse, data, "the Berimond points")) is not None:
            self.faction_points = points

    def _apply_title_ranks(self, body: Any) -> bool:
        """Read a ``uar``; an alliance city title it does not send keeps its value.

        Client: ``CastleTitleData.parseUAR`` (bundle line 21022), which reads ``ATM`` only when it is sent
        """
        ranks = _read(TitleRanksResponse, body, "the title ranks")
        if ranks is None:
            return False
        previous = self.title_ranks
        if previous is not None and isinstance(body, dict) and "ATM" not in body:
            ranks = ranks.model_copy(update={"alliance_city_title": previous.alliance_city_title})
        self.title_ranks = ranks
        return True

    def _apply_achievements(self, body: Any) -> bool:
        """Read a ``vli`` over what is known: finished achievements stay finished, unlisted progress stays.

        Client: ``CastleAchievementData.parse_vli``, ``parse_RA`` and ``parse_FA`` (bundle lines 29837-29842)
        """
        achievements = _read(AchievementsResponse, body, "the achievements")
        if achievements is None:
            return False
        previous = self.achievements
        if previous is not None:
            finished = dict.fromkeys((*previous.finished_achievement_ids, *achievements.finished_achievement_ids))
            progress: dict[int, AchievementProgress] = {entry.achievement_id: entry for entry in previous.progress}
            progress.update((entry.achievement_id, entry) for entry in achievements.progress)
            achievements = achievements.model_copy(
                update={"finished_achievement_ids": tuple(finished), "progress": tuple(progress.values())}
            )
        self.achievements = achievements
        return True

    def get_research(self) -> ResearchInfoResponse | None:
        """Your finished and running research, from the last ``rei``; None until the login data brought one."""
        with self._lock:
            return self.research

    def get_boosts(self) -> BoosterInfoResponse | None:
        """Your boosters, premium account, production slots and festival; None until a ``boi`` arrived.

        Every booster any ``boi`` listed is there, as the last one that listed it left it.
        """
        with self._lock:
            return self.boosts

    def get_might(self) -> MightPointsResponse | None:
        """Your might points, from the last ``gmu``; None until one arrived."""
        with self._lock:
            return self.might

    def get_glory_points(self) -> GloryPointsResponse | None:
        """Your glory points, from the last ``ufa``; None until one arrived."""
        with self._lock:
            return self.glory_points

    def get_faction_points(self) -> FactionPointsResponse | None:
        """Your Berimond points, from the last ``ufp`` push; None until one arrived (the login data has none)."""
        with self._lock:
            return self.faction_points

    def get_title_ranks(self) -> TitleRanksResponse | None:
        """Your top-X ranks, Storm Islands title and displayed title systems, from the last ``uar``; None before one."""
        with self._lock:
            return self.title_ranks

    def get_achievements(self) -> AchievementsResponse | None:
        """Your achievement points, finished achievements and progress; None until a ``vli`` arrived.

        Finished achievements from every ``vli`` are there, and each achievement's progress as
        the last ``vli`` that listed it left it.
        """
        with self._lock:
            return self.achievements

    def get_relocation(self) -> RelocationInfoResponse | None:
        """Your castle relocations, from the last ``gri``; None until one arrived."""
        with self._lock:
            return self.relocation

    def get_plague_monks(self) -> PlagueMonkInfoResponse | None:
        """Your plague monks, from the last ``cpi``; None until one arrived."""
        with self._lock:
            return self.plague_monks
