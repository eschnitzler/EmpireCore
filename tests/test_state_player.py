"""GameState local player tracking: player sections, alliance, inventory and freshness."""

import time
from unittest.mock import patch

import pytest

from empire_core.state.models import Player
from tests.state_helpers import gam_payload, gcl_payload


class TestPlayerParsing:
    def test_relogin_merges_player_data(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "old_name", "LVL": 10}})
        player = state.local_player
        assert player is not None and player.PN == "old_name"

        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "new_name", "LVL": 11}})
        # Identity preserved, data refreshed
        assert state.local_player is player
        assert player.PN == "new_name"
        assert player.LVL == 11

    def test_malformed_inventory_entry_skipped(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "x"}})
        state.update_from_packet("sce", [["GOOD", 5], ["BAD", "not-a-number"], ["ALSO_GOOD", 7]])
        inv = state.local_player.inventory
        assert inv["GOOD"] == 5
        assert inv["ALSO_GOOD"] == 7
        assert "BAD" not in inv


class TestLocalPlayerSnapshots:
    """local_player/inventory are read by user threads while the receive
    thread updates them, so there must be a locked snapshot path."""

    def test_get_local_player_returns_detached_copy(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "me"}})
        snapshot = state.get_local_player()

        assert snapshot is not None and snapshot.PN == "me"
        assert snapshot is not state.local_player
        snapshot.PN = "tampered"
        assert state.local_player.PN == "me"

    def test_get_local_player_is_none_before_login(self, state):
        assert state.get_local_player() is None

    def test_snapshot_containers_are_detached(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]], "gcl": gcl_payload([(1, "Main")])})
        snapshot = state.get_local_player()

        state.update_from_packet("sce", [["B", 2]])
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(2, "Second")])})

        assert snapshot.inventory == {"A": 1}, "snapshot inventory mutated by receive thread"
        assert list(snapshot.castles) == [1], "snapshot castles mutated by receive thread"

    def test_get_inventory_returns_copy(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]]})
        inventory = state.get_inventory()

        assert inventory == {"A": 1}
        inventory["A"] = 999
        assert state.get_inventory() == {"A": 1}

    def test_get_inventory_is_empty_before_login(self, state):
        assert state.get_inventory() == {}

    def test_sce_swaps_inventory_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]]})
        reader_view = state.local_player.inventory  # what an unlocked reader holds

        state.update_from_packet("sce", [["B", 2]])

        assert reader_view == {"A": 1}, "receive thread mutated a dict a reader already holds"
        assert state.get_inventory() == {"A": 1, "B": 2}

    def test_gcl_swaps_player_castles_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        reader_view = state.local_player.castles

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])})

        assert list(reader_view) == [1], "receive thread mutated a dict a reader already holds"
        assert sorted(state.local_player.castles) == [1, 2]

    def test_relogin_merge_has_no_observable_intermediate_state(self, state):
        # Identity in gpi, level/XP in gxp, currency in gcu — the sections a
        # real re-login gbd spreads these fields across. They must land in
        # ONE atomic swap: gpi alone being atomic still lets a reader see
        # "new name, old level" while gxp/gcu are applied field by field.
        state.update_from_packet(
            "gbd", {"gpi": {"PID": 7, "PN": "old"}, "gxp": {"LVL": 10, "XP": 100}, "gcu": {"C1": 50}}
        )
        player = state.local_player
        watched = ("PN", "LVL", "XP", "gold")
        before = {"PN": "old", "LVL": 10, "XP": 100, "gold": 50}
        after = {"PN": "new", "LVL": 11, "XP": 200, "gold": 60}

        observed: list[dict] = []
        real_setattr = Player.__setattr__

        def spy(self, name, value):
            real_setattr(self, name, value)
            if self is player:
                observed.append({field: getattr(self, field) for field in watched})

        with patch.object(Player, "__setattr__", spy):
            state.update_from_packet(
                "gbd", {"gpi": {"PID": 7, "PN": "new"}, "gxp": {"LVL": 11, "XP": 200}, "gcu": {"C1": 60}}
            )

        assert {field: getattr(player, field) for field in watched} == after
        assert all(seen in (before, after) for seen in observed), f"half-merged player observable: {observed}"

    def test_players_dict_holds_only_the_local_player(self, state):
        # Documented contract: `players` is not a map of every player seen
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})
        state.update_from_packet("gam", gam_payload(500, oid=999))
        assert list(state.players) == [7]


class TestPartialSubPacketsPreserveState:
    """A sub-packet that omits a key must not reset that value to 0."""

    def test_partial_gcu_preserves_other_currency(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 200}})

        player = state.get_local_player()
        assert (player.gold, player.rubies) == (200, 5)

    def test_partial_vip_preserves_other_fields(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "vip": {"VP": 10, "VRL": 2, "VRS": 3600}})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "vip": {"VRS": 1800}})

        player = state.get_local_player()
        assert (player.vip_points, player.vip_level, player.vip_time_left) == (10, 2, 1800)


class TestAllianceMembership:
    def test_alliance_parsed(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        player = state.get_local_player()
        assert player.alliance is not None and player.alliance.name == "Clan"
        assert player.AID == 5

    def test_live_gal_shape(self, state):
        # Live capture
        gal = {"AID": 190426, "R": 1, "N": "H.O.P.E", "ACF": 22, "SA": 0}
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": gal})
        alliance = state.get_local_player().alliance
        assert alliance is not None
        assert (alliance.id, alliance.name, alliance.rank, alliance.current_fame) == (190426, "H.O.P.E", 1, 22)
        assert alliance.is_searching is False

    def test_name_under_an_as_the_client_reads_it(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "AN": "Clan", "SA": 1}})
        alliance = state.get_local_player().alliance
        assert alliance is not None and alliance.name == "Clan" and alliance.is_searching

    @pytest.mark.parametrize("gal", [{}, None, {"AID": 0}, {"N": "", "SA": 0}])
    def test_leaving_alliance_clears_it(self, state, gal):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        # Fresh login after leaving/being kicked: the gal section says "none"
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": gal})

        player = state.get_local_player()
        assert player.alliance is None, "stale alliance kept forever after leaving"
        assert player.AID is None

    def test_packet_without_alliance_section_keeps_alliance(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        # No gal key at all: this packet carries no alliance information
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})

        assert state.get_local_player().alliance is not None


class TestFreshnessMetadata:
    """Castle resources/units are only refreshed when a dcl arrives (often just
    once, at login), so consumers need to tell live data from leftovers."""

    LOGIN_DCL = {"C": [{"AI": [{"AID": 1, "W": 10, "S": 20, "F": 30}]}]}

    def _login(self, state, dcl: dict | None = None) -> None:
        payload = {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])}
        if dcl is not None:
            payload["dcl"] = dcl
        state.update_from_packet("gbd", payload)

    def test_castle_without_details_has_no_timestamp(self, state):
        self._login(state)
        assert state.get_castle_last_updated(1) is None, "never-synced castle reported as fresh"
        assert state.get_castle_age(1) is None

    def test_dcl_stamps_only_the_castles_it_refreshed(self, state):
        self._login(state)
        before = time.time()
        state.update_from_packet("dcl", self.LOGIN_DCL)

        stamp = state.get_castle_last_updated(1)
        assert stamp is not None and before <= stamp <= time.time()
        assert state.get_castle_last_updated(2) is None, "untouched castle marked fresh"
        assert 0.0 <= state.get_castle_age(1) < 5.0

    def test_login_embedded_dcl_is_stamped(self, state):
        self._login(state, dcl=self.LOGIN_DCL)
        assert state.get_castle_last_updated(1) is not None

    def test_castle_age_grows_with_wall_clock(self, state):
        self._login(state, dcl=self.LOGIN_DCL)
        with patch("empire_core.state.manager.time.time", return_value=time.time() + 3600):
            age = state.get_castle_age(1)
        assert 3595 <= age <= 3605, "login-time resources still look current an hour later"

    def test_lost_castle_forgets_its_timestamp(self, state):
        self._login(state, dcl=self.LOGIN_DCL)
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(2, "Outpost")])})
        assert state.get_castle_last_updated(1) is None

    def test_packet_times_record_what_was_applied(self, state):
        assert state.get_last_packet_time("gbd") is None
        assert state.get_last_packet_time("dcl") is None

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 5, "C2": 1}})

        assert state.get_last_packet_time("gbd") is not None
        assert state.get_last_packet_time("gcu") is not None, "sub-packet freshness unavailable"
        assert state.get_last_packet_time("dcl") is None, "unseen packet reported as applied"
        assert state.get_last_packet_time("nope") is None

    def test_packet_times_snapshot_is_detached(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})
        snapshot = state.get_packet_times()
        assert "gbd" in snapshot
        snapshot.clear()
        assert state.get_last_packet_time("gbd") is not None

    def test_unhandled_packet_is_not_stamped(self, state):
        state.update_from_packet("zzz", {})
        assert state.get_last_packet_time("zzz") is None

    def test_player_last_updated_tracks_pushes(self, state):
        assert state.get_player_last_updated() is None

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 5}})
        first = state.get_player_last_updated()
        assert first is not None

        time.sleep(0.02)
        state.update_from_packet("sce", [["A", 1]])
        second = state.get_player_last_updated()
        assert second is not None and second > first, "inventory push did not refresh the stamp"
