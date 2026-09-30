"""GameState castle tracking: the castle list (gcl) and castle details (dcl)."""

import logging
from unittest.mock import patch

import pytest

from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError
from empire_core.state.manager import GameState
from empire_core.state.models import Castle
from tests.state.state_helpers import gcl_payload


class TestCastleUpdatesAreAtomic:
    """get_castles() hands out live Castle objects, so dcl must swap, not mutate."""

    def test_dcl_swaps_unit_dict_instead_of_clearing_in_place(self, state):
        state.castles[(Kingdom.GREEN, 42)] = Castle(OID=42, units={7: 100})
        reader_view = state.get_castles()[0].units

        state.update_from_packet("dcl", {"C": [{"AI": [{"AID": 42, "AC": [[8, 5]]}]}]})

        assert reader_view == {7: 100}, "receive thread mutated a dict a reader already holds"
        assert state.get_castles()[0].units == {8: 5}

    def test_dcl_replaces_resources_instead_of_writing_field_by_field(self, state):
        state.castles[(Kingdom.GREEN, 42)] = Castle(OID=42)
        res_before = state.get_castles()[0].resources

        state.update_from_packet("dcl", {"C": [{"AI": [{"AID": 42, "W": 10, "S": 20, "F": 30}]}]})

        assert (res_before.wood, res_before.stone, res_before.food) == (0, 0, 0), "torn read possible"
        now = state.get_castles()[0].resources
        assert (now.wood, now.stone, now.food) == (10, 20, 30)

    def test_gcl_swaps_castles_dict_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])})
        reader_view = state.castles

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})

        assert sorted(reader_view) == [(Kingdom.GREEN, 1), (Kingdom.GREEN, 2)], (
            "receive thread mutated a dict a reader already holds"
        )
        assert sorted(state.castles) == [(Kingdom.GREEN, 1)]

    def test_gcl_castles_in_a_kingdom_the_client_does_not_define_are_skipped(self, state):
        # CastleListVO.parseCastleList keys castles by KID; Kingdom holds every id the client defines
        section = {"C": [*gcl_payload([(1, "Main")])["C"], *gcl_payload([(2, "Odd")], kingdom=11)["C"]]}
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": section})

        assert sorted(state.castles) == [(Kingdom.GREEN, 1)]
        assert state.castles[(Kingdom.GREEN, 1)].kingdom_id is Kingdom.GREEN

    def test_gcl_landmarks_and_stray_row_kingdoms_are_tracked(self, state):
        section = gcl_payload([(1, "Main")])
        castle_row = section["C"][0]["AI"][0]["AI"]
        castle_row.extend([0, 0, 0, -1, -1, "stray"])
        section["C"][0]["AI"].append({"AI": [23, 50, 60, 888, 7, 0, -1, "Tower"]})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": section})

        assert sorted(state.castles) == [(Kingdom.GREEN, 1), (Kingdom.GREEN, 888)]
        assert (state.castles[(Kingdom.GREEN, 888)].name, state.castles[(Kingdom.GREEN, 1)].kingdom_id) == (
            "Tower",
            Kingdom.GREEN,
        )

    def test_gcl_preserves_identity_of_surviving_castles(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        castle = state.castles[(Kingdom.GREEN, 1)]

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Renamed"), (2, "New")])})

        assert state.castles[(Kingdom.GREEN, 1)] is castle, "user-held castle reference went stale"
        assert castle.name == "Renamed"

    def test_gcl_relocation_has_no_observable_intermediate_coords(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")], x=10, y=20)})
        castle = state.castles[(Kingdom.GREEN, 1)]

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
        assert list(state.get_local_player().castles) == [(Kingdom.GREEN, 1)]
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, "schema drift wiped state with only a debug log"
        assert "3/3" in warnings[0].getMessage(), "skip count missing from the warning"

    @pytest.mark.parametrize("gcl", [{}, None, {"X": 1}])
    def test_packet_without_castle_section_keeps_castles(self, state, gcl):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl})

        assert [c.id for c in state.get_castles()] == [1]


class TestCastleIdsRepeatAcrossKingdoms:
    """CastleListVO.parseCastleList keeps a list per KID, so one id can be yours in two kingdoms."""

    SECTION = {"C": [*gcl_payload([(1, "Storm")], kingdom=4)["C"], *gcl_payload([(1, "Berimond")], kingdom=10)["C"]]}

    def test_both_castles_are_kept(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": self.SECTION})

        assert sorted(state.castles) == [(Kingdom.STORM, 1), (Kingdom.BERIMOND, 1)]
        assert sorted((c.kingdom_id, c.name) for c in state.get_castles()) == [
            (Kingdom.STORM, "Storm"),
            (Kingdom.BERIMOND, "Berimond"),
        ]

    def test_dcl_updates_the_castle_in_its_kingdom(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": self.SECTION})

        state.update_from_packet("dcl", {"C": [{"KID": 10, "AI": [{"AID": 1, "W": 55}]}]})

        assert state.castles[(Kingdom.BERIMOND, 1)].resources.wood == 55
        assert state.castles[(Kingdom.STORM, 1)].resources.wood == 0

    def test_the_freshness_of_a_repeated_id_needs_its_kingdom(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": self.SECTION})

        with pytest.raises(AmbiguousCastleError) as raised:
            state.get_castle_age(1)
        assert raised.value.kingdoms == [Kingdom.STORM, Kingdom.BERIMOND]

    def test_losing_one_keeps_the_other(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": self.SECTION})
        kept = state.castles[(Kingdom.BERIMOND, 1)]

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Berimond")], kingdom=10)})

        assert list(state.castles) == [(Kingdom.BERIMOND, 1)]
        assert state.castles[(Kingdom.BERIMOND, 1)] is kept

    def test_mir_applies_both(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})

        state.update_from_packet("mir", {"gcl": self.SECTION})

        assert sorted(state.get_local_player().castles) == [(Kingdom.STORM, 1), (Kingdom.BERIMOND, 1)]


class TestRowKingdom:
    def test_a_rows_own_kingdom_wins_over_its_block(self, state):
        # InteractiveMapobjectVO.parseAreaInfo reads the kingdom from field 16
        row = [1, 10, 20, 5, 7, 1, 1, 1, 0, 0, "Ice", 0, 0, -1, -1, -1, 2]
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": {"C": [{"KID": 0, "AI": [{"AI": row}]}]}})

        assert list(state.castles) == [(Kingdom.ICE, 5)]
        assert state.get_castles()[0].kingdom_id is Kingdom.ICE

    def test_a_row_without_one_takes_its_blocks(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(5, "Fire")], kingdom=3)})

        assert list(state.castles) == [(Kingdom.FIRE, 5)]
