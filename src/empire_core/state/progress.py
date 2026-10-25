"""The player's progress: research, boosts, might, points, titles, achievements, relocation and plague doctors."""

from typing import Any

from empire_core.castle.models.research import ResearchInfoResponse
from empire_core.player.models.progress import (
    AchievementProgress,
    AchievementsResponse,
    BoosterInfoResponse,
    FactionPointsResponse,
    Festival,
    GloryPointsResponse,
    GloryTitleResetResponse,
    IslandTitle,
    MightPointsResponse,
    RelocationInfoResponse,
    SelectTitleResponse,
    TitleRanksResponse,
)
from empire_core.protocol.js import js_int, js_truthy
from empire_core.spy.models import PlagueDoctorInfoResponse
from empire_core.state.base import StateBase, loaded, read_section

_PROGRESS_SECTIONS = ("rei", "boi", "gmu", "ufa", "uar", "vli", "gri", "cpi")


class ProgressState(StateBase):
    def _parse_progress(self, data: dict[str, Any]) -> set[str]:
        """Apply the progress sections of a gbd, or the one a push or reply carries; return those not applied.

        Client: ``GBDCommand.exec`` (bundle line 129381) calls ``parseUFA``, ``parseUAR``,
        ``parse_BOI``, ``parse_GMU``, ``parse_vli``, ``parse_REI``, ``parse_GRI`` and ``parse_CPI``;
        it never reads the gbd's ``ufp``
        """
        applied: set[str] = set()
        if "rei" in data and (research := read_section(ResearchInfoResponse, data["rei"], "the research")) is not None:
            self.research = research
            applied.add("rei")
        if "boi" in data and self._apply_boosts(data["boi"]):
            applied.add("boi")
        gmu = data.get("gmu")
        if isinstance(gmu, dict) and "MP" in gmu and "HMP" in gmu:
            if (might := read_section(MightPointsResponse, gmu, "the might points")) is not None:
                self.might = might
                applied.add("gmu")
        if "ufa" in data and (glory := read_section(GloryPointsResponse, data["ufa"], "the glory points")) is not None:
            self.glory_points = glory
            applied.add("ufa")
        if "uar" in data and self._apply_title_ranks(data["uar"]):
            applied.add("uar")
        if "vli" in data and self._apply_achievements(data["vli"]):
            applied.add("vli")
        if js_truthy(gri := data.get("gri")):
            if (relocation := read_section(RelocationInfoResponse, gri, "the relocation info")) is not None:
                self.relocation = relocation
                applied.add("gri")
        if js_truthy(cpi := data.get("cpi")):
            if (doctors := read_section(PlagueDoctorInfoResponse, cpi, "the plague doctors")) is not None:
                self.plague_doctors = doctors
                applied.add("cpi")
        return {section for section in _PROGRESS_SECTIONS if section in data} - applied

    def _apply_boosts(self, body: Any) -> bool:
        """Read a ``boi`` over the boosters known: one it does not list keeps its values, a falsy ``bfs`` the festival.

        Client: ``CastlePremiumBoostData.parse_BOI`` and ``parse_bfs`` (bundle lines 15202, 15218)
        """
        boosts = read_section(BoosterInfoResponse, body, "the boosters")
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
        if not js_truthy(data) or (festival := read_section(Festival, data, "the festival")) is None:
            return
        boosts = self.boosts if self.boosts is not None else BoosterInfoResponse()
        self.boosts = boosts.model_copy(update={"festival": festival})

    def _handle_ufp(self, data: Any) -> None:
        """Handle a ``ufp`` push: your Berimond points.

        Client: ``UFPCommand`` (bundle line 121010), ``CastleTitleData.parseUFP`` (bundle line 21039)
        """
        if (points := read_section(FactionPointsResponse, data, "the Berimond points")) is not None:
            self.faction_points = points

    def _apply_title_ranks(self, body: Any) -> bool:
        """Read a ``uar``; an alliance city title it does not send keeps its value.

        Client: ``CastleTitleData.parseUAR`` (bundle line 21022), which reads ``ATM`` only when it is sent
        """
        ranks = read_section(TitleRanksResponse, body, "the title ranks")
        if ranks is None:
            return False
        previous = self.title_ranks
        if previous is not None and isinstance(body, dict) and "ATM" not in body:
            ranks = ranks.model_copy(update={"alliance_city_title": previous.alliance_city_title})
        self.title_ranks = ranks
        return True

    def _handle_uht(self, data: Any) -> None:
        """Handle a ``uht`` push: when the glory top-X titles reset, kept on the glory system of the last ``uar``.

        Nothing is applied before a ``uar`` arrived, nor for an ``RS`` that does not read as a number.

        Client: ``UHTCommand.executeCommand`` (bundle line 129926), ``CastleTitleData.parseUHT`` (bundle line 21048),
        which does nothing for a falsy body
        """
        if self.title_ranks is None or not js_truthy(data):
            return
        reset = read_section(GloryTitleResetResponse, data, "the glory title reset")
        if reset is None or reset.reset_seconds is None:
            return
        glory = self.title_ranks.glory.model_copy(
            update={"reset_seconds": reset.reset_seconds, "received_at": reset.received_at}
        )
        self.title_ranks = self.title_ranks.model_copy(update={"glory": glory})

    def _handle_apt(self, data: Any) -> None:
        """Handle an ``apt`` without a player name: its truthy ``TI`` is your Storm Islands title now.

        Client: ``APTCommand.executeCommand`` (bundle line 123623), ``CastleTitleData.parseAPT`` (bundle line 21029)
        """
        if self.title_ranks is None or not isinstance(data, dict) or js_truthy(data.get("PN")):
            return
        if js_truthy(title_id := data.get("TI")):
            island_title = IslandTitle(title_id=js_int(title_id))
            self.title_ranks = self.title_ranks.model_copy(update={"island_title": island_title})

    def _apply_achievements(self, body: Any) -> bool:
        """Read a ``vli`` over what is known: finished achievements stay finished, unlisted progress stays.

        Client: ``CastleAchievementData.parse_vli``, ``parse_RA`` and ``parse_FA`` (bundle lines 29837-29842)
        """
        achievements = read_section(AchievementsResponse, body, "the achievements")
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

    def get_research(self) -> ResearchInfoResponse:
        """Your finished and running research, from the last ``rei``; the login data brings one.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.research, "Research")

    def get_boosts(self) -> BoosterInfoResponse:
        """Your boosters, premium account, production slots and festival; the login data brings a ``boi``.

        Every booster any ``boi`` listed is there, as the last one that listed it left it.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.boosts, "Boosters")

    def get_might(self) -> MightPointsResponse:
        """Your might points, from the last ``gmu``; the login data brings one.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.might, "Might points")

    def get_glory_points(self) -> GloryPointsResponse:
        """Your glory points, from the last ``ufa``; the login data brings one.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.glory_points, "Glory points")

    def get_faction_points(self) -> FactionPointsResponse | None:
        """Your Berimond points, from the last ``ufp`` push; None until one arrived (the login data has none)."""
        with self._lock:
            return self.faction_points

    def select_title_systems(self, selected: SelectTitleResponse) -> None:
        """Apply an ``ste`` reply to the title systems of the kept ``uar``: each one the reply names.

        ``client.player.select_titles`` calls it. Nothing is applied before a ``uar`` arrived.

        Client: ``CastleTitleData.parseSTE`` (bundle line 21041)
        """
        with self._lock:
            if self.title_ranks is None:
                return
            changed = {
                field: system
                for field, system in (
                    ("prefix_system", selected.prefix_system),
                    ("suffix_system", selected.suffix_system),
                )
                if system is not None
            }
            self.title_ranks = self.title_ranks.model_copy(update=changed)

    def get_title_ranks(self) -> TitleRanksResponse:
        """Your top-X ranks, Storm Islands title and displayed title systems, from the last ``uar``.

        The login data brings one.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.title_ranks, "Title ranks")

    def get_achievements(self) -> AchievementsResponse:
        """Your achievement points, finished achievements and progress; the login data brings a ``vli``.

        Finished achievements from every ``vli`` are there, and each achievement's progress as
        the last ``vli`` that listed it left it.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.achievements, "Achievements")

    def get_relocation(self) -> RelocationInfoResponse | None:
        """Your castle relocations, from the last ``gri``; None until one arrived."""
        with self._lock:
            return self.relocation

    def get_plague_doctors(self) -> PlagueDoctorInfoResponse | None:
        """Your plague doctors, from the last ``cpi``; None until one arrived."""
        with self._lock:
            return self.plague_doctors
