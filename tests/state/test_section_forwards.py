"""Login sections carried inside other packets: what each applies and which sections it stamps."""

from typing import Any

import pytest

from empire_core.enums import Kingdom
from empire_core.gamedata.ids.events import Event
from empire_core.state.login_data import LoginDataResponse
from empire_core.state.manager import _TRACKED_SECTIONS, GameState
from tests.state.state_helpers import gcl_payload

PLAYER = {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")]), "gcu": {"C1": 100, "C2": 5}}
UAP = {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}
FKI = {"BFLMS": 1, "RFLMS": 0, "PA": True, "BCR": "1", "RCR": None}
MINES = {"M": [{"OID": 42, "RC": 2, "NC": 3600, "C1": 250}]}
STORAGE = {"SID": 1, "RD": [[300, 3, 1]], "CD": [[301, 55, 20, 1]], "UD": [[302, 77, 40, 0]]}


@pytest.fixture
def state():
    state = GameState()
    state.update_from_packet("gbd", PLAYER)
    yield state
    state.shutdown()


def stamped(state: GameState, command: str, payload: Any, error_code: int = 0) -> set[str]:
    """The packet kinds whose stamp the packet set or moved."""
    before = state.get_packet_times()
    state.update_from_packet(command, payload, error_code)
    return {kind for kind, at in state.get_packet_times().items() if before.get(kind) != at}


class TestLevelUp:
    def test_applies_and_stamps_its_coins_and_xp(self, state):
        # GLUCommand.executeCommand: parseGCU(i.gcu), then parse_GXP(i.gxp)
        payload = {"gcu": {"C1": 160, "C2": 9}, "gxp": {"LVL": 14, "XP": 5880}, "L": 14, "LL": 0}
        assert stamped(state, "glu", payload) == {"glu", "gcu", "gxp"}
        player = state.get_local_player()
        assert (player.coins, player.rubies, player.level, player.xp) == (160, 9, 14, 5880)

    def test_a_null_section_is_still_stamped(self, state):
        assert stamped(state, "glu", {"gcu": None, "L": 2, "LL": 0}) == {"glu", "gcu"}
        assert state.get_local_player().coins == 100


class TestCastleLists:
    def test_only_the_truthy_lists_apply(self, state):
        # CastleUserData.parse_MIR: e.gcl&&parse_GCL(e.gcl), and the same for gkl, gml and gll
        payload: dict[str, Any] = {
            "gcl": gcl_payload([(1, "Main"), (3, "Taken")]),
            "gkl": {"AI": []},
            "gml": None,
            "gll": 0,
        }
        assert stamped(state, "mir", payload) == {"mir", "gcl", "gkl"}
        assert sorted(state.get_local_player().castles) == [1, 3]

    def test_a_faction_join_applies_kingdoms_then_events_then_castle_lists(self, state):
        # FJFCommand.executeCommand: parse_KPI(i.kpi), parse_SEI(i.sei), i.mir&&parse_MIR(i.mir); the kpi's
        # fki comes before the sei that starts the Battle for Berimond, so it finds no event to keep it on
        payload = {
            "FID": 1,
            "kpi": {"UL": [{"KID": 10, "U": 1, "C": 0}], "fki": FKI},
            "sei": {"E": [{"EID": 3, "RS": 600, "UL": 1}]},
            "mir": {"gcl": {"C": [*PLAYER["gcl"]["C"], *gcl_payload([(9, "Camp")], kingdom=10)["C"]]}},
        }
        assert stamped(state, "fjf", payload) == {"fjf", "kpi", "sei", "gcl"}
        assert state.get_kingdoms().kingdom(Kingdom.BERIMOND).is_unlocked
        event = state.get_event(Event.BATTLE_FOR_BERIMOND)
        assert event is not None and event.kingdom_status is None
        assert sorted(state.get_local_player().castles) == [1, 9]

    @pytest.mark.parametrize("castle_lists", [{}, {"mir": None}, {"mir": 0}])
    def test_a_faction_join_without_events_or_castle_lists(self, state, castle_lists):
        assert stamped(state, "fjf", {"FID": 1, "kpi": {"UL": []}, **castle_lists}) == {"fjf", "kpi"}
        assert sorted(state.get_local_player().castles) == [1]


class TestSpyScreen:
    def test_applies_the_protection_of_its_map_read(self, state):
        # CastleSpyData.parse_SSI: parse_UAP(e.gaa.uap)
        payload = {"GC": 0, "AS": 1, "gaa": {"AI": [], "OI": [], "uap": UAP}}
        assert stamped(state, "ssi", payload) == {"ssi", "uap"}
        assert state.get_local_player().beginner_protection[2] is False

    def test_a_null_protection_is_still_stamped(self, state):
        assert stamped(state, "ssi", {"gaa": {"uap": None}}) == {"ssi", "uap"}

    def test_an_unreadable_reply_applies_nothing(self, state, caplog):
        assert stamped(state, "ssi", {"gaa": {"uap": {"KID": "far"}}}) == {"ssi"}
        assert "a spy screen" in caplog.text

    def test_without_a_map_read_only_the_reply_is_stamped(self, state):
        assert stamped(state, "ssi", {"GC": 0, "AS": 1}) == {"ssi"}


class TestShadyLadySkip:
    def test_applies_its_coins_then_events(self, state):
        # BSTCommand.executeCommand: parseGCU(i.gcu), then parse_SEI(i.sei)
        payload = {"gcu": {"C1": 120, "C2": 30}, "sei": {"E": [{"EID": 25, "RS": 600}]}}
        assert stamped(state, "bst", payload) == {"bst", "gcu", "sei"}
        assert state.get_local_player().rubies == 30
        assert state.get_event(25) is not None

    def test_coins_that_are_no_object_are_neither_applied_nor_stamped(self, state):
        assert stamped(state, "bst", {"gcu": None}) == {"bst"}
        assert state.get_local_player().coins == 100

    def test_unreadable_events_are_logged_and_the_coins_still_apply(self, state, caplog):
        assert stamped(state, "bst", {"gcu": {"C1": 1}, "sei": "junk"}) == {"bst", "gcu", "sei"}
        assert state.get_local_player().coins == 1
        assert "Could not read the events login section" in caplog.text


class TestMineCollect:
    def test_applies_its_mines_then_coins(self, state):
        # CMRCommand.executeCommand: parse_GSM(i.gsm), then parseGCU(i.gcu)
        assert stamped(state, "cmr", {"gsm": MINES, "gcu": {"C1": 350}}) == {"cmr", "gsm", "gcu"}
        assert state.get_local_player().coins == 350

    def test_coins_that_are_no_object_are_neither_applied_nor_stamped(self, state):
        assert stamped(state, "cmr", {"gsm": MINES, "gcu": None}) == {"cmr", "gsm"}


class TestAlliance:
    def test_an_automatic_join_applies_the_membership_then_the_alliance(self, state):
        # AJACommand.executeCommand: parse_GAL(o.gal), then parseAllianceInfo(o.A)
        payload = {"gal": {"AID": 301, "R": 0, "AN": "Guild"}, "A": {"AID": 301, "N": "Guild"}}
        assert stamped(state, "aja", payload) == {"aja", "gal", "ain"}
        own = state.get_own_alliance()
        assert own is not None and own.alliance_id == 301 and own.name == "Guild"

    def test_a_membership_reply_applies_the_membership_then_the_alliance(self, state):
        # JOACommand / AAICommand: parse_GAL(gal), then parseAllianceInfo(A)
        before = state.get_packet_times()
        state.apply_membership_response(
            {"gal": {"AID": 301, "R": 0}, "A": {"AID": 301, "N": "Guild"}},
            membership_revision=state.membership_revision,
        )
        changed = {kind for kind, at in state.get_packet_times().items() if before.get(kind) != at}
        assert changed == {"gal", "ain"}
        own = state.get_own_alliance()
        assert own is not None and own.name == "Guild"

    def test_a_membership_reply_with_only_the_membership(self, state):
        # AASCommand.executeCommand: o.gal&&parse_GAL(o.gal)
        state.apply_membership_response({"gal": {"AID": 301, "R": 0}}, membership_revision=state.membership_revision)
        assert state.get_local_player().alliance_id == 301
        assert state.get_own_alliance() is None

    @pytest.mark.parametrize(("payload", "expected"), [({"gal": {"AID": -1}}, {"aqi", "gal"}), ({}, {"aqi"})])
    def test_leaving_applies_the_membership_it_carries(self, state, payload, expected):
        # AQICommand.executeCommand: resetHistory, parse_GAL(i.gal), resetMyAlliance
        assert stamped(state, "aqi", payload) == expected

    def test_leaving_stamps_a_null_membership(self, state):
        assert stamped(state, "aqi", {"gal": None}) == {"aqi", "gal"}


class TestLoginData:
    def test_every_stamped_section_is_a_login_section(self):
        assert (
            set(_TRACKED_SECTIONS) <= LoginDataResponse.model_validate(dict.fromkeys(_TRACKED_SECTIONS)).sent_sections
        )

    def test_sections_built_from_models_count_as_sent(self):
        login = LoginDataResponse(protection=None)
        assert (login.sent_sections, login.unread_sections) == ({"uap"}, set())

    @pytest.mark.parametrize("details", [None, 0])
    def test_falsy_castle_details_are_stamped(self, details):
        state = GameState()
        assert "dcl" in stamped(state, "gbd", {**PLAYER, "dcl": details})

    def test_unreadable_castle_details_are_not(self):
        state = GameState()
        assert "dcl" not in stamped(state, "gbd", {**PLAYER, "dcl": "junk"})

    def test_messages_read_from_the_login_count_are_not_stamped_as_mcd(self):
        # GBDCommand.exec: parse_MCD(n.mcd ? n.mcd : n)
        state = GameState()
        assert "mcd" not in stamped(state, "gbd", {**PLAYER, "MTC": {"1": 3}})
        assert state.get_messages_sent_today() is not None


class TestReplies:
    def test_a_reply_applies_and_stamps_the_sections_it_carries(self, state):
        payload = {"gcu": {"C1": 60}, "kpi": {"UL": [{"KID": 2, "U": 1, "C": 0}]}, "txi": None}
        assert stamped(state, "kut", payload) == {"gcu", "kpi"}
        assert state.get_local_player().coins == 60

    def test_a_reply_applies_the_decoration_storages_it_carries(self, state):
        stamped(state, "sob", {"OID": 9, "sin": [STORAGE]})
        assert list(state.get_decoration_storages()) == [1]
