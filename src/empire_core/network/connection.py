"""
Synchronous WebSocket connection for EmpireCore.

Uses websocket-client library with a dedicated receive thread.
Designed to work well with Discord.py by not competing for the event loop.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import websocket

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError, NetworkError
from empire_core.protocol.errors import GGEError
from empire_core.protocol.packet import Packet

logger = logging.getLogger(__name__)

# Commands that use XT field 4 for data instead of error codes
NON_ERROR_COMMANDS = {"rlu", "core_pol"}

# Fallback zone for keepalive pings when the client doesn't inject one.
# The client always passes keepalive_zone, so this only applies to a bare
# Connection; kept here so the network layer needn't import the protocol layer.
DEFAULT_KEEPALIVE_ZONE = "EmpireEx_21"

# Recv poll interval; also the socket timeout, so sends blocking longer
# than this raise. Keep small so _running is checked promptly on shutdown.
SOCKET_POLL_TIMEOUT = 1.0

KEEPALIVE_INTERVAL = 60.0


@dataclass
class ResponseWaiter:
    """A waiter for a specific command response."""

    event: threading.Event = field(default_factory=threading.Event)
    result: Packet | None = None
    error: Exception | None = None


class Connection:
    """
    Synchronous WebSocket connection with threaded message routing.

    Features:
    - Request/response pattern via waiters (consumed on match)
    - Pub/sub pattern via subscribers (broadcast to all)
    - Automatic keepalive thread
    - Thread-safe operations

    Correlation constraint (important):
        Responses are matched to waiters by *command id only*, FIFO - there is
        no payload-level matching. Two consequences follow:

        1. Two threads issuing the same command concurrently can receive each
           other's responses (the oldest waiter takes the first packet with
           that command id).
        2. An unsolicited server push (chat, movement update, ...) satisfies a
           pending waiter for the same command id, and is then consumed:
           subscribers still see it, but the request gets the push instead of
           its own answer.

        So serialise same-command requests per connection, and prefer
        :meth:`subscribe` over :meth:`request` for command ids the server also
        pushes on its own. See ``TestCorrelationIsFifo`` in
        ``tests/test_connection.py``, which pins this behaviour.
    """

    def __init__(self, url: str, keepalive_zone: str | None = None):
        self.url = url
        self.keepalive_zone = keepalive_zone
        self.ws: websocket.WebSocket | None = None

        self._running = False
        self._closing = False
        # Incremented on every connect; threads from a previous connection
        # notice the mismatch and exit without touching the new session.
        self._generation = 0
        self._recv_thread: threading.Thread | None = None
        self._keepalive_thread: threading.Thread | None = None

        # Request/response waiters: cmd_id -> ResponseWaiter
        # These are consumed when matched (one response per waiter)
        self._waiters: dict[str, list[ResponseWaiter]] = {}
        self._waiters_lock = threading.Lock()

        # Pub/sub subscribers: cmd_id -> list of callbacks
        # These receive copies of all matching packets
        self._subscribers: dict[str, list[Callable[[Packet], None]]] = {}
        self._subscribers_lock = threading.Lock()

        # Global packet handler (for state updates, etc.)
        self.on_packet: Callable[[Packet], None] | None = None

        # Called only on unexpected connection loss, not on disconnect().
        self.on_disconnect: Callable[[], None] | None = None

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        return self.ws is not None and self.ws.connected and self._running

    def connect(self, timeout: float = 10.0) -> None:
        """
        Connect to the WebSocket server.

        Args:
            timeout: Connection timeout in seconds

        Raises:
            NetworkError: The handshake failed (the underlying
                websocket/socket error is chained as ``__cause__``)
        """
        if self.connected:
            logger.warning("Already connected")
            return

        logger.debug(f"Connecting to {self.url}...")

        ws = websocket.WebSocket()
        ws.settimeout(timeout)

        try:
            ws.connect(self.url)
            # After the handshake, drop to the poll timeout used by the
            # recv loop (and, unavoidably, by sends on the shared socket).
            ws.settimeout(SOCKET_POLL_TIMEOUT)

            self.ws = ws
            self._running = True
            self._closing = False
            self._generation += 1
            generation = self._generation

            self._recv_thread = threading.Thread(
                target=self._recv_loop,
                args=(ws, generation),
                name="EmpireCore-Recv",
                daemon=True,
            )
            self._recv_thread.start()

            self._keepalive_thread = threading.Thread(
                target=self._keepalive_loop,
                args=(generation,),
                name="EmpireCore-Keepalive",
                daemon=True,
            )
            self._keepalive_thread.start()

            logger.debug("Connected successfully")

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            try:
                ws.close()
            except Exception:
                pass
            self.ws = None
            # Never let raw websocket-client/socket errors escape the public
            # API: callers guarding with `except EmpireError` (or NetworkError,
            # as send() already raises) must catch connect failures too.
            raise NetworkError(f"Connection to {self.url} failed: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from the server and cleanup resources."""
        if not self._running:
            return

        logger.debug("Disconnecting...")
        self._closing = True
        self._running = False

        # Cancel all waiters
        self._cancel_all_waiters()

        # Close websocket
        self._cleanup()

        # Wait for threads to finish (unless called from one of them,
        # e.g. from inside a subscriber callback on the recv thread)
        current = threading.current_thread()
        if self._recv_thread and self._recv_thread is not current and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)
        if self._keepalive_thread and self._keepalive_thread is not current and self._keepalive_thread.is_alive():
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
            NetworkError: If not connected or the send fails
        """
        # Remove null terminator if present (we'll add it)
        if data.endswith("\x00"):
            data = data[:-1]

        ws = self.ws
        if ws is None or not self._running:
            raise NetworkError("Not connected")

        try:
            ws.send(data)
            logger.debug(f"Sent: {data[:100]}...")
        except Exception as e:
            logger.error(f"Send failed: {e}")
            raise NetworkError(f"Send failed: {e}") from e

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        """
        Send data and wait for the response to ``cmd_id``.

        The waiter is registered *before* the data is sent, so a response
        arriving immediately cannot be lost to a registration race.

        Correlation is by ``cmd_id`` only, FIFO: concurrent requests for the
        same command id can be answered out of order, and a server push with
        that command id satisfies this call. See the class docstring.

        Raises:
            EmpireTimeoutError: No response within ``timeout``
            ConnectionClosedError: Connection dropped while waiting
            NetworkError: The send itself failed
        """
        waiter = self.create_waiter(cmd_id)
        try:
            self.send(data)
        except Exception:
            self.cancel_waiter(cmd_id, waiter)
            raise
        return self.wait_for_result(cmd_id, waiter, timeout=timeout)

    def create_waiter(self, cmd_id: str) -> ResponseWaiter:
        waiter = ResponseWaiter()
        with self._waiters_lock:
            if cmd_id not in self._waiters:
                self._waiters[cmd_id] = []
            self._waiters[cmd_id].append(waiter)
        return waiter

    def wait_for_result(self, cmd_id: str, waiter: ResponseWaiter, timeout: float = 5.0) -> Packet:
        try:
            if waiter.event.wait(timeout=timeout):
                if waiter.error:
                    raise waiter.error
                if waiter.result:
                    return waiter.result
                raise ConnectionClosedError("Waiter completed without result")
            else:
                raise EmpireTimeoutError(f"Timeout waiting for '{cmd_id}'")
        finally:
            self.cancel_waiter(cmd_id, waiter)

    def cancel_waiter(self, cmd_id: str, waiter: ResponseWaiter) -> None:
        with self._waiters_lock:
            if cmd_id in self._waiters:
                try:
                    self._waiters[cmd_id].remove(waiter)
                    if not self._waiters[cmd_id]:
                        del self._waiters[cmd_id]
                except ValueError:
                    pass

    def wait_for(
        self,
        cmd_id: str,
        timeout: float = 5.0,
    ) -> Packet:
        """
        Wait for a response with the given command ID.

        Note: only use this for server-pushed packets. For request/response
        round trips use :meth:`request`, which registers the waiter before
        sending.
        """
        waiter = self.create_waiter(cmd_id)
        return self.wait_for_result(cmd_id, waiter, timeout)

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

    def _recv_loop(self, ws: websocket.WebSocket, generation: int) -> None:
        """Background thread that receives and routes messages."""
        logger.debug("Receive loop started")

        while self._running and generation == self._generation:
            # Only socket-level failures are fatal to this loop; everything
            # about handling a single frame is contained below.
            try:
                data = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue  # Check _running and try again
            except websocket.WebSocketConnectionClosedException:
                if not self._closing:
                    logger.warning("Connection closed by server")
                break
            except (OSError, websocket.WebSocketException):
                if self._running and generation == self._generation:
                    logger.exception("Receive loop stopped by socket error")
                break
            except Exception:
                # Nothing else is expected out of recv(); still fatal, but log
                # it with the traceback so the cause is diagnosable.
                if self._running and generation == self._generation:
                    logger.exception("Unexpected error in receive loop")
                break

            if not data:
                continue

            # A single bad frame must not cost us the connection: parsing can
            # reject e.g. all-null or non-UTF-8 frames, and tearing the session
            # down forces a re-login that the game server rate-limits. Drop the
            # frame, keep the socket.
            try:
                raw = data if isinstance(data, bytes) else data.encode("utf-8")
                self._route_packet(Packet.from_bytes(raw))
            except Exception:
                logger.exception("Dropping frame that could not be parsed or routed")
                continue

        # If a newer connection took over, this thread must not touch
        # shared state - the new session owns it now.
        if generation != self._generation:
            logger.debug("Receive loop superseded by newer connection")
            return

        was_closing = self._closing
        self._running = False
        self._cancel_all_waiters()

        if self.on_disconnect and not was_closing:
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

        # Log server errors (but exclude commands that use field 4 for data)
        # lli 453 is login cooldown, handled as exception in client
        if (
            not packet.is_xml
            and packet.error_code != 0
            and cmd_id not in NON_ERROR_COMMANDS
            and not (cmd_id == "lli" and packet.error_code == 453)
        ):
            error_name = GGEError.from_code(packet.error_code).name
            if packet.error_code == 21:
                logger.debug(f"Server error: {error_name} ({packet.error_code}) for command '{cmd_id}'")
            else:
                logger.error(f"Server error: {error_name} ({packet.error_code}) for command '{cmd_id}'")

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

        # Now dispatch outside of locks.
        # The global handler feeds GameState, so it runs before the waiter is woken:
        # otherwise a caller doing request(...) and then reading state can return
        # before the response it waited for has been applied.
        if self.on_packet:
            try:
                self.on_packet(packet)
            except Exception:
                logger.exception("Packet handler error")

        if waiter:
            waiter.result = packet
            waiter.event.set()

        if callbacks:
            for callback in callbacks:
                try:
                    callback(packet)
                except Exception:
                    logger.exception("Subscriber error")

    def _keepalive_loop(self, generation: int) -> None:
        """Background thread that sends keepalive pings."""
        logger.debug("Keepalive loop started")

        zone = self.keepalive_zone or DEFAULT_KEEPALIVE_ZONE

        def active() -> bool:
            return self._running and generation == self._generation

        while active():
            # Send keepalive every KEEPALIVE_INTERVAL seconds, waking up
            # once per second so shutdown is prompt.
            for _ in range(int(KEEPALIVE_INTERVAL)):
                if not active():
                    break
                time.sleep(1)

            if not active():
                break

            try:
                self.send(f"%xt%{zone}%pin%1%<RoundHouseKick>%")
                logger.debug("Sent keepalive ping")
            except Exception as e:
                if active():
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
                    waiter.error = ConnectionClosedError("Connection closed")
                    waiter.event.set()
            self._waiters.clear()
