"""
Other players' details, player search and your legend skills.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from empire_core.commanders.models.skills import (
    AddSkillPointRequest,
    AddSkillPointResponse,
    GetSkillsRequest,
    GetSkillsResponse,
    ObjectUpdateEvent,
    ResetSkillsRequest,
    SkillList,
)
from empire_core.enums import Kingdom, MysteryBoxKey, PeaceModeDuration, TitleSystem
from empire_core.exceptions import CommandError, EmpireError, EmpireTimeoutError, PacketError
from empire_core.player.models.aqua import AquaPointsResponse, GetAquaPointsRequest
from empire_core.player.models.economy import (
    GetLootBoxesRequest,
    LootBoxesResponse,
    LootBoxKeys,
    OpenLootBoxRequest,
    OpenLootBoxResponse,
)
from empire_core.player.models.info import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.player.models.progress import (
    AchievementFinishedResponse,
    AchievementsResponse,
    AssignTitleRequest,
    AssignTitleResponse,
    GetAchievementsRequest,
    GetTitleRanksRequest,
    SelectTitleRequest,
    SelectTitleResponse,
    TitleRanksResponse,
)
from empire_core.player.models.protection import (
    CANCEL_PEACE_MODE,
    FACTION_PROTECTION_RUBIES,
    GetProtectionRequest,
    ProtectionResponse,
    StartFactionProtectionRequest,
    StartFactionProtectionResponse,
    StartPeaceModeRequest,
)
from empire_core.player.titles import player_title_ids
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.gamedata import Currency, LegendSkill, LootBox, Title
    from empire_core.map.models.areas import KingdomProtection
    from empire_core.player.models.account import (
        BoostedGlobalEffectsResponse,
        DailyResetResponse,
        OfficerTraining,
        PlayerGiftsResponse,
    )
    from empire_core.player.models.progress import (
        BoosterInfoResponse,
        FactionPointsResponse,
        GloryPointsResponse,
        MightPointsResponse,
        RelocationInfoResponse,
    )
    from empire_core.state.models import Player

logger = logging.getLogger(__name__)

# LegendSkillConst.BASE_COST, EXPONENT, BASE_SKILL_POINTS, POINTS_FACTOR (dll line 19477)
_RESET_BASE_RUBIES = 20
_RESET_EXPONENT = 5
_RESET_BASE_POINTS = 50
_RESET_RUBIES_PER_POINT = 30


@dataclass
class PlayerDetailsBulkResult:
    """What :meth:`PlayerService.get_player_details_bulk` got for each player."""

    found: dict[int, GetPlayerInfoResponse] = field(default_factory=dict)
    """The replies, by player id."""
    failed: dict[int, CommandError | PacketError] = field(default_factory=dict)
    """Players whose request the server refused, or whose reply could not be read."""
    timed_out: list[int] = field(default_factory=list)
    """Players whose reply did not come in time."""

    @property
    def complete(self) -> bool:
        """Whether every player was found."""
        return not self.failed and not self.timed_out


class PlayerService(BaseService):
    """
    Other players' details, finding a player by name, and your own player: currencies, skills,
    boosts, points and titles.

    Reached as client.player.
    """

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self.on_response("skl", self._handle_skill_list)
        self.on_response("ego", self._handle_skill_list)
        self.on_response("vfi", self._handle_achievement_finished)
        self.on_response("apt", self._request_title_ranks)

    @property
    def local_player(self) -> Player:
        """A snapshot of the local player.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_local_player()

    @property
    def currencies(self) -> dict[Currency | str, int]:
        """A snapshot of the special currencies (``Currency`` -> amount)."""
        return self.client.state.get_special_currencies()

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

    @property
    def relocation(self) -> RelocationInfoResponse | None:
        """Your castle relocations, from the last ``gri``; None until one arrived."""
        return self.client.state.get_relocation()

    @property
    def officer_training(self) -> OfficerTraining | None:
        """The officers' school training program running, from the last ``gatp`` and the ``gtp`` since."""
        return self.client.state.get_officer_training()

    @property
    def boosted_global_effects(self) -> BoostedGlobalEffectsResponse | None:
        """The global effects the running booster event boosts, from the last ``bie``; None until one arrived."""
        return self.client.state.get_boosted_global_effects()

    @property
    def loot_boxes(self) -> LootBoxesResponse | None:
        """Your loot boxes and key progress; None until a ``gls`` arrived."""
        return self.client.state.get_loot_boxes()

    def get_loot_boxes(self, *, timeout: float = 5.0) -> LootBoxesResponse:
        """
        Request your loot boxes and key progress, as the client does when the mystery boxes open;
        the reply is also kept in :attr:`loot_boxes`.

        Client: ``RewardHubMainDialogMysteryBoxes.show`` (bundle line 92142) sends ``C2SGetLootBoxesStatus``

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetLootBoxesRequest(), LootBoxesResponse, timeout=timeout)

    @property
    def daily_reset(self) -> DailyResetResponse | None:
        """When the daily reset comes, from the login data's ``drt``; None until it arrived."""
        return self.client.state.get_daily_reset()

    @property
    def gifts(self) -> PlayerGiftsResponse | None:
        """Your gift packages and how many you may still send, from the last ``pgl``; None until one arrived."""
        return self.client.state.get_player_gifts()

    # =========================================================================
    # Protection
    # =========================================================================

    def protection(self, kingdom: Kingdom = Kingdom.GREEN) -> KingdomProtection | None:
        """
        Your protection in ``kingdom`` as last sent (login data, ``uap`` pushes and replies); nothing is sent.

        Its seconds count from when it arrived, ``client.state.get_last_packet_time("uap")`` for a push.
        None when none came for that kingdom.

        Raises:
            StateNotLoadedError: No login has brought the player
        """
        return self.local_player.protection.get(kingdom)

    def get_protection(self, kingdom: Kingdom = Kingdom.GREEN, *, timeout: float = 5.0) -> ProtectionResponse:
        """
        Ask for your protection in ``kingdom``; the reply also updates :meth:`protection`, and in Berimond the event.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SUserAttackProtectionVO`` (bundle line 65923) and, for Berimond,
        ``C2SUpdateFactionProtectionVO`` (bundle line 87993); ``UAPCommand`` (bundle line 129888)
        """
        return self.request(GetProtectionRequest(kingdom=kingdom), ProtectionResponse, timeout=timeout)

    def start_peace_mode(
        self, duration: PeaceModeDuration, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """
        Buy peace mode: nobody can attack you, and you attack nobody, for ``duration``.

        It starts after a lead time; the stages arrive as ``uap`` pushes (see :meth:`protection`).

        Args:
            duration: How long; ``duration.rubies`` is its price before ruby discounts
            spend_rubies: Allow the rubies it costs
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleStartPeaceModeDialog.onClick`` (bundle line 35192) and ``setPrice``
        (bundle line 35188); ``C2SPeaceModeStartVO`` (bundle line 47478), ``MPSCommand`` (bundle line 125133)
        """
        self._require_spend_rubies(spend_rubies, f"peace mode for {duration.name} costs {duration.rubies} rubies")
        self.execute(StartPeaceModeRequest(duration=duration), timeout=timeout)

    def cancel_peace_mode(self, *, timeout: float = 5.0) -> None:
        """
        End your peace mode; the new stage arrives as a ``uap`` push.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleManagementDialog.cancelPeaceMode`` (bundle line 24682) sends ``C2SPeaceModeStartVO(-1)``
        """
        self.execute(StartPeaceModeRequest(duration=CANCEL_PEACE_MODE), timeout=timeout)

    def start_faction_protection(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> StartFactionProtectionResponse:
        """
        Buy Berimond faction protection; the reply also updates the running Berimond event.

        Args:
            spend_rubies: Allow the rubies it costs, ``FACTION_PROTECTION_RUBIES`` before discounts
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleFactionProtectionModeDialog.onClick`` (bundle line 64918), priced by
        ``FactionConst.getPeaceC2Cost`` (dll line 19316); ``FFPCommand`` (bundle line 127785)
        """
        self._require_spend_rubies(spend_rubies, f"faction protection costs {FACTION_PROTECTION_RUBIES} rubies")
        return self.request(StartFactionProtectionRequest(), StartFactionProtectionResponse, timeout=timeout)

    def get_player_info(self, player_id: int, *, timeout: float = 5.0) -> GetPlayerInfoResponse:
        """
        Get detailed player information (gdi), including castle list with
        capture info.

        Args:
            player_id: A player's id: ``search_player_by_name(name).get_player().owner_id``,
                an owner record's ``MapObject.owner_id`` from a map scan, or an
                ``AllianceMember.player_id`` from ``client.alliance.get_members()``
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetPlayerInfoRequest(player_id=player_id), GetPlayerInfoResponse, timeout=timeout)

    def get_player_details(self, player_id: int, *, timeout: float = 5.0) -> GetPlayerInfoResponse:
        """Alias for :meth:`get_player_info` (both use the 'gdi' command)."""
        return self.get_player_info(player_id, timeout=timeout)

    def get_player_details_bulk(
        self, player_ids: list[int], send_delay: float = 0.0, *, timeout: float = 5.0
    ) -> PlayerDetailsBulkResult:
        """
        Get detailed info for several players, one gdi request after another.

        Each request waits for its own reply before the next goes out: a gdi
        error reply names no player, so only one request in flight at a time
        tells which player it belongs to. Each runs as :meth:`get_player_info`
        does, under the gdi command lock and taking only a reply whose
        ``O.OID`` is the player asked for.

        Args:
            player_ids: Player ids to fetch, found as for :meth:`get_player_info`; repeats are fetched once
            timeout: Seconds to wait for each reply
            send_delay: Seconds to wait between two requests; by default none, as
                each already waits for the one before it to be answered

        Returns:
            Which players were found, which failed and why, and which timed out

        Raises:
            ConnectionClosedError / NetworkError: the connection failed; the players fetched so far are lost
            ReceiveThreadError: called on the receive thread
        """
        result = PlayerDetailsBulkResult()
        for index, pid in enumerate(dict.fromkeys(player_ids)):
            if index and send_delay > 0:
                time.sleep(send_delay)
            try:
                response = self.get_player_info(pid, timeout=timeout)
            except EmpireTimeoutError:
                result.timed_out.append(pid)
                continue
            except (CommandError, PacketError) as e:
                result.failed[pid] = e
                continue
            result.found[pid] = response
        return result

    def search_player_by_name(self, player_name: str, *, timeout: float = 5.0) -> SearchPlayerResponse:
        return self.request(SearchPlayerRequest(player_name=player_name), SearchPlayerResponse, timeout=timeout)

    def get_skills(self, *, timeout: float = 5.0) -> GetSkillsResponse:
        """
        The player's legend and sceat skills.

        Args:
            timeout: Timeout in seconds

        Returns:
            The ``skl`` response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetSkillsRequest(), GetSkillsResponse, timeout=timeout)

    def add_legend_skill_point(self, skill: LegendSkill, *, timeout: float = 5.0) -> AddSkillPointResponse:
        """
        Buy a legend skill level with skill points: the next level of a skill you hold, or the first of one you don't.

        The client offers it when the skill is not at its last level, its tier and node are unlocked,
        enough points are left (``SkillList.available_points``) and no sceat skill is being activated;
        the server checks the same. Each level bought replaces the one before it in :attr:`skills`.

        Client: ``CastleLegendSkillItem.onClick`` and ``canBuy`` (bundle lines 35643, 35652),
        ``CastleLegendSkillData.parse_SKP`` (bundle line 112073)

        Args:
            skill: The level to buy, e.g. ``LegendSkill.GATE_REDUCTION_T0_G1_L2`` when holding level 1
            timeout: Timeout in seconds

        Returns:
            The levels bought

        Raises:
            CommandError: The server refused: ``ADD_LEGEND_SKILL_FAILED``,
                ``ADD_LEGEND_SKILL_REQUIRED_SKILL_MISSING``, ``ADD_LEGEND_SKILL_NOT_ENOUGH_SKILL_POINTS`` or
                ``ADD_LEGEND_SKILL_TIER_LOCKED``
            GameDataNotLoadedError: The game data cannot be loaded
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        skills = self._require_game_data().legend_skills
        response = self.request(AddSkillPointRequest(skill=skill), AddSkillPointResponse, timeout=timeout)
        self.client.state.add_legend_skills(
            {bought: row.previous_skill_id if (row := skills.get(bought)) else None for bought in response.skill_ids}
        )
        return response

    def reset_skills(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> GetSkillsResponse:
        """
        Take back every legend skill point, and the sceat skills with them.

        Free once the reset cooldown of 15 days has run out. Inside it the same request skips the
        cooldown for ``20 * resets**5 + (points spent + 50) * 30`` rubies, priced from a fresh skill
        list unless ``spend_rubies`` allows any price.

        Client: ``CastleLegendSkillClassicSublayer.onClick`` (bundle line 78657) opens
        ``CastleLegendSkillCooldownDialog`` inside the cooldown, whose ``skipWithRubies`` sends the
        same request (bundle line 78885); ``LegendSkillConst.resetSkipCostC2`` and
        ``RESET_COOLDOWN_IN_SECONDS`` (dll lines 19474, 19470); ``CastleLegendSkillData.resetSkills``
        (bundle line 112104) then asks for the skill list

        Args:
            spend_rubies: Allow the rubies a reset inside the cooldown costs
            timeout: Timeout in seconds, for each request

        Returns:
            The skill list after the reset, also kept in :attr:`skills`

        Raises:
            ValueError: The cooldown is running and ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        if not spend_rubies:
            skills = self.get_skills(timeout=timeout)
            if skills.seconds_until_reset > 0:
                spent = skills.spent_points(game_data=self._require_game_data())
                rubies = (
                    int(_RESET_BASE_RUBIES * skills.reset_count**_RESET_EXPONENT)
                    + (spent + _RESET_BASE_POINTS) * _RESET_RUBIES_PER_POINT
                )
                self._require_spend_rubies(
                    spend_rubies, f"resetting the skills inside the cooldown costs {rubies} rubies"
                )
        self.execute(ResetSkillsRequest(), timeout=timeout)
        return self.get_skills(timeout=timeout)

    def open_loot_box(
        self,
        loot_box: LootBox,
        key: MysteryBoxKey = MysteryBoxKey.COMMON,
        *,
        open_all: bool = False,
        timeout: float = 5.0,
    ) -> OpenLootBoxResponse:
        """
        Open a loot box, or every box of the kind, with a mystery box key.

        The common key never runs out; a rarer one must be held (:attr:`currencies`) and opens one box
        only. The box type's key progress in :attr:`loot_boxes` is set to the reply's; the box count is
        not lowered, as in the client, and :meth:`get_loot_boxes` reads the new one. Reward ids in the
        reply are resolved through the game data.

        Client: ``RewardHubDialogMysteryBoxItem.fillItem`` (bundle line 92191) enables the single open
        with a held or common key and the open-all with the common key only; ``OLECommand`` (bundle line 124819)

        Args:
            loot_box: The box to open, as :attr:`loot_boxes` lists it
            key: The key to open it with
            open_all: Open every box of the kind; the common key only
            timeout: Timeout in seconds

        Returns:
            What the boxes gave, and the keys won

        Raises:
            ValueError: ``open_all`` with a key other than the common one, or a rarer key not held
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        if key is not MysteryBoxKey.COMMON:
            if open_all:
                raise ValueError("only the common key opens every box of a kind")
            held = (
                amount for currency, amount in self.currencies.items() if getattr(currency, "currency_id", None) == key
            )
            if next(held, 0) <= 0:
                raise ValueError(f"no {key.name} mystery box key is held")
        response = self.request(
            OpenLootBoxRequest(loot_box_id=loot_box, key=key, open_all=open_all), OpenLootBoxResponse, timeout=timeout
        )
        game_data = self._require_game_data()
        if response.reward_ids and not response.rewards:
            response = response.model_copy(update={"rewards": game_data.reward_list(response.reward_ids)})
        box = game_data.loot_boxes.get(response.loot_box_id)
        if box is not None:
            self.client.state.set_loot_box_keys(
                LootBoxKeys(loot_box_type_id=box.loot_box_type_id, keys=response.key_progress)
            )
        return response

    def select_titles(
        self, prefix: TitleSystem, suffix: TitleSystem | None = None, *, timeout: float = 5.0
    ) -> SelectTitleResponse:
        """
        Choose the title systems shown before and after your name.

        The dialog offers a system once you hold one of its titles (``held_titles``). The reply's
        systems replace those of :attr:`title_ranks`.

        Client: ``CastleTitleSelectDialog.confirmSelection`` (bundle line 45050),
        ``CastleTitleData.parseSTE`` (bundle line 21041)

        Args:
            prefix: The system shown before your name
            suffix: The system shown after it; None for none
            timeout: Timeout in seconds

        Returns:
            The systems the server set

        Raises:
            CommandError: The server refused: ``TITLE_NOT_AVAILABLE``, ``TITLE_SYSTEM_NOT_AVAILABLE`` or
                ``TITLE_ON_COOLDOWN``
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        selected = self.request(
            SelectTitleRequest(prefix=prefix, suffix=suffix or ""), SelectTitleResponse, timeout=timeout
        )
        self.client.state.select_title_systems(selected)
        return selected

    on_skill_list = Event[SkillList]()
    """
    Register a callback for every skill list the server sends.

    That is each ``skl`` packet, including the reply to :meth:`get_skills`,
    and the ``skl`` block of an ``ego`` push.

    Client: ``SKLCommand.executeCommand`` (bundle line 129742) and
    ``EGOCommand.executeCommand`` (bundle line 122801) both call ``parse_SKL``.

    Removing a callback not registered is a no-op.
    """

    on_achievement_finished = Event[AchievementFinishedResponse]()
    """
    Register a callback for every achievement you finish, called with the ``vfi`` push.

    Client: ``VFICommand.exec`` (bundle line 121164) shows the level-up dialog or the achievement popup.
    """

    def _handle_achievement_finished(self, response: BaseResponse) -> None:
        if isinstance(response, AchievementFinishedResponse):
            self._fire(self.on_achievement_finished, response)

    def _request_title_ranks(self, response: BaseResponse) -> None:
        # APTCommand.executeCommand (bundle line 123625) asks for a uar after every apt, pushed or answered
        try:
            self.client.connection.send_and_drop_reply(
                self.client.frame(GetTitleRanksRequest()), "uar", window=self.client.config.request_timeout
            )
        except EmpireError:
            logger.warning("Could not ask for the title ranks after a title was assigned", exc_info=True)

    def _handle_skill_list(self, response: BaseResponse) -> None:
        if isinstance(response, GetSkillsResponse):
            skills: SkillList | None = response
        elif isinstance(response, ObjectUpdateEvent):
            skills = response.skills
        else:
            return
        if skills is None:
            return
        self._fire(self.on_skill_list, skills)


__all__ = ["PlayerDetailsBulkResult", "PlayerService"]
