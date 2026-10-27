"""Spy reports: reading, forwarding and auto spying."""

from __future__ import annotations

from empire_core.enums import GGEError, Kingdom
from empire_core.exceptions import CommandError
from empire_core.messages.models import ForwardSpyLogRequest, GetSpyReportRequest, SpyReportResponse
from empire_core.services.base import ServiceMixin
from empire_core.spy.models import AutoSpyRequest, AutoSpyResponse, SpyScreenInfoRequest, SpyScreenInfoResponse
from empire_core.spy.service.tracking import _NO_REPORT_ERRORS


class ReportsMixin(ServiceMixin):
    def forward_report(self, message_id: int, player_ids: list[int]) -> None:
        """Share a spy report with other players in game.

        A recipient who has the report already (``ALREADY_HAS_SPY_REPORT``) counts as done,
        as in the client.

        Args:
            message_id: The report's message id: ``SpyResult.message_id``, or a
                ``MessageInfo.message_id`` of a spy log
            player_ids: The recipients. The client offers the members of your alliance
                other than you, ``AllianceMember.player_id`` from
                ``client.alliance.get_local_members()``

        Raises:
            ValueError: ``player_ids`` is empty; the client's forward button stays
                disabled until a recipient is picked
            CommandError: The server refused it; a report can age out of the mailbox

        Client: ``CastleForwardMessageDialog.fillList`` and ``sendMessage`` (bundle lines 60719, 60740),
        ``checkEnableForwardButton`` (bundle line 60753), ``MFSCommand.executeCommand`` (bundle line 125409)
        """
        if not player_ids:
            raise ValueError("a spy report is forwarded to at least one player")
        try:
            self.client.send(ForwardSpyLogRequest(message_id=message_id, player_ids=list(player_ids)), wait=True)
        except CommandError as e:
            if e.error is not GGEError.ALREADY_HAS_SPY_REPORT:
                raise

    def get_screen_info(
        self, target_x: int, target_y: int, target_kingdom: Kingdom = Kingdom.GREEN
    ) -> SpyScreenInfoResponse:
        """
        What a mission against a target would face: its guards, your free spies and the target's map row.

        Raises:
            CommandError: The server refused, e.g. for a target you cannot spy

        Client: ``C2SGetSpyInfo`` (bundle line 22504), ``CastleSpyData.parse_SSI`` (bundle line 139962)
        """
        return self.request(
            SpyScreenInfoRequest(target_x=target_x, target_y=target_y, target_kingdom=target_kingdom),
            SpyScreenInfoResponse,
        )

    def get_report(self, message_id: int) -> SpyReportResponse | None:
        """
        Read any spy report in the mailbox by its message id.

        Returns None when the server has no report for it (error 130
        NO_SPY_DATA or 66 NO_SUCH_MESSAGE), which the client shows as "no spy data".

        Args:
            message_id: A spy log's ``MessageInfo.message_id`` from an ``sne`` push or the
                mailbox, or ``SpyResult.message_id``

        Raises:
            CommandError: The server refused for another reason

        Client: ``CastleSpyData.getSpyLog`` (bundle line 139963), ``BSDCommand.executeCommand``
        (bundle line 125223)
        """
        try:
            return self.request(GetSpyReportRequest(message_id=message_id), SpyReportResponse)
        except CommandError as e:
            if e.error in _NO_REPORT_ERRORS:
                return None
            raise

    def auto_spy(self, target_x: int, target_y: int) -> AutoSpyResponse:
        """
        Spy a target at once with the auto-spy subscription: no spies, no movement, no mail.

        The client offers this only while the subscription covers the target;
        what the server answers without it is untested.

        Raises:
            CommandError: The server refused

        Client: ``ButtonAutoSpyComponent.onClick`` (bundle line 109977), ``SSUCommand.executeCommand``
        (bundle line 128568)
        """
        return self.request(AutoSpyRequest(target_x=target_x, target_y=target_y), AutoSpyResponse)
