"""GameState castle tracking: the castle list (gcl) and castle details (dcl)."""

import logging
from unittest.mock import patch

import pytest

from empire_core.state.manager import GameState
from empire_core.state.models import Castle
from tests.state_helpers import gcl_payload


class TestCastleUpdatesAreAtomic:
    """get_castles() hands out live Castle objects, so dcl must swap, not mutate."""

    def test_dcl_swaps_unit_dict_instead_of_clearing_in_place(self, state):
        state.castles[42] = Castle(OID=42, units={7: 100})
        reader_view = state.get_castles()[0].units

        state.update_from_packet("dcl", {"C": [{"AI": [{"AID": 42, "AC": [[8, 5]]}]}]})

        assert reader_view == {7: 100}, "receive thread mutated a dict a reader already holds"
        assert state.get_castles()[0].units == {8: 5}

    def test_dcl_replaces_resources_instead_of_writing_field_by_field(self, state):
        state.castles[42] = Castle(OID=42)
        res_before = state.get_castles()[0].resources

        state.update_from_packet("dcl", {"C": [{"AI": [{"AID": 42, "W": 10, "S": 20, "F": 30}]}]})

        assert (res_before.wood, res_before.stone, res_before.food) == (0, 0, 0), "torn read possible"
        now = state.get_castles()[0].resources
        assert (now.wood, now.stone, now.food) == (10, 20, 30)

    def test_gcl_swaps_castles_dict_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])})
        reader_view = state.castles

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})

        assert sorted(reader_view) == [1, 2], "receive thread mutated a dict a reader already holds"
        assert sorted(state.castles) == [1]

    def test_gcl_preserves_identity_of_surviving_castles(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        castle = state.castles[1]

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Renamed"), (2, "New")])})

        assert state.castles[1] is castle, "user-held castle reference went stale"
        assert castle.name == "Renamed"

    def test_gcl_relocation_has_no_observable_intermediate_coords(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")], x=10, y=20)})
        castle = state.castles[1]

        observed: list[tuple[int, int]] = []
        real_setattr = Castle.__setattr__

        def spy(self, name, value):
            real_setattr(self, name, value)
            if self is castle:
                observed.append((self.X, self.Y))

        with patch.object(Castle, "__setattr__", spy):
            state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")], x=30, y=40)})

        assert (castle.x, castle.y) == (30, 40)
        assert all(seen in ((10, 20), (30, 40)) for seen in observed), f"castle observable mid-relocation: {observed}"


class TestCastleDetails:
    # Live capture, trimmed
    ENTRY = {
        "AID": 1,
        "W": 7000.0,
        "S": 6500.0,
        "F": 7000.0,
        "A": 12.0,
        "C": 0.0,
        "O": 3.0,
        "D": 57,
        "B": 1,
        "WS": 1,
        "DW": 0,
        "H": 1,
        "MC": 5,
        "AC": [[656, 1], [650, 213]],
        "SHI": [[650, 4]],
        "gpa": {
            "P": 80,
            "NDP": 11927,
            "MRW": 7000,
            "MRS": 7000,
            "MRF": 7000,
            "MRA": 51000,
            "DW": 2239,
            "DS": 1952,
            "DF": 3502,
            "SAFE_W": 1000.0,
            "SAFE_S": 1000.0,
            "SAFE_F": 1000.0,
        },
    }

    def _castle(self, state: GameState, entry: dict) -> Castle:
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("dcl", {"C": [{"KID": 0, "AI": [entry]}]})
        return state.get_castles()[0]

    def test_every_dcl_field_lands_on_the_castle(self, state):
        castle = self._castle(state, self.ENTRY)
        r = castle.resources
        assert (r.wood, r.stone, r.food, r.aquamarine, r.oil) == (7000, 6500, 7000, 12, 3)
        assert (r.wood_cap, r.capacity.aquamarine) == (7000, 51000)
        assert (r.wood_rate, r.stone_rate, r.food_rate) == (223.9, 195.2, 350.2)
        assert r.wood_safe == 1000.0
        assert (castle.population, castle.neutral_deco_points, castle.defence) == (80, 11927, 57)
        assert castle.market_carriages == 5
        assert castle.has_barracks and castle.has_siege_workshop and castle.has_hospital
        assert not castle.has_defense_workshop
        assert castle.units == {656: 1, 650: 213}
        assert castle.stronghold_units == {650: 4}

    def test_castle_without_details_reads_zero(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        castle = state.get_castles()[0]
        assert castle.details is None
        assert (castle.population, castle.market_carriages, castle.has_hospital) == (0, 0, False)

    def test_malformed_entry_keeps_the_old_details(self, state):
        castle = self._castle(state, self.ENTRY)
        state.update_from_packet("dcl", {"C": [{"KID": 0, "AI": [{**self.ENTRY, "AC": "junk"}]}]})
        assert castle.resources.wood == 7000 and castle.market_carriages == 5


class TestCastleStaleDrop:
    def test_lost_castle_is_dropped(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])})
        assert sorted(c.id for c in state.get_castles()) == [1, 2]

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        assert [c.id for c in state.get_castles()] == [1]

    def test_castle_section_listing_zero_owned_castles_drops_all(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})

        # Castle section present, but nothing owned any more (lost last castle)
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": {"C": []}})

        assert state.get_castles() == [], "stale castles never removed"
        assert state.get_local_player().castles == {}

    def test_castle_section_listing_only_foreign_castles_drops_all(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(9, "Enemy")], owner_id=1234)})
        assert state.get_castles() == []

    def test_all_malformed_castle_section_does_not_wipe_castles(self, state, caplog):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})

        # Every entry fails the shape checks: a payload we could not read is
        # not evidence of ownership loss, so the wipe must not be applied.
        drifted = {"C": [{"KID": 0, "AI": [{"AI": {"X": 1}}, {"AI": [0, 1]}, "garbage"]}]}
        with caplog.at_level(logging.DEBUG, logger="empire_core.state.castles"):
            state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": drifted})

        assert [c.id for c in state.get_castles()] == [1], "unreadable gcl destroyed castle state"
        assert list(state.get_local_player().castles) == [1]
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, "schema drift wiped state with only a debug log"
        assert "3/3" in warnings[0].getMessage(), "skip count missing from the warning"

    @pytest.mark.parametrize("gcl", [{}, None, {"X": 1}])
    def test_packet_without_castle_section_keeps_castles(self, state, gcl):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl})

        assert [c.id for c in state.get_castles()] == [1]
