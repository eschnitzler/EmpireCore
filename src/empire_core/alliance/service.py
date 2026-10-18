"""
Your alliance and others: members, chat, help, diplomacy and the treasury.

It covers:

- Alliance members (get members, online status, last seen)
- Member management (kick, rank, invite, applications, leave)
- Diplomacy, auto war, the newsletter and treasury donations
- Alliance chat (send messages, get history)
- Alliance help (the help list and its pushes, helping, asking for help)
- Your alliance's chronicle and subscriber count
- Map bookmarks, your own and your alliance's (list, add, change, delete)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import ValidationError

from empire_core.alliance.models.bookmarks import (
    ATTACK_ORDER_MAX_SECONDS,
    ATTACK_ORDER_MIN_SECONDS,
    BOOKMARK_NAME_MAX_LENGTH,
    AddBookmarkRequest,
    AddBookmarkResponse,
    Bookmark,
    ChangeBookmarkRequest,
    ChangeBookmarkResponse,
    DeleteAllianceBookmarkRequest,
    DeleteBookmarkRequest,
    GetBookmarksRequest,
    GetBookmarksResponse,
)
from empire_core.alliance.models.chat import (
    AllianceChatLogRequest,
    AllianceChatLogResponse,
    AllianceChatMessageRequest,
    AllianceChatMessageResponse,
    ChatMessageData,
)
from empire_core.alliance.models.chronicle import (
    AllianceChronicleEntry,
    AllianceChronicleRequest,
    AllianceChronicleResponse,
    AllianceSubscriberCountRequest,
    AllianceSubscriberCountResponse,
)
from empire_core.alliance.models.diplomacy import (
    AllianceDonation,
    ChangeDiplomacyRequest,
    ChangeDiplomacyResponse,
    DonateRequest,
    DonateResponse,
    RefuseDiplomacyRequest,
    RefuseDiplomacyResponse,
    SendNewsletterRequest,
    SetAutoWarRequest,
    SetAutoWarResponse,
)
from empire_core.alliance.models.forum import (
    CreateForumTopicRequest,
    DeleteForumReplyRequest,
    DeleteForumTopicRequest,
    GetForumTopicRequest,
    GetForumTopicResponse,
    GetForumTopicsRequest,
    GetForumTopicsResponse,
    GetUnreadTopicCountRequest,
    GetUnreadTopicCountResponse,
    ReplyToForumTopicRequest,
    SetForumVisibilityRequest,
    SetForumVisibilityResponse,
    forum_text,
)
from empire_core.alliance.models.founding import ALLIANCE_FOUND_RUBIES, FoundAllianceRequest, FoundAllianceResponse
from empire_core.alliance.models.gifts import AllianceGift, CollectAllianceGiftRequest, CollectAllianceGiftResponse
from empire_core.alliance.models.help import (
    AllianceHelpListResponse,
    AllianceHelpReceived,
    AllianceHelpRequest,
    AllianceHelpRequestChanged,
    AllianceHelpRequestRemoved,
    AskHelpRequest,
    HelpAllRequest,
    HelpMemberRequest,
)
from empire_core.alliance.models.info import (
    AllianceInfo,
    AllianceMember,
    GetAllianceInfoRequest,
    GetAllianceInfoResponse,
)
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
from empire_core.alliance.models.search import AllianceSearchResult, SearchAllianceRequest, SearchAllianceResponse
from empire_core.alliance.models.settings import (
    ALLIANCE_RENAME_RUBIES,
    ChangeAllianceDescriptionRequest,
    ChangeAllianceDescriptionResponse,
    ChangeAllianceLanguageRequest,
    ChangeAllianceLanguageResponse,
    ChangeAllianceNameRequest,
    ChangeAllianceNameResponse,
    SetAllianceEmblemRequest,
    SetAllianceEmblemResponse,
    alliance_name,
    settings_alliance_payload,
)
from empire_core.alliance.models.upgrades import AllianceUpgradeRequest, AllianceUpgradeResponse
from empire_core.enums import (
    AllianceBuffType,
    AllianceRank,
    BookmarkType,
    CollectableKind,
    DiplomacyStatus,
    ForumRankGroup,
    GGEError,
    HelpType,
    Kingdom,
)
from empire_core.exceptions import CommandError, NotInAllianceError, PacketError
from empire_core.map.models.owners import AllianceCrest
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.gamedata import AllianceCrestColor, AllianceCrestLayout

logger = logging.getLogger(__name__)

_MembershipResponse = TypeVar("_MembershipResponse", bound=BaseResponse)

AllianceHelpUpdate = (
    AllianceHelpListResponse | AllianceHelpRequestChanged | AllianceHelpRequestRemoved | AllianceHelpReceived
)

_PLAYER_BOOKMARK_TYPES = frozenset({BookmarkType.PLAYER_ENEMY, BookmarkType.PLAYER_FRIEND})


def _check_bookmark_name(name: str) -> None:
    # CastleWorldmapBookmarkSetDialog.isNameValid (bundle line 19570) and its maxChars (bundle line 19546)
    if not name or len(name) > BOOKMARK_NAME_MAX_LENGTH:
        raise ValueError(f"bookmark names are 1 to {BOOKMARK_NAME_MAX_LENGTH} characters, got {name!r}")


def _echoed(alliance: AllianceInfo | None, command: str) -> AllianceInfo:
    if alliance is None:
        raise PacketError(f"'{command}' reply carries no alliance")
    return alliance


class AllianceService(BaseService):
    """
    Alliance chat, help, members, applications, diplomacy and the treasury.

    Reached as client.alliance.

    Usage:
        client = EmpireClient(...)
        client.login()

        # Send chat message
        client.alliance.send_chat("Hello alliance!")

        # Help every request on the alliance help list
        client.alliance.help_all()

        # Subscribe to incoming messages
        def on_message(response: AllianceChatMessageResponse):
            print(f"{response.player_name}: {response.decoded_text}")

        client.alliance.on_chat_message(on_message)
    """

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)

        self.on_response("acm", self._handle_chat_message)
        for command in ("ahl", "ahh", "ahd", "ahf"):
            self.on_response(command, self._handle_help_update)

    @property
    def own_alliance(self) -> AllianceInfo | None:
        """Your alliance's details and members, from the last ``ain`` about it; None in no alliance or before one."""
        return self.client.state.get_own_alliance()

    @property
    def chat(self) -> list[ChatMessageData]:
        """The alliance chat history, oldest first; a copy of the list, of read-only messages."""
        return self.client.state.get_alliance_chat()

    def upgrade(
        self,
        building_type: AllianceBuffType | int,
        level: int = 1,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> AllianceUpgradeResponse:
        """Upgrade a permanent alliance buff or buy/prolong a temporary boost.

        Fresh alliance details determine the actual treasury cost. Consent covers
        alliance treasury rubies, not personal rubies. The server enforces rank
        permissions and available funds through typed CommandError refusals.

        Client: C2SAllianceUpgradeVO (27432–27435), OpenAllianceBuyBoosterCommand
        (91124–91173), AllianceInfoVO.getUpgradeCosts (26031), customizable
        dialog (91199/91219), forge dialog (69522/69528), AUGCommand (121660).
        """
        # AllianceBuffData.CUSTOMIZABLE_BUFFS (bundle 27759), constants DLL 18805.
        customizable = {12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25}
        supported = set(range(26)) - {11}
        if building_type not in supported or isinstance(building_type, bool):
            raise ValueError(f"unsupported alliance upgrade {building_type}")
        if isinstance(level, bool) or level < 1 or (building_type not in customizable and level != 1):
            raise ValueError("only customizable temporary boosts accept a selected level")
        data = self._require_game_data()
        rows = {row.level: row for row in data.alliance_buffs.values() if row.series_id == building_type}
        if not rows:
            raise ValueError(f"unknown alliance buff series {building_type}")
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        with self.client.connection.command_lock("aug", timeout=timeout):
            preflight_sequence = self.client.state.alliance_upgrade_sequence()
            with (
                self.client.connection.command_lock("ain", timeout=timeout),
                self.client.state.alliance_info_read(alliance_id),
            ):
                preflight, preflight_payload = self._request_membership(
                    GetAllianceInfoRequest(alliance_id=alliance_id), GetAllianceInfoResponse, timeout=timeout
                )
            details = _echoed(preflight.alliance, "ain")
            preflight_sequence = self.client.state.require_alliance_upgrade_preflight(
                preflight_sequence, membership_revision=revision, alliance_id=alliance_id, payload=preflight_payload
            )
            current = next((row for row in details.buildings if row.building_type == building_type), None)
            if details.alliance_id != alliance_id:
                raise PacketError("alliance preflight names a different alliance")
            if (
                current is None
                or not {"building_type", "level", "cooldown"} <= current.model_fields_set
                or current.level not in rows
            ):
                raise ValueError("fresh alliance details contain no known current buff level")
            maximum = rows[current.level].max_level
            next_row = rows.get(min(current.level + 1, maximum))
            if next_row is None:
                raise ValueError("unknown next alliance buff level")
            temporary = next_row.duration_seconds != -1
            if not temporary and current.level >= maximum:
                raise ValueError("alliance buff is already at its maximum level")
            if temporary and next_row.required_buff_id != -1:
                required = data.alliance_buffs.get(next_row.required_buff_id)
                if required is None or not any(
                    row.building_type == required.series_id and row.level >= required.level for row in details.buildings
                ):
                    raise ValueError("temporary boost prerequisite is not satisfied")
            if building_type in customizable:
                if not temporary or level not in rows or level > maximum:
                    raise ValueError("unknown temporary boost level")
                if current.cooldown > 0 and level != current.level:
                    raise ValueError("an active temporary boost can only be prolonged at its current level")
                cost_row = rows[level]
            else:
                cost_row = next_row
            if any(cost.kind == CollectableKind.OTHER or cost.amount < 0 for cost in cost_row.costs):
                raise ValueError("unknown alliance upgrade cost")
            rubies = sum(cost.amount for cost in cost_row.costs if cost.kind == CollectableKind.RUBIES)
            self._require_spend_rubies(
                spend_rubies, f"alliance treasury upgrade costs {rubies} rubies" if rubies else None
            )
            self.client.state.require_alliance_upgrade_preflight(
                preflight_sequence, membership_revision=revision, alliance_id=alliance_id
            )
            with self._own_alliance():
                response, payload = self._request_membership(
                    AllianceUpgradeRequest(building_type=building_type, level=level),
                    AllianceUpgradeResponse,
                    timeout=timeout,
                )
            self.client.state.apply_alliance_settings(
                {
                    "A": {
                        "AID": alliance_id,
                        "STO": payload["STO"],
                        "ABL": [row.to_payload() for row in response.buildings],
                    }
                },
                membership_revision=revision,
                alliance_id=alliance_id,
                command="aug",
                payload=payload,
            )
            return response

    def set_description(self, text: str, *, timeout: float = 5.0) -> AllianceInfo:
        """Change the alliance description, returning echoed alliance details.

        Text follows the client's trim, double encoding and 1000-character wire limit.
        Client: CastleChangeDescriptionDialog.sendDescription (bundle 69775–69778).
        """
        return self._change_settings(
            ChangeAllianceDescriptionRequest(text=text, text_type=1), ChangeAllianceDescriptionResponse, timeout=timeout
        )

    def set_announcement(self, text: str, *, timeout: float = 5.0) -> AllianceInfo:
        """Change the alliance announcement, returning echoed alliance details.

        Client: CastleChangeAnouncementDialog.sendDescription (bundle 70504).
        """
        return self._change_settings(
            ChangeAllianceDescriptionRequest(text=text, text_type=0), ChangeAllianceDescriptionResponse, timeout=timeout
        )

    def rename(self, name: str, *, spend_rubies: bool = False, timeout: float = 5.0) -> AllianceInfo:
        """Rename the alliance; a fresh free rename avoids the 10,000-ruby charge.

        Without consent this first requests alliance details to check free renames.
        Client: CastleNameAllianceDialog.showLoaded (bundle 69791–69792),
        AllianceConst.RENAME_COST_C2 (dll line 18805).
        """
        alliance_name(name)
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        with self.client.connection.command_lock("acn", timeout=timeout):
            if not spend_rubies:
                details = self.get_alliance_info(alliance_id, timeout=timeout)
                self._require_spend_rubies(
                    spend_rubies,
                    f"renaming the alliance costs {ALLIANCE_RENAME_RUBIES} rubies"
                    if details.free_renames == 0
                    else None,
                )
            self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
            return self._change_settings(
                ChangeAllianceNameRequest(name=name),
                ChangeAllianceNameResponse,
                membership=(alliance_id, revision),
                timeout=timeout,
            )

    def set_language(self, language: str, *, timeout: float = 5.0) -> AllianceInfo:
        """Set the alliance language code, returning echoed alliance details.

        Client: CastleAllianceDialogManagement.onLanguageSelect (bundle 69621).
        """
        return self._change_settings(
            ChangeAllianceLanguageRequest(language=language), ChangeAllianceLanguageResponse, timeout=timeout
        )

    def set_emblem(
        self, layout_id: AllianceCrestLayout | int, color_ids: list[AllianceCrestColor | int], *, timeout: float = 5.0
    ) -> AllianceCrest:
        """Save an available alliance crest, returning the acknowledged selection.

        Temporary layouts must still be held. The server pushes authoritative crest
        state separately; this acknowledgment does not fabricate a crest update.
        Client: AllianceCrestCreationDialog.update/doSave (bundle 45205–45211),
        C2SSetAllianceEmblemVO (69672–69674), SAECommand (122004).
        """
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        data = self._require_game_data()
        layout = data.alliance_crest_layouts.get(layout_id)
        if layout is None:
            raise ValueError(f"unknown alliance crest layout {layout_id}")
        if len(color_ids) != layout.color_count or any(color not in data.alliance_crest_colors for color in color_ids):
            raise ValueError("the crest needs one known colour for each layout colour")
        if layout.max_duration > 0:
            details = self.get_alliance_info(alliance_id, timeout=timeout)
            if not any(row.layout_id == layout_id and row.seconds_left > 0 for row in details.crest_layouts):
                raise ValueError("the temporary crest layout is not currently held")
        self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
        with self._own_alliance():
            self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
            self.request(
                SetAllianceEmblemRequest(layout_id=layout_id, color_ids=color_ids),
                SetAllianceEmblemResponse,
                timeout=timeout,
            )
        self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
        return AllianceCrest(layout_id=layout_id, color_ids=list(color_ids))

    def _change_settings(
        self,
        request: BaseRequest,
        response_type: type[GetAllianceInfoResponse],
        *,
        membership: tuple[int, int] | None = None,
        timeout: float,
    ) -> AllianceInfo:
        with self.client.connection.command_lock(request.command, timeout=timeout):
            alliance_id, revision = membership or (
                self._require_local_alliance_id(),
                self.client.state.membership_revision,
            )
            with self._own_alliance():
                self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
                response, payload = self._request_membership(request, response_type, timeout=timeout)
            alliance = _echoed(response.alliance, request.command)
            if alliance.alliance_id != alliance_id:
                raise PacketError(f"'{request.command}' reply names a different alliance")
            self.client.state.apply_alliance_settings(
                settings_alliance_payload(request.command, payload),
                membership_revision=revision,
                alliance_id=alliance_id,
                command=request.command,
                payload=payload,
            )
            return alliance

    @property
    def gifts(self) -> list[AllianceGift]:
        """Your unexpired alliance gifts, soonest expiration first; received through pushes."""
        return self.client.state.get_alliance_gifts()

    def collect_gift(self, gift_id: int, *, timeout: float = 5.0) -> CollectAllianceGiftResponse:
        """Collect a gift and return the unpacked rewards.

        Client: AllianceGiftScrollItem.onMouseClick (bundle 105236),
        AGCCommand (121823) and CastleAllianceGiftData.parse_AGC (131937–131939).
        """
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        with self._own_alliance():
            response = self.request(
                CollectAllianceGiftRequest(gift_id=gift_id), CollectAllianceGiftResponse, timeout=timeout
            )
        self.client.state.apply_alliance_gift_collection(
            response.gift_id, membership_revision=revision, alliance_id=alliance_id
        )
        return response

    def create_topic(self, name: str, text: str, visible_ranks: list[ForumRankGroup], *, timeout: float = 5.0) -> None:
        """Create a forum topic with explicit visibility groups and an opening post.

        Titles must encode to 2–38 characters and posts to 2–2000. Server permission
        refusals raise CommandError. No created id is returned by the client handler.
        """
        forum_text(name, 38)
        forum_text(text, 2000)
        with self._own_alliance():
            self.execute(CreateForumTopicRequest(name=name, text=text, visible_ranks=visible_ranks), timeout=timeout)

    def reply(self, topic_id: int, text: str, *, timeout: float = 5.0) -> None:
        """Post a reply to a forum topic; permission refusals raise CommandError."""
        forum_text(text, 2000)
        with self._own_alliance():
            self.execute(ReplyToForumTopicRequest(topic_id=topic_id, text=text), timeout=timeout)

    def delete_topic(self, topic_id: int, *, timeout: float = 5.0) -> None:
        """Delete a forum topic; permission refusals raise CommandError."""
        with self._own_alliance():
            self.execute(DeleteForumTopicRequest(topic_id=topic_id), timeout=timeout)

    def delete_reply(self, topic_id: int, reply_id: int, *, timeout: float = 5.0) -> None:
        """Delete a forum post; permission refusals raise CommandError."""
        with self._own_alliance():
            self.execute(DeleteForumReplyRequest(topic_id=topic_id, reply_id=reply_id), timeout=timeout)

    def set_topic_visibility(
        self, topic_id: int, visible_ranks: list[ForumRankGroup], *, timeout: float = 5.0
    ) -> GetForumTopicResponse | None:
        """Change the rank groups that can see a topic, returning its details when echoed."""
        with self._own_alliance():
            return self.request(
                SetForumVisibilityRequest(topic_id=topic_id, visible_ranks=visible_ranks),
                SetForumVisibilityResponse,
                timeout=timeout,
            ).topic

    def get_forum_topics(self, *, timeout: float = 5.0) -> GetForumTopicsResponse:
        """Get visible forum topics, newest post first, and the total including hidden topics."""
        with self._own_alliance():
            return self.request(GetForumTopicsRequest(), GetForumTopicsResponse, timeout=timeout)

    def get_topic(self, topic_id: int, *, timeout: float = 5.0) -> GetForumTopicResponse:
        """Open a forum topic and its posts. Opening it may mark it read on the server.

        Client: ``CastleForumViewTopic.requestTopicData`` sends ``gtr`` (bundle line 33651);
        ``GTRCommand.executeCommand`` (bundle line 121768) reads the topic, with
        unread counts delivered separately by ``UTCCommand`` (bundle line 121785).
        """
        with self._own_alliance():
            return self.request(GetForumTopicRequest(topic_id=topic_id), GetForumTopicResponse, timeout=timeout)

    def get_unread_topic_count(self, *, timeout: float = 5.0) -> int:
        """Request the number of unread forum topics."""
        with self._own_alliance():
            return self.request(GetUnreadTopicCountRequest(), GetUnreadTopicCountResponse, timeout=timeout).count

    # =========================================================================
    # Member Operations
    # =========================================================================

    def get_alliance_info(self, alliance_id: int, *, timeout: float = 5.0) -> AllianceInfo:
        """
        Get info about an alliance.

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another is an
                ``AllianceSearchResult.alliance_id`` from ``client.alliance.search_alliances()``
            timeout: Timeout in seconds

        Raises:
            PacketError: The reply names no alliance (no ``AID``), which the client does not read
                (``CastleAllianceData.parseAllianceInfo``, bundle line 11605)
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        request = GetAllianceInfoRequest(alliance_id=alliance_id)
        with self.client.connection.command_lock("ain", timeout=timeout):
            if self.local_alliance_id == alliance_id:
                with self.client.state.alliance_info_read(alliance_id):
                    return _echoed(self.request(request, GetAllianceInfoResponse, timeout=timeout).alliance, "ain")
            return _echoed(self.request(request, GetAllianceInfoResponse, timeout=timeout).alliance, "ain")

    def get_members(self, alliance_id: int, *, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get the list of alliance members from the server.

        This fetches alliance info and returns all members with their
        online status (via AMI array), level, rank, etc.

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another
                alliance's is ``AllianceSearchResult.alliance_id`` from :meth:`search_alliances`
                or a player's ``client.player.get_player_info(player_id).alliance_id``
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceMember objects

        Example:
            members = client.alliance.get_members(301)
            for member in members:
                print(f"{member.name}: online={member.is_online}")
        """
        response = self.request(
            GetAllianceInfoRequest(alliance_id=alliance_id), GetAllianceInfoResponse, timeout=timeout
        )
        return response.members

    def get_online_members(self, alliance_id: int, *, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get alliance members who are currently online.

        Fetches the member list and filters to only online members
        (members with online status from AMI array).

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another
                alliance's is ``AllianceSearchResult.alliance_id`` from :meth:`search_alliances`
                or a player's ``client.player.get_player_info(player_id).alliance_id``
            timeout: Timeout in seconds to wait for response

        Returns:
            List of online AllianceMember objects

        Example:
            online = client.alliance.get_online_members(301)
            print(f"{len(online)} members online")
        """
        members = self.get_members(alliance_id, timeout=timeout)
        return [m for m in members if m.is_online]

    def get_member(self, alliance_id: int, player_id: int, *, timeout: float = 5.0) -> AllianceMember | None:
        """
        Get one member of an alliance, from a fresh member list.

        Your own alliance's members are also in ``client.state.get_own_alliance()``, without a request.

        Args:
            alliance_id: The alliance, as for :meth:`get_members`
            player_id: The member's ``AllianceMember.player_id``

        Returns:
            The member, or None when the alliance has no such member
        """
        return next((m for m in self.get_members(alliance_id, timeout=timeout) if m.player_id == player_id), None)

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

    # =========================================================================
    # Diplomacy, Newsletter and Donations
    # =========================================================================

    def change_diplomacy(
        self, alliance_id: int, new_status: DiplomacyStatus, tribute: int = 0, *, timeout: float = 5.0
    ) -> ChangeDiplomacyResponse:
        """
        Change or propose your alliance's relation with another alliance.

        Args:
            alliance_id: The other alliance, e.g. ``AllianceDiplomacyStatus.alliance_id``
            new_status: The relation to change to
            tribute: Only to accept a peace offer: ``PeaceOffer.tribute`` as the offer states it

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceInfoDialogDiplomacy.updateButtons`` (bundle line 72349) offers
        each change from the other alliance's status to your own
        """
        request = ChangeDiplomacyRequest(alliance_id=alliance_id, new_status=new_status, tribute=tribute)
        with self._own_alliance():
            return self.request(request, ChangeDiplomacyResponse, timeout=timeout)

    def refuse_diplomacy(self, alliance_id: int, *, timeout: float = 5.0) -> AllianceInfo | None:
        """
        Refuse another alliance's diplomacy request or peace offer.

        Returns:
            The other alliance after the refusal

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            PacketError: The reply carries no alliance
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``ARDCommand.executeCommand`` (bundle line 121574) reads the reply's ``A``;
        ``CastleAllianceDialogDiplomacy`` opens the dialogs that refuse (bundle lines 69323, 69352)
        """
        with self._own_alliance():
            response = self.request(
                RefuseDiplomacyRequest(alliance_id=alliance_id), RefuseDiplomacyResponse, timeout=timeout
            )
        return _echoed(response.alliance, "ard")

    def set_auto_war(self, enabled: bool, *, timeout: float = 5.0) -> bool:
        """
        Turn auto war on or off.

        Returns:
            Whether auto war is on afterwards

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        request = SetAutoWarRequest(auto_war=1 if enabled else 0)
        with self._own_alliance():
            return self.request(request, SetAutoWarResponse, timeout=timeout).auto_war

    def send_newsletter(self, subject: str, text: str, *, timeout: float = 5.0) -> None:
        """
        Send the alliance newsletter to every member.

        Args:
            subject: The subject (the client's field takes 20 characters)
            text: The text; the client does not send an empty one

        Raises:
            ValueError: ``text`` is empty
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        if not text:
            raise ValueError("a newsletter needs text")
        with self._own_alliance():
            self.execute(SendNewsletterRequest.create(subject, text), timeout=timeout)

    def donate(
        self, castle_id: int, donation: AllianceDonation, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> DonateResponse:
        """
        Donate resources from one of your castles to the alliance treasury.

        Donating ``AllianceDonation.rubies`` spends them; see "Spending rubies" in the guides.

        Args:
            castle_id: The donating castle, a ``Castle.id`` from ``client.state.get_castles()``
            donation: The amounts; the client sends nothing when every amount is 0
            spend_rubies: Allow a donation of rubies
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            ValueError: every amount is 0, or rubies are donated and ``spend_rubies`` is False
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceDonateDialog.onDonateForAlliance`` (bundle line 45576) sends
        the picked castle's ``objectId`` and ``kingdomID``
        """
        request = DonateRequest.create(castle_id, self._require_own_castle(castle_id).kingdom_id, donation)
        if not request.resources:
            raise ValueError("a donation needs an amount above 0")
        self._require_spend_rubies(
            spend_rubies, f"donating {donation.rubies} rubies spends them" if donation.rubies > 0 else None
        )
        with self._own_alliance():
            return self.request(request, DonateResponse, timeout=timeout)

    # =========================================================================
    # Search Operations
    # =========================================================================

    def search_alliances(self, search_term: str, *, timeout: float = 5.0) -> list[AllianceSearchResult]:
        """
        Search for alliances by name.

        Args:
            search_term: The alliance name to search for (partial match)
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceSearchResult objects matching the search; empty when
            the server finds none (``ALLI_NOT_FOUND``), which the client
            shows as "alliance not found" (``HGHCommand.executeCommand``, bundle line 124377)

        Raises:
            CommandError: The server refused for another reason
            PacketError: The reply's payload is not an object

        Example:
            results = client.alliance.search_alliances("PACT")
            for alliance in results:
                print(f"{alliance.name} (ID: {alliance.alliance_id}, {alliance.member_count} members)")

        Note: 'hgh' is shared with the highscore command. Requests for it run
        one at a time, but after one times out its late reply can be taken by
        the next, a get_highscore() call included. Replies carry ``LT`` and
        ``LID``, but the client takes the list and league a reply names rather
        than the ones it asked for, so no reply is refused on them (see
        ``GetHighscoreRequest``).
        """
        request = SearchAllianceRequest.create(search_term)
        # SearchAllianceResponse is read here because the 'hgh' registry entry
        # is owned by GetHighscoreResponse.
        response_packet = self.client.request_packet(request, "hgh", timeout=timeout)

        if response_packet.error_code == GGEError.ALLI_NOT_FOUND:
            return []
        if response_packet.error_code != 0:
            raise CommandError("hgh", response_packet.error_code)

        if not isinstance(response_packet.payload, dict):
            raise PacketError(f"'hgh' reply payload is not an object: {type(response_packet.payload).__name__}")
        try:
            response = SearchAllianceResponse.model_validate(response_packet.payload)
        except ValidationError as e:
            # PacketError is the documented parse-failure type of request();
            # a raw pydantic error must not leak out of the service layer.
            raise PacketError(f"Could not parse 'hgh' response: {e}") from e

        logger.debug(f"Alliance search found {len(response.results)} results")
        return list(response.results)

    # =========================================================================
    # Own Alliance Operations
    # =========================================================================

    @property
    def local_alliance_id(self) -> int | None:
        """
        Get the local player's alliance ID.

        Returns:
            Alliance ID if in an alliance, None otherwise: the player data sends
            a negative ``AID`` outside one

        Raises:
            StateNotLoadedError: No login has brought the player data

        Client: ``CastleUserData.isInAlliance`` (bundle line 9986) is ``allianceID >= 0``
        """
        alliance_id = self.client.state.get_local_player().alliance_id
        return alliance_id if alliance_id is not None and alliance_id >= 0 else None

    def _require_local_alliance_id(self) -> int:
        alliance_id = self.local_alliance_id
        if alliance_id is None:
            raise NotInAllianceError()
        return alliance_id

    def _request_membership(
        self, request: BaseRequest, response_type: type[_MembershipResponse], *, timeout: float
    ) -> tuple[_MembershipResponse, dict[str, Any]]:
        packet = self.client.request_packet(request, request.command, timeout=timeout)
        if packet.error_code != 0:
            raise CommandError(request.command, packet.error_code, packet.payload)
        if not isinstance(packet.payload, dict):
            raise PacketError(f"'{request.command}' reply payload is not an object")
        try:
            response = response_type.model_validate(packet.payload)
        except ValidationError as error:
            raise PacketError(f"Could not parse '{request.command}' response: {error}") from error
        return response, packet.payload

    @contextmanager
    def _membership_change(self, *, timeout: float) -> Iterator[int]:
        with (
            self.client.connection.command_lock("joa", timeout=timeout),
            self.client.connection.command_lock("aai", timeout=timeout),
            self.client.connection.command_lock("afo", timeout=timeout),
        ):
            yield self.client.state.membership_revision

    @contextmanager
    def _own_alliance(self, *, sent_outside_one: bool = False) -> Iterator[None]:
        """
        A call about your own alliance: nothing is sent outside one, and the server's
        ``ALLI_NOT_FOUND`` (a stale ``AID``) raises :class:`NotInAllianceError`.

        ``sent_outside_one`` sends regardless, for a request the client sends outside an alliance too.

        Client: the senders sit in ``CastleAllianceDialog`` and the dialogs it opens, and it
        hides once ``isInAlliance`` turns false (bundle line 4893); the chronicle's is
        ``CastleAllianceDialogOverview`` (bundle line 70407)
        """
        if not sent_outside_one:
            self._require_local_alliance_id()
        try:
            yield
        except CommandError as e:
            if e.error is GGEError.ALLI_NOT_FOUND:
                raise NotInAllianceError() from e
            raise

    def get_local_members(self, *, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get members of the local player's alliance.

        Convenience method that automatically uses the logged-in player's
        alliance ID.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            List of AllianceMember objects

        Raises:
            NotInAllianceError: You are in no alliance; nothing is sent

        Example:
            members = client.alliance.get_local_members()
            for member in members:
                print(f"{member.name}: {'online' if member.is_online else 'offline'}")
        """
        return self.get_members(self._require_local_alliance_id(), timeout=timeout)

    def get_local_online_members(self, *, timeout: float = 5.0) -> list[AllianceMember]:
        """
        Get online members of the local player's alliance.

        Convenience method that automatically uses the logged-in player's
        alliance ID and filters to online members only.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            List of online AllianceMember objects

        Raises:
            NotInAllianceError: You are in no alliance; nothing is sent

        Example:
            online = client.alliance.get_local_online_members()
            print(f"{len(online)} alliance members online")
        """
        return self.get_online_members(self._require_local_alliance_id(), timeout=timeout)

    def get_chronicle(self, *, timeout: float = 5.0) -> list[AllianceChronicleEntry]:
        """
        Get your alliance's chronicle, newest first.

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceDialogOverview`` (bundle line 70407) asks for it
        """
        with self._own_alliance():
            return self.request(AllianceChronicleRequest(), AllianceChronicleResponse, timeout=timeout).entries

    def get_subscriber_count(self, *, timeout: float = 5.0) -> int:
        """
        Get how many of your alliance's members have a subscription.

        Sent outside an alliance too, as the client sends it at login and right after leaving one.

        Raises:
            NotInAllianceError: The server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``SubscriptionData.onGbdArrived`` (bundle line 120092) and
        ``AQICommand.executeCommand`` (bundle line 121557) call ``requestASC``
        """
        with self._own_alliance(sent_outside_one=True):
            response = self.request(AllianceSubscriberCountRequest(), AllianceSubscriberCountResponse, timeout=timeout)
        return response.subscriber_count

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

    def get_chat_log(self, *, timeout: float = 5.0) -> list[ChatMessageData]:
        """
        Get alliance chat history.

        The game client never asks for acl; it only reads the acl the server
        sends, which a live server pushes once at login. A live server also
        answers this request, with the same ``CM`` list.

        Args:
            timeout: Timeout in seconds to wait for response

        Returns:
            The messages of the acl reply's ``CM`` list

        Example:
            history = client.alliance.get_chat_log()
            for entry in history:
                print(f"{entry.player_name}: {entry.decoded_text}")
        """
        return self.request(AllianceChatLogRequest(), AllianceChatLogResponse, timeout=timeout).chat_log

    on_chat_message = Event[AllianceChatMessageResponse]()
    """
    Register a callback for incoming alliance chat messages.

    The callback will be called whenever a chat message is received,
    including messages from other players and confirmations of your own.

    Callbacks run on the receive thread: they must not block, and a call
    that waits for a reply raises ``ReceiveThreadError``.

    Args:
        callback: Function that receives AllianceChatMessageResponse

    Example:
        def on_message(msg: AllianceChatMessageResponse):
            print(f"[{msg.player_name}] {msg.decoded_text}")

        client.alliance.on_chat_message(on_message)

    ``on_chat_message.remove(callback)`` detaches it, a no-op if it is not
    registered, so reconnect re-wiring can detach unconditionally.
    """

    def _handle_chat_message(self, response) -> None:
        """Internal handler for chat message responses."""
        if isinstance(response, AllianceChatMessageResponse):
            self._fire(self.on_chat_message, response)

    # =========================================================================
    # Help Operations
    # =========================================================================

    @property
    def help_requests(self) -> list[AllianceHelpRequest]:
        """
        The alliance help list as the login data and the pushes since left it; nothing is sent.

        The login data's ``ahl`` section fills it, and so does an ahl push; ahh replaces or adds a
        request by ``LID``, ahd removes one, and leaving your alliance empties it. It is kept when
        the session drops, as the client keeps it.
        """
        return self.client.state.get_alliance_help()

    on_help_update = Event[AllianceHelpUpdate]()
    """
    Call ``callback`` with the login data's ahl section and each ahl, ahh, ahd and ahf push,
    after :attr:`help_requests` is updated.

    Detach it again with ``on_help_update.remove(callback)``, a no-op if it is not registered.
    """

    def _handle_help_update(self, response: BaseResponse) -> None:
        if isinstance(response, AllianceHelpRequestChanged) and response.request is None:
            return
        if isinstance(response, AllianceHelpUpdate):
            self._fire(self.on_help_update, response)

    def help_member(self, request: AllianceHelpRequest | int) -> None:
        """
        Help one request on the help list.

        The client has no handler for an ahc answer, so none is waited for.

        Args:
            request: An :class:`AllianceHelpRequest` from :attr:`help_requests`, or its ``list_id``
        """
        list_id = request.list_id if isinstance(request, AllianceHelpRequest) else request
        self.send(HelpMemberRequest(list_id=list_id))

    def help_all(self) -> None:
        """
        Help every request on the help list.

        The client has no handler for an aha answer, so none is waited for.
        """
        self.send(HelpAllRequest())

    def request_build_help(self, building_id: int, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help build a building.

        Args:
            building_id: The building's object id, e.g. ``BuildResponse.building_id``
        """
        self.execute(AskHelpRequest.build(building_id), timeout=timeout)

    def request_repair_help(self, building_id: int, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help repair a building.

        Args:
            building_id: The damaged building's object id
        """
        self.execute(AskHelpRequest.repair(building_id), timeout=timeout)

    def request_recruit_help(self, recruit_id: int, help_type: HelpType, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help with a recruitment.

        Args:
            recruit_id: The recruitment's id; the library does not read recruitment ids yet
            help_type: ``HelpType.RECRUITMENT``, ``LOOP_RECRUIT`` or ``RECRUITMENT_LIST``
        """
        self.execute(AskHelpRequest.recruit(recruit_id, help_type), timeout=timeout)

    def request_heal_help(self, hospital_entry_id: int, hospital_list_id: int, *, timeout: float = 5.0) -> None:
        """
        Ask the alliance to help heal wounded units.

        Args:
            hospital_entry_id: The hospital entry; the library does not read hospital entry ids yet
            hospital_list_id: The hospital list the entry is on
        """
        self.execute(AskHelpRequest.heal(hospital_entry_id, hospital_list_id), timeout=timeout)

    # =========================================================================
    # Bookmark Operations
    # =========================================================================

    def get_bookmarks(self, *, timeout: float = 5.0) -> GetBookmarksResponse:
        """
        Get your own and your alliance's map bookmarks.

        Returns:
            The gbl reply: ``own_bookmarks`` and ``alliance_bookmarks``

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetBookmarksRequest(), GetBookmarksResponse, timeout=timeout)

    def add_bookmark(
        self,
        x: int,
        y: int,
        name: str,
        bookmark_type: BookmarkType = BookmarkType.PLAYER_FRIEND,
        kingdom: Kingdom = Kingdom.GREEN,
        *,
        attack_in_seconds: int | None = None,
        attacker_ids: list[int] | None = None,
        message_attackers: bool = True,
        timeout: float = 5.0,
    ) -> Bookmark:
        """
        Bookmark a map position: for yourself as a friend or an enemy, or for your alliance.

        An own list holds ``MAX_PLAYER_BOOKMARKS``, an alliance's ``MAX_ALLIANCE_BOOKMARKS``;
        the server refuses a bookmark past them.

        Args:
            x: Map x
            y: Map y
            name: 1 to ``BOOKMARK_NAME_MAX_LENGTH`` characters, sent as typed
            bookmark_type: What it marks; the alliance types need the right to manage bookmarks
            kingdom: The kingdom
            attack_in_seconds: An alliance attack order's attack, ``ATTACK_ORDER_MIN_SECONDS``
                to ``ATTACK_ORDER_MAX_SECONDS`` from now; only for ``ALLIANCE_ATTACK_ORDER``
            attacker_ids: The members an attack order sends, at least one; only for ``ALLIANCE_ATTACK_ORDER``
            message_attackers: Whether an attack order's attackers get a message (the client's default)
            timeout: Timeout in seconds

        Returns:
            The bookmark added, with its ``bookmark_id``

        Raises:
            ValueError: The client's bookmark dialog would not send it
            NotInAllianceError: An alliance type while you are in no alliance; nothing is sent
            CommandError: The server refused it: ``BOOKMARK_ALREADY_ADDED``, ``BOOKMARK_MAX_ENTRYS``,
                ``NO_SELF_TARGET`` (your own castle) and the others ``BADCommand`` shows
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SAddBookmark`` (bundle line 68517), sent by
        ``CastleWorldmapBookmarkSetDialog.onSubmitButtonClicked`` (bundle line 19584) once
        ``isNameValid`` holds and, for an attack order, ``checkButtonSubmitState`` (bundle line
        19547) sees an attacker; the time range is ``TeamAttackConfiguration``'s (bundle line
        68564); the alliance tab is enabled only by ``playerCanCreateAllianceBookmark`` (bundle
        line 19563), which needs ``isInAlliance``; ``BADCommand`` (bundle line 131653)
        """
        bookmark_type = BookmarkType(bookmark_type)
        _check_bookmark_name(name)
        is_attack_order = bookmark_type == BookmarkType.ALLIANCE_ATTACK_ORDER
        if not is_attack_order and (attack_in_seconds is not None or attacker_ids is not None):
            raise ValueError("attack_in_seconds and attacker_ids are only for an ALLIANCE_ATTACK_ORDER bookmark")
        if is_attack_order and not attacker_ids:
            raise ValueError("an attack order sends at least one attacker")
        if is_attack_order and (
            attack_in_seconds is None or not ATTACK_ORDER_MIN_SECONDS <= attack_in_seconds <= ATTACK_ORDER_MAX_SECONDS
        ):
            raise ValueError(
                f"an attack order's attack_in_seconds is {ATTACK_ORDER_MIN_SECONDS} to "
                f"{ATTACK_ORDER_MAX_SECONDS}, got {attack_in_seconds!r}"
            )
        if bookmark_type not in _PLAYER_BOOKMARK_TYPES:
            self._require_local_alliance_id()
        request = AddBookmarkRequest(
            kingdom=kingdom,
            x=x,
            y=y,
            bookmark_type=bookmark_type,
            attack_in_seconds=attack_in_seconds if attack_in_seconds is not None else -1,
            message_attackers=1 if is_attack_order and message_attackers else 0,
            name=name,
            attacker_ids=list(attacker_ids or []),
        )
        return self.request(request, AddBookmarkResponse, timeout=timeout)

    def change_bookmark(
        self,
        x: int,
        y: int,
        name: str,
        bookmark_type: BookmarkType = BookmarkType.PLAYER_FRIEND,
        kingdom: Kingdom = Kingdom.GREEN,
        *,
        timeout: float = 5.0,
    ) -> Bookmark:
        """
        Rename one of your own bookmarks, or switch it between friend and enemy.

        Args:
            x: The bookmark's map x
            y: The bookmark's map y
            name: The new name, 1 to ``BOOKMARK_NAME_MAX_LENGTH`` characters, sent as typed
            bookmark_type: ``PLAYER_FRIEND`` or ``PLAYER_ENEMY``
            kingdom: The bookmark's kingdom
            timeout: Timeout in seconds

        Returns:
            The bookmark changed

        Raises:
            ValueError: An alliance type, or a name the dialog would refuse; the client changes
                only own bookmarks
            CommandError: The server refused it
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SChangeBookmark`` (bundle line 68532), sent by
        ``CastleWorldmapBookmarkSetDialog.onSubmitButtonClicked`` (bundle line 19584) for an own
        bookmark it edits; ``BCHCommand`` (bundle line 131672)
        """
        bookmark_type = BookmarkType(bookmark_type)
        if bookmark_type not in _PLAYER_BOOKMARK_TYPES:
            raise ValueError(f"only own bookmarks change: PLAYER_FRIEND or PLAYER_ENEMY, got {bookmark_type!r}")
        _check_bookmark_name(name)
        friend = bookmark_type == BookmarkType.PLAYER_FRIEND
        request = ChangeBookmarkRequest(kingdom=kingdom, x=x, y=y, friend=friend, name=name)
        return self.request(request, ChangeBookmarkResponse, timeout=timeout)

    def delete_bookmark(self, bookmark: Bookmark, *, notify_attackers: bool = False, timeout: float = 5.0) -> None:
        """
        Delete a bookmark: one of your own by its position, an alliance one by its id.

        Args:
            bookmark: A ``Bookmark`` from :meth:`get_bookmarks` or :meth:`add_bookmark`
            notify_attackers: For an alliance bookmark, tell an attack order's attackers, as the
                delete dialog's notify button does
            timeout: Timeout in seconds

        Raises:
            ValueError: The bookmark has no type the client knows, so it sends nothing
            NotInAllianceError: An alliance bookmark while you are in no alliance; nothing is sent

        Client: ``CastleBookmarkData.deleteBookmark`` (bundle line 33474) sends ``C2SDeleteBookmark``
        (bundle line 68457) for an own bookmark and ``C2SDeleteAllianceBookmark`` (bundle line 68446)
        for an alliance one. ``deleteBookmark`` checks no alliance itself; nothing is sent outside
        one, as the client creates alliance bookmarks only with ``isInAlliance``
        (``playerCanCreateAllianceBookmark``, bundle line 19563)
        """
        bookmark_type = bookmark.bookmark_type_enum
        if bookmark_type in _PLAYER_BOOKMARK_TYPES:
            request: BaseRequest = DeleteBookmarkRequest(positions=[[bookmark.kingdom, bookmark.x, bookmark.y]])
        elif bookmark_type is not None:
            self._require_local_alliance_id()
            request = DeleteAllianceBookmarkRequest(entries=[[bookmark.bookmark_id, 1 if notify_attackers else 0]])
        else:
            raise ValueError(f"bookmark type {bookmark.bookmark_type!r} is neither an own nor an alliance bookmark")
        self.execute(request, timeout=timeout)


__all__ = ["AllianceHelpUpdate", "AllianceService"]
