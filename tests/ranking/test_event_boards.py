"""Event board fixtures follow the client parsers cited by the public models."""

import pytest

from empire_core.enums import RankingType
from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError, PacketError
from tests.service_helpers import conn, make_client, xt_packet


def test_colossus_donor_rows_and_pagination():
    client = make_client(
        {"che": xt_packet("che", {"OP": 400, "LR": 12, "HS": [{"CR": 11, "PN": "Donor", "CP": 300, "PID": 87}]})}
    )
    page = client.ranking.get_colossus_highscore("11")
    assert (page.own_donation_points, page.last_rank) == (400, 12)
    (row,) = page.rows
    assert (row.rank, row.player_name, row.donation_points, row.player_id) == (11, "Donor", 300, 87)
    assert conn(client).request_payloads == [("che", {"SV": "11"})]


def test_colossus_empty_page_and_default_own_rank():
    client = make_client({"che": xt_packet("che", {"OP": 0, "LR": 0, "HS": []})})
    assert client.ranking.get_colossus_highscore().rows == ()
    assert conn(client).request_payloads == [("che", {"SV": "-1"})]


def test_colossus_drops_bad_rows_with_warning(caplog):
    client = make_client(
        {"che": xt_packet("che", {"OP": 0, "LR": 1, "HS": [None, {"CR": 1, "PN": "A", "CP": 2, "PID": 3}]})}
    )
    assert len(client.ranking.get_colossus_highscore().rows) == 1
    assert "unreadable" in caplog.text


def test_season_info_preserves_medals_and_passes():
    client = make_client(
        {
            "kli": xt_packet(
                "kli",
                {
                    "KLD": {"KLDID": 8, "KLDS": 20},
                    "KLM": [[98765, 4]],
                    "KLAM": [],
                    "KLSP": {"KLP": 1, "KLEPE": 0, "KLPP": [456]},
                    "KLR": {"KLRID": 3, "KLMP": 42},
                    "RD": 75,
                    "KLSE": 1,
                    "KLS": 0,
                },
            )
        }
    )
    info = client.ranking.get_season_info()
    assert info.division is not None and info.player_medals is not None
    assert info.passes is not None and info.rank is not None
    assert (info.division.division_id, info.division.size) == (8, 20)
    assert (info.player_medals[0].medal_id, info.player_medals[0].amount) == (98765, 4)
    assert info.alliance_medals == ()
    assert info.passes.season_enabled and not info.passes.event_enabled
    assert info.passes.promotions[0].promotion_id == 456
    assert (info.rank.promotion_id, info.rank.medal_points, info.payout_seconds) == (3, 42, 75)
    assert info.event_dialog_seen and not info.season_dialog_seen
    assert conn(client).request_payloads == [("kli", {})]


def test_season_own_ranks_bare_array_and_unknown_board():
    client = make_client({"klh": xt_packet("klh", [[63, 7], [64, 2], [98765, 9]])})
    rows = client.ranking.get_season_ranks()
    assert [(r.list_type, r.rank) for r in rows] == [(RankingType.KINGDOMS_LEAGUE_SEASON, 7), (64, 2), (98765, 9)]
    assert conn(client).request_payloads == [("klh", {})]


def test_season_empty_ranks():
    client = make_client({"klh": xt_packet("klh", [])})
    assert client.ranking.get_season_ranks() == ()


@pytest.mark.parametrize(
    "command,method", [("che", "get_colossus_highscore"), ("kli", "get_season_info"), ("klh", "get_season_ranks")]
)
@pytest.mark.parametrize("error", [CommandError("x", 1), EmpireTimeoutError("late"), ConnectionClosedError("gone")])
def test_board_failures_propagate(command, method, error):
    client = make_client({command: error})
    with pytest.raises(type(error)):
        getattr(client.ranking, method)(timeout=0.1)


def test_colossus_refusal_and_missing_board_are_not_empty_success():
    client = make_client({"che": xt_packet("che", error_code=145)})
    with pytest.raises(CommandError):
        client.ranking.get_colossus_highscore()
    client = make_client({"che": xt_packet("che", {"OP": 1})})
    with pytest.raises(PacketError):
        client.ranking.get_colossus_highscore()


def test_season_rank_array_dispatches_registered_callback():
    from empire_core.ranking import GetSeasonRanksResponse

    client = make_client({})
    from empire_core.protocol.base import BaseResponse

    received: list[BaseResponse] = []
    client.ranking.on_response("klh", received.append)
    client._on_packet(xt_packet("klh", [[63, 4]]))
    assert isinstance(received[0], GetSeasonRanksResponse)
    assert received[0].ranks[0].rank == 4


def test_season_bad_rank_is_warned_and_unknown_owner_lookup_is_not_invented(caplog):
    client = make_client({"klh": xt_packet("klh", [None, [64, 5]])})
    assert len(client.ranking.get_season_ranks()) == 1
    assert "unreadable" in caplog.text


def test_unparseable_season_info_is_not_an_empty_success():
    client = make_client({"kli": xt_packet("kli", "unreadable")})
    with pytest.raises(PacketError):
        client.ranking.get_season_info()


def test_season_optional_sections_follow_client_falsy_and_empty_object_branches():
    client = make_client(
        {
            "kli": [
                xt_packet("kli", {"KLD": 0, "KLSP": False, "KLR": None, "KLM": None}),
                xt_packet("kli", {"KLD": {}, "KLSP": {}, "KLR": {}}),
            ]
        }
    )
    absent = client.ranking.get_season_info()
    assert absent.division is None and absent.passes is None and absent.rank is None
    assert absent.player_medals is None
    empty = client.ranking.get_season_info()
    assert empty.division is not None and empty.passes is not None and empty.rank is not None
    assert (empty.division.division_id, empty.division.size) == (0, 0)
    assert not empty.passes.season_enabled and not empty.passes.event_enabled
    assert (empty.rank.promotion_id, empty.rank.medal_points) == (0, 0)
