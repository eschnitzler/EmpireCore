"""Your spies and plague doctors, and how many are free."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from empire_core.enums import TitleSystem
from empire_core.gamedata import EnumOrInt
from empire_core.player.titles import held_titles
from empire_core.services.base import ServiceMixin
from empire_core.spy.pool import (
    island_title_chain,
    legend_spy_bonus,
    research_spy_bonus,
    title_spy_percent,
    total_spies,
)

if TYPE_CHECKING:
    from empire_core.gamedata import LegendSkill, Research
    from empire_core.spy.models import MaxSpiesResponse, PlagueDoctorInfoResponse


class SpiesMixin(ServiceMixin):
    @property
    def max_spies(self) -> MaxSpiesResponse:
        """The spies you own before boosts, from ``gms``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_max_spies()

    @property
    def plague_doctors(self) -> PlagueDoctorInfoResponse | None:
        """Your plague doctors, from the last ``cpi``; None until one arrived."""
        return self.client.state.get_plague_doctors()

    def spies_in_use(self) -> int:
        """
        Spies on your own spy movements, out or on their way home, as the state tracks them.

        Client: ``CastleSpyData.getNumAvailableSpies`` (bundle line 139970), which counts the
        ``spyCount`` of every ``SpyMapmovementVO`` you own
        """
        return sum(
            m.spy.spy_count if m.spy is not None else 0
            for m in self.client.state.get_all_movements()
            if m.is_mine and m.is_spy
        )

    def total_spies(
        self,
        *,
        research_ids: Iterable[EnumOrInt["Research"]] | None = None,
        legend_skill_ids: Iterable[EnumOrInt["LegendSkill"]] | None = None,
        title_ids: Iterable[int] | None = None,
        island_title_id: int | None = None,
        legend_target: bool = False,
    ) -> int:
        """
        All your spies, home or out, counted as the client does: the ``gms`` count plus boosts.

        The count is for the whole account, not one castle. Each boost left as None is read
        from state: your finished research (``rei``), legend skills (``skl``), and the glory,
        Berimond and Storm Islands titles your points and ranks give (``ufa``, ``ufp``, ``uar``).
        Pass a value to count that instead, ``()`` for none. A boost reads
        the game data, loaded on first use; after login the state's titles always count.

        Args:
            research_ids: Your finished research ids, the ``BR`` of the ``rei`` section
            legend_skill_ids: ``SkillList.legend_skill_ids``; counted only with ``legend_target``
            title_ids: Every glory and Berimond title you hold, each one below your current
                title included, as the client lists them
            island_title_id: Your Storm Islands title, -1 for none; the titles below it count too
            legend_target: Add legend skills: the client does for a target whose owner is a
                legend or that is a landmark, for your own legend status, and always in the
                attack screen's spy alert

        Returns:
            The count

        Raises:
            StateNotLoadedError: No login has brought ``gms``
            GameDataNotLoadedError: A boost counts and the game data cannot be loaded

        Client: ``CastleSpyData.getNumAllSpies`` (bundle line 139976), called with the target's
        ``ownerInfo.isLegend`` (bundle lines 34325, 34342, 127082) or ``userData.isLegend``
        (bundle line 102169); ``CastleTitleSystemHelper.returnTitleEffectValue`` (bundle line 4420)
        over ``CastleTitleData.thisUsersTitles`` (bundle line 21073)
        """
        state = self.client.state
        max_spies = state.get_max_spies()
        if research_ids is None:
            research_ids = state.get_research().bought_research_ids
        if legend_skill_ids is None:
            skills = state.get_skills()
            legend_skill_ids = skills.legend_skill_ids if skills is not None else ()
        ranks = state.get_title_ranks()
        if island_title_id is None:
            island_title_id = ranks.island_title.held_title_id
        glory, faction = state.get_glory_points(), state.get_faction_points()
        titles_from_state = title_ids is None
        research_ids, legend_skill_ids = list(research_ids), list(legend_skill_ids)
        title_ids = [] if title_ids is None else list(title_ids)
        boosted = research_ids or (legend_target and legend_skill_ids) or title_ids or island_title_id >= 0
        if not (boosted or titles_from_state):
            return total_spies(max_spies.max_spies)
        game_data = self._require_game_data()
        if titles_from_state:
            title_ids = [
                *held_titles(TitleSystem.GLORY, glory.glory_points, ranks.glory.top_rank, game_data=game_data),
                *held_titles(
                    TitleSystem.FACTION,
                    faction.faction_points if faction else None,
                    ranks.faction.top_rank,
                    game_data=game_data,
                ),
            ]
        titles = title_ids + island_title_chain(island_title_id, game_data=game_data)
        return total_spies(
            max_spies.max_spies,
            research_bonus=research_spy_bonus(game_data, research_ids),
            legend_bonus=legend_spy_bonus(game_data, legend_skill_ids) if legend_target else 0,
            title_percent=title_spy_percent(game_data, titles),
        )

    def available_spies(
        self,
        *,
        research_ids: Iterable[EnumOrInt["Research"]] | None = None,
        legend_skill_ids: Iterable[EnumOrInt["LegendSkill"]] | None = None,
        title_ids: Iterable[int] | None = None,
        island_title_id: int | None = None,
        legend_target: bool = False,
    ) -> int:
        """
        Spies at home: :meth:`total_spies` less :meth:`spies_in_use`, as the client counts them.

        The client uses this count to offer the spy button. The spy dialog
        itself sends with the ``ssi`` reply's ``available_spies``, as
        :meth:`execute_instant_spy` does.

        Takes the arguments of :meth:`total_spies`, read from state the same way.

        Returns:
            The count, which can be negative as in the client

        Raises:
            StateNotLoadedError: No login has brought ``gms``

        Client: ``CastleSpyData.getNumAvailableSpies`` (bundle line 139970)
        """
        total = self.total_spies(
            research_ids=research_ids,
            legend_skill_ids=legend_skill_ids,
            title_ids=title_ids,
            island_title_id=island_title_id,
            legend_target=legend_target,
        )
        return total - self.spies_in_use()
