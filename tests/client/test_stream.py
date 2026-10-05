"""EmpireClient.listen: the callbacks as an asyncio stream (no real socket)."""

from __future__ import annotations

import ast
import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from typing_extensions import Unpack, assert_type

import empire_core
from empire_core.alliance.models.chat import AllianceChatMessageResponse
from empire_core.client.client import EmpireClient
from empire_core.client.stream import Args, ClientEvent, EventStream, callback_sources
from empire_core.exceptions import EventStreamOverflowError
from empire_core.movements.tracked import Movement
from tests.client.test_disconnect import drop
from tests.service_helpers import xt_packet
from tests.state.state_helpers import arrive, gam_payload, login, wait_for


def chat(text: str):
    return xt_packet("acm", {"CM": {"PN": "LeaderGuy", "MT": text, "PID": 7001}})


@pytest.fixture
def client() -> Iterator[EmpireClient]:
    client = EmpireClient(username="user", password="pass")
    login(client.state)
    yield client
    client.close()


async def take(stream: EventStream[Unpack[Args]], count: int) -> list[ClientEvent[Unpack[Args]]]:
    return [await asyncio.wait_for(stream.__anext__(), 2) for _ in range(count)]


async def settle(client: EmpireClient) -> None:
    """Let every queued callback run and its event reach the loop."""
    while client.state.callback_queue_depth:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)


class TestSources:
    def test_every_remove_callback_in_the_package_has_its_registration_streamed(self, client):
        removers = [
            node.name.removeprefix("remove_").removesuffix("_callback")
            for path in empire_core.__path__
            for file in Path(path).rglob("*.py")
            for node in ast.walk(ast.parse(file.read_text()))
            if isinstance(node, ast.FunctionDef) and node.name.startswith("remove_") and node.name.endswith("_callback")
        ]

        assert set(callback_sources(client)) == set(removers)
        assert len(removers) == len(set(removers))

    def test_every_public_registration_in_the_package_has_its_remove_callback(self):
        not_callback_registrations = {
            ("BaseService", "on_response"): "a command's response handler, kept for the service's lifetime",
        }
        classes = [
            node
            for path in empire_core.__path__
            for file in Path(path).rglob("*.py")
            for node in ast.walk(ast.parse(file.read_text()))
            if isinstance(node, ast.ClassDef)
        ]
        without_remover: set[tuple[str, str]] = set()
        for cls in classes:
            methods = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
            without_remover.update(
                (cls.name, method)
                for method in methods
                if method.startswith("on_") and f"remove_{method.removeprefix('on_')}_callback" not in methods
            )

        assert without_remover == set(not_callback_registrations)

    def test_response_handlers_are_not_a_source(self, client):
        assert "response" not in callback_sources(client)


class TestDelivery:
    def test_events_of_state_and_services_reach_the_loop_in_packet_order(self, client):
        async def scenario():
            async with client.listen() as events:
                client._on_packet(xt_packet("gam", gam_payload(100)))
                client._on_packet(chat("hi"))
                client._on_packet(xt_packet("gam", gam_payload(101)))
                return await take(events, 3)

        got = asyncio.run(scenario())

        assert [event.name for event in got] == ["incoming_attack", "chat_message", "incoming_attack"]
        assert [event.args[0].movement_id for event in (got[0], got[2])] == [100, 101]
        assert got[1].args[0].decoded_text == "hi"

    def test_a_movement_event_carries_the_id_and_the_movement(self, client):
        async def scenario():
            async with client.listen(client.state.on_movement_arrived) as events:
                client._on_packet(xt_packet("gam", gam_payload(100)))
                arrive(client.state, 100)
                return await take(events, 1)

        (event,) = asyncio.run(scenario())

        assert event.name == "movement_arrived"
        movement_id, movement = event.args
        assert movement_id == 100
        assert isinstance(movement, Movement)

    def test_sources_pick_the_registrations_streamed(self, client):
        async def scenario():
            async with client.listen(client.alliance.on_chat_message) as events:
                client._on_packet(xt_packet("gam", gam_payload(100)))
                client._on_packet(chat("only me"))
                await settle(client)
                return await take(events, 1), events._queue.empty()

        (event,), drained = asyncio.run(scenario())

        assert event.name == "chat_message"
        assert drained

    def test_a_method_that_is_not_a_registration_is_refused(self, client):
        async def scenario():
            client.listen(client.alliance.send_chat)

        with pytest.raises(ValueError, match="not callback registrations"):
            asyncio.run(scenario())

    def test_listening_needs_a_running_loop(self, client):
        with pytest.raises(RuntimeError):
            client.listen()

    def test_a_dropped_session_is_an_event_and_the_stream_keeps_listening(self, client):
        async def scenario():
            async with client.listen(client.on_disconnect, client.alliance.on_chat_message) as events:
                await asyncio.to_thread(drop, client)
                client._on_packet(chat("back"))
                return await take(events, 2)

        got = asyncio.run(scenario())

        assert [(event.name, event.args) for event in got[:1]] == [("disconnect", ())]
        assert got[1].name == "chat_message"


SERVICE_PUSHES = {
    "chat_message": chat("hi"),
    "help_update": xt_packet("ahd", {"LID": 1}),
    "skill_list": xt_packet("skl", {"SID": [3]}),
    "new_messages": xt_packet("sne", {"MSG": [[501, 1, "Hello", "Sender", 4242, 40, 1, 0, 0]]}),
}


class TestTyping:
    def test_a_stream_of_one_registration_types_its_events_as_the_callback_parameters(self, client: EmpireClient):
        async def scenario():
            assert_type(client.listen(client.state.on_incoming_attack_updated), EventStream[Movement, Movement])
            assert_type(client.listen(client.alliance.on_chat_message), EventStream[AllianceChatMessageResponse])
            assert_type(client.listen(client.on_disconnect), "EventStream[()]")
            assert_type(client.listen(client.state.on_occupation_started), EventStream[Movement])
            assert_type(client.listen(client.state.on_occupation_updated), EventStream[Movement, Movement])
            assert_type(client.listen(client.state.on_occupation_ended), EventStream[Movement, bool])
            async with client.listen(client.state.on_incoming_attack) as attacks:
                client._on_packet(xt_packet("gam", gam_payload(100)))
                (attack,) = await take(attacks, 1)
            (movement,) = assert_type(attack, ClientEvent[Movement]).args
            return movement

        assert asyncio.run(scenario()).movement_id == 100


class TestSieges:
    def test_a_siege_streams_as_its_own_event(self, client):
        async def scenario():
            async with client.listen(client.state.on_occupation_started) as occupations:
                client._on_packet(xt_packet("gam", gam_payload(100, movement_type=5)))
                (occupation,) = await take(occupations, 1)
            return occupation

        occupation = asyncio.run(scenario())

        assert occupation.name == "occupation_started"
        assert occupation.args[0].is_occupation

    def test_an_ended_occupation_streams_with_whether_it_was_captured(self, client: EmpireClient):
        async def scenario():
            async with client.listen(client.state.on_occupation_ended) as ended:
                client._on_packet(xt_packet("gam", gam_payload(100, movement_type=5)))
                client._on_packet(xt_packet("mrm", {"MID": 100}))
                (event,) = await take(ended, 1)
            assert event.name == "occupation_ended"
            return assert_type(event, ClientEvent[Movement, bool]).args

        movement, captured = asyncio.run(scenario())

        assert movement.movement_id == 100
        assert captured is False


class TestServiceCallbacks:
    @pytest.mark.parametrize("name", list(SERVICE_PUSHES))
    def test_a_stream_closing_mid_push_does_not_skip_another_callback(self, client, name):
        register = callback_sources(client)[name].register
        inside = threading.Event()
        closed = threading.Event()
        ran: list[str] = []

        def slow(_):
            ran.append("slow")
            inside.set()
            closed.wait(2)

        async def scenario():
            stream = client.listen(register)
            async with stream:
                register(slow)
                register(lambda _: ran.append("after"))
                receive = threading.Thread(target=client._on_packet, args=(SERVICE_PUSHES[name],))
                receive.start()
                await asyncio.to_thread(inside.wait, 2)
            closed.set()
            await asyncio.to_thread(receive.join, 2)

        asyncio.run(scenario())

        assert ran == ["slow", "after"]


class TestEnding:
    def test_a_stream_not_entered_refuses_iteration_and_does_not_listen(self, client):
        async def scenario():
            events = client.listen(client.alliance.on_chat_message)
            assert client.alliance._chat_callbacks == []
            with pytest.raises(RuntimeError, match="async with"):
                await events.__anext__()

        asyncio.run(scenario())

    def test_a_stream_is_entered_once(self, client):
        async def scenario():
            events = client.listen(client.alliance.on_chat_message)
            async with events:
                pass
            with pytest.raises(RuntimeError, match="entered once"):
                await events.__aenter__()

        asyncio.run(scenario())
        assert client.alliance._chat_callbacks == []

    def test_leaving_the_block_unsubscribes_and_a_second_close_is_harmless(self, client):
        async def scenario():
            async with client.listen() as events:
                pass
            events.close()
            return events

        events = asyncio.run(scenario())

        assert client.state._attack_listeners.announced == []
        assert client.state._movement_arrived_callbacks == []
        assert client.alliance._chat_callbacks == []
        assert client._streams == set()
        assert events._subscribed == []

    def test_a_stream_keeps_listening_across_close_and_the_next_session(self, client):
        async def scenario():
            async with client.listen() as events:
                client._on_packet(chat("before"))
                before = await take(events, 1)
                client.close()
                executor_after_close = client.state._callback_executor
                login(client.state)
                client._on_packet(chat("after"))
                after = await take(events, 1)
                return before + after, executor_after_close, events._ending

        got, executor_after_close, ending = asyncio.run(scenario())

        assert [event.args[0].decoded_text for event in got] == ["before", "after"]
        assert executor_after_close is None
        assert client.state._callback_executor is not None
        assert not ending

    def test_close_streams_after_close_ends_the_stream_without_a_callback_thread(self, client):
        async def scenario():
            async with client.listen(client.alliance.on_chat_message) as events:
                client._on_packet(chat("last"))
                await settle(client)
                client.close()
                client.close_streams()
                return [event async for event in events]

        got = asyncio.run(asyncio.wait_for(scenario(), 2))

        assert [event.args[0].decoded_text for event in got] == ["last"]
        assert client.state._callback_executor is None
        assert client.alliance._chat_callbacks == []

    def test_close_streams_ends_every_stream_and_keeps_the_client(self, client):
        async def scenario():
            async with client.listen(client.alliance.on_chat_message) as chats, client.listen() as everything:
                client._on_packet(chat("last"))
                client.close_streams()
                return [event async for event in chats], [event async for event in everything]

        chats, everything = asyncio.run(asyncio.wait_for(scenario(), 2))

        assert [event.name for event in chats] == ["chat_message"]
        assert [event.name for event in everything] == ["chat_message"]
        assert client.alliance._chat_callbacks == []
        assert client._streams == set()

    def test_a_full_stream_stops_listening_and_says_so_after_the_events_it_holds(self, client):
        async def scenario():
            async with client.listen(client.alliance.on_chat_message, maxsize=1) as events:
                client._on_packet(chat("one"))
                client._on_packet(chat("two"))
                await settle(client)
                first = await take(events, 1)
                with pytest.raises(EventStreamOverflowError):
                    await events.__anext__()
                return first

        (event,) = asyncio.run(scenario())

        assert event.args[0].decoded_text == "one"
        assert client.alliance._chat_callbacks == []

    def test_a_stream_whose_loop_is_gone_unsubscribes_on_the_next_event(self, client):
        async def scenario():
            await client.listen(client.alliance.on_chat_message).__aenter__()

        asyncio.run(scenario())
        client._on_packet(chat("nobody reads this"))

        assert wait_for(lambda: client.alliance._chat_callbacks == [])
