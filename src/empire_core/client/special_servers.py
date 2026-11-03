"""The source session's introduction and teaser before a special-server transfer."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from empire_core.enums import ServerType
from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError, PacketError
from empire_core.gamedata.ids.events import Event
from empire_core.gamedata.ids.quests import QuestId
from empire_core.protocol.auth import GetSpecialServerTokenRequest, SpecialServerTokenResponse

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.quests.models import Quest


_EVENTS = {
    ServerType.OUTER_REALMS: Event.OUTER_REALMS,
    ServerType.HORIZON: Event.BEYOND_THE_HORIZON,
}


class SpecialServerPreparation:
    """Mirror the introduction/teaser clicks before asking for a transfer token.

    Client: ``StatusIconTemporaryServerEvent.onClick``, ``CastleStartQuestDialog.finishQuestStarter``,
    ``TempServerEventVO.getEventTeaserMessageVO``, ``AllianceBattleGroundEventVO.getEventTeaserMessageVO``
    and ``CastleOpenMessageDialogCommand`` (Game.bundle.e2ca3c4ee155ea53c7c7).
    """

    def __init__(self, client: EmpireClient) -> None:
        self.client = client
        # Avoid repeating a successful write when glt fails before qfi arrives. A new
        # quest object from qli/qst, or a new connection, is authoritative again.
        self._starter_sent: tuple[int, Quest] | None = None

    def require_source(self, generation: int) -> None:
        client = self.client
        if not client.is_logged_in or not client.connection.connected or client.connection.generation != generation:
            raise ConnectionClosedError("The source session ended during the special-server transfer")

    def prepare(self, server_type: ServerType, timeout: float) -> int:
        client = self.client
        generation = client.connection.generation
        self.require_source(generation)
        if server_type is ServerType.OUTER_REALMS:
            self._wait_for_quests(generation, timeout)

        def acknowledge() -> None:
            self.require_source(generation)
            # Items 788.03: 3490 is event 106's starter; 3491 is its join objective.
            # No event 113 starter is defined. Do not guess one or require a CDN load.
            if server_type is ServerType.OUTER_REALMS:
                quest = client.state.get_quest(QuestId.STARTER_3490)
                if (
                    quest is not None
                    and not (quest.completed or quest.failed or quest.locked)
                    and quest.remaining_seconds() != 0
                    and not (
                        self._starter_sent is not None
                        and self._starter_sent[0] == generation
                        and self._starter_sent[1] is quest
                    )
                ):
                    client.quests.finish_starter(quest.quest_id)
                    self._starter_sent = generation, quest

            # The client finds the first matching teaser, including an archived one;
            # a read first match does not cause it to open a later unread duplicate.
            for message in client.messages.mailbox:
                header = message.special_event_start_header()
                if header is not None and header.event == _EVENTS[server_type]:
                    if not message.is_read:
                        self.require_source(generation)
                        client.messages.mark_read(message.message_id)
                    break

        # Keep these immediate writes on the source socket, never a replacement login.
        if not client.connection.run_if_current(generation, acknowledge):
            self.require_source(generation)
        self.require_source(generation)
        return generation

    def request_token(self, server_type: ServerType, generation: int, timeout: float) -> SpecialServerTokenResponse:
        """Ask on the prepared socket, even if an automatic re-login races the send."""
        request = GetSpecialServerTokenRequest(server_type=server_type)
        packet = self.client.connection.request(
            self.client.frame(request), "glt", timeout=timeout, expected_generation=generation
        )
        if packet.error_code:
            raise CommandError("glt", packet.error_code, packet.payload)
        try:
            return SpecialServerTokenResponse.model_validate(packet.payload)
        except ValidationError as error:
            raise PacketError(f"Could not parse 'glt' response: {error}") from error

    def _wait_for_quests(self, generation: int, timeout: float) -> None:
        client = self.client
        connection = client.connection
        deadline = time.monotonic() + timeout
        while client.state.get_last_packet_time("qli") is None:
            waiter = connection.create_waiter("qli")
            try:
                self.require_source(generation)
                # Register before rechecking: qli can arrive immediately after login,
                # between the first state read and registration, or while we wait.
                if client.state.get_last_packet_time("qli") is not None:
                    return
                try:
                    packet = connection.wait_for_result("qli", waiter, timeout=max(0.0, deadline - time.monotonic()))
                except EmpireTimeoutError:
                    # Another observer can consume the push's one waiter slot;
                    # state is authoritative even when our waiter did not get it.
                    self.require_source(generation)
                    if client.state.get_last_packet_time("qli") is not None:
                        return
                    raise
                self.require_source(generation)
                if packet.error_code:
                    raise CommandError("qli", packet.error_code, packet.payload)
                if client.state.get_last_packet_time("qli") is None and time.monotonic() >= deadline:
                    raise EmpireTimeoutError("Timeout waiting for the source session's quest list ('qli')")
            finally:
                connection.cancel_waiter("qli", waiter)
