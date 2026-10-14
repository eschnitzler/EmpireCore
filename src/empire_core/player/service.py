"""
Other players' details, player search and your legend skills.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from empire_core.commanders.models.skills import GetSkillsRequest, GetSkillsResponse, ObjectUpdateEvent, SkillList
from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError
from empire_core.player.models.info import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.gamedata import Currency
    from empire_core.player.models.account import (
        BoostedGlobalEffectsResponse,
        DailyResetResponse,
        OfficerTraining,
        PlayerGiftsResponse,
    )
    from empire_core.player.models.economy import LootBoxesResponse
    from empire_core.player.models.progress import (
        AchievementsResponse,
        BoosterInfoResponse,
        FactionPointsResponse,
        GloryPointsResponse,
        MightPointsResponse,
        RelocationInfoResponse,
        TitleRanksResponse,
    )
    from empire_core.state.models import Player


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

    @property
    def local_player(self) -> Player | None:
        """A snapshot of the local player, or None before login."""
        return self.client.state.get_local_player()

    @property
    def currencies(self) -> dict[Currency | str, int]:
        """A snapshot of the special currencies (``Currency`` -> amount)."""
        return self.client.state.get_special_currencies()

    @property
    def skills(self) -> SkillList | None:
        """Your legend and sceat skills as the last ``skl`` listed them; None until one arrived."""
        return self.client.state.get_skills()

    @property
    def boosts(self) -> BoosterInfoResponse | None:
        """Your boosters, premium account, production slots and festival; None until a ``boi`` arrived."""
        return self.client.state.get_boosts()

    @property
    def might(self) -> MightPointsResponse | None:
        """Your might points, from the last ``gmu``; None until one arrived."""
        return self.client.state.get_might()

    @property
    def glory_points(self) -> GloryPointsResponse | None:
        """Your glory points, from the last ``ufa``; None until one arrived."""
        return self.client.state.get_glory_points()

    @property
    def faction_points(self) -> FactionPointsResponse | None:
        """Your Berimond points, from the last ``ufp`` push; None until one arrived (the login data has none)."""
        return self.client.state.get_faction_points()

    @property
    def title_ranks(self) -> TitleRanksResponse | None:
        """Your top-X ranks, Storm Islands title and displayed title systems, from the last ``uar``; None before one."""
        return self.client.state.get_title_ranks()

    @property
    def achievements(self) -> AchievementsResponse | None:
        """Your achievement points, finished achievements and progress; None until a ``vli`` arrived."""
        return self.client.state.get_achievements()

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

    @property
    def daily_reset(self) -> DailyResetResponse | None:
        """When the daily reset comes, from the login data's ``drt``; None until it arrived."""
        return self.client.state.get_daily_reset()

    @property
    def gifts(self) -> PlayerGiftsResponse | None:
        """Your gift packages and how many you may still send, from the last ``pgl``; None until one arrived."""
        return self.client.state.get_player_gifts()

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

    on_skill_list = Event[SkillList]()
    """
    Register a callback for every skill list the server sends.

    That is each ``skl`` packet, including the reply to :meth:`get_skills`,
    and the ``skl`` block of an ``ego`` push.

    Client: ``SKLCommand.executeCommand`` (bundle line 129742) and
    ``EGOCommand.executeCommand`` (bundle line 122801) both call ``parse_SKL``.

    Removing a callback not registered is a no-op.
    """

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
