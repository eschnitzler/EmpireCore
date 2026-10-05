"""
Your alliance and others: members, chat, help, diplomacy and the treasury.

It covers:

- Alliance members (get members, online status, last seen)
- Member management (kick, rank, invite, applications, leave)
- Diplomacy, auto war, the newsletter and treasury donations
- Alliance chat (send messages, get history)
- Alliance help (the help list and its pushes, helping, asking for help)
- Your alliance's chronicle and subscriber count
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from pydantic import ValidationError

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
from empire_core.alliance.models.search import (
    AllianceSearchResult,
    GetBookmarksRequest,
    GetBookmarksResponse,
    SearchAllianceRequest,
    SearchAllianceResponse,
)
from empire_core.enums import AllianceRank, DiplomacyStatus, HelpType
from empire_core.exceptions import CommandError, NotInAllianceError, PacketError
from empire_core.protocol.base import BaseResponse
from empire_core.protocol.errors import GGEError
from empire_core.services.base import BaseService

logger = logging.getLogger(__name__)

AllianceHelpUpdate = (
    AllianceHelpListResponse | AllianceHelpRequestChanged | AllianceHelpRequestRemoved | AllianceHelpReceived
)

_ALLIANCE_GONE = frozenset({GGEError.ALLI_NOT_FOUND})


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

    def __init__(self, client) -> None:
        super().__init__(client)
        self._callbacks_lock = threading.Lock()
        self._chat_callbacks: list[Callable[[AllianceChatMessageResponse], None]] = []
        self._members: dict[int, AllianceMember] = {}
        self._members_alliance_id: int | None = None
        self._help_requests: list[AllianceHelpRequest] = []
        self._help_lock = threading.Lock()
        self._help_callbacks: list[Callable[[AllianceHelpUpdate], None]] = []

        self.on_response("acm", self._handle_chat_message)
        for command in ("ahl", "ahh", "ahd", "ahf"):
            self.on_response(command, self._handle_help_update)

    # =========================================================================
    # Member Operations
    # =========================================================================

    def get_alliance_info(self, alliance_id: int, timeout: float = 5.0) -> GetAllianceInfoResponse:
        """
        Get info about an alliance.

        Args:
            alliance_id: Your own is ``client.alliance.local_alliance_id``; another is an
                ``AllianceSearchResult.alliance_id`` from ``client.alliance.search_alliances()``
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetAllianceInfoRequest(alliance_id=alliance_id), GetAllianceInfoResponse, timeout=timeout)

    def get_members(self, alliance_id: int, timeout: float = 5.0) -> list[AllianceMember]:
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
        # Update cached members and remember which alliance they belong to
        self._members = {m.player_id: m for m in response.members}
        self._members_alliance_id = alliance_id
        return response.members

    def get_online_members(self, alliance_id: int, timeout: float = 5.0) -> list[AllianceMember]:
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

    def get_member(self, player_id: int, no_cache: bool = False) -> AllianceMember | None:
        """
        Get a specific member by player ID.

        Args:
            player_id: The member's ``AllianceMember.player_id``, as :meth:`get_members` lists it
            no_cache: If True, refresh alliance data from server first

        Returns:
            AllianceMember if found, None otherwise

        Raises:
            NotInAllianceError: ``no_cache`` with no alliance cached, and you are in none; nothing is sent

        Example:
            member = client.alliance.get_member(12345)  # From cache
            member = client.alliance.get_member(12345, no_cache=True)  # Fresh data
        """
        if no_cache:
            # Refresh the alliance the cache actually belongs to, not
            # unconditionally the local one
            if self._members_alliance_id is not None:
                self.get_members(self._members_alliance_id)
            else:
                self.get_local_members()
        return self._members.get(player_id)

    @property
    def cached_members(self) -> dict[int, AllianceMember]:
        """
        Get the cached member dictionary.

        Returns members from the last get_members() call, keyed by player_id.
        Call get_members() to refresh.

        Returns:
            Dict mapping player_id to AllianceMember
        """
        return self._members.copy()

    # =========================================================================
    # Member Management
    # =========================================================================

    def kick_member(self, player_id: int, timeout: float = 5.0) -> AllianceInfo:
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

    def set_rank(self, player_id: int, rank: AllianceRank, timeout: float = 5.0) -> AllianceInfo | None:
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

    def invite(self, player_id: int, timeout: float = 5.0) -> bool:
        """
        Invite a player to your alliance.

        Args:
            player_id: The player's id, e.g. ``PlayerOwnerInfo.player_id`` from ``client.player.get_player_info()``

        Returns:
            Whether the server accepted the invitation; it refuses an id that names
            no player with ``INVALID_PLAYER_ID``

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``

        Client: ``CastlePlayerInfoDialog`` shows its invite button for
        ``CastleUserData.canInviteToAlliance`` (bundle line 9994), which needs ``isInAlliance``
        """
        with self._own_alliance():
            return self.execute(InvitePlayerRequest.for_player(player_id), timeout=timeout, raise_on=_ALLIANCE_GONE)

    def get_applications(self, timeout: float = 5.0) -> AllianceApplicationListResponse:
        """
        Get your alliance's applications, nearest first, with the applicants' owner records.

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        with self._own_alliance():
            return self.request(AllianceApplicationListRequest(), AllianceApplicationListResponse, timeout=timeout)

    def answer_application(self, player_id: int, accept: bool, timeout: float = 5.0) -> bool:
        """
        Accept or refuse an application.

        Args:
            player_id: The applicant's ``AllianceApplication.player_id``
            accept: True to accept, False to refuse

        Returns:
            Whether the server accepted the answer

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        request = AnswerApplicationRequest.create(player_id, accept)
        with self._own_alliance():
            return self.execute(request, timeout=timeout, raise_on=_ALLIANCE_GONE)

    def leave(self, timeout: float = 5.0) -> bool:
        """
        Leave your alliance. Once the server accepts, :attr:`help_requests` is emptied.

        Client: ``AQICommand.executeCommand`` (bundle line 121556) calls
        ``CastleAllianceData.resetMyAlliance`` (bundle line 11620), which cleans the help list

        Returns:
            Whether the server accepted it

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        with self._own_alliance():
            left = self.execute(QuitAllianceRequest(), timeout=timeout, raise_on=_ALLIANCE_GONE)
        if left:
            with self._help_lock:
                self._help_requests = []
        return left

    # =========================================================================
    # Diplomacy, Newsletter and Donations
    # =========================================================================

    def change_diplomacy(
        self, alliance_id: int, new_status: DiplomacyStatus, tribute: int = 0, timeout: float = 5.0
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

    def refuse_diplomacy(self, alliance_id: int, timeout: float = 5.0) -> AllianceInfo | None:
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

    def set_auto_war(self, enabled: bool, timeout: float = 5.0) -> bool:
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

    def send_newsletter(self, subject: str, text: str, timeout: float = 5.0) -> bool:
        """
        Send the alliance newsletter to every member.

        Args:
            subject: The subject (the client's field takes 20 characters)
            text: The text; the client does not send an empty one

        Returns:
            Whether the server accepted it

        Raises:
            ValueError: ``text`` is empty
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        if not text:
            raise ValueError("a newsletter needs text")
        with self._own_alliance():
            return self.execute(SendNewsletterRequest.create(subject, text), timeout=timeout, raise_on=_ALLIANCE_GONE)

    def donate(self, castle_id: int, donation: AllianceDonation, timeout: float = 5.0) -> DonateResponse:
        """
        Donate resources from one of your castles to the alliance treasury.

        Args:
            castle_id: The donating castle, a ``Castle.id`` from ``client.state.get_castles()``
            donation: The amounts; the client sends nothing when every amount is 0
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms
            ValueError: every amount is 0
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceDonateDialog.onDonateForAlliance`` (bundle line 45576) sends
        the picked castle's ``objectId`` and ``kingdomID``
        """
        request = DonateRequest.create(castle_id, self._require_own_castle(castle_id).kingdom_id, donation)
        if not request.resources:
            raise ValueError("a donation needs an amount above 0")
        with self._own_alliance():
            return self.request(request, DonateResponse, timeout=timeout)

    # =========================================================================
    # Search Operations
    # =========================================================================

    def search_alliances(self, search_term: str, timeout: float = 5.0) -> list[AllianceSearchResult]:
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

        Client: ``CastleUserData.isInAlliance`` (bundle line 9986) is ``allianceID >= 0``
        """
        player = self.client.state.local_player
        if player is None or player.alliance_id is None or player.alliance_id < 0:
            return None
        return player.alliance_id

    def _require_local_alliance_id(self) -> int:
        alliance_id = self.local_alliance_id
        if alliance_id is None:
            raise NotInAllianceError()
        return alliance_id

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

    def get_local_members(self, timeout: float = 5.0) -> list[AllianceMember]:
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

    def get_local_online_members(self, timeout: float = 5.0) -> list[AllianceMember]:
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

    def get_chronicle(self, timeout: float = 5.0) -> list[AllianceChronicleEntry]:
        """
        Get your alliance's chronicle, newest first.

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceDialogOverview`` (bundle line 70407) asks for it
        """
        with self._own_alliance():
            return self.request(AllianceChronicleRequest(), AllianceChronicleResponse, timeout=timeout).entries

    def get_subscriber_count(self, timeout: float = 5.0) -> int:
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

    def get_chat_log(self, timeout: float = 5.0) -> list[ChatMessageData]:
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

    def on_chat_message(self, callback: Callable[[AllianceChatMessageResponse], None]) -> None:
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
        """
        with self._callbacks_lock:
            self._chat_callbacks.append(callback)

    def remove_chat_message_callback(self, callback: Callable[[AllianceChatMessageResponse], None]) -> None:
        """Remove a callback registered with :meth:`on_chat_message`.

        No-op if the callback is not registered, so reconnect re-wiring can
        detach unconditionally.
        """
        with self._callbacks_lock:
            if callback in self._chat_callbacks:
                self._chat_callbacks.remove(callback)

    def _handle_chat_message(self, response) -> None:
        """Internal handler for chat message responses."""
        if isinstance(response, AllianceChatMessageResponse):
            with self._callbacks_lock:
                callbacks = list(self._chat_callbacks)
            for callback in callbacks:
                try:
                    callback(response)
                except Exception:
                    logger.exception("Chat message callback error")

    # =========================================================================
    # Help Operations
    # =========================================================================

    @property
    def help_requests(self) -> list[AllianceHelpRequest]:
        """
        The alliance help list as the login data and the pushes since left it.

        The login data's ``ahl`` section fills it, and so does an ahl push;
        ahh replaces or adds a request by ``LID``, ahd removes one. The client
        never asks the server for the list, and neither does this library.
        The list is not emptied when the session drops, as the client keeps
        it; the next login's ``ahl`` section replaces it.

        Client: ``AllianceHelpRequestData`` (bundle line 133359) keeps the list
        the same way, from ``GBDCommand.exec`` (bundle line 129381) and the
        ``AHL``/``AHH``/``AHD`` commands; it has no ``reset`` of its own
        (``CastleBasicData.reset``, bundle line 2109, is empty)
        """
        with self._help_lock:
            return list(self._help_requests)

    def on_help_update(self, callback: Callable[[AllianceHelpUpdate], None]) -> None:
        """
        Call ``callback`` with the login data's ahl section and each ahl, ahh, ahd and ahf push,
        after :attr:`help_requests` is updated.

        Detach it again with :meth:`remove_help_update_callback`.
        """
        with self._callbacks_lock:
            self._help_callbacks.append(callback)

    def remove_help_update_callback(self, callback: Callable[[AllianceHelpUpdate], None]) -> None:
        """Remove a callback registered with :meth:`on_help_update`; a no-op if it is not registered."""
        with self._callbacks_lock:
            if callback in self._help_callbacks:
                self._help_callbacks.remove(callback)

    def _apply_help_update(self, response: BaseResponse) -> AllianceHelpUpdate | None:
        if isinstance(response, AllianceHelpListResponse):
            self._help_requests = list(response.requests)
        elif isinstance(response, AllianceHelpRequestChanged) and response.request is not None:
            changed = response.request
            index = next((i for i, r in enumerate(self._help_requests) if r.list_id == changed.list_id), None)
            if index is None:
                self._help_requests.append(changed)
            else:
                self._help_requests[index] = changed
        elif isinstance(response, AllianceHelpRequestRemoved):
            self._help_requests = [r for r in self._help_requests if r.list_id != response.list_id]
        elif not isinstance(response, AllianceHelpReceived):
            return None
        return response

    def _handle_help_update(self, response: BaseResponse) -> None:
        with self._help_lock:
            update = self._apply_help_update(response)
        if update is None:
            return
        with self._callbacks_lock:
            callbacks = list(self._help_callbacks)
        for callback in callbacks:
            try:
                callback(update)
            except Exception:
                logger.exception("Help update callback error")

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

    def request_build_help(self, building_id: int, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help build a building.

        Args:
            building_id: The building's object id, e.g. ``BuildResponse.building_id``

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.build(building_id), timeout=timeout)

    def request_repair_help(self, building_id: int, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help repair a building.

        Args:
            building_id: The damaged building's object id

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.repair(building_id), timeout=timeout)

    def request_recruit_help(self, recruit_id: int, help_type: HelpType, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help with a recruitment.

        Args:
            recruit_id: The recruitment's id; the library does not read recruitment ids yet
            help_type: ``HelpType.RECRUITMENT``, ``LOOP_RECRUIT`` or ``RECRUITMENT_LIST``

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.recruit(recruit_id, help_type), timeout=timeout)

    def request_heal_help(self, hospital_entry_id: int, hospital_list_id: int, timeout: float = 5.0) -> bool:
        """
        Ask the alliance to help heal wounded units.

        Args:
            hospital_entry_id: The hospital entry; the library does not read hospital entry ids yet
            hospital_list_id: The hospital list the entry is on

        Returns:
            Whether the server accepted the request
        """
        return self.execute(AskHelpRequest.heal(hospital_entry_id, hospital_list_id), timeout=timeout)

    # =========================================================================
    # Bookmark Operations
    # =========================================================================

    def get_bookmarks(self, timeout: float = 5.0) -> GetBookmarksResponse:
        """
        Get your own and your alliance's map bookmarks.

        Returns:
            The gbl reply: ``own_bookmarks`` and ``alliance_bookmarks``

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetBookmarksRequest(), GetBookmarksResponse, timeout=timeout)


__all__ = ["AllianceHelpUpdate", "AllianceService"]
