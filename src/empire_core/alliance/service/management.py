"""Joining, leaving and managing an alliance's members."""

from __future__ import annotations

from empire_core.alliance.models.founding import ALLIANCE_FOUND_RUBIES, FoundAllianceRequest, FoundAllianceResponse
from empire_core.alliance.models.info import AllianceInfo
from empire_core.alliance.models.members import (
    AllianceApplicationListRequest,
    AllianceApplicationListResponse,
    AnswerApplicationRequest,
    InvitePlayerRequest,
    KickMemberRequest,
    KickMemberResponse,
    QuitAllianceRequest,
    RerankMemberRequest,
    RerankMemberResponse,
)
from empire_core.alliance.models.membership import (
    AcceptAllianceInvitationRequest,
    AcceptAllianceInvitationResponse,
    ApplyToAllianceRequest,
    FindAllianceRecruitsRequest,
    FindAllianceRecruitsResponse,
    GetAllianceInvitationRequest,
    GetAllianceInvitationResponse,
    JoinOpenAllianceRequest,
    JoinOpenAllianceResponse,
    SetLookingForAllianceRequest,
    SetLookingForMembersRequest,
)
from empire_core.alliance.models.search import AutoAllianceSearchRequest, AutoAllianceSearchResponse
from empire_core.alliance.models.settings import alliance_name
from empire_core.alliance.service.own import OwnAllianceMixin, _echoed
from empire_core.enums import AllianceRank, GGEError
from empire_core.exceptions import CommandError, PacketError


class MemberManagementMixin(OwnAllianceMixin):
    # =========================================================================
    # Member Management
    # =========================================================================

    def kick_member(self, player_id: int, *, timeout: float = 5.0) -> AllianceInfo:
        """
        Remove a member from your alliance.

        Args:
            player_id: The member's ``AllianceMember.player_id``

        Returns:
            The alliance after the kick

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            PacketError: The reply carries no alliance
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``AKMCommand.executeCommand`` (bundle line 121513) reads the reply's ``ain``
        """
        with self._own_alliance():
            response = self.request(KickMemberRequest(player_id=player_id), KickMemberResponse, timeout=timeout)
        return _echoed(response.alliance, "akm")

    def set_rank(self, player_id: int, rank: AllianceRank, *, timeout: float = 5.0) -> AllianceInfo | None:
        """
        Give a member another rank; ``AllianceRank.LEADER`` hands over the leadership.

        Args:
            player_id: The member's ``AllianceMember.player_id``
            rank: The new rank

        Returns:
            The alliance after the change, or None when the server answers ``NO_CHANGE``,
            which the client takes as nothing to do

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            PacketError: The reply carries no alliance
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``ARMCommand.executeCommand`` (bundle line 121589) reads the reply's ``ain``
        and passes over ``NO_CHANGE``
        """
        request = RerankMemberRequest(player_id=player_id, rank=rank)
        try:
            with self._own_alliance():
                response = self.request(request, RerankMemberResponse, timeout=timeout)
        except CommandError as e:
            if e.error is GGEError.NO_CHANGE:
                return None
            raise
        return _echoed(response.alliance, "arm")

    def found(
        self,
        name: str,
        description: str,
        language: str,
        *,
        open_join: bool = True,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> AllianceInfo:
        """Found an alliance and return its created details.

        Base costs are 50 coins, 100 wood, 50 stone and 375 rubies, before cost
        modifiers. An active premium account waives the ruby cost. Without ruby
        consent its remaining time must cover the request timeout. Missing resources
        are never bought with rubies. Server refusals preserve local membership.

        Client: CastleNewAllianceDialog.showLoaded/onCreateNewAlliance (bundle
        44123–44125, 44138–44141), C2SFoundAllianceVO (44153–44156),
        AFOCommand (121465–121466), AllianceConst (dll line 18805).
        """
        alliance_name(name)
        request = FoundAllianceRequest(name=name, description=description, language=language, open_join=open_join)
        request.validate_description()
        with self._membership_change(timeout=timeout) as revision:
            if self.local_alliance_id is not None:
                raise ValueError("you already belong to an alliance")
            if not spend_rubies:
                premium_seconds = self.client.state.get_boosts().premium_remaining_seconds()
                self._require_spend_rubies(
                    spend_rubies,
                    f"founding an alliance may spend rubies (base price {ALLIANCE_FOUND_RUBIES})"
                    if not 0 <= timeout < premium_seconds
                    else None,
                )
            response, payload = self._request_membership(request, FoundAllianceResponse, timeout=timeout)
            self.client.state.apply_membership_response(payload, membership_revision=revision)
            return response.alliance

    def apply(self, alliance_id: int, text: str, *, timeout: float = 5.0) -> None:
        """Send an application to an alliance, waiting for acceptance by the server."""
        self.execute(ApplyToAllianceRequest(alliance_id=alliance_id, text=text), timeout=timeout)

    def join_open(self, alliance_id: int, *, timeout: float = 5.0) -> AllianceInfo:
        """Join an alliance that permits open joining and return its details.

        A refused join raises CommandError. Its membership and details are applied
        to state only after a successful, consistent reply. A newer membership
        update or session reset raises ReplyMismatchError and keeps that newer state.
        """
        with self._membership_change(timeout=timeout) as revision:
            response, data = self._request_membership(
                JoinOpenAllianceRequest(alliance_id=alliance_id), JoinOpenAllianceResponse, timeout=timeout
            )
            self.client.state.apply_membership_response(data, membership_revision=revision)
            return response.alliance

    def auto_join(
        self, name: str, *, description: str = "", language: str = "", timeout: float = 5.0
    ) -> AutoAllianceSearchResponse:
        """Ask the server to put you in an alliance; it either does, or lists alliances to join.

        Its ``membership`` is your new one when you were put in an alliance, and is applied
        to state with the movements beside it; else ``alliances`` lists alliances to join.
        ``name`` and ``description`` are what the game sends: its translated default alliance
        name and an empty text. ``language`` limits the list to one language code.

        Raises:
            ValueError: You already belong to an alliance; the client offers this only outside one
            CommandError: The server refused

        Client: ``CastleAllianceTeaserDialog.onJoinAlliance`` (bundle line 14670) and
        ``CastleSearchAllianceDialog.setAllianceLanguage`` (bundle line 34593), ``AASCommand``
        (bundle lines 121270-121279)
        """
        with self._membership_change(timeout=timeout) as revision:
            if self.local_alliance_id is not None:
                raise ValueError("you already belong to an alliance")
            response, payload = self._request_membership(
                AutoAllianceSearchRequest(name=name, description=description, language=language),
                AutoAllianceSearchResponse,
                timeout=timeout,
            )
            if response.membership is not None:
                self.client.state.apply_membership_response(payload, membership_revision=revision)
            return response

    def get_invitation(self, message_id: int, *, timeout: float = 5.0) -> AllianceInfo:
        """Read the inviting alliance using the invitation's message id."""
        return _echoed(
            self.request(
                GetAllianceInvitationRequest(message_id=message_id), GetAllianceInvitationResponse, timeout=timeout
            ).alliance,
            "bai",
        )

    def accept_invitation(self, message_id: int, *, accept: bool = True, timeout: float = 5.0) -> AllianceInfo | None:
        """Accept an invitation, or refuse with ``accept=False``; return echoed alliance details.

        ``message_id`` is the invitation message id, not the sender's player id.
        Refusing normally returns no alliance. A refused command still raises CommandError.
        A newer membership update or session reset raises ReplyMismatchError;
        it keeps the newer state even if the invitation was accepted remotely.
        """
        with self._membership_change(timeout=timeout) as revision:
            response, data = self._request_membership(
                AcceptAllianceInvitationRequest(message_id=message_id, accept=accept),
                AcceptAllianceInvitationResponse,
                timeout=timeout,
            )
            if accept and (response.membership is None or response.alliance is None):
                raise PacketError("'aai' acceptance reply carries no membership or alliance")
            self.client.state.apply_membership_response(data, membership_revision=revision)
            return response.alliance

    def find_recruits(self, *, timeout: float = 5.0) -> FindAllianceRecruitsResponse:
        """Find players looking for an alliance, nearest first, with their owner records."""
        with self._own_alliance():
            return self.request(FindAllianceRecruitsRequest(), FindAllianceRecruitsResponse, timeout=timeout)

    def set_looking_for_members(self, enabled: bool, *, open_join: bool, timeout: float = 5.0) -> None:
        """Set recruitment and open joining independently; refresh alliance info to read them."""
        with self._own_alliance():
            self.execute(
                SetLookingForMembersRequest(enabled=enabled, open_join=open_join),
                timeout=timeout,
            )

    def set_looking_for_alliance(self, enabled: bool, *, timeout: float = 5.0) -> None:
        """Set your player's looking-for-alliance flag."""
        self.execute(SetLookingForAllianceRequest(enabled=enabled), timeout=timeout)

    def invite(self, player_id: int, *, timeout: float = 5.0) -> None:
        """
        Invite a player to your alliance.

        Args:
            player_id: The player's id, e.g. ``PlayerOwnerInfo.player_id`` from ``client.player.get_player_info()``

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError: The server refused it, with ``INVALID_PLAYER_ID`` for an id that names no player

        Client: ``CastlePlayerInfoDialog`` shows its invite button for
        ``CastleUserData.canInviteToAlliance`` (bundle line 9994), which needs ``isInAlliance``
        """
        with self._own_alliance():
            self.execute(InvitePlayerRequest.for_player(player_id), timeout=timeout)

    def get_applications(self, *, timeout: float = 5.0) -> AllianceApplicationListResponse:
        """
        Get your alliance's applications, nearest first, with the applicants' owner records.

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        with self._own_alliance():
            return self.request(AllianceApplicationListRequest(), AllianceApplicationListResponse, timeout=timeout)

    def answer_application(self, player_id: int, accept: bool, *, timeout: float = 5.0) -> None:
        """
        Accept or refuse an application.

        Args:
            player_id: The applicant's ``AllianceApplication.player_id``
            accept: True to accept, False to refuse

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        request = AnswerApplicationRequest.create(player_id, accept)
        with self._own_alliance():
            self.execute(request, timeout=timeout)

    def leave(self, *, timeout: float = 5.0) -> None:
        """
        Leave your alliance. Once the server accepts, :attr:`help_requests` is emptied.

        Client: ``AQICommand.executeCommand`` (bundle line 121556) calls
        ``CastleAllianceData.resetMyAlliance`` (bundle line 11620), which cleans the help list

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        with self._own_alliance():
            self.execute(QuitAllianceRequest(), timeout=timeout)
