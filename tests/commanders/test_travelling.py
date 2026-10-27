"""Tests for the commanders that lead one of your movements, read from state."""

from __future__ import annotations

import pytest

from empire_core.commanders.models.roster import Commander, CommanderRoster
from empire_core.exceptions import StateNotLoadedError
from empire_core.movements.tracked import Movement
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client
from tests.state.state_helpers import arrive, gam_payload, login

ME = 1001


def roster(*ids: int) -> CommanderRoster:
    return CommanderRoster.model_validate({"C": [{"ID": i} for i in ids]})


def led_by(commander_id: int, *, owner_id: int = ME, returning: bool = False) -> Movement:
    return Movement(
        owner_id=owner_id,
        local_player_id=ME,
        direction=int(returning),
        commander=Commander.model_validate({"ID": commander_id}),
    )


def holding(state: GameState, *movements: Movement) -> GameState:
    state.movements = dict(enumerate(movements))
    return state


def ids(commanders: list[Commander]) -> list[int]:
    return [c.commander_id for c in commanders]


class TestTravellingCommanders:
    def test_reads_before_the_roster_raise(self, state):
        client = make_client(state=holding(state, led_by(1)))

        with pytest.raises(StateNotLoadedError):
            _ = client.commanders.travelling_commanders
        with pytest.raises(StateNotLoadedError):
            _ = client.commanders.idle_commanders

    def test_roster_is_the_state_roster(self, state):
        state.commanders = roster(0, 1)
        client = make_client(state=state)

        assert client.commanders.roster == roster(0, 1)

    def test_a_commander_leading_your_movement_is_travelling(self, state):
        holding(state, led_by(1), Movement(owner_id=ME, local_player_id=ME))
        state.commanders = roster(0, 1, 2)
        client = make_client(state=state)

        assert ids(client.commanders.travelling_commanders) == [1]
        assert ids(client.commanders.idle_commanders) == [0, 2]

    def test_a_returning_army_keeps_its_commander_away(self, state):
        holding(state, led_by(2, returning=True))
        state.commanders = roster(0, 2)
        client = make_client(state=state)

        assert ids(client.commanders.travelling_commanders) == [2]
        assert ids(client.commanders.idle_commanders) == [0]

    def test_other_players_movements_are_ignored(self, state):
        holding(state, led_by(0, owner_id=2002), led_by(1, owner_id=2002, returning=True))
        state.commanders = roster(0, 1)
        client = make_client(state=state)

        assert ids(client.commanders.travelling_commanders) == []
        assert ids(client.commanders.idle_commanders) == [0, 1]

    def test_a_landed_attack_keeps_its_commander_away_until_the_way_home_comes(self, state):
        login(state, ME)
        attack = gam_payload(1, oid=ME)
        attack["M"][0]["UM"] = {"L": {"ID": 1}}
        state.update_from_packet("gam", attack)
        state.commanders = roster(0, 1)
        client = make_client(state=state)
        arrive(state, 1)

        assert state.movements == {}
        assert ids(client.commanders.travelling_commanders) == [1]
        assert ids(client.commanders.idle_commanders) == [0]

    def test_nothing_is_sent(self, state):
        holding(state, led_by(1))
        state.commanders = roster(1)
        client = make_client(state=state)

        assert ids(client.commanders.travelling_commanders) == [1]
        assert ids(client.commanders.idle_commanders) == []
        assert conn(client).sent == []
