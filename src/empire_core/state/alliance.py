"""Your own alliance's details (ain), the alliance chat history (acl, acm) and the help list (ahl, ahh, ahd)."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from empire_core.alliance.models.chat import AllianceChatLogResponse, AllianceChatMessageResponse, ChatMessageData
from empire_core.alliance.models.gifts import AllianceGift, AllianceGiftReceived
from empire_core.alliance.models.help import (
    AllianceHelpListResponse,
    AllianceHelpRequest,
    AllianceHelpRequestChanged,
    AllianceHelpRequestRemoved,
)
from empire_core.alliance.models.horizon import (
    HorizonMemberPerformance,
    HorizonPerformanceResponse,
    JadePhase,
    JadePhaseResponse,
)
from empire_core.alliance.models.info import (
    AllianceBuffsResponse,
    AllianceCrestChangedResponse,
    AllianceCrests,
    AllianceGloryResponse,
    AllianceInfo,
    GetAllianceInfoResponse,
)
from empire_core.alliance.models.landmarks import AllianceLaboratoriesResponse
from empire_core.alliance.models.membership import (
    AllianceMembership,
    AllianceMembershipChange,
    AutoJoinedAllianceResponse,
)
from empire_core.enums import OnlineState
from empire_core.exceptions import ReplyMismatchError
from empire_core.player.models.aqua import CargoPointsResponse, StormIslandsInfo
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_int
from empire_core.state.base import StateBase, read_section
from empire_core.state.login_data import LoginDataResponse

logger = logging.getLogger(__name__)


class AllianceState(StateBase):
    def _parse_own_alliance(self, login: LoginDataResponse) -> bool:
        """Apply an ``ain`` section when it is about your own alliance; whether it was applied.

        Other alliances' details (``client.alliance.get_alliance_info(other_id)``) are not kept.
        A reply for the same alliance is read over the last one (:meth:`AllianceInfo.filled_over`).

        Client: ``CastleAllianceData.parse_AIN`` (split.js line 61657) and ``parseAllianceInfo``
        (split.js line 61810), which keeps the alliance whose ``AID`` is ``userData.allianceID`` as
        ``myAllianceVO``
        """
        alliance = login.alliance_info.alliance if login.alliance_info is not None else None
        if alliance is None or not self._is_own_alliance(alliance):
            return False
        previous = self.own_alliance
        if previous is not None and previous.alliance_id == alliance.alliance_id:
            alliance = alliance.filled_over(previous)
        self._store_own_alliance(alliance)
        return True

    def _is_own_alliance(self, alliance: AllianceInfo) -> bool:
        player = self.local_player
        return player is not None and player.AID is not None and alliance.alliance_id == js_int(player.AID)

    def _store_own_alliance(self, alliance: AllianceInfo) -> None:
        for name in AllianceInfo.model_fields:
            self._alliance_field_order[name] = self._packet_sequence
        self.own_alliance = alliance

    def _patch_own_alliance(self, **fields: Any) -> None:
        """Change ``fields`` of your alliance's details, while they are about your alliance."""
        alliance = self.own_alliance
        if alliance is None or not self._is_own_alliance(alliance):
            return
        patched = alliance.model_copy(deep=True, update=fields)
        patched.model_post_init(None)
        for name in fields:
            self._alliance_field_order[name] = self._packet_sequence
        self.own_alliance = patched

    def _handle_afa(self, data: Any) -> None:
        """Client: ``AllianceInfoVO.parseAFA`` (bundle line 26001); see :class:`AllianceGloryResponse`."""
        if not isinstance(data, dict) or "raw" in data:
            return
        if (glory := read_section(AllianceGloryResponse, data, "the alliance's glory")) is not None:
            self._patch_own_alliance(glory_points=glory.glory_points, highest_glory_points=glory.highest_glory_points)

    def _handle_abl(self, data: Any) -> None:
        """Client: ``AllianceInfoVO.parseABL`` (bundle line 26003); see :class:`AllianceBuffsResponse`."""
        buffs = read_or_none(AllianceBuffsResponse.model_validate, data, warn=logger, what="the alliance's buffs")
        if buffs is not None:
            self._patch_own_alliance(buildings=list(buffs.buildings))

    def _handle_aee(self, data: Any) -> None:
        """Client: ``AEECommand`` (bundle line 121450); see :class:`AllianceCrestChangedResponse`.

        A missing current crest stays unknown rather than random.
        """
        changed = read_section(AllianceCrestChangedResponse, data, "the alliance's crest")
        if changed is None or changed.crests is None:
            return
        fallback = changed.fallback_crest if changed.fallback_crest is not None else changed.crests.fallback_crest
        self._patch_own_alliance(crests=AllianceCrests(crest=changed.crests.crest, fallback_crest=fallback))

    def _handle_sll(self, data: Any) -> None:
        """Client: ``CastleAllianceData.parseSLL`` (split.js line 61793) replaces your alliance's laboratories."""
        if (listed := read_section(AllianceLaboratoriesResponse, data, "the alliance's laboratories")) is not None:
            self._patch_own_alliance(laboratories=list(listed.laboratories))

    def _handle_gap(self, data: Any) -> None:
        """Keep your cargo points and your alliance's.

        Client: ``CastleUserData.parse_GAP`` (bundle line 9881) sets ``P`` on the player and ``A`` on
        your alliance, when it knows one
        """
        points = read_section(CargoPointsResponse, data, "the cargo points")
        if points is None:
            return
        self.cargo_points = points.player_points
        if "alliance_points" in points.model_fields_set:
            self._patch_own_alliance(cargo_points=points.alliance_points)

    def _handle_sii(self, data: Any) -> None:
        """Keep your and your alliance's Storm Islands standing, and your cargo points.

        Client: ``SIICommand.executeCommand`` (bundle line 127742) sets ``AP`` as your cargo points
        """
        info = read_section(StormIslandsInfo, data, "the Storm Islands standing")
        if info is None:
            return
        self.storm_islands = info
        self.cargo_points = info.cargo_points

    def get_storm_islands(self) -> StormIslandsInfo | None:
        """Your and your alliance's Storm Islands standing, from the last ``sii``; None until one arrived."""
        with self._lock:
            return self.storm_islands

    def _handle_gae(self, data: Any) -> None:
        """Keep your alliance members' Beyond the Horizon performance.

        Client: ``CastleAllianceBattleGroundData.parseAlliancePerformance`` (bundle line 144898) replaces
        ``alliancePerformanceVOs``
        """
        performance = read_section(HorizonPerformanceResponse, data, "Beyond the Horizon performance")
        if performance is not None:
            self.horizon_performance = tuple(performance.members)

    def _handle_abgi(self, data: Any) -> None:
        """Apply a Jade Desert scoring phase push over the phase the earlier ones left.

        Client: ``AllianceBattleGroundEventVO.parseJadePhaseInfo`` (split.js line 585444)
        """
        push = read_section(JadePhaseResponse, data, "the Jade Desert's scoring phase")
        if push is not None:
            self.jade_phase = (self.jade_phase or JadePhase()).updated(push, time.time())

    def _handle_aja(self, data: Any) -> None:
        """Apply your new membership, then the alliance you were put in.

        Client: ``AJACommand.executeCommand`` (split.js line 623480): ``parse_GAL(o.gal)``, then
        ``parseAllianceInfo(o.A)``
        """
        if (joined := read_section(AutoJoinedAllianceResponse, data, "an automatic alliance join")) is not None:
            self._apply_login(
                LoginDataResponse(
                    alliance=joined.membership, alliance_info=GetAllianceInfoResponse(alliance=joined.alliance)
                )
            )

    def _forget_own_alliance(self) -> None:
        self._alliance_field_order = {}
        self._alliance_reply_order = {}
        self.own_alliance = None
        self.alliance_chat = ()
        self.alliance_help = ()
        self.alliance_gifts = ()

    def _apply_gal_reset(
        self, membership: AllianceMembership | None, *, present: bool, previous_alliance_id: int | None
    ) -> None:
        """Forget details, chat and help when a ``gal`` changes your alliance identity.

        Args:
            membership: The gal section as read, None when the packet has none or it is no object
            present: Whether the packet carried a gal section at all
            previous_alliance_id: Your alliance before the section was applied

        Client: ``CastleUserData.parse_GAL`` (bundle line 9876): ``_allianceID<0`` runs
        ``chatData.resetHistory`` and ``allianceData.resetMyAlliance``
        """
        if present:
            self.membership_revision += 1
        if membership is not None:
            player = self.local_player
            aid = membership.alliance_id
            if aid < 0 or (aid > 0 and player is not None and player.AID != previous_alliance_id):
                self._forget_own_alliance()

    def apply_membership_response(self, data: dict[str, Any], *, membership_revision: int) -> None:
        """Apply only an accepted service reply, while its membership context is still current.

        The service scopes these replies so rejected or late replies cannot replace a newer
        authoritative ``gal`` or a new session.

        Client: ``JOACommand`` / ``AAICommand`` (split.js lines 624892 / 622475) apply gal before A,
        ``AASCommand`` (split.js line 622569) gal, then the movements of a truthy gam; see
        :class:`AllianceMembershipChange`
        """
        change = read_section(AllianceMembershipChange, data, "a membership reply")
        if change is None:
            return
        sections: dict[str, Any] = {}
        if change.membership is not None:
            sections["gal"] = change.membership
        if change.alliance is not None:
            sections["ain"] = GetAllianceInfoResponse(alliance=change.alliance)
        if not sections:
            return
        with self._lock:
            if self.membership_revision != membership_revision:
                expected = change.membership.alliance_id if change.membership is not None else -1
                current = self.local_player.AID if self.local_player is not None else None
                raise ReplyMismatchError(expected, current if current is not None else -1)
            self._apply_login(LoginDataResponse.model_validate(sections))
            if change.membership is not None and change.movements is not None:
                self._apply_movement_list(change.movements, ())

    @contextmanager
    def alliance_info_read(self, alliance_id: int) -> Iterator[None]:
        """Scope an own-alliance read to its membership while the command lock is held."""
        with self._lock:
            revision = self.membership_revision
            self._alliance_info_read_revision = revision
        try:
            yield
            with self._lock:
                self._require_membership_revision(revision, alliance_id)
        finally:
            with self._lock:
                self._alliance_info_read_revision = None

    def alliance_upgrade_sequence(self) -> int:
        """Receive sequence before an upgrade's fresh alliance-info read."""
        with self._lock:
            return self._packet_sequence

    def require_alliance_upgrade_preflight(
        self,
        sequence: int,
        *,
        membership_revision: int,
        alliance_id: int,
        payload: dict[str, Any] | None = None,
    ) -> int:
        """Reject costs superseded by received buff data, in the same membership.

        Client: AllianceInfoVO.getUpgradeCosts (bundle 26031) reads the current
        buff level; a previously received level cannot authorize its next price.
        """
        with self._lock:
            self._require_membership_revision(membership_revision, alliance_id)
            receipt = self._alliance_reply_order.get("ain")
            if payload is not None and receipt is not None and receipt[0] is payload:
                sequence = receipt[1]
            if self._alliance_field_order.get("buildings", 0) > sequence:
                raise ValueError("alliance buffs changed during the upgrade preflight; request the upgrade again")
            return sequence

    def apply_alliance_settings(
        self,
        data: dict[str, Any],
        *,
        membership_revision: int,
        alliance_id: int,
        command: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Apply validated settings only in the membership that sent the request."""
        with self._lock:
            self._require_membership_revision(membership_revision, alliance_id)
            if command is None:
                return
            sequence = self._alliance_reply_sequence(command, payload)
            reply = read_section(GetAllianceInfoResponse, data, "an alliance settings reply")
            alliance = reply.alliance if reply is not None else None
            if alliance is None or not self._is_own_alliance(alliance):
                return
            if self.own_alliance is None:
                self._store_own_alliance(alliance)
                return
            superseded = {name for name, order in self._alliance_field_order.items() if order > sequence}
            self._patch_own_alliance(**{name: getattr(alliance, name) for name in alliance.read_fields - superseded})

    def apply_auto_war(
        self, enabled: bool, *, membership_revision: int, alliance_id: int, payload: dict[str, Any]
    ) -> None:
        """Set your alliance's auto war from an accepted ``saw`` reply, in the membership that sent it.

        Client: ``SAWCommand.executeCommand`` (split.js line 625171) sets ``myAllianceVO.autoWarOn``
        """
        with self._lock:
            self._require_membership_revision(membership_revision, alliance_id)
            if self._alliance_field_order.get("auto_war", 0) <= self._alliance_reply_sequence("saw", payload):
                self._patch_own_alliance(auto_war=enabled)

    def _alliance_reply_sequence(self, command: str, payload: dict[str, Any] | None) -> int:
        receipt = self._alliance_reply_order.get(command)
        return receipt[1] if receipt is not None and receipt[0] is payload else self._packet_sequence

    def _require_membership_revision(self, revision: int, alliance_id: int) -> None:
        current = self.local_player.AID if self.local_player is not None else None
        if self.membership_revision != revision or current != alliance_id:
            raise ReplyMismatchError(alliance_id, current if current is not None else -1)

    def _handle_agr(self, data: Any) -> None:
        """Client: CastleAllianceGiftData.parse_AGR (bundle lines 131949–131951)."""
        if self.own_alliance is None:
            return
        received = read_section(AllianceGiftReceived, data, "an alliance gift")
        if received is not None:
            self.alliance_gifts = tuple(
                sorted((*self.alliance_gifts, received.gift), key=lambda gift: gift.remaining_seconds())
            )

    def get_alliance_gifts(self) -> list[AllianceGift]:
        """Unexpired gifts, in expiry order. Client: executeUpdate (bundle 131953–131959)."""
        with self._lock:
            return [gift.model_copy(deep=True) for gift in self.alliance_gifts if gift.remaining_seconds() > 0]

    def apply_alliance_gift_collection(self, gift_id: int, *, membership_revision: int, alliance_id: int) -> None:
        """Remove a collected gift only in the membership that sent the request."""
        with self._lock:
            self._require_membership_revision(membership_revision, alliance_id)
            self.alliance_gifts = tuple(gift for gift in self.alliance_gifts if gift.gift_id != gift_id)

    def _handle_aqi(self, data: Any) -> None:
        """Handle the reply to leaving your alliance: the chat and details are forgotten, its ``gal`` applied.

        Client: ``AQICommand.executeCommand`` (split.js line 623712): ``resetHistory``, ``parse_GAL(i.gal)``,
        ``resetMyAlliance``
        """
        self.membership_revision += 1
        self.alliance_chat = ()
        self.alliance_help = ()
        self._apply_login(LoginDataResponse.carried_by(data, ("gal",)))
        self._forget_own_alliance()

    def _parse_alliance_help(self, login: LoginDataResponse) -> bool:
        """Apply the login data's ``ahl`` section; whether it was applied."""
        if login.alliance_help is None:
            return False
        self.alliance_help = tuple(login.alliance_help.requests)
        return True

    def _handle_ahl(self, data: Any) -> None:
        """Replace the help list with an ``ahl``'s."""
        if (listed := read_section(AllianceHelpListResponse, data, "the alliance help list")) is not None:
            self.alliance_help = tuple(listed.requests)

    def _handle_ahh(self, data: Any) -> None:
        """Replace the help request an ``ahh`` names by ``LID``, or add it."""
        changed = read_section(AllianceHelpRequestChanged, data, "an alliance help request")
        if changed is None or (request := changed.request) is None:
            return
        listed = [request if r.list_id == request.list_id else r for r in self.alliance_help]
        if not any(r.list_id == request.list_id for r in self.alliance_help):
            listed.append(request)
        self.alliance_help = tuple(listed)

    def _handle_ahd(self, data: Any) -> None:
        """Remove the help request an ``ahd`` names."""
        removed = read_section(AllianceHelpRequestRemoved, data, "a removed alliance help request")
        if removed is not None:
            self.alliance_help = tuple(r for r in self.alliance_help if r.list_id != removed.list_id)

    def get_alliance_help(self) -> list[AllianceHelpRequest]:
        """The alliance help list as the login data and the pushes since left it.

        The login data's ``ahl`` section fills it, and so does an ahl push; ahh replaces or adds a
        request by ``LID``, ahd removes one, and leaving your alliance (``aqi``) empties it. The
        client never asks the server for the list, and neither does this library. The list is
        kept when the session drops, as the client keeps it; the next login's ``ahl`` replaces it.

        Client: ``AllianceHelpRequestData`` (bundle line 133359) keeps the list the same way, from
        ``GBDCommand.exec`` (bundle line 129381) and the ``AHL``/``AHH``/``AHD`` commands; it has no
        ``reset`` of its own (``CastleBasicData.reset``, bundle line 2109, is empty);
        ``AQICommand.executeCommand`` (bundle line 121556) calls ``CastleAllianceData.resetMyAlliance``
        (bundle line 11620), which cleans it
        """
        with self._lock:
            return list(self.alliance_help)

    def _parse_chat_history(self, log: AllianceChatLogResponse | None, *, replace: bool = False) -> bool:
        """Add an ``acl`` section's messages to the chat history, after the ones already there;
        whether it was applied.

        ``replace`` starts the history over with them instead, for an ``acl`` reply: the client
        asks for the history only at login, when it is empty, so a reply to
        ``client.alliance.get_chat_log()`` would otherwise list every message twice.

        Client: ``CastleChatData.parseHistory`` (bundle line 111294), which appends every ``CM`` entry
        """
        if log is None:
            return False
        self.alliance_chat = (*(() if replace else self.alliance_chat), *log.chat_log)
        return True

    def _handle_acm(self, data: Any) -> None:
        """Add an ``acm`` message to the chat history, and mark its sender online in your alliance.

        Client: ``CastleChatData.parseSingleMessage`` (bundle line 111288), from ``ACMCommand``
        (bundle line 121317): it appends the message, then sets the sender's ``AMI`` login
        activity to ``ONLINESTATE_ONLINE`` when the player id is 0 or more, and changes nothing else
        about the members (``AllianceInfoVO.getOnlineUserList``, bundle line 25980)
        """
        pushed = read_section(AllianceChatMessageResponse, data, "an alliance chat message")
        if pushed is None or (message := pushed.chat_message) is None:
            return
        self.alliance_chat = (*self.alliance_chat, message)
        alliance = self.own_alliance
        if message.player_id < 0 or alliance is None:
            return
        info = next((i for i in reversed(alliance.member_info) if i.player_id == message.player_id), None)
        if info is not None:
            # The row the members share, set in place: rebuilding the members would restart their protection times
            info.login_activity = int(OnlineState.ONLINE)

    def get_cargo_points(self) -> int | float | None:
        """Your cargo points, from the last ``gap``; None until one arrived."""
        with self._lock:
            return self.cargo_points

    def get_horizon_performance(self) -> list[HorizonMemberPerformance] | None:
        """Your alliance members' Beyond the Horizon performance, from the last ``gae``; None until one arrived."""
        with self._lock:
            if self.horizon_performance is None:
                return None
            return [member.model_copy(deep=True) for member in self.horizon_performance]

    def get_jade_phase(self) -> JadePhase | None:
        """The Jade Desert's scoring phase, from the ``abgi`` pushes so far; None until one arrived."""
        with self._lock:
            return self.jade_phase

    def get_own_alliance(self) -> AllianceInfo | None:
        """Your alliance's details and members, from the last ``ain`` about it; None in no alliance or before one.

        The login gbd brings it, and so do ``client.alliance.get_alliance_info(your_id)`` and the
        replies that carry it (``acd``, ``acn``, ``ado``, ``akm``, ``arm``, ``cal``). An ``acm`` marks its
        sender online here. A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.own_alliance is None else self.own_alliance.model_copy(deep=True)

    def get_alliance_chat(self) -> list[ChatMessageData]:
        """The alliance chat history, oldest first; a copy of the list, of read-only messages.

        The login gbd's ``acl`` starts it, an ``acl`` reply (``client.alliance.get_chat_log()``)
        replaces it, and every ``acm`` adds one. Leaving the alliance, a ``gal`` with no alliance
        and a disconnect start it over.
        """
        with self._lock:
            return list(self.alliance_chat)
