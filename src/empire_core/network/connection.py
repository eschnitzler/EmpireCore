"""
Synchronous WebSocket connection for EmpireCore.

Uses websocket-client library with a dedicated receive thread.
Designed to work well with Discord.py by not competing for the event loop.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import websocket

from empire_core.exceptions import TimeoutError
from empire_core.protocol.packet import Packet

logger = logging.getLogger(__name__)


@dataclass
class ResponseWaiter:
    """A waiter for a specific command response."""

    event: threading.Event = field(default_factory=threading.Event)
    result: Optional[Packet] = None
    error: Optional[Exception] = None


class Connection:
    """
    Synchronous WebSocket connection with threaded message routing.

    Features:
    - Request/response pattern via waiters (consumed on match)
    - Pub/sub pattern via subscribers (broadcast to all)
    - Automatic keepalive thread
    - Thread-safe operations
    """

    def __init__(self, url: str):
        self.url = url
        self.ws: Optional[websocket.WebSocket] = None

        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._keepalive_thread: Optional[threading.Thread] = None

        # Request/response waiters: cmd_id -> ResponseWaiter
        # These are consumed when matched (one response per waiter)
        self._waiters: Dict[str, List[ResponseWaiter]] = {}
        self._waiters_lock = threading.Lock()

        # Pub/sub subscribers: cmd_id -> list of callbacks
        # These receive copies of all matching packets
        self._subscribers: Dict[str, List[Callable[[Packet], None]]] = {}
        self._subscribers_lock = threading.Lock()

        # Global packet handler (for state updates, etc.)
        self.on_packet: Optional[Callable[[Packet], None]] = None

        # Disconnect callback
        self.on_disconnect: Optional[Callable[[], None]] = None

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        return self.ws is not None and self.ws.connected and self._running

    def connect(self, timeout: float = 10.0) -> None:
        """
        Connect to the WebSocket server.

        Args:
            timeout: Connection timeout in seconds
        """
        if self.connected:
            logger.warning("Already connected")
            return

        logger.debug(f"Connecting to {self.url}...")

        self.ws = websocket.WebSocket()
        self.ws.settimeout(timeout)

        try:
            self.ws.connect(self.url)
            self._running = True

            # Start receive thread
            self._recv_thread = threading.Thread(
                target=self._recv_loop,
                name="EmpireCore-Recv",
                daemon=True,
            )
            self._recv_thread.start()

            # Start keepalive thread
            self._keepalive_thread = threading.Thread(
                target=self._keepalive_loop,
                name="EmpireCore-Keepalive",
                daemon=True,
            )
            self._keepalive_thread.start()

            logger.debug("Connected successfully")

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._cleanup()
            raise

    def disconnect(self) -> None:
        """Disconnect from the server and cleanup resources."""
        if not self._running:
            return

        logger.debug("Disconnecting...")
        self._running = False

        # Cancel all waiters
        self._cancel_all_waiters()

        # Close websocket
        self._cleanup()

        # Wait for threads to finish
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=2.0)

        logger.debug("Disconnected")

    def _cleanup(self) -> None:
        """Close websocket connection."""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

    def send(self, data: str) -> None:
        """
        Send data to the server.

        Args:
            data: String data to send

        Raises:
            RuntimeError: If not connected
        """
        if not self.connected:
            raise RuntimeError("Not connected")

        # Remove null terminator if present (we'll add it)
        if data.endswith("\x00"):
            data = data[:-1]

        try:
            if self.ws is None:
                raise RuntimeError("Not connected")
            self.ws.send(data)
            logger.debug(f"Sent: {data[:100]}...")
        except Exception as e:
            logger.error(f"Send failed: {e}")
            raise

    def send_bytes(self, data: bytes) -> None:
        """Send raw bytes to the server."""
        self.send(data.decode("utf-8"))

    def wait_for(
        self,
        cmd_id: str,
        timeout: float = 5.0,
    ) -> Packet:
        """
        Wait for a response with the given command ID.

        This is a blocking call that waits for a matching packet.
        The waiter is consumed when a match is found.

        Args:
            cmd_id: Command ID to wait for
            timeout: Timeout in seconds

        Returns:
            The matching Packet

        Raises:
            TimeoutError: If no response within timeout
            RuntimeError: If connection closed while waiting
        """
        waiter = ResponseWaiter()

        with self._waiters_lock:
            if cmd_id not in self._waiters:
                self._waiters[cmd_id] = []
            self._waiters[cmd_id].append(waiter)

        try:
            if waiter.event.wait(timeout=timeout):
                if waiter.error:
                    raise waiter.error
                if waiter.result:
                    return waiter.result
                raise RuntimeError("Waiter completed without result")
            else:
                raise TimeoutError(f"Timeout waiting for '{cmd_id}'")
        finally:
            # Clean up waiter
            with self._waiters_lock:
                if cmd_id in self._waiters:
                    try:
                        self._waiters[cmd_id].remove(waiter)
                        if not self._waiters[cmd_id]:
                            del self._waiters[cmd_id]
                    except ValueError:
                        pass

    def subscribe(self, cmd_id: str, callback: Callable[[Packet], None]) -> None:
        """
        Subscribe to packets with the given command ID.

        Unlike waiters, subscribers receive ALL matching packets
        and are not consumed.

        Args:
            cmd_id: Command ID to subscribe to
            callback: Function to call with matching packets
        """
        with self._subscribers_lock:
            if cmd_id not in self._subscribers:
                self._subscribers[cmd_id] = []
            self._subscribers[cmd_id].append(callback)

    def unsubscribe(self, cmd_id: str, callback: Callable[[Packet], None]) -> None:
        """Remove a subscriber."""
        with self._subscribers_lock:
            if cmd_id in self._subscribers:
                try:
                    self._subscribers[cmd_id].remove(callback)
                    if not self._subscribers[cmd_id]:
                        del self._subscribers[cmd_id]
                except ValueError:
                    pass

    def _recv_loop(self) -> None:
        """Background thread that receives and routes messages."""
        logger.debug("Receive loop started")

        while self._running:
            try:
                if not self.ws:
                    break

                # Set a timeout so we can check _running periodically
                self.ws.settimeout(1.0)

                try:
                    data = self.ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue  # Check _running and try again

                if not data:
                    continue

                # Parse packet
                if isinstance(data, bytes):
                    packet = Packet.from_bytes(data)
                else:
                    packet = Packet.from_bytes(data.encode("utf-8"))

                # Route the packet
                self._route_packet(packet)

            except websocket.WebSocketConnectionClosedException:
                logger.warning("Connection closed by server")
                break
            except Exception as e:
                if self._running:
                    logger.error(f"Error in receive loop: {e}")
                break

        # Connection lost
        self._running = False
        self._cancel_all_waiters()

        if self.on_disconnect:
            try:
                self.on_disconnect()
            except Exception as e:
                logger.error(f"Error in disconnect callback: {e}")

        logger.debug("Receive loop ended")

    def _route_packet(self, packet: Packet) -> None:
        """
        Route a packet to waiters and subscribers.

        Order:
        1. Check waiters (consumed on match)
        2. Notify subscribers (broadcast)
        3. Call global handler

        Uses copy-on-read pattern to minimize lock hold time.
        """
        cmd_id = packet.command_id

        waiter = None
        callbacks = None

        # Acquire locks briefly just to extract what we need
        if cmd_id:
            # Check waiters (request/response pattern)
            with self._waiters_lock:
                waiters_list = self._waiters.get(cmd_id)
                if waiters_list:
                    waiter = waiters_list.pop(0)
                    if not waiters_list:
                        del self._waiters[cmd_id]

            # Get subscriber callbacks (copy the list)
            with self._subscribers_lock:
                subs = self._subscribers.get(cmd_id)
                if subs:
                    callbacks = list(subs)

        # Now dispatch outside of locks
        if waiter:
            waiter.result = packet
            waiter.event.set()

        if callbacks:
            for callback in callbacks:
                try:
                    callback(packet)
                except Exception as e:
                    logger.error(f"Subscriber error: {e}")

        # Global handler
        if self.on_packet:
            try:
                self.on_packet(packet)
            except Exception as e:
                logger.error(f"Packet handler error: {e}")

    def _keepalive_loop(self) -> None:
        """Background thread that sends keepalive pings."""
        logger.debug("Keepalive loop started")

        try:
            from empire_core.protocol.models.base import DEFAULT_ZONE

            zone = DEFAULT_ZONE
        except ImportError:
            zone = "EmpireEx_21"

        while self._running:
            # Send keepalive every 60s
            # Server timeout is likely >60s, sending too often might be unnecessary
            for _ in range(60):
                if not self._running:
                    break
                time.sleep(1)

            if not self._running:
                break

            try:
                self.send(f"%xt%{zone}%pin%1%<RoundHouseKick>%")
                logger.debug("Sent keepalive ping")
            except Exception as e:
                if self._running:
                    logger.error(f"Keepalive failed: {e}")
                    # Don't break immediately, retry on next cycle if still running
                    # Only break if socket is explicitly closed
                    if not self.connected:
                        break

        logger.debug("Keepalive loop ended")

    def _cancel_all_waiters(self) -> None:
        """Cancel all pending waiters."""
        with self._waiters_lock:
            for waiters in self._waiters.values():
                for waiter in waiters:
                    waiter.error = RuntimeError("Connection closed")
                    waiter.event.set()
            self._waiters.clear()
