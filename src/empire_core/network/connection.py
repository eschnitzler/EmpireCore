import asyncio
import logging
import aiohttp
from typing import Optional, Dict, Set, Callable, Awaitable, Tuple
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
        
        # Global callback
        self.packet_handler: Optional[Callable[[Packet], Awaitable[None]]] = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    @handle_errors(log_msg="Connection failed", cleanup_method="_close_resources")
    async def connect(self):
        if self.connected:
            return

        logger.info(f"Connecting to {self.url}...")
        self._session = aiohttp.ClientSession()
        # If ws_connect fails, the decorator catches it, logs, runs cleanup, and re-raises
        self._ws = await self._session.ws_connect(self.url)
        self._read_task = asyncio.create_task(self._read_loop())
        logger.info("Connected.")

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
                    fut.cancel()
        self._waiters.clear()

    async def send(self, data: bytes | str):
        if not self.connected:
            raise RuntimeError("Not connected")
        
        if isinstance(data, bytes):
            data = data.decode('utf-8')
            
        if data.endswith('\x00'):
             data = data[:-1]
            
        await self._ws.send_str(data)

    def create_waiter(self, cmd_id: str, predicate: Optional[Callable[[Packet], bool]] = None) -> asyncio.Future:
        if not self.connected:
             raise RuntimeError("Cannot wait for packet when not connected")

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        
        if cmd_id not in self._waiters:
            self._waiters[cmd_id] = set()
        
        if predicate is None:
            predicate = lambda p: True
            
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

    async def wait_for(self, cmd_id: str, predicate: Optional[Callable[[Packet], bool]] = None, timeout: float = 5.0) -> Packet:
        fut = self.create_waiter(cmd_id, predicate)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for command '{cmd_id}'")

    @handle_errors(log_msg="Read loop error", ignore=(asyncio.CancelledError,))
    async def _read_loop(self):
        logger.debug("Read loop started.")
        if not self._ws: return

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._process_message(msg.data.encode('utf-8'))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._process_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                     logger.error('WS connection closed with exception %s', self._ws.exception())
                     break
        finally:
            logger.warning("Connection closed.")

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