"""Achievements and Storm Islands titles: vli, vfi, uar, uht, iot and apt, as the client sends and reads them."""

import pytest

from empire_core.enums import GGEError
from empire_core.exceptions import CommandError
from empire_core.gamedata import Achievement, Title
from empire_core.player import (
    AchievementFinishedResponse,
    AchievementsResponse,
    AssignTitleRequest,
    AssignTitleResponse,
    GetAchievementsRequest,
    GetTitleRanksRequest,
    GloryTitleResetResponse,
    TitleInfoResponse,
    TitleRanksResponse,
)
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, request_payload, xt_packet

UAR = {"FTM": {"CTXT": -1, "RS": 600}, "BTM": {"CTXT": -1}, "ITM": {"TID": 50}, "PFX": "FAME", "SFX": "FAME"}


def test_the_requests_have_no_fields():
    assert GetAchievementsRequest().to_payload() == {}
    assert GetTitleRanksRequest().to_payload() == {}


def test_the_assign_request():
    assert AssignTitleRequest(title_id=Title.STORM_LORD, player_name="Ally").to_payload() == {"TI": 50, "PN": "Ally"}
    assert AssignTitleRequest(title_id=50).to_payload() == {"TI": 50, "PN": ""}


class TestReplies:
    def test_a_finished_achievement(self):
        pushed = parse_response("vfi", {"AID": 1, "gcu": {"C1": 40, "C2": 2}, "grc": {"AID": 9, "KID": 0, "W": 5}})

        assert isinstance(pushed, AchievementFinishedResponse)
        assert isinstance(pushed.achievement_id, Achievement)
        assert pushed.currencies is not None and (pushed.currencies.coins, pushed.currencies.rubies) == (40, 2)
        assert pushed.resources is not None and (pushed.resources.castle_id, pushed.resources.wood) == (9, 5)

    def test_a_finished_achievement_without_resources(self):
        pushed = AchievementFinishedResponse.model_validate({"AID": "7", "gcu": {"C1": 1}})

        assert pushed.achievement_id == 7 and pushed.resources is None

    def test_the_glory_reset(self):
        # parseUHT reads parseInt(RS)
        assert GloryTitleResetResponse.model_validate({"RS": "3600"}).reset_seconds == 3600
        assert GloryTitleResetResponse.model_validate({"RS": "x"}).reset_seconds is None

    def test_titles_info_reads_nothing(self):
        assert isinstance(parse_response("iot", {"X": 1}), TitleInfoResponse)

    @pytest.mark.parametrize(
        ("payload", "title", "name", "own"),
        [
            ({"TI": 50, "PN": "Ally"}, Title.STORM_LORD, "Ally", False),
            ({"TI": "50"}, Title.STORM_LORD, None, True),
            ({"TI": 50, "PN": ""}, Title.STORM_LORD, None, True),
            ({}, None, None, False),
        ],
    )
    def test_an_assigned_title(self, payload, title, name, own):
        reply = AssignTitleResponse.model_validate(payload)

        assert (reply.title_id, reply.player_name, reply.is_own_title) == (title, name, own)


class TestService:
    def test_get_achievements(self):
        client = make_client({"vli": xt_packet("vli", {"AVP": 30, "FA": [1], "RA": []})})

        reply = client.player.get_achievements()

        assert conn(client).request_payloads == [("vli", {})]
        assert isinstance(reply, AchievementsResponse) and reply.achievement_points == 30

    def test_get_title_ranks(self):
        client = make_client({"uar": xt_packet("uar", UAR)})

        reply = client.player.get_title_ranks()

        assert conn(client).request_payloads == [("uar", {})]
        assert isinstance(reply, TitleRanksResponse) and reply.island_title.title_id is Title.STORM_LORD

    def test_assign_title(self):
        client = make_client({"apt": xt_packet("apt", {"TI": 50, "PN": "Ally"})})

        reply = client.player.assign_title(Title.STORM_LORD, "Ally")

        assert conn(client).request_payloads == [("apt", {"TI": 50, "PN": "Ally"})]
        assert reply.player_name == "Ally"

    def test_assign_title_needs_a_name(self):
        client = make_client()

        with pytest.raises(ValueError):
            client.player.assign_title(Title.STORM_LORD, "")

        assert conn(client).request_payloads == []

    def test_revoke_title_sends_an_empty_name(self):
        client = make_client()

        client.player.revoke_title(Title.STORM_LORD)

        assert conn(client).request_payloads == [("apt", {"TI": 50, "PN": ""})]

    @pytest.mark.parametrize("error", [GGEError.IS_NOT_KING, GGEError.PLAYER_NOT_FOUND, GGEError.ALREADY_HAS_TITLE])
    def test_a_refusal_raises(self, error):
        client = make_client({"apt": xt_packet("apt", {}, error_code=error)})

        with pytest.raises(CommandError) as raised:
            client.player.assign_title(Title.STORM_LORD, "Ally")

        assert raised.value.error is error

    def test_every_apt_asks_for_the_title_ranks(self):
        # APTCommand.executeCommand sends C2SUserAchievedRanksVO on ALL_OK, for a push too
        client = make_client(state=logged_in_state())

        client._on_packet(xt_packet("apt", {"TI": 50}))
        client._on_packet(xt_packet("apt", {}, error_code=GGEError.IS_NOT_KING))

        assert [(frame.split("%")[3], request_payload(frame)) for frame in conn(client).sent] == [("uar", {})]

    def test_a_finished_achievement_is_announced(self):
        client = make_client(state=logged_in_state())
        finished: list[AchievementFinishedResponse] = []
        client.player.on_achievement_finished(finished.append)

        client._on_packet(xt_packet("vfi", {"AID": 1, "gcu": {"C1": 40, "C2": 2}}))

        assert [pushed.achievement_id for pushed in finished] == [1]


class TestState:
    def test_a_finished_achievement_applies_its_coins(self):
        # VFICommand.exec parses the gcu next to the joined castle's grc
        state = logged_in_state(gcu={"C1": 100, "C2": 5})

        state.update_from_packet("vfi", {"AID": 1, "gcu": {"C1": 140, "C2": 7}})

        player = state.get_local_player()
        assert (player.coins, player.rubies) == (140, 7)

    def test_the_glory_reset_replaces_the_glory_reset_time(self):
        state = logged_in_state(uar=UAR)

        state.update_from_packet("uht", {"RS": 3600})

        ranks = state.get_title_ranks()
        assert ranks.glory.reset_seconds == 3600 and ranks.faction.reset_seconds == 0
        assert state.get_last_packet_time("uht") is not None

    @pytest.mark.parametrize(("payload", "error_code"), [({"RS": 3600}, 1), ({"RS": "x"}, 0), ({}, 0)])
    def test_a_glory_reset_not_read_keeps_it(self, payload, error_code):
        state = logged_in_state(uar=UAR)

        state.update_from_packet("uht", payload, error_code=error_code)

        assert state.get_title_ranks().glory.reset_seconds == 600

    def test_a_title_without_a_name_is_yours(self):
        # parseAPT runs only when the apt has no PN
        state = logged_in_state(uar={**UAR, "ITM": {"TID": -1}})

        state.update_from_packet("apt", {"TI": 50, "PN": "Ally"})
        assert state.get_title_ranks().island_title.title_id is None

        state.update_from_packet("apt", {"TI": 50})
        assert state.get_title_ranks().island_title.title_id is Title.STORM_LORD
