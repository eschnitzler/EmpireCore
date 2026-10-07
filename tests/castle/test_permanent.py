"""The gpc section: each castle's unlocked units and horses, and the castle service's get_horses."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from empire_core.castle.models import PermanentCastleDataResponse
from empire_core.enums import Kingdom
from empire_core.exceptions import GameDataNotLoadedError, UnknownCastleError
from empire_core.gamedata import GameData, Horse
from empire_core.state.manager import GameState
from tests.service_helpers import make_client
from tests.state.state_helpers import gcl_payload

# Shaped like a live login's gpc: one castle, no stable yet so no horses
LIVE_GPC: dict[str, Any] = {
    "A": [
        {
            "UH": [],
            "U": {
                "U": [640, 641, 611, 644, 614, 647, 626, 602, 603, 637],
                "L": [256, 513, 642, 645, 646, 524, 653, 13, 654, 14, 660, 148],
            },
            "AID": 2001,
            "KID": 0,
        }
    ]
}

HORSES = [
    {"wodID": 1001, "name": "Horse", "group": "Travelbooster", "type": "1", "unitBoost": "6", "marketBoost": "10",
     "spyBoost": "10", "costFactorC1": "1", "costFactorC2": "0.0"},
    {"wodID": 1002, "name": "Horse", "group": "Travelbooster", "type": "2", "unitBoost": "10", "marketBoost": "17",
     "spyBoost": "17", "costFactorC1": "0", "costFactorC2": "1.0"},
    {"wodID": 1003, "name": "Horse", "group": "Travelbooster", "type": "3", "unitBoost": "16", "marketBoost": "27",
     "spyBoost": "27", "costFactorC1": "0", "costFactorC2": "2.1", "isInstantSpyHorse": "1"},
]  # fmt: skip


class TestPermanentCastleData:
    def test_live_shape_parses(self):
        [castle] = PermanentCastleDataResponse.model_validate(LIVE_GPC).castles

        assert (castle.castle_id, castle.kingdom_id, castle.horse_ids) == (2001, Kingdom.GREEN, [])
        assert castle.units.unlocked_unit_ids[:3] == [640, 641, 611]
        assert castle.units.locked_unit_ids[-1] == 148

    def test_horse_ids_keep_the_order_sent(self):
        [castle] = PermanentCastleDataResponse.model_validate(
            {"A": [{"AID": 2001, "KID": 0, "U": {"U": [], "L": []}, "UH": [1003, 1001]}]}
        ).castles

        assert castle.horse_ids == [Horse.COURSER_STABLE1, Horse.HORSE_STABLE1]

    def test_entries_that_are_no_number_are_dropped(self):
        # The client looks each id up in its game data, where no such entry has a row
        [castle] = PermanentCastleDataResponse.model_validate(
            {"A": [{"AID": 2001, "KID": 0, "U": {"U": [620, "x", None], "L": [True]}, "UH": [1001, "1002", 1003.0]}]}
        ).castles

        assert castle.units.unlocked_unit_ids == [620]
        assert castle.units.locked_unit_ids == []
        assert castle.horse_ids == [1001, 1003]

    def test_missing_units_and_horses_read_as_none_unlocked(self):
        # CastleUnitsVO.parseParamObject's if(e), CastleHorsesVO.parseParamObject's t&&
        [castle] = PermanentCastleDataResponse.model_validate({"A": [{"AID": "2001", "KID": "2"}]}).castles

        assert (castle.castle_id, castle.kingdom_id) == (2001, Kingdom.ICE)
        assert castle.units.unlocked_unit_ids == [] and castle.horse_ids == []

    def test_an_unreadable_castle_costs_only_itself(self):
        payload = {"A": [{"KID": 0}, {"AID": 2002, "KID": 99}, None, {"AID": 2001, "KID": 0, "UH": [1001]}]}

        castles = PermanentCastleDataResponse.model_validate(payload).castles

        assert [(c.castle_id, c.horse_ids) for c in castles] == [(2001, [1001])]


@pytest.fixture
def game_state() -> Iterator[GameState]:
    state = GameState()
    yield state
    state.shutdown()


def _login(state: GameState, gpc: dict[str, Any], kingdom: int = 0) -> None:
    state.update_from_packet(
        "gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(2001, "Main")], kingdom=kingdom), "gpc": gpc}
    )


class TestPermanentCastleState:
    def test_login_stores_each_castle_by_kingdom_and_id(self, game_state):
        _login(game_state, LIVE_GPC)

        assert list(game_state.permanent_castles) == [(Kingdom.GREEN, 2001)]
        permanent = game_state.get_permanent_castle(2001)
        assert permanent is not None and permanent.units.unlocked_unit_ids[0] == 640
        assert game_state.get_castle_horse_ids(2001) == []
        assert game_state.get_last_packet_time("gpc") is not None

    def test_a_push_replaces_the_castles_it_names_and_keeps_the_others(self, game_state):
        other = {"AID": 2002, "KID": 1, "U": {"U": [], "L": []}, "UH": [1001]}
        _login(game_state, {"A": [*LIVE_GPC["A"], other]})
        before = game_state.permanent_castles

        game_state.update_from_packet("gpc", {"A": [{"AID": 2001, "KID": 0, "U": {"U": [620], "L": []}, "UH": [1002]}]})

        assert game_state.get_castle_horse_ids(2001) == [1002]
        assert game_state.permanent_castles[(Kingdom.SANDS, 2002)].horse_ids == [1001]
        assert before[(Kingdom.GREEN, 2001)].horse_ids == [], "the dict a reader held was changed in place"

    def test_a_gbd_without_gpc_leaves_the_castles_alone(self, game_state):
        _login(game_state, {"A": [{"AID": 2001, "KID": 0, "UH": [1001]}]})

        game_state.update_from_packet("gbd", {"gpi": {"PID": 7}})

        assert game_state.get_castle_horse_ids(2001) == [1001]

    def test_the_castle_is_looked_up_in_its_own_kingdom(self, game_state):
        # getDicKey is kingdom and id: an entry under another kingdom is not this castle's
        _login(game_state, {"A": [{"AID": 2001, "KID": 0, "UH": [1001]}]}, kingdom=2)

        assert game_state.get_permanent_castle(2001) is None
        assert game_state.get_castle_horse_ids(2001) is None

    def test_a_castle_not_in_the_castle_list_has_none(self, game_state):
        _login(game_state, LIVE_GPC)

        assert game_state.get_castle_horse_ids(2009) is None

    def test_reset_forgets_them(self, game_state):
        _login(game_state, LIVE_GPC)

        game_state.reset()

        assert game_state.permanent_castles == {}


class TestGetHorses:
    def _client(self, horse_ids: list[int] | None, *, game_data: bool = True):
        client = make_client()
        client.state = GameState()
        if horse_ids is not None:
            _login(client.state, {"A": [{"AID": 2001, "KID": 0, "UH": horse_ids}]})
        if game_data:
            client.game_data = GameData.parse("test", {"horses": HORSES})
        return client

    def test_returns_the_game_data_rows_sorted_by_wod_id(self):
        client = self._client([1003, 1001])

        horses = client.castle.get_horses(2001)

        assert horses is not None
        assert [(h.wod_id, h.spy_boost, h.is_instant_spy_horse) for h in horses] == [
            (1001, 10, False),
            (1003, 27, True),
        ]
        client.state.shutdown()

    def test_ids_missing_from_the_game_data_are_left_out(self):
        # createVObyWOD finds no row, so CastleHorsesVO skips the id
        client = self._client([1002, 4242])

        horses = client.castle.get_horses(2001)

        assert horses is not None and [h.wod_id for h in horses] == [1002]
        client.state.shutdown()

    def test_none_when_no_gpc_named_the_castle_yet(self):
        client = self._client(None)
        client.state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(2001, "Main")])})

        assert client.castle.get_horses(2001) is None
        client.state.shutdown()

    def test_a_castle_not_yours_raises(self):
        client = self._client([1001])

        with pytest.raises(UnknownCastleError):
            client.castle.get_horses(2009)
        client.state.shutdown()

    def test_needs_game_data(self):
        client = self._client([1001], game_data=False)

        with pytest.raises(GameDataNotLoadedError):
            client.castle.get_horses(2001)
        client.state.shutdown()
