"""
Alliance service for EmpireCore.

Provides high-level APIs for:
- Alliance members (get members, online status, last seen)
- Alliance chat (send messages, get history)
- Alliance help (the help list and its pushes, helping, asking for help)
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import ValidationError

from empire_core.alliance.models.chat import (
    AllianceChatLogRequest,
    AllianceChatLogResponse,
    AllianceChatMessageRequest,
    AllianceChatMessageResponse,
    ChatMessageData,
)
from empire_core.alliance.models.help import (
    AllianceHelpListRequest,
    AllianceHelpListResponse,
    AllianceHelpReceived,
    AllianceHelpRequest,
    AllianceHelpRequestChanged,
    AllianceHelpRequestRemoved,
    AskHelpRequest,
    HelpAllRequest,
    HelpMemberRequest,
)
from empire_core.alliance.models.info import AllianceMember, GetAllianceInfoRequest, GetAllianceInfoResponse
from empire_core.alliance.models.search import (
    AllianceBookmark,
    AllianceSearchResult,
    GetAllianceBookmarksRequest,
    GetAllianceBookmarksResponse,
    SearchAllianceRequest,
    SearchAllianceResponse,
)
from empire_core.enums import HelpType
from empire_core.exceptions import CommandError, PacketError
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService, register_service

logger = logging.getLogger(__name__)

AllianceHelpUpdate = (
    AllianceHelpListResponse | AllianceHelpRequestChanged | AllianceHelpRequestRemoved | AllianceHelpReceived
)


@register_service("alliance")
class AllianceService(BaseService):
    """
    Service for alliance operations.

    Accessible via client.alliance after auto-registration.

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

    def __init__(self, client) -> None:
        super().__init__(client)
        self._chat_callbacks: list[Callable[[AllianceChatMessageResponse], None]] = []
        self._members: dict[int, AllianceMember] = {}
        self._members_alliance_id: int | None = None
        self._help_requests: list[AllianceHelpRequest] = []
        self._help_callbacks: list[Callable[[AllianceHelpUpdate], None]] = []

        self.on_response("acm", self._handle_chat_message)
        for command in ("ahl", "ahh", "ahd", "ahf"):
            self.on_response(command, self._handle_help_update)

    # =========================================================================
    # Member Operations
    # =========================================================================

    def get_alliance_info(self, alliance_id: int, timeout: float = 5.0) -> GetAllianceInfoResponse:
        """
        Get info about an alliance.

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another is an
                ``AllianceSearchResult.alliance_id`` from ``client.alliance.search_alliances()``
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetAllianceInfoRequest(AID=alliance_id), GetAllianceInfoResponse, timeout=timeout)

    def get_members(self, alliance_id: int, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get the list of alliance members from the server.

        This fetches alliance info and returns all members with their
        online status (via AMI array), level, rank, etc.

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another
                alliance's is ``AllianceSearchResult.alliance_id`` from :meth:`search_alliances`
                or a player's ``client.player.get_player_info(player_id).alliance_id``
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceMember objects

        Example:
            members = client.alliance.get_members(190426)
            for member in members:
                print(f"{member.name}: online={member.is_online}")
        """
        response = self.request(GetAllianceInfoRequest(AID=alliance_id), GetAllianceInfoResponse, timeout=timeout)
        # Update cached members and remember which alliance they belong to
        self._members = {m.player_id: m for m in response.members}
        self._members_alliance_id = alliance_id
        return response.members

    def get_online_members(self, alliance_id: int, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get alliance members who are currently online.

        Fetches the member list and filters to only online members
        (members with online status from AMI array).

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another
                alliance's is ``AllianceSearchResult.alliance_id`` from :meth:`search_alliances`
                or a player's ``client.player.get_player_info(player_id).alliance_id``
            timeout: Timeout in seconds to wait for response

        Returns:
            List of online AllianceMember objects

        Example:
            online = client.alliance.get_online_members(190426)
            print(f"{len(online)} members online")
        """
        members = self.get_members(alliance_id, timeout=timeout)
        return [m for m in members if m.is_online]

    def get_member(self, player_id: int, no_cache: bool = False) -> AllianceMember | None:
        """
        Get a specific member by player ID.

        Args:
            player_id: The member's ``AllianceMember.player_id``, as :meth:`get_members` lists it
            no_cache: If True, refresh alliance data from server first

        Returns:
            AllianceMember if found, None otherwise

        Example:
            member = client.alliance.get_member(12345)  # From cache
            member = client.alliance.get_member(12345, no_cache=True)  # Fresh data
        """
        if no_cache:
            # Refresh the alliance the cache actually belongs to, not
            # unconditionally the local one
            if self._members_alliance_id is not None:
                self.get_members(self._members_alliance_id)
            else:
                self.get_local_members()
        return self._members.get(player_id)

    @property
    def cached_members(self) -> dict[int, AllianceMember]:
        """
        Get the cached member dictionary.

        Returns members from the last get_members() call, keyed by player_id.
        Call get_members() to refresh.

        Returns:
            Dict mapping player_id to AllianceMember
        """
        return self._members.copy()

    # =========================================================================
    # Search Operations
    # =========================================================================

    def search_alliances(self, search_term: str, timeout: float = 5.0) -> list[AllianceSearchResult]:
        """
        Search for alliances by name.

        Args:
            search_term: The alliance name to search for (partial match)
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceSearchResult objects matching the search

        Example:
            results = client.alliance.search_alliances("HOPE")
            for alliance in results:
                print(f"{alliance.name} (ID: {alliance.alliance_id}, {alliance.member_count} members)")

        Note: 'hgh' is shared with the highscore command, so a concurrent
        get_highscore() call can receive this response (and vice versa) —
        the protocol offers no way to correlate them.
        """
        request = SearchAllianceRequest.create(search_term)
        packet = request.to_packet(zone=self.zone, room_id=self.client.connection.room_id)

        # connection.request registers the waiter before sending (race-free).
        # SearchAllianceResponse is instantiated manually because the 'hgh'
        # registry entry is owned by GetHighscoreResponse.
        response_packet = self.client.connection.request(packet, "hgh", timeout=timeout)

        # 114 = nothing found; a legitimate empty result
        if response_packet.error_code == 114:
            return []
        if response_packet.error_code != 0:
            raise CommandError("hgh", response_packet.error_code)

        if not isinstance(response_packet.payload, dict):
            return []
        try:
            response = SearchAllianceResponse.model_validate(response_packet.payload)
        except ValidationError as e:
            # PacketError is the documented parse-failure type of request();
            # a raw pydantic error must not leak out of the service layer.
            raise PacketError(f"Could not parse 'hgh' response: {e}") from e

        logger.debug(f"Alliance search found {len(response.results)} results")
        return list(response.results)

    # =========================================================================
    # Own Alliance Operations
    # =========================================================================

    @property
    def local_alliance_id(self) -> int | None:
        """
        Get the local player's alliance ID.

        Returns:
            Alliance ID if in an alliance, None otherwise
        """
        if self.client.state.local_player:
            return self.client.state.local_player.alliance_id
        return None

    def get_local_members(self, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get members of the local player's alliance.

        Convenience method that automatically uses the logged-in player's
        alliance ID.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceMember objects, empty list if not in alliance

        Example:
            members = client.alliance.get_local_members()
            for member in members:
                print(f"{member.name}: {'online' if member.is_online else 'offline'}")
        """
        alliance_id = self.local_alliance_id
        if alliance_id is None:
            return []
        return self.get_members(alliance_id, timeout=timeout)

    def get_local_online_members(self, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get online members of the local player's alliance.

        Convenience method that automatically uses the logged-in player's
        alliance ID and filters to online members only.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            List of online AllianceMember objects, empty list if not in alliance

        Example:
            online = client.alliance.get_local_online_members()
            print(f"{len(online)} alliance members online")
        """
        alliance_id = self.local_alliance_id
        if alliance_id is None:
            return []
        return self.get_online_members(alliance_id, timeout=timeout)

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

    def get_chat_log(self, timeout: float = 5.0) -> list[ChatMessageData]:
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

    def on_chat_message(self, callback: Callable[[AllianceChatMessageResponse], None]) -> None:
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
        """
        self._chat_callbacks.append(callback)

    def remove_chat_message_callback(self, callback: Callable[[AllianceChatMessageResponse], None]) -> None:
        """Remove a callback registered with :meth:`on_chat_message`.

        No-op if the callback is not registered, so reconnect re-wiring can
        detach unconditionally.
        """
        try:
            self._chat_callbacks.remove(callback)
        except ValueError:
            pass

    def _handle_chat_message(self, response) -> None:
        """Internal handler for chat message responses."""
        if isinstance(response, AllianceChatMessageResponse):
            for callback in self._chat_callbacks:
                try:
                    callback(response)
                except Exception:
                    logger.exception("Chat message callback error")

    # =========================================================================
    # Help Operations
    # =========================================================================

    @property
    def help_requests(self) -> list[AllianceHelpRequest]:
        """
        The alliance help list as the ahl, ahh and ahd pushes left it.

        Client: ``AllianceHelpRequestData`` (bundle line 133359) keeps the list
        the same way: ahl replaces it, ahh replaces or adds by ``LID``, ahd removes by ``LID``
        """
        return list(self._help_requests)

    def get_help_requests(self, timeout: float = 5.0) -> AllianceHelpListResponse:
        """
        Ask the server for the alliance help list.

        The game client never asks for ahl, it only reads the ahl the server
        sends; whether the server answers this request is unverified. The
        reply also refreshes :attr:`help_requests`.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(AllianceHelpListRequest(), AllianceHelpListResponse, timeout=timeout)

    def on_help_update(self, callback: Callable[[AllianceHelpUpdate], None]) -> None:
        """
        Call ``callback`` with each ahl, ahh, ahd and ahf the server sends, after :attr:`help_requests` is updated.

        Detach it again with :meth:`remove_help_update_callback`.
        """
        self._help_callbacks.append(callback)

    def remove_help_update_callback(self, callback: Callable[[AllianceHelpUpdate], None]) -> None:
        """Remove a callback registered with :meth:`on_help_update`; a no-op if it is not registered."""
        try:
            self._help_callbacks.remove(callback)
        except ValueError:
            pass

    def _handle_help_update(self, response: BaseResponse) -> None:
        if isinstance(response, AllianceHelpListResponse):
            self._help_requests = list(response.requests)
        elif isinstance(response, AllianceHelpRequestChanged) and response.request is not None:
            changed = response.request
            index = next((i for i, r in enumerate(self._help_requests) if r.list_id == changed.list_id), None)
            if index is None:
                self._help_requests.append(changed)
            else:
                self._help_requests[index] = changed
        elif isinstance(response, AllianceHelpRequestRemoved):
            self._help_requests = [r for r in self._help_requests if r.list_id != response.list_id]
        elif not isinstance(response, AllianceHelpReceived):
            return
        for callback in list(self._help_callbacks):
            try:
                callback(response)
            except Exception:
                logger.exception("Help update callback error")

    def help_member(self, request: AllianceHelpRequest | int) -> None:
        """
        Help one request on the help list.

        The client has no handler for an ahc answer, so none is waited for.

        Args:
            request: An :class:`AllianceHelpRequest` from :attr:`help_requests`, or its ``list_id``
        """
        list_id = request.list_id if isinstance(request, AllianceHelpRequest) else request
        self.send(HelpMemberRequest(LID=list_id))

    def help_all(self) -> None:
        """
        Help every request on the help list.

        The client has no handler for an aha answer, so none is waited for.
        """
        self.send(HelpAllRequest())

    def request_build_help(self, building_id: int, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help build a building.

        Args:
            building_id: The building's object id, e.g. ``BuildResponse.building_id``

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.build(building_id), timeout=timeout)

    def request_repair_help(self, building_id: int, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help repair a building.

        Args:
            building_id: The damaged building's object id

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.repair(building_id), timeout=timeout)

    def request_recruit_help(self, recruit_id: int, help_type: HelpType, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help with a recruitment.

        Args:
            recruit_id: The recruitment's id; the library does not read recruitment ids yet
            help_type: ``HelpType.RECRUITMENT``, ``LOOP_RECRUIT`` or ``RECRUITMENT_LIST``

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.recruit(recruit_id, help_type), timeout=timeout)

    def request_heal_help(self, hospital_entry_id: int, hospital_list_id: int, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help heal wounded units.

        Args:
            hospital_entry_id: The hospital entry; the library does not read hospital entry ids yet
            hospital_list_id: The hospital list the entry is on

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.heal(hospital_entry_id, hospital_list_id), timeout=timeout)

    # =========================================================================
    # Bookmark Operations
    # =========================================================================

    def get_bookmarks(self, timeout: float = 5.0) -> list[AllianceBookmark]:
        """
        Get alliance bookmarks.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceBookmark objects
        """
        return self.request(GetAllianceBookmarksRequest(), GetAllianceBookmarksResponse, timeout=timeout).bookmarks


__all__ = ["AllianceHelpUpdate", "AllianceService"]
