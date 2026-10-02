"""
The mailbox and mail.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable

from empire_core.exceptions import CommandError, MessageUnavailableError
from empire_core.messages.models import (
    MAX_SUBJECT_LENGTH,
    MAX_TEXT_LENGTH,
    MIN_TEXT_LENGTH,
    ArchiveMessageRequest,
    ArchiveMessageResponse,
    DeleteMessageRequest,
    DeleteMessagesRequest,
    DeleteMessagesResponse,
    MarkMessageReadRequest,
    MessageInfo,
    ReadMessageRequest,
    ReadMessageResponse,
    SendMessageRequest,
    SendMessageResponse,
    SystemNotificationEvent,
)
from empire_core.protocol.base import BaseResponse
from empire_core.protocol.errors import GGEError
from empire_core.services.base import BaseService

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s")


class MessagesService(BaseService):
    """
    The mailbox and mail.

    Accessible via client.messages. The mailbox is kept as the client keeps it:
    the login data's ``sne`` section fills it, each sne push row replaces the
    message with its id or is added, and dms and ams answers remove or archive.

    Client: ``CastleMessageData`` (bundle lines 134955-134991); ``GBDCommand.exec``
    (bundle line 129381) and ``SNECommand.exec`` (bundle line 125499) both call
    ``parse_SNE`` (bundle line 134961)
    """

    def __init__(self, client) -> None:
        super().__init__(client)
        self._mailbox: dict[int, MessageInfo] = {}
        self._mailbox_lock = threading.Lock()
        self._callbacks: list[Callable[[SystemNotificationEvent], None]] = []
        self.on_response("sne", self._handle_update)
        self.on_response("dms", self._handle_update)
        self.on_response("ams", self._handle_update)

    def _reset(self) -> None:
        """
        Empty the mailbox; the client calls this when the session drops, and the next login's gbd refills it.

        Client: ``CastleDestroyGameCommand`` (bundle line 120270) resets every model,
        and ``CastleMessageData.reset`` (bundle line 134889) empties the mailbox
        """
        with self._mailbox_lock:
            self._mailbox.clear()

    @property
    def mailbox(self) -> list[MessageInfo]:
        """The messages from the login data and the pushes since, in the order they first arrived."""
        with self._mailbox_lock:
            return list(self._mailbox.values())

    def on_new_messages(self, callback: Callable[[SystemNotificationEvent], None]) -> None:
        """Call ``callback`` with the login data's sne section and each sne push, after :attr:`mailbox` is updated."""
        self._callbacks.append(callback)

    def remove_new_messages_callback(self, callback: Callable[[SystemNotificationEvent], None]) -> None:
        """Remove a callback registered with :meth:`on_new_messages`; a no-op if it is not registered."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def _handle_update(self, response: BaseResponse) -> None:
        with self._mailbox_lock:
            self._apply_update(response)
        if isinstance(response, SystemNotificationEvent):
            for callback in list(self._callbacks):
                try:
                    callback(response)
                except Exception:
                    logger.exception("New messages callback error")

    def _apply_update(self, response: BaseResponse) -> None:
        if isinstance(response, SystemNotificationEvent):
            for message in response.messages:
                self._mailbox[message.message_id] = message
        elif isinstance(response, DeleteMessagesResponse):
            for message_id in response.message_ids:
                self._mailbox.pop(message_id, None)
        elif isinstance(response, ArchiveMessageResponse) and response.message_id is not None:
            archived = self._mailbox.get(response.message_id)
            if archived is not None:
                self._mailbox[response.message_id] = archived.model_copy(update={"is_archived": True})

    def read(self, message_id: int, timeout: float = 5.0) -> ReadMessageResponse:
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
        with self._mailbox_lock:
            message = self._mailbox.get(message_id)
            if message is not None:
                self._mailbox[message_id] = message.model_copy(update={"is_read": True})

    def archive(self, message_id: int, timeout: float = 5.0) -> ArchiveMessageResponse:
        """
        Move a message to the archive, which holds 20.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(ArchiveMessageRequest(message_id=message_id), ArchiveMessageResponse, timeout=timeout)

    def delete(self, message_id: int, timeout: float = 5.0) -> list[int]:
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

    def delete_many(self, message_ids: list[int], timeout: float = 5.0) -> list[int]:
        """
        Delete several messages at once.

        Returns:
            The ids the server reports deleted

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        request = DeleteMessagesRequest(message_ids=list(message_ids))
        return self.request(request, DeleteMessagesResponse, timeout=timeout).message_ids

    def send_message(self, receiver_name: str, subject: str, text: str, timeout: float = 5.0) -> None:
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


__all__ = ["MessagesService"]
