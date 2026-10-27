"""Alliance map bookmarks."""

from __future__ import annotations

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
from empire_core.alliance.service.own import OwnAllianceMixin
from empire_core.enums import BookmarkType, Kingdom
from empire_core.protocol.base import BaseRequest

_PLAYER_BOOKMARK_TYPES = frozenset({BookmarkType.PLAYER_ENEMY, BookmarkType.PLAYER_FRIEND})


def _check_bookmark_name(name: str) -> None:
    # CastleWorldmapBookmarkSetDialog.isNameValid (bundle line 19570) and its maxChars (bundle line 19546)
    if not name or len(name) > BOOKMARK_NAME_MAX_LENGTH:
        raise ValueError(f"bookmark names are 1 to {BOOKMARK_NAME_MAX_LENGTH} characters, got {name!r}")


class BookmarksMixin(OwnAllianceMixin):
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
