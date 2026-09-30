"""
The connection: a receive thread routes each packet to its waiter, its subscribers and state.

It uses websocket-client with its own receive and keepalive threads, so it
never competes with a host event loop.
"""

import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import websocket

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError, NetworkError, ReceiveThreadError
from empire_core.network.framing import FrameBuffer
from empire_core.protocol.base import NO_ROOM, build_command
from empire_core.protocol.errors import GGEError
from empire_core.protocol.packet import DegradedFrameCounts, Packet, degraded_frame_counts

logger = logging.getLogger(__name__)

_DATA_OPCODES = frozenset({websocket.ABNF.OPCODE_TEXT, websocket.ABNF.OPCODE_BINARY})

# Commands that use XT field 4 for data instead of error codes
NON_ERROR_COMMANDS = {"rlu", "core_pol"}

# Replies whose refusals the login turns into typed errors; logged at debug only.
LOGIN_REPLY_COMMANDS = frozenset({"lli", "vck"})

# Commands whose payload carries credentials (login, registration, social
# login). Their bodies are never logged - only the command id and frame size.
AUTH_COMMANDS = frozenset({"lli", "core_reg", "scp"})

# Longest frame prefix we are willing to log, kept as defense in depth on top
# of the redaction above.
LOG_FRAME_CHARS = 100

# Credential shapes to mask in frames whose command we do not recognize.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # XT/JSON payloads: {"PW": "hunter2"}. The value pattern must consume
    # escaped characters (\" and \\): with a plain [^"]* a password containing
    # a double-quote would leak its tail after the json.dumps-escaped \".
    (
        re.compile(r'("(?:PW|PWD|PASS|PASSWORD|TOKEN|SECRET|AUTH|LT|RCT)"\s*:\s*)"(?:\\.|[^"\\])*"', re.IGNORECASE),
        r'\1"<redacted>"',
    ),
    # SmartFox XML handshake: <pword><![CDATA[...]]></pword>
    (re.compile(r"(<pword>).*?(</pword>)", re.IGNORECASE | re.DOTALL), r"\1<redacted>\2"),
)

_XML_ACTION_RE = re.compile(r"""action=['"]([^'"]+)['"]""")


def _frame_command(frame: str) -> str | None:
    """Best-effort command id of an outbound frame, for logging decisions."""
    if frame.startswith("%xt%"):
        # %xt%<zone>%<command>%<request id>%<payload>%
        parts = frame.split("%")
        return parts[3] if len(parts) > 4 else None
    match = _XML_ACTION_RE.search(frame)
    return match.group(1) if match else None


def _summarize_frame(frame: str) -> str:
    """Render an outbound frame in a form that is safe to log.

    Auth frames carry the plaintext password, so their body is dropped
    entirely; everything else is scrubbed for known credential keys and
    truncated. Truncation alone is not protection: which fields land inside
    the first ``LOG_FRAME_CHARS`` characters depends on payload key order.
    """
    command = _frame_command(frame)
    if command and command.lower() in AUTH_COMMANDS:
        return f"<{command} auth frame redacted, {len(frame)} chars>"

    safe = frame
    for pattern, replacement in _SECRET_PATTERNS:
        safe = pattern.sub(replacement, safe)
    if len(safe) > LOG_FRAME_CHARS:
        safe = safe[:LOG_FRAME_CHARS] + "..."
    return safe


# Fallback zone for keepalive pings when the client doesn't inject one.
# The client always passes keepalive_zone, so this only applies to a bare
# Connection; kept here so the network layer needn't import the protocol layer.
DEFAULT_KEEPALIVE_ZONE = "EmpireEx_21"

# Recv poll interval; also the socket timeout, so sends blocking longer
# than this raise. Keep small so _running is checked promptly on shutdown.
SOCKET_POLL_TIMEOUT = 1.0

KEEPALIVE_INTERVAL = 60.0

# A live session always yields inbound traffic — game events, or at minimum the
# server's answer to our keepalive. Silence for this long means the session died
# server-side with the socket still open, which no socket-level check can see.
SESSION_IDLE_TIMEOUT = KEEPALIVE_INTERVAL * 3

# How long disconnect() waits for each background thread before reporting it
# as leaked (a subscriber callback can block the receive thread indefinitely).
THREAD_JOIN_TIMEOUT = 2.0

# A reply check that raises would do so on every reply, so it is reported at most this often.
REPLY_CHECK_WARN_INTERVAL = 60.0


@dataclass
class ResponseWaiter:
    """A waiter for a specific command response."""

    event: threading.Event = field(default_factory=threading.Event)
    result: Packet | None = None
    error: Exception | None = None
    # Decides whether a successful reply is this waiter's; None takes the first one.
    accepts: Callable[[Packet], bool] | None = None


class Connection:
    """
    Synchronous WebSocket connection with threaded message routing.

    Features:
    - Request/response pattern via waiters (consumed on match)
    - Pub/sub pattern via subscribers (broadcast to all)
    - Disconnect notification via :meth:`add_disconnect_listener`
    - Automatic keepalive thread
    - Thread-safe operations: :meth:`connect` and :meth:`disconnect` are
      serialized against each other and against the receive thread's shutdown
      by an internal lifecycle lock, so concurrent calls cannot leak a socket
      or let a dying session tear down its successor.

    Correlation:
        The protocol carries no request id, and the game client never pairs a
        reply with its request: every reply goes to the one handler for its
        command id. So :meth:`request` runs one request per command id at a
        time: a second caller for the same command waits for the first to be
        answered (or to time out), and that wait counts against its timeout.
        Different commands still run in parallel.

        A reply goes to the oldest waiter for its command id that accepts it.
        A waiter with an ``accepts`` check takes only the successful replies
        that pass it, plus any error reply; other replies still reach state
        and subscribers. Without a check, a server push or a late reply to an
        earlier timed-out request with the same command id is taken as the
        answer.

    Client: ``BasicSmartfoxClient.onExtensionResponse`` (ggs.dll line 7151) and
    ``CastleExtensionResponseCommand`` (bundle line 110733), which hands each reply
    to the command registered for its id.
    """

    def __init__(self, url: str, keepalive_zone: str | None = None):
        self.url = url
        self.keepalive_zone = keepalive_zone
        # The joined room's id, which every command carries; the login sets it from joinOK.
        self.room_id = NO_ROOM
        self.ws: websocket.WebSocket | None = None

        self._running = False
        self._closing = False
        self._close_error: BaseException | None = None
        # Incremented on every connect; threads from a previous connection
        # notice the mismatch and exit without touching the new session.
        self._generation = 0
        self._recv_thread: threading.Thread | None = None
        self._keepalive_thread: threading.Thread | None = None
        self._last_recv_at = 0.0

        # Guards every lifecycle transition (ws swap, _running/_closing,
        # generation bump, thread starts) so connect(), disconnect() and the
        # receive thread's epilogue cannot interleave. Never held while a user
        # callback runs or while joining a thread: a disconnect listener that
        # reconnects must not deadlock.
        self._lifecycle_lock = threading.RLock()

        # Request/response waiters: cmd_id -> ResponseWaiter
        # These are consumed when matched (one response per waiter)
        self._waiters: dict[str, list[ResponseWaiter]] = {}
        self._waiters_lock = threading.Lock()
        self._reply_check_warn_at = 0.0

        # cmd_id -> the lock request() holds for that command (see Correlation)
        self._command_locks: dict[str, threading.RLock] = {}
        self._command_locks_lock = threading.Lock()

        # Pub/sub subscribers: cmd_id -> list of callbacks
        # These receive copies of all matching packets
        self._subscribers: dict[str, list[Callable[[Packet], None]]] = {}
        self._subscribers_lock = threading.Lock()

        # Global packet handler (for state updates, etc.)
        self.on_packet: Callable[[Packet], None] | None = None

        # Called only on unexpected connection loss, not on disconnect(), with
        # the generation of the session that dropped (see run_if_current).
        # Single slot, claimed by EmpireClient for its own bookkeeping; other
        # observers register via add_disconnect_listener.
        self.on_disconnect: Callable[[int], None] | None = None

        self._disconnect_listeners: list[Callable[[], None]] = []
        self._disconnect_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        # Snapshot the socket: a concurrent disconnect() can null self.ws
        # between two reads, and callers use this property from inside except
        # handlers (keepalive loop) where an AttributeError would kill the
        # thread outright.
        ws = self.ws
        return ws is not None and ws.connected and self._running

    @property
    def close_error(self) -> BaseException | None:
        """What ended the last connection, or None while connected or after a clean disconnect()."""
        return self._close_error

    def connect(self, timeout: float = 10.0) -> None:
        """
        Connect to the WebSocket server.

        Holds the lifecycle lock for the whole handshake, so a concurrent
        ``connect()`` waits and then returns early instead of opening a second
        socket that would be leaked when ``self.ws`` is overwritten. A
        concurrent ``disconnect()`` likewise waits, and then tears down the
        session this call established.

        Args:
            timeout: Connection timeout in seconds

        Raises:
            NetworkError: The handshake failed (the underlying
                websocket/socket error is chained as ``__cause__``)
        """
        with self._lifecycle_lock:
            if self.connected:
                logger.warning("Already connected")
                return

            logger.debug(f"Connecting to {self.url}...")

            # UTF-8 is checked where the message is decoded (see _receive), not per byte here.
            ws = websocket.WebSocket(skip_utf8_validation=True)
            ws.settimeout(timeout)

            try:
                ws.connect(self.url)
                # After the handshake, drop to the poll timeout used by the
                # recv loop (and, unavoidably, by sends on the shared socket).
                ws.settimeout(SOCKET_POLL_TIMEOUT)

                # A socket left behind by a session that died without a
                # disconnect() would be leaked (along with its server-side
                # session) the moment self.ws is replaced below.
                self._cleanup()

                self.ws = ws
                self._running = True
                self._closing = False
                self._close_error = None
                self.room_id = NO_ROOM
                self._last_recv_at = time.monotonic()
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
                if self.ws is ws:
                    self.ws = None
                # Never let raw websocket-client/socket errors escape the
                # public API: callers guarding with `except EmpireError` (or
                # NetworkError, as send() already raises) must catch connect
                # failures too.
                raise NetworkError(f"Connection to {self.url} failed: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from the server and cleanup resources.

        Safe to call repeatedly, and safe to call from a subscriber callback on
        the receive thread (that thread is then not joined).
        """
        with self._lifecycle_lock:
            if not self._running and self.ws is None:
                return

            logger.debug("Disconnecting...")
            self._closing = True
            self._running = False

            # Cancel all waiters
            self._cancel_all_waiters()

            # Close websocket
            self._cleanup()

            threads = (self._recv_thread, self._keepalive_thread)

        # Join outside the lock: the receive thread's epilogue needs the lock
        # to shut down, so holding it here would deadlock the join.
        current = threading.current_thread()
        for thread in threads:
            if thread is None or thread is current or not thread.is_alive():
                continue
            thread.join(timeout=THREAD_JOIN_TIMEOUT)
            if thread.is_alive():
                # Generation guards make this safe (the thread can no longer
                # touch a new session), but a leak should still be visible.
                logger.warning(
                    f"Thread {thread.name} still alive {THREAD_JOIN_TIMEOUT}s after disconnect "
                    "(blocked in a callback?); it is leaked but can no longer affect this connection"
                )

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
        # The client sends frames without a null terminator
        if data.endswith("\x00"):
            data = data[:-1]

        ws = self.ws
        if ws is None or not self._running:
            raise NetworkError("Not connected")

        try:
            ws.send(data)
        except Exception as e:
            logger.error(f"Send failed: {e}")
            raise NetworkError(f"Send failed: {e}") from e

        # Logged after the send so nothing here can be mistaken for a send
        # failure. Frames carry credentials; see _summarize_frame.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Sent: %s", _summarize_frame(data))

    def request(
        self,
        data: str,
        cmd_id: str,
        timeout: float = 5.0,
        accepts: Callable[[Packet], bool] | None = None,
    ) -> Packet:
        """
        Send data and wait for the response to ``cmd_id``.

        Holds ``cmd_id`` (see :meth:`command_lock`) from before the send until
        the reply, so only one request per command id is in flight; time spent
        waiting for the lock counts against ``timeout``. The waiter is
        registered before the data is sent, so an immediate reply is not lost.

        Args:
            data: The packet to send
            cmd_id: The command id the reply arrives under
            timeout: Seconds to wait, queueing included
            accepts: Whether a successful reply is the answer to this request;
                replies it rejects still reach state and subscribers. Error
                replies carry nothing to check, so they are always taken.

        ``EmpireClient.send`` and ``request_packet`` pass the check of a request
        model that defines ``accepts_reply`` (gaa, ssi, ain, grc, dfc, mcm, jaa by
        position, csm, cra, cds, cat): those replies name what was asked for. Most
        commands' replies do not (gam, gcl, dcl, gli, gui, hgh, jca, ranking pages,
        the attack-info family, chat and every write), so without a check a reply
        cannot be told from another one under the same command: after one
        request times out, its late reply is taken by the next request for that
        command, whose own reply then goes to the one after, until a request
        times out with nothing arriving. A server push under that command id is
        taken the same way. An error reply for a checked command still goes to
        the oldest waiter.

        Raises:
            EmpireTimeoutError: No response within ``timeout``
            ConnectionClosedError: Connection dropped while waiting
            NetworkError: The send itself failed
            ReceiveThreadError: Called on the receive thread, which alone could route the reply
        """
        self._refuse_receive_thread(cmd_id)
        deadline = time.monotonic() + timeout
        with self.command_lock(cmd_id, timeout=timeout):
            if time.monotonic() >= deadline:
                raise EmpireTimeoutError(
                    f"Timeout waiting for '{cmd_id}': an earlier '{cmd_id}' request was still running"
                )
            waiter = self.create_waiter(cmd_id, accepts)
            try:
                self.send(data)
            except Exception:
                self.cancel_waiter(cmd_id, waiter)
                raise
            return self.wait_for_result(cmd_id, waiter, timeout=max(0.0, deadline - time.monotonic()))

    @contextmanager
    def command_lock(self, cmd_id: str, timeout: float = 5.0) -> Iterator[None]:
        """Hold ``cmd_id``: no :meth:`request` for it runs on another thread until the block ends.

        For work that sends ``cmd_id`` itself, several requests at once for
        example, so that neither their replies nor their errors can land on a
        concurrent :meth:`request`. Reentrant on the holding thread.

        Raises:
            EmpireTimeoutError: Another thread held it for all of ``timeout``
            ReceiveThreadError: Called on the receive thread, where waiting for it would stall routing
        """
        self._refuse_receive_thread(cmd_id)
        with self._command_locks_lock:
            lock = self._command_locks.get(cmd_id)
            if lock is None:
                lock = self._command_locks[cmd_id] = threading.RLock()
        if not lock.acquire(timeout=max(0.0, timeout)):
            raise EmpireTimeoutError(f"Timeout waiting for '{cmd_id}': an earlier '{cmd_id}' request was still running")
        try:
            yield
        finally:
            lock.release()

    def create_waiter(self, cmd_id: str, accepts: Callable[[Packet], bool] | None = None) -> ResponseWaiter:
        """Register a waiter for the next reply under ``cmd_id`` that ``accepts`` takes (see :meth:`request`)."""
        waiter = ResponseWaiter(accepts=accepts)
        with self._waiters_lock:
            if cmd_id not in self._waiters:
                self._waiters[cmd_id] = []
            self._waiters[cmd_id].append(waiter)
        return waiter

    def wait_for_result(self, cmd_id: str, waiter: ResponseWaiter, timeout: float = 5.0) -> Packet:
        """Wait for the reply a waiter from :meth:`create_waiter` receives, then drop the waiter.

        Raises:
            EmpireTimeoutError / ConnectionClosedError: as :meth:`request`
            ReceiveThreadError: Called on the receive thread
        """
        try:
            self._refuse_receive_thread(cmd_id)
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

    def _refuse_receive_thread(self, cmd_id: str) -> None:
        if threading.current_thread() is self._recv_thread:
            raise ReceiveThreadError(
                f"Waiting for '{cmd_id}' on the receive thread would stall it until the timeout: "
                "hand the call to another thread, or use a GameState callback"
            )

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

        Raises:
            ReceiveThreadError: Called on the receive thread
        """
        self._refuse_receive_thread(cmd_id)
        waiter = self.create_waiter(cmd_id)
        return self.wait_for_result(cmd_id, waiter, timeout)

    def subscribe(self, cmd_id: str, callback: Callable[[Packet], None]) -> None:
        """
        Subscribe to packets with the given command ID.

        Unlike waiters, subscribers receive ALL matching packets
        and are not consumed.

        Callbacks run on the receive thread, which routes every reply: they must
        not block, and a call that waits for a reply raises ``ReceiveThreadError``.

        Args:
            cmd_id: Command ID to subscribe to
            callback: Function to call with matching packets
        """
        with self._subscribers_lock:
            if cmd_id not in self._subscribers:
                self._subscribers[cmd_id] = []
            self._subscribers[cmd_id].append(callback)

    def add_disconnect_listener(self, callback: Callable[[], None]) -> None:
        """
        Register a callback fired on *unexpected* connection loss.

        Additive, unlike the single-slot :attr:`on_disconnect` attribute that
        :class:`~empire_core.client.client.EmpireClient` claims for its own
        bookkeeping: several consumers can observe disconnects without
        clobbering each other or patching the client's wiring. Registering the
        same callback twice is a no-op.

        Not called by :meth:`disconnect` - only when the session drops on its
        own. Callbacks run on the receive thread, outside every internal lock,
        so a listener may call :meth:`connect` to reconnect.
        """
        with self._disconnect_lock:
            if callback not in self._disconnect_listeners:
                self._disconnect_listeners.append(callback)

    def remove_disconnect_listener(self, callback: Callable[[], None]) -> None:
        """Remove a listener added with :meth:`add_disconnect_listener`.

        No-op if the callback is not registered.
        """
        with self._disconnect_lock:
            try:
                self._disconnect_listeners.remove(callback)
            except ValueError:
                pass

    def _notify_disconnect(self, generation: int) -> None:
        """Fire the on_disconnect slot, then every registered listener."""
        if self.on_disconnect is not None:
            try:
                self.on_disconnect(generation)
            except Exception:
                logger.exception("Error in disconnect callback")
        with self._disconnect_lock:
            callbacks = list(self._disconnect_listeners)
        for callback in callbacks:
            try:
                callback()
            except Exception:
                logger.exception("Error in disconnect callback")

    @property
    def degraded_frames(self) -> DegradedFrameCounts:
        """Inbound frames that degraded to a raw wrapper, which match no waiter and are dropped.

        Counted for the whole process, not for this connection: frames are read
        without knowing which connection they came in on.
        """
        return degraded_frame_counts()

    @property
    def generation(self) -> int:
        """Counts the sessions: :meth:`connect` starts a new one."""
        return self._generation

    def run_if_current(self, generation: int, action: Callable[[], None]) -> bool:
        """Run ``action`` unless a newer session has started since ``generation``; say whether it ran.

        Holds the lifecycle lock while it runs, so no :meth:`connect` can start a
        session in between: cleanup for a dropped session cannot touch its successor.
        """
        with self._lifecycle_lock:
            if generation != self._generation:
                return False
            action()
            return True

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
        """Background thread that receives and routes messages.

        However the loop ends, even by an error nothing inside it expects, the
        epilogue runs: waiters are cancelled, the connection is marked down
        and, unless :meth:`disconnect` ended it, the disconnect listeners run.
        """
        logger.debug("Receive loop started")
        try:
            self._receive(ws, generation)
        except Exception as e:
            if self._running and generation == self._generation:
                self._close_error = e
                logger.exception("Receive loop stopped by an unexpected error")
        finally:
            self._end_receive_loop(generation)

    def _receive(self, ws: websocket.WebSocket, generation: int) -> None:
        """Read messages until the socket fails or the session ends.

        Each message is decoded as UTF-8 with bad bytes replaced and a leading
        byte order mark dropped, as the client's ``FileReader.readAsText(data,
        "utf-8")`` decodes it. The client only reads binary messages; a text
        message is decoded the same way, where a browser would fail the
        connection on invalid UTF-8.

        Client: ``BasicSmartfoxClient.handleSocketData`` (ggs.dll line 7208).
        """
        frames = FrameBuffer()

        while self._running and generation == self._generation:
            # Only socket-level failures are fatal to this loop; everything
            # about handling a single frame is contained below.
            try:
                opcode, data = ws.recv_data()
            except websocket.WebSocketTimeoutException:
                continue  # Check _running and try again
            except websocket.WebSocketConnectionClosedException as e:
                if not self._closing:
                    self._close_error = e
                    logger.warning("Connection closed by server")
                break
            except (OSError, websocket.WebSocketException) as e:
                if self._running and generation == self._generation:
                    self._close_error = e
                    logger.exception("Receive loop stopped by socket error")
                break
            except Exception as e:
                # Nothing else is expected out of recv_data(); still fatal, but log
                # it with the traceback so the cause is diagnosable.
                if self._running and generation == self._generation:
                    self._close_error = e
                    logger.exception("Unexpected error in receive loop")
                break

            if opcode not in _DATA_OPCODES or not data:
                continue

            self._last_recv_at = time.monotonic()

            # A single bad packet must not cost us the connection: tearing the
            # session down forces a re-login that the game server rate-limits.
            # Drop the packet, keep the socket.
            text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
            try:
                raws = frames.feed(text)
            except Exception:
                logger.exception("Dropping buffered data that could not be split into packets")
                frames = FrameBuffer()
                continue
            for raw in raws:
                try:
                    self._route_packet(Packet.from_bytes(raw.encode("utf-8")))
                except Exception:
                    logger.exception("Dropping a packet that could not be parsed or routed")

    def _end_receive_loop(self, generation: int) -> None:
        # If a newer connection took over, this thread must not touch shared
        # state - the new session owns it now. The check happens under the
        # lifecycle lock so a connect() cannot slip in between the check and
        # the mutations below and have its fresh session torn down here.
        with self._lifecycle_lock:
            if generation != self._generation:
                logger.debug("Receive loop superseded by newer connection")
                return

            notify = not self._closing
            self._running = False
            self._cancel_all_waiters(self._close_error)

        # Callbacks run outside the lock: they commonly reconnect.
        if notify:
            self._notify_disconnect(generation)

        logger.debug("Receive loop ended")

    def _route_packet(self, packet: Packet) -> None:
        """
        Route a packet to waiters and subscribers.

        Order:
        1. Pick the waiter that takes it (consumed on match)
        2. Call the global handler, which feeds state
        3. Wake the waiter
        4. Notify subscribers (broadcast)

        Uses copy-on-read pattern to minimize lock hold time.
        """
        cmd_id = packet.command_id

        # Log server errors (but exclude commands that use field 4 for data).
        # The login raises its own typed errors for lli and vck refusals.
        if not packet.is_xml and packet.error_code != 0 and cmd_id not in NON_ERROR_COMMANDS:
            error_name = GGEError.from_code(packet.error_code).name
            if packet.error_code == 21 or cmd_id in LOGIN_REPLY_COMMANDS:
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
                    index = next((i for i, w in enumerate(waiters_list) if self._takes(w, packet)), None)
                    if index is not None:
                        waiter = waiters_list.pop(index)
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

    def _takes(self, waiter: ResponseWaiter, packet: Packet) -> bool:
        """Whether ``waiter`` takes ``packet``; a check that raises counts as no. Called under the waiters lock."""
        if waiter.accepts is None or packet.error_code != 0:
            return True
        try:
            return bool(waiter.accepts(packet))
        except Exception:
            now = time.monotonic()
            if now >= self._reply_check_warn_at:
                self._reply_check_warn_at = now + REPLY_CHECK_WARN_INTERVAL
                logger.exception(f"Reply check for '{packet.command_id}' raised; the reply is not taken")
            return False

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
                self.send(build_command(zone, "pin", [""], self.room_id))
                logger.debug("Sent keepalive ping")
            except Exception as e:
                if active():
                    logger.error(f"Keepalive failed: {e}")
                    # Don't break immediately, retry on next cycle if still running
                    # Only break if socket is explicitly closed
                    if not self.connected:
                        break

            if active():
                self._check_session_liveness()

        logger.debug("Keepalive loop ended")

    def _check_session_liveness(self) -> None:
        """Tear down a session the server has stopped answering.

        Closing the socket is all this does: the receive loop then fails out of
        ``recv()`` and runs its normal epilogue, so waiter cancellation and
        disconnect notification keep to a single code path.
        """
        with self._lifecycle_lock:
            if not self._running or self._closing:
                return
            idle_for = time.monotonic() - self._last_recv_at
            if idle_for <= SESSION_IDLE_TIMEOUT:
                return
            ws = self.ws
            logger.warning(
                f"No traffic for {idle_for:.0f}s (limit {SESSION_IDLE_TIMEOUT:.0f}s); treating session as dead"
            )

        if ws is not None:
            try:
                ws.close()
            except Exception:
                logger.debug("Closing a dead session's socket failed", exc_info=True)

    def _cancel_all_waiters(self, cause: BaseException | None = None) -> None:
        """Cancel all pending waiters, with the error that ended the connection as the cause."""
        message = "Connection closed" if cause is None else f"Connection closed: {type(cause).__name__}: {cause}"
        with self._waiters_lock:
            for waiters in self._waiters.values():
                for waiter in waiters:
                    error = ConnectionClosedError(message)
                    error.__cause__ = cause
                    waiter.error = error
                    waiter.event.set()
            self._waiters.clear()
