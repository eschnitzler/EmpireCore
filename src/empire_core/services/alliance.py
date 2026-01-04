"""
Alliance service for EmpireCore.

Provides high-level APIs for:
- Alliance chat (send messages, get history)
- Alliance help (help members, help all, request help)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from empire_core.protocol.models import (
    AllianceChatLogRequest,
    AllianceChatLogResponse,
    AllianceChatMessageRequest,
    AllianceChatMessageResponse,
    AskHelpRequest,
    ChatLogEntry,
    HelpAllRequest,
    HelpAllResponse,
    HelpMemberRequest,
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

        # Register internal handler for chat messages
        self.on_response("acm", self._handle_chat_message)

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


__all__ = ["AllianceService"]
