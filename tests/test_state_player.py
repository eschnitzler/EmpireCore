"""GameState local player tracking: player sections, alliance, special currencies and freshness."""

import time
from unittest.mock import patch

import pytest

from empire_core.state.models import Player
from tests.state_helpers import gam_payload, gcl_payload


class TestPlayerParsing:
    def test_relogin_merges_player_data(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "old_name"}, "gxp": {"LVL": 10, "XP": 3000}})
        player = state.local_player
        assert player is not None and player.PN == "old_name"

        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "new_name"}, "gxp": {"LVL": 11, "XP": 3630}})
        # Identity preserved, data refreshed
        assert state.local_player is player
        assert player.PN == "new_name"
        assert player.level == 11

    def test_malformed_special_currency_entry_skipped(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "x"}})
        state.update_from_packet("sce", [["GOOD", 5], ["BAD", "not-a-number"], ["ALSO_GOOD", 7]])
        inv = state.local_player.special_currencies
        assert inv["GOOD"] == 5
        assert inv["ALSO_GOOD"] == 7
        assert "BAD" not in inv


class TestLocalPlayerSnapshots:
    """local_player/special_currencies are read by user threads while the receive
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

        assert snapshot.special_currencies == {"A": 1}, "snapshot currencies mutated by receive thread"
        assert list(snapshot.castles) == [1], "snapshot castles mutated by receive thread"

    def test_get_special_currencies_returns_copy(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]]})
        currencies = state.get_special_currencies()

        assert currencies == {"A": 1}
        currencies["A"] = 999
        assert state.get_special_currencies() == {"A": 1}

    def test_get_special_currencies_is_empty_before_login(self, state):
        assert state.get_special_currencies() == {}

    def test_sce_swaps_currencies_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]]})
        reader_view = state.local_player.special_currencies  # what an unlocked reader holds

        state.update_from_packet("sce", [["B", 2]])

        assert reader_view == {"A": 1}, "receive thread mutated a dict a reader already holds"
        assert state.get_special_currencies() == {"A": 1, "B": 2}

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
        watched = ("PN", "level", "xp", "gold")
        before = {"PN": "old", "level": 10, "xp": 100, "gold": 50}
        after = {"PN": "new", "level": 11, "xp": 200, "gold": 60}

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
        with patch("time.time", return_value=time.time() + 3600):
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
        assert second is not None and second > first, "currency push did not refresh the stamp"


# Live capture of a login gbd's player sections; name scrubbed.
LIVE_GPI = {"UID": 230862, "PID": 7, "PN": "me", "E": "-1", "V": 0, "CTAC": 1, "CL": 0, "RD": 1762208793}
LIVE_LOGIN: dict = {
    "gpi": LIVE_GPI,
    "gxp": {"XP": 5329, "LVL": 13, "LL": 0, "XPFCL": 5070, "XPTNL": 5880},
    "gcu": {"C1": 155600, "C2": 3098},
    "vip": {"VP": 2, "VRL": 3, "VRS": 0, "UPG": 0},
    "gal": {"AID": 190426, "R": 1, "N": "H.O.P.E", "ACF": 22, "SA": 0},
    "gho": {"H": 0, "RP": 93},
    "uap": {"KID": 0, "NS": -1, "PMS": -1, "PMT": 0},
    "gac": None,
}


class TestPlayerPushes:
    """Each login section is also pushed on its own, with the section body as payload."""

    def test_live_login_sections(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        player = state.get_local_player()
        assert (player.gold, player.rubies, player.level, player.xp) == (155600, 3098, 13, 5329)
        assert (player.honor, player.ranking) == (0, 93)
        assert player.beginner_protection == {0: False}
        assert state.get_last_packet_time("gho") is not None

    def test_gcu_push(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet("gcu", {"C1": 150000, "C2": 3100})
        player = state.get_local_player()
        assert (player.gold, player.rubies) == (150000, 3100)
        assert state.get_last_packet_time("gcu") is not None

    def test_gxp_push(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet("gxp", {"LVL": 13, "XP": 5400})
        assert state.get_local_player().xp == 5400

    def test_gal_push_joins_and_leaves(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})
        state.update_from_packet("gal", {"AID": 5, "R": 3, "AN": "Clan", "ACF": 0, "SA": 0})
        player = state.get_local_player()
        assert player.alliance is not None and (player.AID, player.alliance.name) == (5, "Clan")

        state.update_from_packet("gal", {"AID": -1})
        player = state.get_local_player()
        assert (player.alliance, player.AID) == (None, None)

    def test_gpi_push(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet("gpi", {**LIVE_GPI, "PN": "renamed"})
        assert state.get_local_player().PN == "renamed"

    def test_vip_push(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet("vip", {"VP": 50, "VRL": 4, "VRS": 3600, "UPG": 0})
        player = state.get_local_player()
        assert (player.vip_points, player.vip_level, player.vip_time_left) == (50, 4, 3600)

    def test_gcl_push(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("gcl", gcl_payload([(1, "Main"), (2, "Outpost")]))
        assert sorted(state.get_local_player().castles) == [1, 2]

    def test_gcl_push_before_login_is_ignored(self, state):
        state.update_from_packet("gcl", gcl_payload([(1, "Main")]))
        assert state.castles == {}

    def test_glu_applies_its_currency_and_xp(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet(
            "glu", {"gcu": {"C1": 160000, "C2": 3098}, "gxp": {"LVL": 14, "XP": 5880}, "L": 14, "LL": 0}
        )
        player = state.get_local_player()
        assert (player.level, player.xp, player.gold) == (14, 5880, 160000)
        assert state.get_last_packet_time("glu") is not None
        assert state.get_last_packet_time("gxp") is not None

    def test_mir_applies_its_castle_list(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("mir", {"gcl": gcl_payload([(1, "Main"), (3, "Taken")]), "CID": 3, "KID": 0})
        assert sorted(state.get_local_player().castles) == [1, 3]

    def test_gho_push(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet("gho", {"H": 120, "RP": 95})
        player = state.get_local_player()
        assert (player.honor, player.ranking) == (120, 95)

    def test_uap_push_is_kept_per_kingdom(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        state.update_from_packet("uap", {"KID": 2, "NS": 86400, "PMS": -1, "PMT": 0})
        assert state.get_local_player().beginner_protection == {0: False, 2: True}

    def test_push_before_login_is_ignored(self, state):
        state.update_from_packet("gcu", {"C1": 5, "C2": 1})
        assert state.get_local_player() is None

    def test_push_refreshes_player_stamp(self, state):
        state.update_from_packet("gbd", LIVE_LOGIN)
        first = state.get_player_last_updated()
        time.sleep(0.02)
        state.update_from_packet("gcu", {"C1": 1, "C2": 1})
        second = state.get_player_last_updated()
        assert first is not None and second is not None and second > first

    def test_alliance_change_is_one_swap(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        player = state.local_player
        observed: list[tuple] = []
        real_setattr = Player.__setattr__

        def spy(self, name, value):
            real_setattr(self, name, value)
            if self is player:
                observed.append((self.AID, self.alliance))

        with patch.object(Player, "__setattr__", spy):
            state.update_from_packet("gal", {"AID": -1})

        assert (player.AID, player.alliance) == (None, None)
        assert observed == [], f"alliance fields written one at a time: {observed}"


class TestPushRobustness:
    def test_snapshot_does_not_share_beginner_protection(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "uap": {"KID": 0, "NS": 60}})
        snapshot = state.get_local_player()
        snapshot.beginner_protection[5] = True
        assert 5 not in state.get_local_player().beginner_protection

    def test_unreadable_gal_push_keeps_the_alliance(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        state.update_from_packet("gal", {"raw": ""})
        alliance = state.get_local_player().alliance
        assert alliance is not None and alliance.id == 5

    def test_leave_alliance_push_still_clears_it(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        state.update_from_packet("gal", {"AID": -1})
        assert state.get_local_player().alliance is None


class TestSpecialCurrencies:
    # Live capture of a login gbd's sce section.
    LIVE_SCE = [["GRT", 2], ["STL", 100], ["PTT", 1604], ["MS1", 197], ["SLWT", 6], ["KTK", 5]]

    def test_live_sce_shape(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": self.LIVE_SCE})
        assert state.get_special_currencies() == {"GRT": 2, "STL": 100, "PTT": 1604, "MS1": 197, "SLWT": 6, "KTK": 5}

    def test_push_updates_amounts(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": self.LIVE_SCE})
        state.update_from_packet("sce", [["PTT", 1500]])
        currencies = state.get_special_currencies()
        assert currencies["PTT"] == 1500 and currencies["MS1"] == 197

    def test_old_names_still_read_through(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["PTT", 3]]})
        with pytest.deprecated_call():
            assert state.get_inventory() == {"PTT": 3}
        player = state.get_local_player()
        with pytest.deprecated_call():
            assert player.inventory == {"PTT": 3}
        assert Player.model_validate({"inventory": {"PTT": 1}}).special_currencies == {"PTT": 1}
        with pytest.deprecated_call():
            player.inventory = {"KTK": 2}
        assert player.special_currencies == {"KTK": 2}


class TestLevelProgress:
    """LL, XPFCL and XPTNL are computed from LVL and XP, as CastleUserData.parse_GXP does."""

    def _player_after(self, state, gxp: dict) -> Player:
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gxp": gxp})
        player = state.get_local_player()
        assert player is not None
        return player

    def test_matches_what_a_live_login_sends(self, state):
        player = self._player_after(state, {"LVL": 13, "XP": 5329})
        live = LIVE_LOGIN["gxp"]
        assert (player.legendary_level, player.xp_for_current_level, player.xp_to_next_level) == (
            live["LL"],
            live["XPFCL"],
            live["XPTNL"],
        )
        assert player.xp_progress == pytest.approx((5329 - 5070) / (5880 - 5070) * 100)

    # Expected values from the client's PlayerConst functions run in node.
    @pytest.mark.parametrize(
        ("xp", "legend", "current", "following"),
        [
            (200000, 11, 196295, 201973),
            (1000000, 115, 994119, 1002920),
            (99999999999, 950, 10630311, 10630311),
        ],
    )
    def test_legend_levels_past_level_70(self, state, xp, legend, current, following):
        player = self._player_after(state, {"LVL": 70, "XP": xp})
        assert (player.legendary_level, player.xp_for_current_level, player.xp_to_next_level) == (
            legend,
            current,
            following,
        )

    def test_level_up_push_recomputes(self, state):
        self._player_after(state, {"LVL": 69, "XP": 146000})
        state.update_from_packet("glu", {"gxp": {"LVL": 70, "XP": 200000}, "L": 70, "LL": 0})
        assert state.get_local_player().legendary_level == 11

    @pytest.mark.parametrize("bad", [None, "", "x"])
    def test_unreadable_level_keeps_the_rest_of_the_packet(self, state, bad):
        self._player_after(state, {"LVL": 13, "XP": 5329})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gxp": {"LVL": bad, "XP": 5400}, "gcu": {"C1": 77}})
        player = state.get_local_player()
        assert (player.level, player.xp, player.gold) == (13, 5400, 77)

    def test_xp_progress_edges(self):
        assert Player().xp_progress == 0.0
        at_cap = Player(LVL=70, XP=10630311, LL=950, XPFCL=10630311, XPTNL=10630311)
        assert at_cap.xp_progress == 0.0
        just_past_70 = Player(LVL=70, XP=147000, LL=1, XPFCL=147250, XPTNL=151095)
        assert just_past_70.xp_progress == 0.0
