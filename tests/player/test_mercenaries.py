"""The mercenary camp: mpe lists, starts and collects missions."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.gamedata import Collectable
from empire_core.player import (
    MercenaryMissionRarity,
    MercenaryMissionsResponse,
    MercenaryMissionState,
    MercenaryPackageRequest,
)
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


def mission(mission_id: int, state: int, rd: float = 0, quality: int = 1) -> dict[str, Any]:
    return {"ID": mission_id, "R": [["C1", 500]], "D": 3600, "P": 120, "Q": quality, "S": state, "RD": rd}


def mpe(*missions: dict[str, Any]) -> dict[str, Any]:
    return {"NM": 600, "M": list(missions)}


class TestModels:
    def test_a_mission_reads_rarity_state_and_rewards(self):
        reply = parse_response("mpe", mpe(mission(7, 1, rd=90, quality=4), mission(8, 3)))
        assert isinstance(reply, MercenaryMissionsResponse)
        # parse_MPE drops collected missions
        (running,) = reply.missions
        assert running.quality is MercenaryMissionRarity.LEGENDARY
        assert running.state is MercenaryMissionState.STARTED
        assert running.duration_seconds == 3600 and running.price == 120
        assert all(isinstance(reward, Collectable) for reward in running.rewards)

    def test_a_started_mission_whose_time_ran_out_is_collectable(self):
        reply = MercenaryMissionsResponse.model_validate(mpe(mission(7, 1, rd=90)))
        (running,) = reply.missions
        read = running.received_at
        assert running.current_state(read + 30) is MercenaryMissionState.STARTED
        assert running.current_state(read + 91) is MercenaryMissionState.COLLECTABLE
        assert reply.current_mission_state(read + 30) is MercenaryMissionState.STARTED
        assert reply.current_mission_state(read + 91) is MercenaryMissionState.COLLECTABLE

    def test_the_camp_is_open_while_no_mission_runs(self):
        reply = MercenaryMissionsResponse.model_validate(mpe(mission(1, 0), mission(2, 0)))
        assert reply.current_mission_state() is MercenaryMissionState.OPEN
        assert reply.get_mission(2) is not None and reply.get_mission(3) is None

    def test_the_request_defaults_to_listing(self):
        assert MercenaryPackageRequest().to_payload() == {"MID": -1}
        assert MercenaryPackageRequest(mission_id=7).to_payload() == {"MID": 7}


class TestService:
    def test_list_missions_sends_minus_one_and_feeds_the_state(self):
        client = make_client({"mpe": xt_packet("mpe", mpe(mission(1, 0)))}, state=GameState())  # type: ignore[arg-type]
        conn(client).on_packet = client._on_packet

        missions = client.player.list_missions()

        assert conn(client).request_payloads == [("mpe", {"MID": -1})]
        assert [m.mission_id for m in missions.missions] == [1]
        stored = client.state.get_mercenary_missions()
        assert stored is not None and stored.get_mission(1) is not None

    def test_start_mission_lists_then_starts_an_open_mission(self):
        listed = xt_packet("mpe", mpe(mission(1, 0), mission(2, 0)))
        client = make_client({"mpe": [listed, xt_packet("mpe", mpe(mission(1, 0), mission(2, 1, rd=3600)))]})

        assert client.player.start_mission(2) is True

        assert conn(client).request_payloads == [("mpe", {"MID": -1}), ("mpe", {"MID": 2})]

    @pytest.mark.parametrize(
        ("missions", "mission_id"),
        [
            # starting while one runs is the client's ruby skip dialog
            ((mission(1, 0), mission(2, 1, rd=600)), 1),
            # the client disables start while one waits to be collected
            ((mission(1, 0), mission(2, 2)), 1),
            ((mission(1, 0), mission(2, 1, rd=0)), 1),
            ((mission(2, 1, rd=600),), 2),
            ((mission(1, 0),), 9),
        ],
    )
    def test_start_mission_refuses_what_the_client_would_not_send_free(self, missions: Any, mission_id: int):
        client = make_client({"mpe": xt_packet("mpe", mpe(*missions))})

        with pytest.raises(ValueError):
            client.player.start_mission(mission_id)

        assert conn(client).request_payloads == [("mpe", {"MID": -1})]

    # a started mission with RD 0 has no end time for the client (bundle line 81134), and its skip costs 0 rubies
    @pytest.mark.parametrize(
        "finished", [mission(4, 2), mission(4, 1, rd=0), mission(4, 1, rd=-2), mission(4, 1, rd=-600)]
    )
    def test_collect_mission_collects_a_finished_mission(self, finished: dict[str, Any]):
        client = make_client({"mpe": [xt_packet("mpe", mpe(finished)), xt_packet("mpe", mpe())]})

        assert client.player.collect_mission(4) is True

        assert conn(client).request_payloads == [("mpe", {"MID": -1}), ("mpe", {"MID": 4})]

    # the same mpe on a started mission is the ruby skip (confirmSkip), which costs ceil(RD / 60 * 5) rubies,
    # so a started mission is collected only once its time ran out two seconds ago: RD is rounded
    @pytest.mark.parametrize(
        "not_finished", [mission(4, 1, rd=600), mission(4, 1, rd=1), mission(4, 1, rd=-1), mission(4, 0)]
    )
    def test_collect_mission_never_skips_a_running_mission(self, not_finished: dict[str, Any]):
        client = make_client({"mpe": xt_packet("mpe", mpe(not_finished))})

        with pytest.raises(ValueError):
            client.player.collect_mission(4)

        assert conn(client).request_payloads == [("mpe", {"MID": -1})]

    def test_a_started_mission_runs_out_by_the_listing_time(self):
        (listed,) = MercenaryMissionsResponse.model_validate(mpe(mission(4, 1, rd=0))).missions
        assert listed.seconds_past_end(listed.received_at + 3) == pytest.approx(3)
        assert listed.remaining_seconds(listed.received_at + 3) == 0

    def test_a_refused_start_is_false(self):
        client = make_client({"mpe": [xt_packet("mpe", mpe(mission(1, 0))), xt_packet("mpe", error_code=21)]})
        assert client.player.start_mission(1) is False
