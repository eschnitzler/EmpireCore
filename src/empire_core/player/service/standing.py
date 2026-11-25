"""Your level, VIP status, cargo points, skills, boosts, titles and achievements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.commanders.models.skills import SkillList
from empire_core.player.models.account import (
    BUY_LEVEL_RANGE,
    BuyLevelRequest,
    BuyLevelResponse,
    FoodProductionStatus,
    VipStatusRequest,
    VipStatusResponse,
)
from empire_core.player.models.aqua import (
    CargoPointsResponse,
    GetCargoPointsRequest,
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
    from empire_core.gamedata import MightRankDef, Title
    from empire_core.player.models.progress import (
        BoosterInfoResponse,
        GallantryPointsResponse,
        GloryPointsResponse,
        MightPointsResponse,
    )


class StandingMixin(ServiceMixin):
    def buy_level(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Buy your next level with rubies; see "Spending rubies" in the guides.

        The client offers it from level 10 to 69 to a split-run test group it reads from the server, so the
        server may refuse an account outside that group. It always needs ``spend_rubies``;
        :attr:`buy_level_cost` gives the price.

        Args:
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False, or your level is outside ``BUY_LEVEL_RANGE``
            StateNotLoadedError: No login has brought your level
            CommandError: The server refused

        Client: ``ButtonBuyLevelComponent.onClickButton`` and ``onConfirm`` (bundle lines 548838, 548859),
        priced by ``buyLevelData.getLevelUpCost``; ``updateButtonVisibility`` (bundle line 548864) shows the
        button for ``SplitRunConst.BUY_LEVEL_TEST_PARAM`` and a level in range; ``BLVCommand.executeCommand``
        (bundle line 650885)
        """
        player = self.client.state.get_local_player()
        if player.level not in BUY_LEVEL_RANGE:
            raise ValueError(f"the game offers no level to buy at level {player.level}")
        self._require_spend_rubies(spend_rubies, "buying a level costs rubies")
        request = BuyLevelRequest(new_level=player.level + player.legendary_level + 1)
        self.request(request, BuyLevelResponse, timeout=timeout, spend_rubies=spend_rubies)

    @property
    def buy_level_cost(self) -> int | None:
        """
        The rubies :meth:`buy_level` costs at your level: 0 when the game data prices no such level, as the client
        shows it, None when the price is unreadable.

        Client: ``ButtonBuyLevelComponent.onClickButton`` (split.js line 548838) prices
        ``CastleBuyLevelData.getLevelUpCost(level, level + 1)`` (split.js line 573872)

        Raises:
            StateNotLoadedError: No login has brought your level
            GameDataNotLoadedError: The game data cannot be loaded
        """
        player = self.client.state.get_local_player()
        level = player.level + player.legendary_level
        return self._require_game_data().level_up_cost(level, level + 1)

    def get_vip_status(self, *, timeout: float = 5.0) -> VipStatusResponse:
        """
        Request your VIP status: points, level, VIP time left and premium commanders used today; it is
        applied to your player in state too.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SVIPInfoEvent`` (bundle line 400604), ``VIPCommand.exec`` (bundle line 653087)
        """
        return self.request(VipStatusRequest(), VipStatusResponse, timeout=timeout)

    @property
    def cargo_points(self) -> int | float | None:
        """Your cargo points, from the last ``gap``; None until one arrived (:meth:`get_cargo_points` asks)."""
        return self.client.state.get_cargo_points()

    def get_cargo_points(self, *, timeout: float = 5.0) -> CargoPointsResponse:
        """
        Your and your alliance's cargo points; both are applied to state.

        Client: ``CastleEilandPanel`` (bundle line 56736) asks while it knows none
        """
        return self.request(GetCargoPointsRequest(), CargoPointsResponse, timeout=timeout)

    @property
    def storm_islands(self) -> StormIslandsInfo | None:
        """Your and your alliance's Storm Islands standing, from the last ``sii``; None until one arrived."""
        return self.client.state.get_storm_islands()

    def get_storm_islands_info(self, *, timeout: float = 5.0) -> StormIslandsInfo:
        """
        Your and your alliance's Storm Islands standing; it and your cargo points are applied to state.

        Raises:
            CommandError: The server refused

        Client: ``CastleStormIslandsMainDialog.showLoaded`` (bundle line 17524) asks while you are in an
        alliance; ``SIICommand`` (bundle line 127742)
        """
        return self.request(StormIslandsInfoRequest(), StormIslandsInfo, timeout=timeout)

    @property
    def skills(self) -> SkillList | None:
        """Your Legendary and sceat skills as the last ``skl`` listed them; None until one arrived."""
        return self.client.state.get_skills()

    @property
    def spent_skill_points(self) -> int | None:
        """Points spent on your held Legendary skills; None until a skill list arrived."""
        skills = self.skills
        return skills.spent_points(game_data=self._require_game_data()) if skills is not None else None

    @property
    def available_skill_points(self) -> int | None:
        """Legendary skill points left to spend; None until a skill list arrived."""
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
            self.glory_points, self.gallantry_points, self.title_ranks, game_data=self._require_game_data()
        )

    @property
    def boosts(self) -> BoosterInfoResponse:
        """Your boosters, premium account, production slots and feast.

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
    def next_might_rank(self) -> MightRankDef | None:
        """The might rank after your highest might points, from the last ``gmu``; None past the last rank or
        while your highest might is unreadable.

        Client: ``CastleUserStatePanel.onChangeMight`` (split.js line 162857) shows
        ``MightData.getNextMightRank(userHighestMightAchieved)``

        Raises:
            StateNotLoadedError: No login has brought your might
            GameDataNotLoadedError: The game data cannot be loaded
        """
        highest = self.might.highest_might_points
        return None if highest is None else self._require_game_data().next_might_rank(highest)

    @property
    def might_to_next_rank(self) -> int | None:
        """Might points from your current might to :attr:`next_might_rank`'s threshold; 0 past the last rank, None
        while your might is unreadable.

        Client: ``MightData.userMightToNextLevel`` (split.js line 582073)

        Raises:
            StateNotLoadedError: No login has brought your might
            GameDataNotLoadedError: The game data cannot be loaded
        """
        rank, current = self.next_might_rank, self.might.might_points
        if rank is None:
            return 0
        return None if rank.threshold is None or current is None else rank.threshold - current

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
    def gallantry_points(self) -> GallantryPointsResponse | None:
        """Your Berimond points, from the last ``ufp`` push; None until one arrived (the login data has none)."""
        return self.client.state.get_gallantry_points()

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
