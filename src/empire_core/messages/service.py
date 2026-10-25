"""
The mailbox, mail and battle reports.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from empire_core.enums import GGEError
from empire_core.exceptions import CommandError, MessageUnavailableError
from empire_core.messages.models import (
    MAX_SUBJECT_LENGTH,
    MAX_TEXT_LENGTH,
    MIN_TEXT_LENGTH,
    ArchiveMessageRequest,
    ArchiveMessageResponse,
    BattleLogDetailResponse,
    BattleLogMiddleResponse,
    BattleLogShortResponse,
    BattleReport,
    DeleteMessageRequest,
    DeleteMessagesRequest,
    DeleteMessagesResponse,
    ForwardBattleLogRequest,
    GetBattleLogDetailRequest,
    GetBattleLogMiddleRequest,
    GetBattleLogShortRequest,
    GetIgnoredPlayersRequest,
    GetTradeReportRequest,
    GetWorldLinkRequest,
    IgnoredPlayer,
    IgnoredPlayersResponse,
    IgnorePlayerRequest,
    IgnorePlayerResponse,
    MarkMessageReadRequest,
    MessageInfo,
    ReadMessageRequest,
    ReadMessageResponse,
    SendMessageRequest,
    SendMessageResponse,
    ServerMessage,
    ServerShutdownWarning,
    SystemNotificationEvent,
    TradeReportResponse,
    WorldLinkResponse,
)
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

_WHITESPACE = re.compile(r"\s")

BattleReportDetail = Literal["short", "middle", "full"]
_DETAILS = ("short", "middle", "full")


class MessagesService(BaseService):
    """
    The mailbox, mail and battle reports.

    Accessible via client.messages. The mailbox is kept as the client keeps it
    (``CastleMessageData``, bundle lines 134955-134991).
    """

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self.on_response("sne", self._handle_update)
        self.on_response("smg", self._handle_server_message)
        self.on_response("ssd", self._handle_server_shutdown)

    @property
    def mailbox(self) -> list[MessageInfo]:
        """
        The messages from the login data and the pushes since, in the order they first arrived; nothing is sent.

        Emptied when the session drops, as the client empties it; the next login's ``sne`` refills it.
        """
        return self.client.state.get_mailbox()

    on_new_messages = Event[SystemNotificationEvent]()
    """Call ``callback`` with the login data's sne section and each sne push, after :attr:`mailbox` is updated.

    Removing a callback not registered is a no-op.
    """

    def _handle_update(self, response: BaseResponse) -> None:
        if isinstance(response, SystemNotificationEvent):
            self._fire(self.on_new_messages, response)

    on_server_message = Event[ServerMessage]()
    """Call ``callback`` with each server message pushed (``smg``).

    Removing a callback not registered is a no-op.
    """

    def _handle_server_message(self, response: BaseResponse) -> None:
        if isinstance(response, ServerMessage):
            self._fire(self.on_server_message, response)

    on_server_shutdown = Event[ServerShutdownWarning]()
    """Call ``callback`` when the server warns it is about to shut down (``ssd``); the client says in a minute.

    Removing a callback not registered is a no-op.
    """

    def _handle_server_shutdown(self, response: BaseResponse) -> None:
        if isinstance(response, ServerShutdownWarning):
            self._fire(self.on_server_shutdown, response)

    def read(self, message_id: int, *, timeout: float = 5.0) -> ReadMessageResponse:
        """
        Read a message's body.

        Args:
            message_id: The message's ``MessageInfo.message_id``, e.g. from :attr:`mailbox`

        Raises:
            MessageUnavailableError: error 66 (no such message) or 225 (too old to read), which the client
                answers alike (``RMSCommand.executeCommand``, bundle line 125454)
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        try:
            return self.request(ReadMessageRequest(message_id=message_id), ReadMessageResponse, timeout=timeout)
        except CommandError as e:
            if e.error in (GGEError.NO_SUCH_MESSAGE, GGEError.MESSAGEDATA_TOO_OLD):
                raise MessageUnavailableError(e.command, e.code, e.payload) from e
            raise

    def mark_read(self, message_id: int) -> None:
        """
        Mark a message read. The client has no handler for an answer, so none is waited for.

        The message in :attr:`mailbox` is marked read too, as the client marks its own copy.
        """
        self.send(MarkMessageReadRequest(message_id=message_id))
        self.client.state.mark_message_read(message_id)

    def archive(self, message_id: int, *, timeout: float = 5.0) -> None:
        """
        Move a message to the archive, which holds 20.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        self.request(ArchiveMessageRequest(message_id=message_id), ArchiveMessageResponse, timeout=timeout)

    def delete(self, message_id: int, *, timeout: float = 5.0) -> list[int]:
        """
        Delete one message.

        Returns:
            The ids the server reports deleted

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(
            DeleteMessageRequest(message_id=message_id), DeleteMessagesResponse, timeout=timeout
        ).message_ids

    def delete_many(self, message_ids: list[int], *, timeout: float = 5.0) -> list[int]:
        """
        Delete several messages at once.

        Returns:
            The ids the server reports deleted

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        request = DeleteMessagesRequest(message_ids=list(message_ids))
        return self.request(request, DeleteMessagesResponse, timeout=timeout).message_ids

    def send_message(self, receiver_name: str, subject: str, text: str, *, timeout: float = 5.0) -> None:
        """
        Send a message to a player.

        The limits are the client's: a subject of at most 20 characters, and a
        text of at most 1300 with at least 3 that are not whitespace
        (``ClientConstMessage.isValidText``, bundle line 44214). The receiver's
        name field takes 15 characters, more on special and crossplay servers,
        so its length is left to the server.

        Raises:
            ValueError: the receiver is empty, or the subject or text breaks a limit
            CommandError: the server refused the message, e.g. error 68 (no such receiver),
                69 (the receiver ignores you) or 70 (a bad word)
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        if not receiver_name:
            raise ValueError("a message needs a receiver")
        if len(subject) > MAX_SUBJECT_LENGTH:
            raise ValueError(f"a subject takes at most {MAX_SUBJECT_LENGTH} characters")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"a text takes at most {MAX_TEXT_LENGTH} characters")
        if len(_WHITESPACE.sub("", text)) < MIN_TEXT_LENGTH:
            raise ValueError(f"a text needs at least {MIN_TEXT_LENGTH} characters that are not whitespace")
        self.request(SendMessageRequest.create(receiver_name, subject, text), SendMessageResponse, timeout=timeout)

    def get_battle_report(
        self, message_id: int, detail: BattleReportDetail = "short", *, timeout: float = 5.0
    ) -> BattleReport:
        """
        Read a battle report from the mailbox.

        The short log comes first, a ``bls`` with ``IM`` 0 as the client always sends it;
        the middle and detail logs are then asked for by its ``log_id``, one request each,
        as the client asks when its battle report dialogs open them.

        Args:
            message_id: A battle log's ``MessageInfo.message_id``: one in :attr:`mailbox`
                whose ``is_battle_log`` is true
            detail: ``"short"`` for the overview (players, loot, area, commanders),
                ``"middle"`` adds the waves per flank, ``"full"`` adds every unit per flank and wave

        Raises:
            ValueError: ``detail`` is none of the three
            MessageUnavailableError: error 66 (no such message) or 225 (too old to read) for the short
                log, which the client shows as a log that does not exist (``BLSCommand``, bundle line 125196)
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleMessageData.getBattleLogShort``, ``getBattleLogMiddle`` and
        ``getBattleLogDetailed`` (bundle lines 134905-134907)
        """
        if detail not in _DETAILS:
            raise ValueError(f"detail must be one of {_DETAILS}, not {detail!r}")
        request = GetBattleLogShortRequest(message_id=message_id, include_details=0)
        try:
            short = self.request(request, BattleLogShortResponse, timeout=timeout)
        except CommandError as e:
            if e.error in (GGEError.NO_SUCH_MESSAGE, GGEError.MESSAGEDATA_TOO_OLD):
                raise MessageUnavailableError(e.command, e.code, e.payload) from e
            raise
        if detail == "short":
            return BattleReport(short)
        middle = self.request(GetBattleLogMiddleRequest(log_id=short.log_id), BattleLogMiddleResponse, timeout=timeout)
        if detail == "middle":
            return BattleReport(short, middle)
        full = self.request(GetBattleLogDetailRequest(log_id=short.log_id), BattleLogDetailResponse, timeout=timeout)
        return BattleReport(short, middle, full)

    def get_trade_report(self, message_id: int, *, timeout: float = 5.0) -> TradeReportResponse:
        """
        Read a market carriage's report from the mailbox: its two areas and the goods.

        Args:
            message_id: A trade message's ``MessageInfo.message_id``

        Client: ``CastleTradeMessageDialog.requestTradeData`` (bundle line 136636) sends
        ``C2SMarketCarriageNotifyVO``; ``MMNCommand.executeCommand`` (bundle line 125460)
        """
        return self.request(GetTradeReportRequest(message_id=message_id), TradeReportResponse, timeout=timeout)

    def forward_battle_report(self, message_id: int, player_ids: list[int], *, timeout: float = 5.0) -> None:
        """
        Forward a battle report to other players.

        Args:
            message_id: A battle log's ``MessageInfo.message_id``
            player_ids: The recipients. The client offers the members of your alliance
                other than you, ``AllianceMember.player_id`` from ``client.alliance.get_local_members()``

        Raises:
            ValueError: no recipients
            CommandError: the server refused; the client handles no error specially
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleForwardMessageDialog.sendMessage`` (bundle line 60740),
        ``MFBCommand.executeCommand`` (bundle line 125396)
        """
        if not player_ids:
            raise ValueError("a battle report needs at least one recipient")
        self.send(
            ForwardBattleLogRequest(message_id=message_id, player_ids=list(player_ids)), wait=True, timeout=timeout
        )

    def get_ignored_players(self, *, timeout: float = 5.0) -> list[IgnoredPlayer]:
        """
        The players you ignore, whose mail does not reach you.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleMessageData.getIgnoredPlayer`` (bundle line 135009), ``ILICommand`` (bundle line 125319)
        """
        return self.request(GetIgnoredPlayersRequest(), IgnoredPlayersResponse, timeout=timeout).players

    def ignore(self, player_id: int, *, timeout: float = 5.0) -> list[IgnoredPlayer]:
        """
        Ignore a player.

        Args:
            player_id: The player: a ``MessageInfo.sender_id``, or
                ``client.player.search_player_by_name(name).get_player().owner_id``

        Returns:
            The players you ignore now

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleMessageData.ignorePlayer`` (bundle line 135008), ``IPLCommand`` (bundle line 125334)
        """
        request = IgnorePlayerRequest(player_id=player_id, ignore=True)
        return self.request(request, IgnorePlayerResponse, timeout=timeout).ignore_list.players

    def unignore(self, player_id: int, *, timeout: float = 5.0) -> list[IgnoredPlayer]:
        """
        Stop ignoring a player.

        Args:
            player_id: An ``IgnoredPlayer.player_id`` from :meth:`get_ignored_players`

        Returns:
            The players you ignore now

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``PlayerIgnoreList_Item.unignorePlayer`` (bundle line 106828), ``IPLCommand`` (bundle line 125334)
        """
        request = IgnorePlayerRequest(player_id=player_id, ignore=False)
        return self.request(request, IgnorePlayerResponse, timeout=timeout).ignore_list.players

    def get_world_link(self, zone_id: int, website_id: int, *, timeout: float = 5.0) -> str:
        """
        Request the link to a new world a mail announces (gil): the zone and website ids are the mail's.

        Client: ``CastleNewServerAnnounceDialogProperties`` (bundle line 137138), ``GILCommand.executeCommand``
        (bundle line 128173)
        """
        return self.request(
            GetWorldLinkRequest(website_id=website_id, zone_id=zone_id), WorldLinkResponse, timeout=timeout
        ).url


__all__ = ["BattleReportDetail", "MessagesService"]
