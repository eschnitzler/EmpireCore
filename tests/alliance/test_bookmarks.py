"""Tests for adding, changing and deleting map bookmarks."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.alliance import (
    ATTACK_ORDER_MAX_SECONDS,
    ATTACK_ORDER_MIN_SECONDS,
    AddBookmarkRequest,
    Bookmark,
    ChangeBookmarkRequest,
    DeleteBookmarkResponse,
)
from empire_core.enums import BookmarkType, Kingdom
from empire_core.exceptions import CommandError, NotInAllianceError
from empire_core.protocol.errors import GGEError
from tests.service_helpers import StubPlayer, StubState, conn, make_client, xt_packet

# A bad or bch reply, read as a gbl entry
ENTRY: dict[str, Any] = {"KID": 0, "X": 640, "Y": 655, "N": "Farm", "TY": 1, "BID": 11, "AI": []}


def member_client(script=None, alliance_id: int = 5):
    """A client whose player is in alliance ``alliance_id``; -1 is none."""
    return make_client(script, state=StubState(StubPlayer(alliance_id=alliance_id)))


class TestRequests:
    def test_add_keeps_the_client_key_order(self):
        request = AddBookmarkRequest(kingdom=0, x=640, y=655, bookmark_type=1, name="Farm")

        # C2SAddBookmark sets K, X, Y, TY, TI, IM first, then N and M
        assert request.to_packet().split("%")[5] == '{"K":0,"X":640,"Y":655,"TY":1,"TI":-1,"IM":0,"N":"Farm","M":[]}'

    def test_change_sends_if_as_a_boolean(self):
        request = ChangeBookmarkRequest(kingdom=0, x=1, y=2, friend=False, name="x")
        assert '"IF":false' in request.to_packet()

    def test_a_deleted_position_alone_or_in_a_list(self):
        alone = DeleteBookmarkResponse.model_validate({"K": 0, "X": 1, "Y": 2})
        listed = DeleteBookmarkResponse.model_validate({"BM": [{"K": 2, "X": 3, "Y": 4}]})

        assert [(p.kingdom, p.x, p.y) for p in alone.deleted] == [(0, 1, 2)]
        assert [(p.kingdom, p.x, p.y) for p in listed.deleted] == [(2, 3, 4)]


class TestAddBookmark:
    def test_an_own_bookmark(self):
        client = make_client({"bad": xt_packet("bad", ENTRY)})

        added = client.alliance.add_bookmark(640, 655, "Farm")

        assert isinstance(added, Bookmark)
        assert (added.bookmark_id, added.name, added.bookmark_type_enum) == (11, "Farm", BookmarkType.PLAYER_FRIEND)
        assert conn(client).request_payloads == [
            ("bad", {"K": 0, "X": 640, "Y": 655, "TY": 1, "TI": -1, "IM": 0, "N": "Farm", "M": []})
        ]

    def test_an_attack_order_carries_its_time_and_attackers(self):
        client = member_client({"bad": xt_packet("bad", {**ENTRY, "TY": 4, "C": 7, "M": [7], "TI": 3600})})

        client.alliance.add_bookmark(
            640,
            655,
            "Hit",
            BookmarkType.ALLIANCE_ATTACK_ORDER,
            Kingdom.FIRE,
            attack_in_seconds=7200,
            attacker_ids=[7, 8],
        )

        assert conn(client).request_payloads == [
            ("bad", {"K": 3, "X": 640, "Y": 655, "TY": 4, "TI": 7200, "IM": 1, "N": "Hit", "M": [7, 8]})
        ]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"attacker_ids": [], "attack_in_seconds": 7200},
            {"attacker_ids": [7], "attack_in_seconds": ATTACK_ORDER_MIN_SECONDS - 1},
            {"attacker_ids": [7], "attack_in_seconds": ATTACK_ORDER_MAX_SECONDS + 1},
            {"attacker_ids": [7]},
        ],
    )
    def test_an_attack_order_the_dialog_would_not_send(self, kwargs):
        client = member_client()
        with pytest.raises(ValueError):
            client.alliance.add_bookmark(1, 2, "Hit", BookmarkType.ALLIANCE_ATTACK_ORDER, **kwargs)
        assert conn(client).request_payloads == []

    def test_attack_details_are_only_for_an_attack_order(self):
        client = make_client()
        with pytest.raises(ValueError, match="ALLIANCE_ATTACK_ORDER"):
            client.alliance.add_bookmark(1, 2, "x", attacker_ids=[7])

    @pytest.mark.parametrize("name", ["", "x" * 31])
    def test_a_name_the_dialog_refuses(self, name):
        client = make_client()
        with pytest.raises(ValueError, match="1 to 30"):
            client.alliance.add_bookmark(1, 2, name)
        assert conn(client).request_payloads == []

    def test_a_full_list_raises_its_error(self):
        client = make_client({"bad": xt_packet("bad", {}, error_code=int(GGEError.BOOKMARK_MAX_ENTRYS))})
        with pytest.raises(CommandError) as raised:
            client.alliance.add_bookmark(1, 2, "x")
        assert raised.value.error is GGEError.BOOKMARK_MAX_ENTRYS

    @pytest.mark.parametrize(
        "bookmark_type",
        [BookmarkType.ALLIANCE_ATTACK_ORDER, BookmarkType.ALLIANCE_DEFEND, BookmarkType.ALLIANCE_FREE_ATTACK],
    )
    def test_an_alliance_bookmark_outside_an_alliance_sends_nothing(self, bookmark_type):
        # the dialog's alliance tab needs isInAlliance (playerCanCreateAllianceBookmark, bundle line 19563)
        client = member_client(alliance_id=-1)
        order = (
            {"attack_in_seconds": 7200, "attacker_ids": [7]}
            if bookmark_type == BookmarkType.ALLIANCE_ATTACK_ORDER
            else {}
        )
        with pytest.raises(NotInAllianceError):
            client.alliance.add_bookmark(1, 2, "x", bookmark_type, **order)
        assert conn(client).request_payloads == []

    def test_an_own_bookmark_outside_an_alliance_is_sent(self):
        client = member_client({"bad": xt_packet("bad", ENTRY)}, alliance_id=-1)
        client.alliance.add_bookmark(640, 655, "Farm", BookmarkType.PLAYER_ENEMY)
        assert [command for command, _ in conn(client).request_payloads] == ["bad"]


class TestChangeBookmark:
    def test_rename(self):
        client = make_client({"bch": xt_packet("bch", {**ENTRY, "N": "Barn"})})

        changed = client.alliance.change_bookmark(640, 655, "Barn")

        assert changed.name == "Barn"
        assert conn(client).request_payloads == [("bch", {"KID": 0, "X": 640, "Y": 655, "IF": True, "DN": "Barn"})]

    def test_an_enemy_bookmark_sends_if_false(self):
        client = make_client({"bch": xt_packet("bch", {**ENTRY, "TY": 0})})
        client.alliance.change_bookmark(640, 655, "Foe", BookmarkType.PLAYER_ENEMY)
        assert conn(client).request_payloads[0][1]["IF"] is False

    def test_an_alliance_bookmark_does_not_change(self):
        client = make_client()
        with pytest.raises(ValueError, match="own bookmarks"):
            client.alliance.change_bookmark(1, 2, "x", BookmarkType.ALLIANCE_DEFEND)
        assert conn(client).request_payloads == []


class TestDeleteBookmark:
    def test_an_own_bookmark_by_its_position(self):
        client = make_client({"bde": xt_packet("bde", {"BM": [{"K": 0, "X": 640, "Y": 655}]})})

        assert client.alliance.delete_bookmark(Bookmark.model_validate(ENTRY)) is True
        assert conn(client).request_payloads == [("bde", {"BM": [[0, 640, 655]]})]

    def test_an_alliance_bookmark_by_its_id(self):
        client = member_client({"abd": xt_packet("abd", {})})
        bookmark = Bookmark.model_validate({**ENTRY, "TY": 3, "BID": 42})

        assert client.alliance.delete_bookmark(bookmark, notify_attackers=True) is True
        assert conn(client).request_payloads == [("abd", {"BM": [[42, 1]]})]

    def test_an_alliance_bookmark_outside_an_alliance_sends_nothing(self):
        client = member_client(alliance_id=-1)
        bookmark = Bookmark.model_validate({**ENTRY, "TY": 3, "BID": 42})
        with pytest.raises(NotInAllianceError):
            client.alliance.delete_bookmark(bookmark)
        assert conn(client).request_payloads == []

    def test_an_own_bookmark_outside_an_alliance_is_deleted(self):
        client = member_client({"bde": xt_packet("bde", {})}, alliance_id=-1)
        assert client.alliance.delete_bookmark(Bookmark.model_validate(ENTRY)) is True

    def test_a_refused_delete_is_false(self):
        client = make_client({"bde": xt_packet("bde", {}, error_code=1)})
        assert client.alliance.delete_bookmark(Bookmark.model_validate(ENTRY)) is False

    def test_an_unknown_type_sends_nothing(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.alliance.delete_bookmark(Bookmark.model_validate({**ENTRY, "TY": 9}))
        assert conn(client).request_payloads == []
