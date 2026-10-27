"""The alliance forum, chat and help requests."""

from __future__ import annotations

from empire_core.alliance.models.chat import (
    AllianceChatLogRequest,
    AllianceChatLogResponse,
    AllianceChatMessageRequest,
    AllianceChatMessageResponse,
    ChatMessageData,
)
from empire_core.alliance.models.forum import (
    CreateForumTopicRequest,
    DeleteForumReplyRequest,
    DeleteForumTopicRequest,
    GetForumTopicRequest,
    GetForumTopicResponse,
    GetForumTopicsRequest,
    GetForumTopicsResponse,
    GetUnreadTopicCountRequest,
    GetUnreadTopicCountResponse,
    ReplyToForumTopicRequest,
    SetForumVisibilityRequest,
    SetForumVisibilityResponse,
    forum_text,
)
from empire_core.alliance.models.help import (
    AllianceHelpListResponse,
    AllianceHelpReceived,
    AllianceHelpRequest,
    AllianceHelpRequestChanged,
    AllianceHelpRequestRemoved,
    AskHelpRequest,
    HelpAllRequest,
    HelpMemberRequest,
)
from empire_core.alliance.service.own import OwnAllianceMixin
from empire_core.enums import ForumRankGroup, HelpType
from empire_core.protocol.base import BaseResponse
from empire_core.utils.callbacks import Event

AllianceHelpUpdate = (
    AllianceHelpListResponse | AllianceHelpRequestChanged | AllianceHelpRequestRemoved | AllianceHelpReceived
)


class CommunicationMixin(OwnAllianceMixin):
    def create_topic(self, name: str, text: str, visible_ranks: list[ForumRankGroup], *, timeout: float = 5.0) -> None:
        """Create a forum topic with explicit visibility groups and an opening post.

        Titles must encode to 2–38 characters and posts to 2–2000. Server permission
        refusals raise CommandError. No created id is returned by the client handler.
        """
        forum_text(name, 38)
        forum_text(text, 2000)
        with self._own_alliance():
            self.execute(CreateForumTopicRequest(name=name, text=text, visible_ranks=visible_ranks), timeout=timeout)

    def reply(self, topic_id: int, text: str, *, timeout: float = 5.0) -> None:
        """Post a reply to a forum topic; permission refusals raise CommandError."""
        forum_text(text, 2000)
        with self._own_alliance():
            self.execute(ReplyToForumTopicRequest(topic_id=topic_id, text=text), timeout=timeout)

    def delete_topic(self, topic_id: int, *, timeout: float = 5.0) -> None:
        """Delete a forum topic; permission refusals raise CommandError."""
        with self._own_alliance():
            self.execute(DeleteForumTopicRequest(topic_id=topic_id), timeout=timeout)

    def delete_reply(self, topic_id: int, reply_id: int, *, timeout: float = 5.0) -> None:
        """Delete a forum post; permission refusals raise CommandError."""
        with self._own_alliance():
            self.execute(DeleteForumReplyRequest(topic_id=topic_id, reply_id=reply_id), timeout=timeout)

    def set_topic_visibility(
        self, topic_id: int, visible_ranks: list[ForumRankGroup], *, timeout: float = 5.0
    ) -> GetForumTopicResponse | None:
        """Change the rank groups that can see a topic, returning its details when echoed."""
        with self._own_alliance():
            return self.request(
                SetForumVisibilityRequest(topic_id=topic_id, visible_ranks=visible_ranks),
                SetForumVisibilityResponse,
                timeout=timeout,
            ).topic

    def get_forum_topics(self, *, timeout: float = 5.0) -> GetForumTopicsResponse:
        """Get visible forum topics, newest post first, and the total including hidden topics."""
        with self._own_alliance():
            return self.request(GetForumTopicsRequest(), GetForumTopicsResponse, timeout=timeout)

    def get_topic(self, topic_id: int, *, timeout: float = 5.0) -> GetForumTopicResponse:
        """Open a forum topic and its posts. Opening it may mark it read on the server.

        Client: ``CastleForumViewTopic.requestTopicData`` sends ``gtr`` (bundle line 33651);
        ``GTRCommand.executeCommand`` (bundle line 121768) reads the topic, with
        unread counts delivered separately by ``UTCCommand`` (bundle line 121785).
        """
        with self._own_alliance():
            return self.request(GetForumTopicRequest(topic_id=topic_id), GetForumTopicResponse, timeout=timeout)

    def get_unread_topic_count(self, *, timeout: float = 5.0) -> int:
        """Request the number of unread forum topics."""
        with self._own_alliance():
            return self.request(GetUnreadTopicCountRequest(), GetUnreadTopicCountResponse, timeout=timeout).count

    # =========================================================================
    # Chat Operations
    # =========================================================================

    def send_chat(self, message: str) -> None:
        """
        Send a message to alliance chat.

        Args:
            message: The message text to send (will be auto-encoded)

        Example:
            client.alliance.send_chat("Hello alliance!")
            client.alliance.send_chat("Special chars work: 100% safe!")
        """
        request = AllianceChatMessageRequest.create(message)
        self.send(request)

    def get_chat_log(self, *, timeout: float = 5.0) -> list[ChatMessageData]:
        """
        Get alliance chat history.

        The game client never asks for acl; it only reads the acl the server
        sends, which a live server pushes once at login. A live server also
        answers this request, with the same ``CM`` list.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            The messages of the acl reply's ``CM`` list

        Example:
            history = client.alliance.get_chat_log()
            for entry in history:
                print(f"{entry.player_name}: {entry.decoded_text}")
        """
        return self.request(AllianceChatLogRequest(), AllianceChatLogResponse, timeout=timeout).chat_log

    on_chat_message = Event[AllianceChatMessageResponse]()
    """
    Register a callback for incoming alliance chat messages.

    The callback will be called whenever a chat message is received,
    including messages from other players and confirmations of your own.

    Callbacks run on the receive thread: they must not block, and a call
    that waits for a reply raises ``ReceiveThreadError``.

    Args:
        callback: Function that receives AllianceChatMessageResponse

    Example:
        def on_message(msg: AllianceChatMessageResponse):
            print(f"[{msg.player_name}] {msg.decoded_text}")

        client.alliance.on_chat_message(on_message)

    ``on_chat_message.remove(callback)`` detaches it, a no-op if it is not
    registered, so reconnect re-wiring can detach unconditionally.
    """

    def _handle_chat_message(self, response) -> None:
        """Internal handler for chat message responses."""
        if isinstance(response, AllianceChatMessageResponse):
            self._fire(self.on_chat_message, response)

    # =========================================================================
    # Help Operations
    # =========================================================================

    @property
    def help_requests(self) -> list[AllianceHelpRequest]:
        """
        The alliance help list as the login data and the pushes since left it; nothing is sent.

        The login data's ``ahl`` section fills it, and so does an ahl push; ahh replaces or adds a
        request by ``LID``, ahd removes one, and leaving your alliance empties it. It is kept when
        the session drops, as the client keeps it.
        """
        return self.client.state.get_alliance_help()

    on_help_update = Event[AllianceHelpUpdate]()
    """
    Call ``callback`` with the login data's ahl section and each ahl, ahh, ahd and ahf push,
    after :attr:`help_requests` is updated.

    Detach it again with ``on_help_update.remove(callback)``, a no-op if it is not registered.
    """

    def _handle_help_update(self, response: BaseResponse) -> None:
        if isinstance(response, AllianceHelpRequestChanged) and response.request is None:
            return
        if isinstance(response, AllianceHelpUpdate):
            self._fire(self.on_help_update, response)

    def help_member(self, request: AllianceHelpRequest | int) -> None:
        """
        Help one request on the help list.

        The client has no handler for an ahc answer, so none is waited for.

        Args:
            request: An :class:`AllianceHelpRequest` from :attr:`help_requests`, or its ``list_id``
        """
        list_id = request.list_id if isinstance(request, AllianceHelpRequest) else request
        self.send(HelpMemberRequest(list_id=list_id))

    def help_all(self) -> None:
        """
        Help every request on the help list.

        The client has no handler for an aha answer, so none is waited for.
        """
        self.send(HelpAllRequest())

    def request_build_help(self, building_id: int, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help build a building.

        Args:
            building_id: The building's object id, e.g. ``BuildResponse.building_id``
        """
        self.execute(AskHelpRequest.build(building_id), timeout=timeout)

    def request_repair_help(self, building_id: int, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help repair a building.

        Args:
            building_id: The damaged building's object id
        """
        self.execute(AskHelpRequest.repair(building_id), timeout=timeout)

    def request_recruit_help(self, recruit_id: int, help_type: HelpType, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help with a recruitment.

        Args:
            recruit_id: The recruitment's id; the library does not read recruitment ids yet
            help_type: ``HelpType.RECRUITMENT``, ``LOOP_RECRUIT`` or ``RECRUITMENT_LIST``
        """
        self.execute(AskHelpRequest.recruit(recruit_id, help_type), timeout=timeout)

    def request_heal_help(self, hospital_entry_id: int, hospital_list_id: int, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help heal wounded units.

        Args:
            hospital_entry_id: The hospital entry; the library does not read hospital entry ids yet
            hospital_list_id: The hospital list the entry is on
        """
        self.execute(AskHelpRequest.heal(hospital_entry_id, hospital_list_id), timeout=timeout)
