"""
Alliance service for EmpireCore.

Provides high-level APIs for:
- Alliance members (get members, online status, last seen)
- Alliance chat (send messages, get history)
- Alliance help (help members, help all, request help)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from empire_core.protocol.models import (
    AllianceBookmark,
    AllianceChatLogRequest,
    AllianceChatLogResponse,
    AllianceChatMessageRequest,
    AllianceChatMessageResponse,
    AllianceMember,
    AllianceSearchResult,
    AskHelpRequest,
    ChatLogEntry,
    GetAllianceBookmarksRequest,
    GetAllianceBookmarksResponse,
    GetAllianceInfoRequest,
    GetAllianceInfoResponse,
    HelpAllRequest,
    HelpAllResponse,
    HelpMemberRequest,
    SearchAllianceRequest,
    SearchAllianceResponse,
)

from .base import BaseService, register_service

if TYPE_CHECKING:
    pass


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

        # Help all members
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

        # Register internal handler for chat messages
        self.on_response("acm", self._handle_chat_message)

    # =========================================================================
    # Member Operations
    # =========================================================================

    def get_members(self, alliance_id: int, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get the list of alliance members from the server.

        This fetches alliance info and returns all members with their
        online status (via AMI array), level, rank, etc.

        Args:
            alliance_id: The alliance ID to get members for
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceMember objects

        Example:
            members = client.alliance.get_members(190426)
            for member in members:
                print(f"{member.name}: online={member.is_online}")
        """
        request = GetAllianceInfoRequest(AID=alliance_id)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, GetAllianceInfoResponse):
            # Update cached members
            self._members = {m.player_id: m for m in response.members}
            return response.members

        return []

    def get_online_members(self, alliance_id: int, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get alliance members who are currently online.

        Fetches the member list and filters to only online members
        (members with online status from AMI array).

        Args:
            alliance_id: The alliance ID to get members for
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
            player_id: The player's ID
            no_cache: If True, refresh alliance data from server first

        Returns:
            AllianceMember if found, None otherwise

        Example:
            member = client.alliance.get_member(12345)  # From cache
            member = client.alliance.get_member(12345, no_cache=True)  # Fresh data
        """
        if no_cache:
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
        """
        request = SearchAllianceRequest.create(search_term)
        packet = request.to_packet(zone=self.zone)
        self.client.connection.send(packet)

        try:
            response_packet = self.client.connection.wait_for("hgh", timeout=timeout)

            # Check for error code (e.g., 114 = not found)
            if response_packet.error_code != 0:
                return []

            if isinstance(response_packet.payload, dict):
                from empire_core.protocol.models import parse_response

                response = parse_response("hgh", response_packet.payload)
                if isinstance(response, SearchAllianceResponse):
                    return response.results
        except Exception:
            pass

        return []

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
            members = client.alliance.get_my_members()
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
            online = client.alliance.get_my_online_members()
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

    def get_chat_log(self, timeout: float = 5.0) -> list[ChatLogEntry]:
        """
        Get alliance chat history.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            List of ChatLogEntry objects

        Example:
            history = client.alliance.get_chat_log()
            for entry in history:
                print(f"{entry.player_name}: {entry.decoded_text}")
        """
        request = AllianceChatLogRequest()
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, AllianceChatLogResponse):
            return response.chat_log

        return []

    def on_chat_message(self, callback: Callable[[AllianceChatMessageResponse], None]) -> None:
        """
        Register a callback for incoming alliance chat messages.

        The callback will be called whenever a chat message is received,
        including messages from other players and confirmations of your own.

        Args:
            callback: Function that receives AllianceChatMessageResponse

        Example:
            def on_message(msg: AllianceChatMessageResponse):
                print(f"[{msg.player_name}] {msg.decoded_text}")

            client.alliance.on_chat_message(on_message)
        """
        self._chat_callbacks.append(callback)

    def _handle_chat_message(self, response) -> None:
        """Internal handler for chat message responses."""
        if isinstance(response, AllianceChatMessageResponse):
            for callback in self._chat_callbacks:
                try:
                    callback(response)
                except Exception:
                    pass  # Silently ignore callback errors

    # =========================================================================
    # Help Operations
    # =========================================================================

    def help_all(self) -> HelpAllResponse | None:
        """
        Help all alliance members who need help.

        Sends a single request that helps all pending help requests
        (heal, repair, recruit).

        Returns:
            HelpAllResponse with helped_count, or None on failure

        Example:
            response = client.alliance.help_all()
            if response:
                print(f"Helped {response.helped_count} members")
        """
        request = HelpAllRequest()
        response = self.send(request, wait=True, timeout=5.0)

        if isinstance(response, HelpAllResponse):
            return response

        return None

    def help_member_heal(self, player_id: int, castle_id: int) -> None:
        """
        Help heal a specific member's wounded soldiers.

        Args:
            player_id: The player's ID
            castle_id: The castle ID with wounded soldiers
        """
        request = HelpMemberRequest.heal(player_id, castle_id)
        self.send(request)

    def help_member_repair(self, player_id: int, castle_id: int) -> None:
        """
        Help repair a specific member's building.

        Args:
            player_id: The player's ID
            castle_id: The castle ID with damaged building
        """
        request = HelpMemberRequest.repair(player_id, castle_id)
        self.send(request)

    def help_member_recruit(self, player_id: int, castle_id: int) -> None:
        """
        Help a specific member with soldier recruitment.

        Args:
            player_id: The player's ID
            castle_id: The castle ID recruiting soldiers
        """
        request = HelpMemberRequest.recruit(player_id, castle_id)
        self.send(request)

    def request_heal_help(self, castle_id: int) -> None:
        """
        Request heal help from alliance for a castle.

        Args:
            castle_id: The castle ID with wounded soldiers
        """
        request = AskHelpRequest.heal(castle_id)
        self.send(request)

    def request_repair_help(self, castle_id: int, building_id: int) -> None:
        """
        Request repair help from alliance for a building.

        Args:
            castle_id: The castle ID
            building_id: The building ID that needs repair
        """
        request = AskHelpRequest.repair(castle_id, building_id)
        self.send(request)

    def request_recruit_help(self, castle_id: int) -> None:
        """
        Request recruit help from alliance for a castle.

        Args:
            castle_id: The castle ID recruiting soldiers
        """
        request = AskHelpRequest.recruit(castle_id)
        self.send(request)

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
        request = GetAllianceBookmarksRequest()
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, GetAllianceBookmarksResponse):
            return response.bookmarks

        return []


__all__ = ["AllianceService"]
