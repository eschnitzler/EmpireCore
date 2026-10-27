"""
Your alliance and others: members, chat, help, diplomacy and the treasury.

It covers:

- Alliance members (get members, online status, last seen)
- Member management (kick, rank, invite, applications, leave)
- Diplomacy, auto war, the newsletter and treasury donations
- Alliance chat (send messages, get history)
- Alliance help (the help list and its pushes, helping, asking for help)
- Your alliance's chronicle and subscriber count
- Map bookmarks, your own and your alliance's (list, add, change, delete)
- Joining automatically, members' aqua points and the alliance forge
- Beyond the Horizon: entry, performance, influence, centers of power and alliance towers
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.alliance.models.chat import ChatMessageData
from empire_core.alliance.models.info import AllianceInfo
from empire_core.alliance.service.bookmarks import BookmarksMixin
from empire_core.alliance.service.communication import AllianceHelpUpdate, CommunicationMixin
from empire_core.alliance.service.diplomacy import DiplomacyMixin
from empire_core.alliance.service.horizon import HorizonMixin
from empire_core.alliance.service.management import MemberManagementMixin
from empire_core.alliance.service.own import OwnAllianceMixin
from empire_core.alliance.service.settings import AllianceSettingsMixin
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient


class AllianceService(
    AllianceSettingsMixin,
    MemberManagementMixin,
    DiplomacyMixin,
    HorizonMixin,
    CommunicationMixin,
    BookmarksMixin,
    OwnAllianceMixin,
    BaseService,
):
    """
    Alliance chat, help, members, applications, diplomacy and the treasury.

    Reached as client.alliance.

    Usage:
        client = EmpireClient(...)
        client.login()

        # Send chat message
        client.alliance.send_chat("Hello alliance!")

        # Help every request on the alliance help list
        client.alliance.help_all()

        # Subscribe to incoming messages
        def on_message(response: AllianceChatMessageResponse):
            print(f"{response.player_name}: {response.decoded_text}")

        client.alliance.on_chat_message(on_message)
    """

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)

        self.on_response("acm", self._handle_chat_message)
        for command in ("ahl", "ahh", "ahd", "ahf"):
            self.on_response(command, self._handle_help_update)

    @property
    def own_alliance(self) -> AllianceInfo | None:
        """Your alliance's details and members, from the last ``ain`` about it; None in no alliance or before one."""
        return self.client.state.get_own_alliance()

    @property
    def chat(self) -> list[ChatMessageData]:
        """The alliance chat history, oldest first; a copy of the list, of read-only messages."""
        return self.client.state.get_alliance_chat()


__all__ = ["AllianceHelpUpdate", "AllianceService"]
