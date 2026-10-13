"""The mailbox: the login data's sne section, the sne pushes, and the dms and ams replies."""

from typing import Any

from empire_core.messages.models import (
    ArchiveMessageResponse,
    DeleteMessagesResponse,
    MessageInfo,
    SystemNotificationEvent,
)
from empire_core.state.base import StateBase, read_section


class MailboxState(StateBase):
    def _parse_mailbox(self, data: dict[str, Any]) -> bool:
        """Apply the login data's ``sne`` section; whether it was applied."""
        if "sne" not in data:
            return False
        return self._handle_sne(data["sne"])

    def _handle_sne(self, data: Any) -> bool:
        """Add or replace the messages an ``sne`` names, by message id.

        Client: ``GBDCommand.exec`` (bundle line 129381) and ``SNECommand.exec`` (bundle line 125499)
        both call ``parse_SNE`` (bundle line 134961)
        """
        event = read_section(SystemNotificationEvent, data, "the mailbox messages")
        if event is None:
            return False
        self.mailbox = {**self.mailbox, **{message.message_id: message for message in event.messages}}
        return True

    def _handle_dms(self, data: Any) -> None:
        """Remove the messages a delete reply names."""
        deleted = read_section(DeleteMessagesResponse, data, "the deleted messages")
        if deleted is not None:
            gone = set(deleted.message_ids)
            self.mailbox = {mid: message for mid, message in self.mailbox.items() if mid not in gone}

    def _handle_ams(self, data: Any) -> None:
        """Mark the message an archive reply names archived."""
        archived = read_section(ArchiveMessageResponse, data, "the archived message")
        if archived is not None and archived.message_id is not None:
            self._replace_message(archived.message_id, is_archived=True)

    def _replace_message(self, message_id: int, **update: bool) -> None:
        message = self.mailbox.get(message_id)
        if message is not None:
            self.mailbox = {**self.mailbox, message_id: message.model_copy(update=update)}

    def get_mailbox(self) -> list[MessageInfo]:
        """The messages from the login data and the pushes since, in the order they first arrived.

        Emptied when the session drops, as the client empties it; the next login's ``sne`` refills it.

        Client: ``CastleMessageData.reset`` (bundle line 134889)
        """
        with self._lock:
            return list(self.mailbox.values())

    def mark_message_read(self, message_id: int) -> None:
        """Mark a message in the mailbox read, as the client marks its own copy when it sends ``mmr``.

        ``client.messages.mark_read`` calls it; the server sends no answer to apply.
        """
        with self._lock:
            self._replace_message(message_id, is_read=True)
