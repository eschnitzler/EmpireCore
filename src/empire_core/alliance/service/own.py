"""Your own alliance, any alliance's members and the alliance search."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from pydantic import ValidationError

from empire_core.alliance.models.chronicle import (
    AllianceChronicleEntry,
    AllianceChronicleRequest,
    AllianceChronicleResponse,
    AllianceSubscriberCountRequest,
    AllianceSubscriberCountResponse,
)
from empire_core.alliance.models.info import (
    AllianceInfo,
    AllianceMember,
    GetAllianceInfoRequest,
    GetAllianceInfoResponse,
)
from empire_core.alliance.models.search import AllianceSearchResult, SearchAllianceRequest, SearchAllianceResponse
from empire_core.enums import GGEError
from empire_core.exceptions import CommandError, NotInAllianceError, PacketError
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.services.base import ServiceMixin

logger = logging.getLogger(__name__)

_MembershipResponse = TypeVar("_MembershipResponse", bound=BaseResponse)


def _echoed(alliance: AllianceInfo | None, command: str) -> AllianceInfo:
    if alliance is None:
        raise PacketError(f"'{command}' reply carries no alliance")
    return alliance


class OwnAllianceMixin(ServiceMixin):
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
            self.client.connection.command_lock("aas", timeout=timeout),
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
