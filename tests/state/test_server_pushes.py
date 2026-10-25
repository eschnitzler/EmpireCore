"""The server's lifecycle pushes: frozen food production (DTS), the shutdown warning (ssd), the events
shutting down (sde), the new day (kik), the joined castle moving (ghw), and the version check reply (vck)."""

import pytest

from empire_core.castle.models.updates import JoinedAreaMoved, NewDay
from empire_core.enums import Kingdom, Weekday
from empire_core.events.models import ShuttingDownEvents
from empire_core.gamedata import Event
from empire_core.messages.models import ServerShutdownWarning
from empire_core.player.models import FoodProductionStatus
from empire_core.protocol.auth import VersionCheckResponse
from empire_core.protocol.base import parse_response
from empire_core.protocol.packet import Packet
from empire_core.state.manager import GameState
from empire_core.state.models import JoinedArea
from tests.service_helpers import make_client, xt_packet
from tests.state.test_castle_pushes import jaa_payload, login


class TestFoodProduction:
    # CastleUserData.parse_DTS: e&&(this._foodFrozen=1==e.DTS)

    @pytest.mark.parametrize(("value", "frozen"), [(1, True), ("1", True), (0, False), (2, False)])
    def test_the_push_parses(self, value, frozen):
        status = parse_response("DTS", {"DTS": value})

        assert isinstance(status, FoodProductionStatus)
        assert status.frozen is frozen

    def test_the_login_section_and_the_push_set_it(self, state):
        assert state.get_food_production() is None

        state.update_from_packet("gbd", {"DTS": {"DTS": 1}})
        assert state.get_food_production() == FoodProductionStatus(frozen=True)

        state.update_from_packet("DTS", {"DTS": 0})
        assert state.get_food_production() == FoodProductionStatus(frozen=False)
        assert state.get_last_packet_time("DTS") is not None

    def test_a_null_section_and_a_refused_push_change_nothing(self, state):
        state.update_from_packet("gbd", {"DTS": {"DTS": 1}})

        state.update_from_packet("gbd", {"DTS": None})
        state.update_from_packet("DTS", {"DTS": 0}, error_code=1)

        assert state.get_food_production() == FoodProductionStatus(frozen=True)

    def test_the_service_reads_it_and_calls_back_for_the_section_and_the_push(self):
        client = make_client(state=GameState())
        seen: list[FoodProductionStatus] = []
        client.player.on_food_production(seen.append)

        client._on_packet(xt_packet("gbd", {"DTS": {"DTS": 1}}))
        client._on_packet(xt_packet("DTS", {"DTS": 0}))

        assert [status.frozen for status in seen] == [True, False]
        assert client.player.food_production == FoodProductionStatus(frozen=False)


class TestServerShutdown:
    def test_the_empty_push_reaches_the_callbacks(self):
        client = make_client()
        seen: list[ServerShutdownWarning] = []
        client.messages.on_server_shutdown(seen.append)

        client._on_packet(Packet.from_bytes(b"%xt%ssd%-1%0%"))

        assert len(seen) == 1
        assert isinstance(seen[0], ServerShutdownWarning)

    def test_a_refused_push_is_not_a_warning(self):
        client = make_client()
        seen: list[ServerShutdownWarning] = []
        client.messages.on_server_shutdown(seen.append)

        client._on_packet(Packet.from_bytes(b"%xt%ssd%-1%1%"))

        assert seen == []


class TestShuttingDownEvents:
    # CastleSpecialEventData.parse_SDE: a new map of the SD event ids each time

    def test_the_push_names_the_events(self):
        events = parse_response("sde", {"SD": [Event.FACTION, 999999]})

        assert isinstance(events, ShuttingDownEvents)
        assert events.event_ids == (Event.FACTION, 999999)

    def test_each_push_replaces_the_list(self, state):
        assert state.get_shutting_down_events() is None

        state.update_from_packet("sde", {"SD": [Event.FACTION, Event.POINT_EVENT]})
        state.update_from_packet("sde", {"SD": [Event.POINT_EVENT]})

        assert state.get_shutting_down_events() == ShuttingDownEvents(event_ids=(Event.POINT_EVENT,))
        assert state.get_last_packet_time("sde") is not None

    def test_an_unreadable_or_refused_push_changes_nothing(self, state):
        state.update_from_packet("sde", {"SD": [Event.FACTION]})

        state.update_from_packet("sde", {"raw": "x"})
        state.update_from_packet("sde", {"SD": []}, error_code=1)

        assert state.get_shutting_down_events() == ShuttingDownEvents(event_ids=(Event.FACTION,))

    def test_the_service_reads_it(self):
        client = make_client(state=GameState())
        client._on_packet(xt_packet("sde", {"SD": [Event.FACTION]}))

        assert client.events.shutting_down == ShuttingDownEvents(event_ids=(Event.FACTION,))


class TestNewDay:
    @pytest.mark.parametrize(
        ("value", "day"),
        [(2, Weekday.MONDAY), (2.0, Weekday.MONDAY), ("1", Weekday.SUNDAY), (2.5, None), ("x", None), (None, None)],
    )
    def test_the_push_names_the_day(self, value, day):
        new_day = parse_response("kik", {} if value is None else {"DOW": value})

        assert isinstance(new_day, NewDay)
        assert new_day.day_of_week == day

    def test_only_a_monday_resets_the_open_gate_counters(self, state):
        login(state, entry={"OGC": 2})

        state.update_from_packet("kik", {})
        state.update_from_packet("kik", {"DOW": Weekday.SUNDAY})
        assert state.get_castles()[0].open_gate_counter == 2

        state.update_from_packet("kik", {"DOW": Weekday.MONDAY})
        assert state.get_castles()[0].open_gate_counter == 0

    def test_a_float_monday_resets_and_a_fraction_does_not(self, state):
        login(state, entry={"OGC": 2})

        state.update_from_packet("kik", {"DOW": 2.5})
        assert state.get_castles()[0].open_gate_counter == 2

        state.update_from_packet("kik", {"DOW": 2.0})
        assert state.get_castles()[0].open_gate_counter == 0


class TestJoinedAreaMoved:
    # GHWCommand: activeArea&&changePosOfOwnArea(new Point(X, Y))

    def test_the_jaa_brings_the_position(self, state):
        state.update_from_packet("jaa", jaa_payload())

        assert state.get_joined_area() == JoinedArea(kingdom_id=Kingdom.GREEN, castle_id=1, x=10, y=20)

    def test_ghw_moves_the_joined_area_and_calls_back(self):
        client = make_client(state=GameState())
        seen: list[tuple[JoinedAreaMoved, JoinedArea | None]] = []
        client.castle.on_joined_area_moved(lambda moved: seen.append((moved, client.castle.joined_area)))
        client._on_packet(xt_packet("jaa", jaa_payload()))

        client._on_packet(xt_packet("ghw", {"X": 300, "Y": "400"}))

        area = client.castle.joined_area
        assert area is not None and (area.x, area.y, area.castle_id) == (300, 400, 1)
        assert seen == [(JoinedAreaMoved(x=300, y=400), area)]

    def test_without_a_joined_area_only_the_callback_runs(self):
        client = make_client(state=GameState())
        seen: list[JoinedAreaMoved] = []
        client.castle.on_joined_area_moved(seen.append)

        client._on_packet(xt_packet("ghw", {"X": 1, "Y": 2}))

        assert client.castle.joined_area is None
        assert seen == [JoinedAreaMoved(x=1, y=2)]

    def test_a_removed_callback_no_longer_fires(self):
        client = make_client(state=GameState())
        seen: list[JoinedAreaMoved] = []
        client.castle.on_joined_area_moved(seen.append)
        client.castle.on_joined_area_moved.remove(seen.append)

        client._on_packet(xt_packet("ghw", {"X": 1, "Y": 2}))

        assert seen == []

    def test_the_castle_list_keeps_its_position(self, state):
        # changePosOfOwnArea moves activeArea.areaInfo, a VO of its own, not the castle list's
        login(state)
        before = [(c.x, c.y) for c in state.get_castles()]
        state.update_from_packet("jaa", jaa_payload())

        state.update_from_packet("ghw", {"X": 300, "Y": 400})

        assert [(c.x, c.y) for c in state.get_castles()] == before

    def test_a_refused_push_changes_nothing(self):
        client = make_client(state=GameState())
        seen: list[JoinedAreaMoved] = []
        client.castle.on_joined_area_moved(seen.append)
        client._on_packet(xt_packet("jaa", jaa_payload()))

        client._on_packet(xt_packet("ghw", {"X": 300, "Y": 400}, error_code=1))

        area = client.castle.joined_area
        assert area is not None and (area.x, area.y) == (10, 20)
        assert seen == []


class TestVersionCheckReply:
    # CastleVCKCommand.executeCommand: the server's build is t[1], the first field after the status

    def test_the_build_is_the_first_field(self):
        packet = Packet.from_bytes(b"%xt%vck%1%0%1170001%")
        assert isinstance(packet.payload, dict)

        reply = parse_response("vck", packet.payload)

        assert reply == VersionCheckResponse(server_build="1170001")

    def test_a_reply_without_fields_has_no_build(self):
        packet = Packet.from_bytes(b"%xt%vck%1%2%")

        assert VersionCheckResponse.model_validate(packet.payload).server_build is None
