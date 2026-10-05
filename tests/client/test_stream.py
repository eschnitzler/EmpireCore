"""EmpireClient.listen: the callbacks as an asyncio stream (no real socket)."""

from __future__ import annotations

import ast
import asyncio
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

import empire_core
from empire_core.client.client import EmpireClient
from empire_core.client.stream import ClientEvent, EventStream, callback_sources
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


async def take(stream: EventStream, count: int) -> list[ClientEvent]:
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

        assert client.state._incoming_attack_callbacks == []
        assert client.state._movement_arrived_callbacks == []
        assert client.alliance._chat_callbacks == []
        assert client._streams == set()
        assert events._subscribed == []

    def test_closing_the_client_ends_the_stream_after_the_events_on_their_way(self, client):
        async def scenario():
            async with client.listen() as events:
                client._on_packet(chat("last"))
                client.close()
                return [event async for event in events]

        got = asyncio.run(asyncio.wait_for(scenario(), 2))

        assert [event.name for event in got] == ["chat_message"]
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
