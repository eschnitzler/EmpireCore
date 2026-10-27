"""Your aqua points, skills, boosts, titles and achievements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.commanders.models.skills import SkillList
from empire_core.player.models.account import FoodProductionStatus
from empire_core.player.models.aqua import (
    AquaPointsResponse,
    GetAquaPointsRequest,
    StormIslandsInfo,
    StormIslandsInfoRequest,
)
from empire_core.player.models.progress import (
    AchievementsResponse,
    AssignTitleRequest,
    AssignTitleResponse,
    GetAchievementsRequest,
    GetTitleRanksRequest,
    TitleRanksResponse,
)
from empire_core.player.titles import player_title_ids
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import Title
    from empire_core.player.models.progress import (
        BoosterInfoResponse,
        FactionPointsResponse,
        GloryPointsResponse,
        MightPointsResponse,
    )


class StandingMixin(ServiceMixin):
    @property
    def aqua_points(self) -> int | float | None:
        """Your aqua points, from the last ``gap``; None until one arrived (:meth:`get_aqua_points` asks)."""
        return self.client.state.get_aqua_points()

    def get_aqua_points(self, *, timeout: float = 5.0) -> AquaPointsResponse:
        """
        Your and your alliance's aqua points; both are applied to state.

        Client: ``CastleEilandPanel`` (bundle line 56736) asks while it knows none
        """
        return self.request(GetAquaPointsRequest(), AquaPointsResponse, timeout=timeout)

    @property
    def storm_islands(self) -> StormIslandsInfo | None:
        """Your and your alliance's Storm Islands standing, from the last ``sii``; None until one arrived."""
        return self.client.state.get_storm_islands()

    def get_storm_islands_info(self, *, timeout: float = 5.0) -> StormIslandsInfo:
        """
        Your and your alliance's Storm Islands standing; it and your aqua points are applied to state.

        Raises:
            CommandError: The server refused

        Client: ``CastleStormIslandsMainDialog.showLoaded`` (bundle line 17524) asks while you are in an
        alliance; ``SIICommand`` (bundle line 127742)
        """
        return self.request(StormIslandsInfoRequest(), StormIslandsInfo, timeout=timeout)

    @property
    def skills(self) -> SkillList | None:
        """Your legend and sceat skills as the last ``skl`` listed them; None until one arrived."""
        return self.client.state.get_skills()

    @property
    def spent_skill_points(self) -> int | None:
        """Points spent on your held legend skills; None until a skill list arrived."""
        skills = self.skills
        return skills.spent_points(game_data=self._require_game_data()) if skills is not None else None

    @property
    def available_skill_points(self) -> int | None:
        """Legend skill points left to spend; None until a skill list arrived."""
        skills = self.skills
        return skills.available_points(game_data=self._require_game_data()) if skills is not None else None

    @property
    def title_ids(self) -> list[Title | int]:
        """Your held titles, in glory, Berimond and Storm Islands order.

        Raises:
            StateNotLoadedError: No login has brought your points and title ranks
            GameDataNotLoadedError: The game data cannot be loaded
        """
        return player_title_ids(
            self.glory_points, self.faction_points, self.title_ranks, game_data=self._require_game_data()
        )

    @property
    def boosts(self) -> BoosterInfoResponse:
        """Your boosters, premium account, production slots and festival.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_boosts()

    @property
    def might(self) -> MightPointsResponse:
        """Your might points, from the last ``gmu``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_might()

    @property
    def glory_points(self) -> GloryPointsResponse:
        """Your glory points, from the last ``ufa``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_glory_points()

    @property
    def food_production(self) -> FoodProductionStatus | None:
        """Whether your food production is frozen, from the login data's ``DTS`` and each push since; None until
        one arrived."""
        return self.client.state.get_food_production()

    @property
    def faction_points(self) -> FactionPointsResponse | None:
        """Your Berimond points, from the last ``ufp`` push; None until one arrived (the login data has none)."""
        return self.client.state.get_faction_points()

    @property
    def title_ranks(self) -> TitleRanksResponse:
        """Your top-X ranks, Storm Islands title and displayed title systems, from the last ``uar``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_title_ranks()

    def get_title_ranks(self, *, timeout: float = 5.0) -> TitleRanksResponse:
        """
        Request your top-X ranks, Storm Islands title and displayed title systems, as the client does when
        the Storm Islands title ranking opens; the reply is also kept in :attr:`title_ranks`.

        Client: ``CastleEilandRankingDialogTitle.show`` (bundle line 98292) sends ``C2SUserAchievedRanksVO``

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetTitleRanksRequest(), TitleRanksResponse, timeout=timeout)

    def assign_title(self, title: Title | int, player_name: str, *, timeout: float = 5.0) -> AssignTitleResponse:
        """
        Give a Storm Islands title to a player, as the island's king does.

        The client asks for the title ranks after every title given (:attr:`title_ranks`), and so does
        the library, without waiting for them.

        Client: ``CastleEilandAssignTitleDialog.onConfirmAssignment`` (bundle line 98376),
        ``APTCommand.executeCommand`` (bundle line 123623)

        Args:
            title: The title to give
            player_name: The player to give it to
            timeout: Timeout in seconds

        Returns:
            The title and the player given it

        Raises:
            ValueError: ``player_name`` is empty, which takes the title back (:meth:`revoke_title`)
            CommandError: The server refused: ``IS_NOT_KING``, ``LEVEL_TOO_HIGH_OR_LOW``,
                ``NOT_IN_SAME_ALLIANCE``, ``PLAYER_NOT_FOUND``, ``CANNOT_ASSIGN_TO_SELF`` or ``ALREADY_HAS_TITLE``
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        if not player_name:
            raise ValueError("a title is given to a named player; revoke_title() takes it back")
        request = AssignTitleRequest(title_id=title, player_name=player_name)
        return self.request(request, AssignTitleResponse, timeout=timeout)

    def revoke_title(self, title: Title | int, *, timeout: float = 5.0) -> None:
        """
        Take a Storm Islands title back from the player holding it.

        Client: ``CastleEilandAssignTitleDialog.onConfirmAssignment`` (bundle line 98376) sends the title with
        an empty name; ``APTCommand.executeCommand`` (bundle line 123623)

        Raises:
            CommandError: The server refused, e.g. ``IS_NOT_KING``
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        self.execute(AssignTitleRequest(title_id=title), timeout=timeout)

    @property
    def achievements(self) -> AchievementsResponse:
        """Your achievement points, finished achievements and progress.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_achievements()

    def get_achievements(self, *, timeout: float = 5.0) -> AchievementsResponse:
        """
        Request your achievements, as the client does when the achievements dialog opens.

        The reply is what the server sent; :attr:`achievements` holds it merged over what was known.

        Client: ``CastleAchievementDialog.showLoaded`` (bundle line 106960) sends ``C2SAchievementListVO``

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetAchievementsRequest(), AchievementsResponse, timeout=timeout)
