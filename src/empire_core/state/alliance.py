"""Your own alliance's details (ain), the alliance chat history (acl, acm) and the help list (ahl, ahh, ahd)."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from empire_core.alliance.models.battleground import BattlegroundMemberPerformance, BattlegroundPerformanceResponse
from empire_core.alliance.models.chat import AllianceChatLogResponse, ChatMessageData
from empire_core.alliance.models.gifts import AllianceGift, AllianceGiftReceived
from empire_core.alliance.models.help import (
    AllianceHelpListResponse,
    AllianceHelpRequest,
    AllianceHelpRequestChanged,
    AllianceHelpRequestRemoved,
)
from empire_core.alliance.models.info import AllianceInfo, alliance_of_ain
from empire_core.alliance.models.landmarks import AllianceLaboratoriesResponse
from empire_core.alliance.models.membership import AutoJoinedAllianceResponse
from empire_core.enums import OnlineState
from empire_core.exceptions import ReplyMismatchError
from empire_core.player.models.aqua import AquaPointsResponse, StormIslandsInfo
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_int, js_truthy
from empire_core.state.base import StateBase, read_section

logger = logging.getLogger(__name__)

# Keys AllianceInfoVO.fillFromParamObject leaves as they were when a reply sends them as null
_KEPT_WHEN_NULL = ("AA", "AW", "AP")
# ... and when it sends them falsy
_KEPT_WHEN_FALSY = ("STO", "ACLS", "aee")
_FORGE_KEYS = ("MF", "IF", "SRFU", "HRFU")


class AllianceState(StateBase):
    def _parse_own_alliance(self, data: dict[str, Any], *, changed_keys: set[str] | None = None) -> bool:
        """Apply an ``ain`` section when it is about your own alliance; whether it was applied.

        Other alliances' details (``client.alliance.get_alliance_info(other_id)``) are not kept.
        A reply for the same alliance is read over the last one: the keys the client keeps
        when a reply leaves them out (``AA``, ``AW``, ``AP``, ``STO``, ``ACLS``, ``aee``, and
        ``MF``, ``IF``, ``SRFU``, ``HRFU`` unless both ``MF`` and ``IF`` are sent) keep their values.

        Client: ``CastleAllianceData.parse_AIN`` (bundle line 11560) and ``parseAllianceInfo``
        (bundle line 11605), which keeps the alliance whose ``AID`` is ``userData.allianceID`` as
        ``myAllianceVO``; ``AllianceInfoVO.fillFromParamObject`` (bundle line 25928)
        """
        if "ain" not in data:
            return False
        block = alliance_of_ain(data["ain"])
        player = self.local_player
        if block is None or player is None or player.AID is None:
            return False
        if js_int(block["AID"]) != js_int(player.AID):
            return False
        raw = dict(block)
        previous = self._own_alliance_raw
        if previous is not None and js_int(previous.get("AID")) == js_int(raw["AID"]):
            for key in _KEPT_WHEN_NULL:
                if raw.get(key) is None and key in previous:
                    raw[key] = previous[key]
            for key in _KEPT_WHEN_FALSY:
                if not js_truthy(raw.get(key)) and key in previous:
                    raw[key] = previous[key]
            if raw.get("MF") is None or raw.get("IF") is None:
                for key in _FORGE_KEYS:
                    raw.pop(key, None)
                    if key in previous:
                        raw[key] = previous[key]
        return self._store_own_alliance(raw, changed_keys=changed_keys)

    def _store_own_alliance(self, raw: dict[str, Any], *, changed_keys: set[str] | None = None) -> bool:
        alliance = read_or_none(AllianceInfo.model_validate, raw, warn=logger, what="your alliance's details")
        if alliance is None:
            return False
        if changed_keys is not None and self.own_alliance is not None:
            updates = {
                name: getattr(alliance, name)
                for name, field in AllianceInfo.model_fields.items()
                if field.validation_alias in changed_keys
            }
            alliance = self.own_alliance.model_copy(deep=True, update=updates)
            alliance.model_post_init(None)
        keys = changed_keys if changed_keys is not None else set(raw) | set(self._own_alliance_raw or {})
        for key in keys:
            self._alliance_field_order[key] = self._packet_sequence
        self._own_alliance_raw = raw
        self.own_alliance = alliance
        return True

    def _patch_own_alliance(self, fields: dict[str, Any]) -> None:
        raw = self._own_alliance_raw
        player = self.local_player
        if raw is None or player is None or player.AID is None or js_int(raw.get("AID")) != player.AID:
            return
        self._store_own_alliance({**raw, **fields}, changed_keys=set(fields))

    def _handle_afa(self, data: Any) -> None:
        """Client: ``AllianceInfoVO.parseAFA`` (bundle line 25959)."""
        if isinstance(data, dict) and "CF" in data and "HF" in data:
            self._patch_own_alliance({"CF": data["CF"], "HF": data["HF"]})

    def _handle_abl(self, data: Any) -> None:
        """Client: ``AllianceInfoVO.parseABL/parseBuffList`` (bundle lines 25961–25967)."""
        buffs = data.get("ABL") if isinstance(data, dict) else data
        if isinstance(buffs, list) and all(isinstance(row, dict) for row in buffs):
            self._patch_own_alliance({"ABL": buffs})

    def _handle_aee(self, data: Any) -> None:
        """Client: ``AEECommand`` (121435–36), ``parseAllianceCrestForAlliance`` (11595).

        The command passes its ACCA wrapper, then overwrites the fallback with
        the top-level ACFB. Missing current crests remain unknown rather than random.
        """
        if not isinstance(data, dict) or not isinstance(data.get("ACCA"), dict):
            return
        crest = data["ACCA"].get("ACCA")
        if crest is not None and not isinstance(crest, dict):
            return
        self._patch_own_alliance({"aee": {"ACCA": crest, "ACFB": data.get("ACFB")}})

    def _handle_sll(self, data: Any) -> None:
        """Client: ``CastleAllianceData.parseSLL`` (bundle line 11605) replaces your alliance's laboratories."""
        if read_section(AllianceLaboratoriesResponse, data, "the alliance's laboratories") is not None:
            self._patch_own_alliance({"ALA": data.get("ALA")})

    def _handle_gap(self, data: Any) -> None:
        """Keep your aqua points and your alliance's.

        Client: ``CastleUserData.parse_GAP`` (bundle line 9881) sets ``P`` on the player and ``A`` on
        your alliance, when it knows one
        """
        points = read_section(AquaPointsResponse, data, "the aqua points")
        if points is None:
            return
        self.aqua_points = points.player_points
        if "A" in data:
            self._patch_own_alliance({"AP": points.alliance_points})

    def _handle_sii(self, data: Any) -> None:
        """Keep your and your alliance's Storm Islands standing, and your aqua points.

        Client: ``SIICommand.executeCommand`` (bundle line 127742) sets ``AP`` as your aqua points
        """
        info = read_section(StormIslandsInfo, data, "the Storm Islands standing")
        if info is None:
            return
        self.storm_islands = info
        self.aqua_points = info.aqua_points

    def get_storm_islands(self) -> StormIslandsInfo | None:
        """Your and your alliance's Storm Islands standing, from the last ``sii``; None until one arrived."""
        with self._lock:
            return self.storm_islands

    def _handle_gae(self, data: Any) -> None:
        """Keep your alliance members' battleground performance.

        Client: ``CastleAllianceBattleGroundData.parseAlliancePerformance`` (bundle line 144898) replaces
        ``alliancePerformanceVOs``
        """
        performance = read_section(BattlegroundPerformanceResponse, data, "the battleground performance")
        if performance is not None:
            self.battleground_performance = tuple(performance.members)

    def _handle_aja(self, data: Any) -> None:
        """Apply your new membership, then the alliance you were put in.

        Client: ``AJACommand.executeCommand`` (bundle lines 121532-121534): ``parse_GAL(gal)``, then
        ``parseAllianceInfo(A)``
        """
        if read_section(AutoJoinedAllianceResponse, data, "an automatic alliance join") is not None:
            self._handle_gbd({"gal": data["gal"], "ain": {"A": data["A"]}})

    def _forget_own_alliance(self) -> None:
        self._own_alliance_raw = None
        self._alliance_field_order = {}
        self._alliance_reply_order = {}
        self.own_alliance = None
        self.alliance_chat = ()
        self.alliance_help = ()
        self.alliance_gifts = ()

    def _apply_gal_reset(self, data: dict[str, Any], *, previous_alliance_id: int | None) -> None:
        """Forget details, chat and help when a ``gal`` changes your alliance identity.

        Client: ``CastleUserData.parse_GAL`` (bundle line 9869): ``_allianceID<0`` runs
        ``chatData.resetHistory`` and ``allianceData.resetMyAlliance``
        """
        if "gal" in data:
            self.membership_revision += 1
        gal = data.get("gal")
        if isinstance(gal, dict):
            player = self.local_player
            aid = js_int(gal.get("AID"))
            if aid < 0 or (aid > 0 and player is not None and player.AID != previous_alliance_id):
                self._forget_own_alliance()

    def apply_membership_response(self, data: dict[str, Any], *, membership_revision: int) -> None:
        """Apply only an accepted service reply, while its membership context is still current.

        Client: ``JOACommand`` / ``AAICommand`` (bundle lines 121934 / 121203)
        apply gal before A, ``AASCommand`` (bundle line 121272) gal before gam. The service scopes
        these replies so rejected or late replies cannot replace a newer authoritative GAL or a new session.
        """
        sections = {}
        gal = data.get("gal")
        alliance = data.get("A")
        if isinstance(gal, dict):
            sections["gal"] = gal
        if isinstance(alliance, dict) and alliance.get("AID") is not None:
            sections["ain"] = {"A": alliance}
        if not sections:
            return
        with self._lock:
            if self.membership_revision != membership_revision:
                expected = js_int(gal.get("AID")) if isinstance(gal, dict) else -1
                current = self.local_player.AID if self.local_player is not None else None
                raise ReplyMismatchError(expected, current if current is not None else -1)
            self._handle_gbd(sections)
            if isinstance(movements := data.get("gam"), dict):
                self._handle_gam(movements)

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
            if self._alliance_field_order.get("ABL", 0) > sequence:
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
            receipt = self._alliance_reply_order.get(command)
            if receipt is not None and receipt[0] is payload:
                sequence = receipt[1]
            else:
                sequence = self._packet_sequence
            block = alliance_of_ain(data)
            if block is None:
                return
            previous = self._own_alliance_raw or {}
            raw = {**previous, **block}
            changed_keys = set(block)
            for key, order in self._alliance_field_order.items():
                if order > sequence:
                    changed_keys.discard(key)
                    raw.pop(key, None)
                    if key in previous:
                        raw[key] = previous[key]
            self._parse_own_alliance({"ain": {"A": raw}}, changed_keys=changed_keys)

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

        Client: ``AQICommand.executeCommand`` (bundle line 121557): ``resetHistory``, ``parse_GAL(i.gal)``,
        ``resetMyAlliance``
        """
        self.membership_revision += 1
        self.alliance_chat = ()
        self.alliance_help = ()
        if isinstance(data, dict) and "gal" in data:
            self._handle_gbd({"gal": data["gal"]})
        self._forget_own_alliance()

    def _parse_alliance_help(self, data: dict[str, Any]) -> bool:
        """Apply the login data's ``ahl`` section; whether it was applied."""
        if "ahl" not in data:
            return False
        return self._handle_ahl(data["ahl"])

    def _handle_ahl(self, data: Any) -> bool:
        """Replace the help list with an ``ahl``'s."""
        listed = read_section(AllianceHelpListResponse, data, "the alliance help list")
        if listed is None:
            return False
        self.alliance_help = tuple(listed.requests)
        return True

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

    def _parse_chat_history(self, data: dict[str, Any], *, replace: bool = False) -> bool:
        """Add an ``acl`` section's messages to the chat history, after the ones already there;
        whether it was applied.

        ``replace`` starts the history over with them instead, for an ``acl`` reply: the client
        asks for the history only at login, when it is empty, so a reply to
        ``client.alliance.get_chat_log()`` would otherwise list every message twice.

        Client: ``CastleChatData.parseHistory`` (bundle line 111294), which appends every ``CM`` entry
        """
        acl = data.get("acl")
        if not isinstance(acl, dict):
            return False
        log = read_or_none(AllianceChatLogResponse.model_validate, acl, warn=logger, what="the alliance chat log")
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
        block = data.get("CM") if isinstance(data, dict) else None
        if not isinstance(block, dict):
            return
        message = read_or_none(ChatMessageData.model_validate, block, warn=logger, what="an alliance chat message")
        if message is None:
            return
        self.alliance_chat = (*self.alliance_chat, message)
        alliance = self.own_alliance
        if message.player_id < 0 or alliance is None:
            return
        info = next((i for i in reversed(alliance.member_info) if i.player_id == message.player_id), None)
        if info is not None:
            # The row the members share, set in place: rebuilding the members would restart their protection times
            info.login_activity = int(OnlineState.ONLINE)

    def get_aqua_points(self) -> int | float | None:
        """Your aqua points, from the last ``gap``; None until one arrived."""
        with self._lock:
            return self.aqua_points

    def get_battleground_performance(self) -> list[BattlegroundMemberPerformance] | None:
        """Your alliance members' battleground performance, from the last ``gae``; None until one arrived."""
        with self._lock:
            if self.battleground_performance is None:
                return None
            return [member.model_copy(deep=True) for member in self.battleground_performance]

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
