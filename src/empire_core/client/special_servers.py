"""The source session's introduction and teaser before a special-server transfer."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from empire_core.enums import ServerType
from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError, PacketError
from empire_core.gamedata.ids.events import Event
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
        # The session and quest a starter was last sent for, so a token retry does not resend it.
        self._starter_sent: tuple[int, Quest | None] = (-1, None)

    def require_source(self, generation: int) -> None:
        client = self.client
        if not client.is_logged_in or not client.connection.connected or client.connection.generation != generation:
            raise ConnectionClosedError("The source session ended during the special-server transfer")

    def prepare(self, server_type: ServerType, timeout: float) -> int:
        client = self.client
        generation = client.connection.generation
        self.require_source(generation)
        self._wait_for_quests(generation, timeout)
        event = _EVENTS[server_type]
        starter = client.quests.starter_quest(event)

        def acknowledge() -> None:
            self.require_source(generation)
            quest = client.quests.quest(starter.quest_id) if starter is not None else None
            if (
                quest is not None
                and not (quest.completed or quest.failed or quest.locked)
                and quest.remaining_seconds() != 0
                and not (self._starter_sent[0] == generation and self._starter_sent[1] is quest)
            ):
                client.quests.finish_starter(quest.quest_id)
                self._starter_sent = generation, quest
            for message in client.messages.mailbox:
                header = message.special_event_start_header()
                if header is not None and header.event == event:
                    if not message.is_read:
                        client.messages.mark_read(message.message_id)
                    break

        if not client.connection.run_if_current(generation, acknowledge):
            raise ConnectionClosedError("The source session ended during the special-server transfer")
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
        connection = self.client.connection
        deadline = time.monotonic() + timeout
        while not self._quests_loaded(generation):
            # Register, then recheck: the push can land before the waiter exists, or reach
            # another observer's waiter instead of ours.
            waiter = connection.create_waiter("qli")
            try:
                if self._quests_loaded(generation):
                    return
                packet = connection.wait_for_result("qli", waiter, timeout=max(0.0, deadline - time.monotonic()))
            except EmpireTimeoutError:
                if self._quests_loaded(generation):
                    return
                raise
            finally:
                connection.cancel_waiter("qli", waiter)
            if packet.error_code:
                raise CommandError("qli", packet.error_code, packet.payload)

    def _quests_loaded(self, generation: int) -> bool:
        self.require_source(generation)
        return self.client.state.get_last_packet_time("qli") is not None
