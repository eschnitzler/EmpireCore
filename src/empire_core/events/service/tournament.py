"""The Grand Tournament, the Rift Raid and event announcements."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from empire_core.enums.events import RaidBossCardStatus
from empire_core.events.service.base import EventsBaseMixin
from empire_core.exceptions import CommandError, PacketError, ReplyMismatchError
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.base import BaseRequest, BaseResponse

if TYPE_CHECKING:
    from empire_core.gamedata import RaidBoss

from empire_core.events.models import ClaimAnnouncementRewardRequest, RiftRaidEvent
from empire_core.events.status_models import (
    AbortRaidRequest,
    AbortRaidResponse,
    CancelGrandTournamentQuestRequest,
    CancelGrandTournamentQuestResponse,
    CompleteGrandTournamentQuestRequest,
    CompleteGrandTournamentQuestResponse,
    GetGrandTournamentContributionsRequest,
    GetGrandTournamentContributionsResponse,
    GetGrandTournamentStatusRequest,
    GetRiftRaidStatusRequest,
    GetRiftRaidStatusResponse,
    GrandTournamentContribution,
    GrandTournamentQuestStatus,
    RerollGrandTournamentQuestRequest,
    RerollGrandTournamentQuestResponse,
    RiftRaidStatus,
    SelectRaidBossRequest,
    SelectRaidBossResponse,
    SkipGrandTournamentCooldownRequest,
    SkipGrandTournamentCooldownResponse,
    StartGrandTournamentQuestRequest,
    StartGrandTournamentQuestResponse,
)

QuestActionResponse = TypeVar("QuestActionResponse", bound=BaseResponse)


class GrandTournamentMixin(EventsBaseMixin):
    def get_grand_tournament_status(self, *, timeout: float = 5.0) -> GrandTournamentQuestStatus:
        """Request alliance Grand Tournament quest slots and participating member count.

        Requires the running Grand Tournament event. Successful replies also update its quest_status.
        Client: ``AllianceMobilizationEventEventVO.requestAllianceQuestStatus`` (bundle 5117).
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self.request(
            GetGrandTournamentStatusRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            GrandTournamentQuestStatus,
            timeout=timeout,
        )

    def get_grand_tournament_contributions(self, *, timeout: float = 5.0) -> tuple[GrandTournamentContribution, ...]:
        """Request player contributions for the current alliance Grand Tournament.

        The response carries no event identity; a late reply after timeout cannot be identified.
        Client: ``AllianceMobilizationEventDialogContributions.show`` (bundle 47205), AQPCCommand (127404).
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self.request(
            GetGrandTournamentContributionsRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            GetGrandTournamentContributionsResponse,
            timeout=timeout,
        ).contributions

    def get_rift_raid_status(self, *, timeout: float = 5.0) -> RiftRaidStatus:
        """Request current alliance raid boss, health, cards and walls.

        Requires the raid event. Successful replies and bbs broadcasts update RiftRaidEvent.boss_status.
        An inactive status clears the active boss fields; missing identity/stage/walls preserve prior values
        exactly where the client does. Replies carry no event or alliance identity, so a late reply after
        timeout cannot be correlated. Refusals/transport failures raise without changing the event.
        Client: ``C2SGetAllianceRaidBossStatus`` (bundle 47183-47187), raid parser (76190-76205).
        """
        self._require_running(Event.RIFT_RAID)
        deadline = time.monotonic() + timeout
        with self.client.connection.command_lock("bse", timeout=timeout):
            packet = self.client.request_packet(
                GetRiftRaidStatusRequest(), "bse", timeout=max(0.0, deadline - time.monotonic())
            )
            if packet.error_code != 0:
                raise CommandError("bse", packet.error_code, packet.payload)
            try:
                GetRiftRaidStatusResponse.model_validate(packet.payload)
            except ValidationError as error:
                raise PacketError(f"Could not parse 'bse' response: {error}") from error
            status = self.client.state._raid_status_reply(packet.payload)
            if status is None:
                raise PacketError("The 'bse' reply has no matching applied raid status")
            return status

    def start_grand_tournament_quest(
        self, slot_id: int, alliance_quest_id: int, *, timeout: float = 5.0
    ) -> StartGrandTournamentQuestResponse:
        """Accept a quest, consuming an event ticket. The server checks ticket balance and assignments.

        Client: C2S quest action and dialog (bundle 75732-75735, 75830-75833).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self._request_grand_tournament_action(
            StartGrandTournamentQuestRequest(
                event_id=int(Event.GRAND_TOURNAMENT), slot_id=slot_id, alliance_quest_id=alliance_quest_id
            ),
            StartGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def complete_grand_tournament_quest(self, *, timeout: float = 5.0) -> CompleteGrandTournamentQuestResponse:
        """Collect the completed active quest. The server checks completion.

        Client: C2S quest action and dialog (bundle 75705-75708, 75779).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self._request_grand_tournament_action(
            CompleteGrandTournamentQuestRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            CompleteGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def cancel_grand_tournament_quest(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> CancelGrandTournamentQuestResponse:
        """Cancel the active quest; its configured cancelCostC2 defaults to 199 rubies.

        Client: C2S quest action and dialog (bundle 75696-75699, 75826-75827, 111069).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        self._require_spend_rubies(
            spend_rubies, "Cancel the active quest; its configured cancelCostC2 defaults to 199 rubies."
        )
        return self._request_grand_tournament_action(
            CancelGrandTournamentQuestRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            CancelGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def reroll_grand_tournament_quest(
        self, slot_id: int, alliance_quest_id: int, *, timeout: float = 5.0
    ) -> RerollGrandTournamentQuestResponse:
        """Reroll an unassigned quest; the client shows no currency charge.

        Client: C2S quest action and dialog (bundle 75714-75717, 75855).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self._request_grand_tournament_action(
            RerollGrandTournamentQuestRequest(
                event_id=int(Event.GRAND_TOURNAMENT), slot_id=slot_id, alliance_quest_id=alliance_quest_id
            ),
            RerollGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def skip_grand_tournament_cooldown(
        self, slot_id: int, alliance_quest_id: int, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> SkipGrandTournamentCooldownResponse:
        """Skip a quest slot cooldown for 999 rubies.

        Client: C2S quest action and dialog (bundle 75723-75726, 34974).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        self._require_spend_rubies(spend_rubies, "Skip a quest slot cooldown for 999 rubies.")
        return self._request_grand_tournament_action(
            SkipGrandTournamentCooldownRequest(
                event_id=int(Event.GRAND_TOURNAMENT), slot_id=slot_id, alliance_quest_id=alliance_quest_id
            ),
            SkipGrandTournamentCooldownResponse,
            timeout=timeout,
        )

    def _request_grand_tournament_action(
        self, request: BaseRequest, response_type: type[QuestActionResponse], *, timeout: float
    ) -> QuestActionResponse:
        deadline = time.monotonic() + timeout
        with self.client.connection.command_lock("aqs", timeout=timeout):
            context = self.client.state._begin_quest_action()
            try:
                result = self.request(request, response_type, timeout=max(0.0, deadline - time.monotonic()))
                current = self.client.state._quest_action_context()
                if context != current:
                    expected = context[1] if context is not None else None
                    received = current[1] if current is not None else None
                    raise ReplyMismatchError(
                        expected if expected is not None else -1, received if received is not None else -1
                    )
                return result
            finally:
                self.client.state._end_quest_action()

    def select_raid_boss(self, boss_id: RaidBoss | int, *, timeout: float = 5.0) -> SelectRaidBossResponse:
        """Select an available raid boss and return the server acknowledgement.

        The server checks leader/co-leader permission. Known cards must be available;
        a newer boss id is supported. No ruby payment is shown by the client.
        Status is updated by bbs broadcasts; call get_rift_raid_status for a fresh snapshot.
        Client: ``AllianceRaidBossCardItem.onClick`` (current bundle 75377),
        ``canManageAllianceRaid`` (current DLL 18796), ``SRBCommand`` (bundle 127571-127580).
        """
        event = self._require_running(Event.RIFT_RAID)
        request = SelectRaidBossRequest(boss_id=boss_id)
        if isinstance(event, RiftRaidEvent) and event.boss_status is not None:
            card = next((card for card in event.boss_status.cards if card.boss_id == boss_id), None)
            if card is not None and card.status != RaidBossCardStatus.AVAILABLE:
                raise ValueError("the raid boss card is not available")
        return self.request(request, SelectRaidBossResponse, timeout=timeout)

    def abort_raid(self, *, timeout: float = 5.0) -> AbortRaidResponse:
        """Abort the active raid boss and return the server acknowledgement.

        Requires leader/co-leader permission; the server checks it. A known inactive raid
        or last playable boss cannot be aborted. No ruby payment is shown by the client.
        This acknowledgement does not clear the boss; bbs supplies the resulting status.
        Client: ``AllianceRaidBossCardItem.handleAbort``, ``updateAbortButton`` (current bundle
        75351-75365), ``isLastPlayableBoss`` (76260-76263), ``ARBCommand`` (127528-127537).
        """
        event = self._require_running(Event.RIFT_RAID)
        if isinstance(event, RiftRaidEvent) and event.boss_status is not None:
            status = event.boss_status
            if not status.active:
                raise ValueError("there is no active raid to abort")
            locked = {RaidBossCardStatus.LOCKED_FINAL_DEFEATED, RaidBossCardStatus.LOCKED_ABORTED}
            if sum(card.status not in locked for card in status.cards) <= 1:
                raise ValueError("the last playable raid boss cannot be aborted")
        return self.request(AbortRaidRequest(), AbortRaidResponse, timeout=timeout)

    def claim_announcement_reward(self, *, timeout: float = 5.0) -> None:
        """
        Claim the reward of the running event announcement, the teaser for an event to come; the
        announcement's ``reward_collected`` turns True in :attr:`running`.

        Client: ``CastleEventTeaserDialog.claimRewards`` (bundle line 91443), ``CARCommand.executeCommand``
        (bundle line 125277)

        Raises:
            CommandError: The server refused the claim
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        self.execute(ClaimAnnouncementRewardRequest(), timeout=timeout)
