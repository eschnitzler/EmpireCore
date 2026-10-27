"""
Other players' details, player search and your legend skills.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from empire_core.commanders.models.skills import GetSkillsResponse, ObjectUpdateEvent, SkillList
from empire_core.exceptions import EmpireError
from empire_core.player.models.account import FoodProductionStatus
from empire_core.player.models.progress import AchievementFinishedResponse, GetTitleRanksRequest
from empire_core.player.service.account import AccountMixin
from empire_core.player.service.base import PlayerBaseMixin
from empire_core.player.service.players import PlayerDetailsBulkResult, PlayersMixin
from empire_core.player.service.protection import ProtectionMixin
from empire_core.player.service.skills import SkillsMixin
from empire_core.player.service.standing import StandingMixin
from empire_core.player.service.training import TrainingMixin
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


class PlayerService(
    StandingMixin, TrainingMixin, AccountMixin, ProtectionMixin, PlayersMixin, SkillsMixin, PlayerBaseMixin, BaseService
):
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
        self.on_response("DTS", self._handle_food_production)

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

    on_food_production = Event[FoodProductionStatus]()
    """
    Register a callback for each food production status the server sends: the login data's ``DTS``
    and each ``DTS`` push, after :attr:`food_production` has it.

    Client: ``CastleUserData.parse_DTS`` (bundle line 9925) fires ``DOWNTIME_STATUS_UPDATED`` on each one

    Removing a callback not registered is a no-op.
    """

    def _handle_food_production(self, response: BaseResponse) -> None:
        if isinstance(response, FoodProductionStatus):
            self._fire(self.on_food_production, response)


__all__ = ["PlayerDetailsBulkResult", "PlayerService"]
