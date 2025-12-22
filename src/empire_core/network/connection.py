import asyncio
import logging
from typing import Awaitable, Callable, Dict, Optional, Set, Tuple, Union

import aiohttp

from empire_core.protocol.packet import Packet
from empire_core.utils.decorators import handle_errors

logger = logging.getLogger(__name__)


class SFSConnection:
    """
    Manages the WebSocket connection to the SmartFoxServer.
    Handles async reading, writing, and packet dispatching.
    """

    def __init__(self, url: str):
        self.url = url
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._read_task: Optional[asyncio.Task] = None

        # Waiters: cmd_id -> Set of (Future, Predicate)
        self._waiters: Dict[str, Set[Tuple[asyncio.Future, Callable[[Packet], bool]]]] = {}

        # Callbacks
        self.packet_handler: Optional[Callable[[Packet], Awaitable[None]]] = None
        self.on_close: Optional[Callable[[], Awaitable[None]]] = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    @handle_errors(log_msg="Connection failed", cleanup_method="_close_resources")
    async def connect(self):
        if self.connected:
            return

        logger.info(f"Connecting to {self.url}...")
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(self.url, heartbeat=30.0)
            self._read_task = asyncio.create_task(self._read_loop())
            logger.info("Connected.")
        except Exception as e:
            await self._close_resources()
            raise e

    async def disconnect(self):
        logger.info("Disconnecting...")
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        await self._close_resources()
        self._cancel_all_waiters()
        logger.info("Disconnected.")

    async def _close_resources(self):
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None

    def _cancel_all_waiters(self):
        for waiters in self._waiters.values():
            for fut, _ in waiters:
                if not fut.done():
                    fut.set_exception(asyncio.CancelledError("Connection closed"))
        self._waiters.clear()

    async def send(self, data: Union[bytes, str]):
        if not self.connected:
            raise RuntimeError("Not connected")

        if self._ws is None:
            raise RuntimeError("WebSocket not initialized")

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        if data.endswith("\x00"):
            data = data[:-1]

        try:
            await self._ws.send_str(data)
        except Exception as e:
            logger.error(f"Error sending data: {e}")
            await self.disconnect()
            raise e

    def create_waiter(self, cmd_id: str, predicate: Optional[Callable[[Packet], bool]] = None) -> asyncio.Future:
        if not self.connected:
            # We don't raise here because we might be in the middle of reconnecting
            # and want to set up a waiter for the next connection.
            # But usually it's safer to ensure we are connected.
            pass

        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        if cmd_id not in self._waiters:
            self._waiters[cmd_id] = set()

        if predicate is None:

            def predicate(p):
                return True

        entry = (fut, predicate)
        self._waiters[cmd_id].add(entry)

        def _cleanup(_):
            if cmd_id in self._waiters:
                try:
                    self._waiters[cmd_id].remove(entry)
                    if not self._waiters[cmd_id]:
                        del self._waiters[cmd_id]
                except KeyError:
                    pass

        fut.add_done_callback(_cleanup)
        return fut

    async def wait_for(
        self,
        cmd_id: str,
        predicate: Optional[Callable[[Packet], bool]] = None,
        timeout: float = 5.0,
    ) -> Packet:
        fut = self.create_waiter(cmd_id, predicate)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            from empire_core.exceptions import TimeoutError

            raise TimeoutError(f"Timed out waiting for command '{cmd_id}'")

    async def _read_loop(self):
        logger.debug("Read loop started.")
        if not self._ws:
            return

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._process_message(msg.data.encode("utf-8"))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._process_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WS connection closed with exception %s", self._ws.exception())
                    break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    break
        except Exception as e:
            logger.error(f"Error in read loop: {e}")
        finally:
            logger.warning("Connection lost.")
            await self._close_resources()
            self._cancel_all_waiters()
            if self.on_close:
                # Wrap in a coroutine to satisfy mypy
                async def _trigger_close():
                    if self.on_close:
                        await self.on_close()

                asyncio.create_task(_trigger_close())

    @handle_errors(log_msg="Failed to parse packet", re_raise=False)
    async def _process_message(self, data: bytes):
        packet = Packet.from_bytes(data)
        await self._dispatch_packet(packet)

    @handle_errors(log_msg="Error dispatching packet", re_raise=False)
    async def _dispatch_packet(self, packet: Packet):
        # 1. Notify Waiters
        if packet.command_id and packet.command_id in self._waiters:
            current_waiters = list(self._waiters[packet.command_id])
            for fut, predicate in current_waiters:
                if not fut.done():
                    try:
                        if predicate(packet):
                            fut.set_result(packet)
                    except Exception as e:
                        logger.error(f"Error in waiter predicate: {e}")

        # 2. Global Handler
        if self.packet_handler:
            await self.packet_handler(packet)
