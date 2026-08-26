# Code Review — EmpireCore + dreambot-v3

*Rigorous professional-grade review of two tightly-coupled repositories. Every finding below was reported by a dimension-specialist reviewer and then independently re-verified by an adversarial checker instructed to refute it; only survivors are listed. 172 findings confirmed, 7 refuted.*

| | 🔴 Critical | 🟠 Major | 🟡 Minor | 💡 Suggestion |
|---|---|---|---|---|
| **EmpireCore** | 4 | 35 | 42 | 8 |
| **dreambot-v3** | 7 | 32 | 37 | 7 |


---

# EmpireCore

## Executive summary

- **ec-api-packaging** — The typing story is genuinely good at the code level — protocol models, services, and the connection layer are consistently annotated and the repo's own mypy run is clean — but the packaging contradicts the brand: no py.typed marker ships in the wheel (so installed consumers get zero types), the flagship scan APIs and ~20 other defs are unannotated, and nothing in CI enforces strictness. Packaging/release hygiene has real problems a public library shouldn't ship: import-time load_dotenv(), heavy hard dependencies (sqlmodel/aiosqlite) for a dead experimental module, and a publish workflow whose '|| true' can silently skip or mis-classify releases. The exported API surface is under-curated — README and dreambot both deep-import internal modules — and the services/client layers that dreambot depends on have zero test coverage.
- **ec-concurrency** — The connection layer shows real concurrency thinking (generation counters, waiter-before-send registration, callback executor in GameState, locks on waiters/subscribers) but the lifecycle itself is unserialized: connect/disconnect/recv-teardown race each other, the abnormal-exit path leaks open sockets, and correlation is FIFO-by-command with no protection against crossed or unsolicited responses. The state lock is undermined twice — client helpers bypass it entirely and locked accessors hand out live objects that the recv thread mutates in place. The sync refactor is visibly unfinished: storage/ is an unreachable asyncio island whose aiosqlite/sqlmodel deps every installer pays for; this needs a lifecycle lock, snapshot semantics, and a storage decision before public release.
- **ec-lifecycle** — The happy paths are genuinely well built — waiters are registered before send, cancelled in finally blocks, and blocked callers are woken with ConnectionClosedError on drop, so nothing hangs forever and daemon threads keep interpreter exit clean. The error paths are weaker: an unexpected server drop leaves the socket fd unclosed with disconnect() early-returning, login() failures strand live connections and threads, lifecycle state is mutated across three threads with no lock (a real reconnect race), and there is no half-open-connection detection or reconnect story in the library itself. There is also no context-manager support anywhere — for a publicly published client library, close()-by-convention is not an adequate lifecycle contract.
- **ec-errors** — The exception hierarchy itself is coherent — a single EmpireError root with sensible subclasses, and protocol/errors.py is an error-code enum rather than a competing exception family — and the request/response hot path (client.send/request, BaseService) raises typed exceptions consistently. The systemic weakness is at the boundaries: connect() leaks raw websocket-client exceptions, the recv loop tears down the connection on any single bad frame, and several layers (pool.lease, get_active_events, map scanner error codes, movement parsing) collapse real failures into None/[]/debug-log-and-continue, so production degradation is silent — a serious liability for a long-running alerting bot. The B904 ignore hides three real raise-without-from sites in login(); F841 currently hides nothing and both ignores should be dropped.
- **ec-protocol** — The protocol layer is total for common malformed-string cases (junk prefixes, bad ints, broken JSON/XML all degrade to raw-wrapper packets) and there are no asserts used for validation, but the two inputs that do raise — invalid UTF-8 and null-only frames — escape straight into the recv loop's catch-all and tear down the entire connection, which is the worst possible failure mode for a long-running bot behind a login-cooldown-enforcing server. The pydantic models are forward-compatible on unknown fields (extra="allow"), yet strict required fields on nested list elements plus unguarded from_list positional parsers mean single malformed entries discard whole batches, abort kingdom scans, or leak raw ValidationError/TypeError through the documented API. Test coverage for exactly these failure modes is near zero: test_packet.py and test_models.py cover happy paths and error-code shapes but not one of the raising or batch-poisoning paths found here.
- **ec-secrets** — Credential handling is functional but not publish-ready: there is one verified plaintext-password-to-log path (pydantic ValidationError interpolation in accounts.py), password-bearing pydantic models with default reprs, and raw-frame DEBUG logging whose failure to leak the login password today is pure accident of key ordering and a 100-char slice. The account pool honestly documents it is not thread-safe, yet its sole stated purpose — concurrent operations with a synchronous client — requires threads, so the double-checkout race and the hidden global registry (plus import-time load_dotenv) are API decisions that need fixing before a public release.
- **ec-state** — The GameState core is better than average hobby code — there is a real lock, an identity-map merge strategy, atomic list swaps for events, time-based pruning of dead movements, and a concurrency test — but the thread-safety story is only skin-deep: the lock guards dict containers while the objects inside (Castle.units, Resources, Player, inventory) are mutated in place and handed to readers by reference, and both EmpireCore's own client facade and dreambot routinely bypass the locked accessors because the raw dicts are public. Combined with no freshness metadata, no post-reconnect resync, and pruning that only runs on gam packets, a long-running consumer will intermittently crash on dict-size-changed errors and silently act on stale movements/castles. The fixes are localized: swap-don't-mutate, private dicts with snapshot accessors, prune on every mutation path, and timestamps on cached models.
- **ec-general** — EmpireCore's hygiene baseline is genuinely solid for a pre-1.0 game library: no bare excepts, all HTTP calls have timeouts, no mutable default args, logging (not print) throughout, tests pass, and the README/CHANGELOG accurately describe the shipped code (the package really is on PyPI at 0.28.0). The real problems are concentrated at the edges: two correctness bugs (unlocked iteration over receive-thread-mutated movement state, and scan_kingdom timeouts silently reporting partial scans as complete — which dreambot's caching layer actively trusts), plus library-publishing hygiene issues (import-time load_dotenv side effect, heavy deps for an unwired experimental storage module, module-level mutable singletons, and duplicated protocol enums with contradictory values). All are fixable with small, local changes; nothing structural needs to move.


## 🔴 Critical (4)

### Pydantic ValidationError logging writes plaintext passwords to error logs
- **Where:** `src/empire_core/accounts.py:120`
- **Why:** pydantic v2's ValidationError string embeds the offending input as input_value=... . For a missing/misspelled field the input is the ENTIRE entry dict, password included. Verified empirically: a dict with a typo'd 'username' key logs "Field required [type=missing, input_value={'password': 'SuperSecret123', ...}]". So one typo in accounts.json (line 120) or in an EMPIRE_ACCOUNT_* JSON env var (line 147) dumps the plaintext game password into the application's ERROR-level log, which is exactly the log level people ship to aggregators.
- **Fix:** Never interpolate the ValidationError itself. Log field locations only, e.g. `logger.error(f"Skipping invalid account entry in {target_path}: {[err['loc'] for err in e.errors(include_input=False)]}")` — apply to both accounts.py:120 and accounts.py:147.

### Movement helper methods iterate the shared movements dict without the state lock
- **Where:** `src/empire_core/client/client.py:414`
- **Why:** get_incoming_attacks/get_incoming_movements/get_outgoing_movements (lines 412-422) iterate self.state.movements.values() directly. That dict is mutated in-place by the receive thread (manager.py:317 'self.movements[mid] = mov', :324 'del self.movements[mid]'). If a 'gam' packet lands mid-iteration, the caller gets 'RuntimeError: dictionary changed size during iteration' — exactly the crash a long-running bot polling incoming attacks will eventually hit. GameState already provides locked snapshot methods (manager.py:526 get_incoming_movements takes self._lock), but the client helpers bypass them.
- **Fix:** Delegate: return [m for m in self.state.get_incoming_movements() if m.is_attack] etc., or add a get_incoming_attacks() to GameState under the lock. Also stop exposing state.movements/castles/players as raw public dict attributes (make them _private and expose snapshot accessors only).

### _route_packet wakes the waiter before on_packet updates state, so request-then-read-state APIs can return stale data
- **Where:** `src/empire_core/network/connection.py:397`
- **Why:** In _route_packet the waiter is completed (waiter.event.set(), line 397) before self.on_packet runs (line 407), and on_packet is what feeds GameState. EmpireClient.get_movements(wait=True) (client.py:364-368) does connection.request(..., 'gam') and then immediately reads self.state.get_all_movements(). The requesting thread can be scheduled between event.set() and on_packet, returning a movement list that does not include the response it just waited for. Same pattern for any 'request then read state' flow. Nondeterministic stale results in the flagship API; worst case an incoming attack in the gam response is missing from the returned list.
- **Fix:** In _route_packet, invoke on_packet (state update) BEFORE completing waiters, or have get_movements parse movements out of the returned response packet instead of re-reading shared state.

### Snapshots return live shared objects whose inner collections are cleared/repopulated in place by the receive thread
- **Where:** `src/empire_core/state/manager.py:354`
- **Why:** get_castles() (line 549) returns list(self.castles.values()) — references to shared Castle objects, not copies. _handle_dcl then mutates those same objects on the receive thread: castle.units.clear() followed by re-insertion (lines 354-359), and non-atomic field-by-field resource updates (lines 346-348). A user thread iterating castle.units after a get_castles() call races the clear/repopulate → 'RuntimeError: dictionary changed size during iteration', or observes an empty/partial unit list and torn resources (new wood, old stone). The class docstring's claim that 'all mutation and snapshot reads are guarded by a lock' (lines 26-28) only holds for the container, not object contents — the lock is released before the user ever touches the Castle.
- **Fix:** Stop mutating in place: build a fresh units dict and swap it atomically (castle.units = new_units), or better, construct a new Castle/Resources and replace the dict entry (as _store_movement already does for Movement); alternatively have get_castles() return model_copy(deep=True) snapshots and document that.


## 🟠 Major (35)

### Release step swallows all semantic-release failures with '|| true' and infers success by grepping output
- **Where:** `.github/workflows/publish.yml:72`
- **Why:** output=$(uv run semantic-release version 2>&1) || true makes every failure mode exit 0. A real failure (auth error pushing the tag, changelog write error, build failure) produces output without 'No release will be made' and an empty dist/, so released=false and the workflow goes green — the release silently never happens and nobody is alerted. Worse, a partial failure after 'uv build' succeeded (e.g. GitHub release creation fails) leaves dist/ populated, so released=true and the PyPI publish proceeds against a repo whose tag/release state is inconsistent.
- **Fix:** Drop '|| true' and rely on semantic-release's exit code plus its documented output handling: use the official python-semantic-release GitHub Action (which sets a 'released' output), or run 'semantic-release --strict version' and branch on exit codes (0=released, 2=no release) so genuine errors fail the job.

### No py.typed marker: the 'fully typed' library ships as untyped to every consumer
- **Where:** `pyproject.toml:8`
- **Why:** PEP 561 requires a py.typed marker for type checkers to use inline annotations of an installed package. I built the wheel (uv build) and verified py.typed is absent, so pip-installed empire-core gives mypy/pyright users 'module is installed, but missing library stubs or py.typed marker' and all its annotations are ignored. The package description and README both lead with 'Fully typed Python API' — the claim is currently false for anyone consuming the published artifact.
- **Fix:** Add an empty src/empire_core/py.typed file. Hatchling includes package data by default with packages=["src/empire_core"], but add a CI assertion (e.g. unzip the wheel in publish.yml's 'Verify clean install' step and check for py.typed) so it can't regress.

### sqlmodel and aiosqlite are hard runtime dependencies for a dead experimental module
- **Where:** `pyproject.toml:19`
- **Why:** storage/database.py opens with 'EXPERIMENTAL: not yet wired into the client' and nothing in src/ or in dreambot imports it (verified by grep). Yet sqlmodel>=0.0.14 and aiosqlite>=0.19.0 are unconditional dependencies, dragging SQLAlchemy + greenlet + aiosqlite into every consumer's environment for code that is unreachable. For a to-be-published library this bloats installs and widens the CVE/compatibility surface for zero functionality. It's also an async module inside a library that just completed a sync refactor.
- **Fix:** Move sqlmodel/aiosqlite to an optional extra (empire-core[storage]) with a lazy import guard in empire_core.storage, or delete the module until the storage story is real.

### Top-level API exports the wrong/parallel enums; the types consumers actually need require deep imports
- **Where:** `src/empire_core/__init__.py:22`
- **Why:** __init__ exports KingdomType/MapObjectType (utils/enums.py), but every real map API — scan_kingdom, scan_chunks, scan_map_area, MapAreaItem — is typed against protocol.models.map.Kingdom and MapItemType, which are NOT exported. KingdomType is not even equivalent (it lacks BERIMOND=10). Result: dreambot deep-imports empire_core.protocol.models.map in six files, plus empire_core.client.map_scanner.ScanResult, empire_core.services.spy.{SpyService,SpyResult}, empire_core.state.world_models.Movement, and empire_core.accounts.{Account,accounts}. Every one of those internal module paths is now frozen by external usage, and having two near-identical kingdom/map-type enums invites value-mismatch bugs (MapItemType.EMPTY_CASTLE_SLOT=2 vs MapObjectType.DUNGEON=2).
- **Fix:** Promote Kingdom, MapItemType, ScanResult, SpyResult, Account/accounts, and the commonly-used response models to the top-level __all__; deprecate or clearly scope KingdomType/MapObjectType (they describe a different array) with names that say so.

### Curated top-level exports don't cover the de-facto public API; README and the flagship consumer must deep-import internal modules
- **Where:** `src/empire_core/__init__.py:27`
- **Why:** The README itself instructs 'from empire_core.protocol.models.map import Kingdom, MapItemType', and dreambot's imports show the real surface: Kingdom/MapItemType (protocol.models.map), ScanResult (client.map_scanner), SpyResult/SpyService (services.spy), Packet (protocol.packet), Account/accounts (accounts), RankingEntry, decode_chat_text. None are in __all__. Every consumer is therefore coupled to the internal module layout — any file move (like the CLI refactor that already happened) is a breaking change with no deprecation path, and there is no boundary telling users what is public vs internal.
- **Fix:** Re-export the actually-used surface from the top level (Kingdom, MapItemType, ScanResult, CastleInfo, AllianceMember, SpyResult, Packet, Account, RankingEntry, decode/encode_chat_text) and update README/dreambot to import from empire_core. Treat everything not re-exported as private and say so in the README.

### load_dotenv() runs at import time of the top-level package, mutating the consumer's process environment
- **Where:** `src/empire_core/accounts.py:20`
- **Why:** Import chain: empire_core/__init__.py:19 imports empire_core.pool, pool.py:11 imports empire_core.accounts, which executes load_dotenv() at module scope. So a bare 'import empire_core' silently loads whatever .env file sits in the consumer's CWD into os.environ. A library mutating the host process environment as an import side effect is a hygiene violation for a public package: it can inject/shadow configuration in apps (like dreambot) that manage their own env loading, and behavior depends on the CWD at first import.
- **Fix:** Remove the module-level call. Call load_dotenv() lazily inside AccountRegistry.load() behind an explicit opt-in parameter, or drop python-dotenv as a core dependency entirely and leave env-file loading to applications.

### Account and EmpireConfig repr/str expose plaintext password
- **Where:** `src/empire_core/accounts.py:30`
- **Why:** Both are plain pydantic BaseModels with `password: str`, so the default __repr__/__str__ include the secret. Verified: repr(Account(...)) -> "Account(username='bob', password='SuperSecret123')". Any user doing print(account), any f-string log of a config, and any error-reporting tool that reprs locals in tracebacks (Sentry, structlog) leaks credentials. Same defect at src/empire_core/config.py:63 (`password: str | None = None`), and Account -> to_empire_config() copies the password into every client's config object.
- **Fix:** Use pydantic SecretStr for both password fields (call .get_secret_value() at the single point the login packet is built), or at minimum Field(repr=False). Do the same for EmpireConfig.password in config.py.

### _on_packet silently drops every packet whose payload is a JSON array, defeating _handle_sce's documented list handling
- **Where:** `src/empire_core/client/client.py:144`
- **Why:** packet.py:98 parses payloads starting with '[' into a Python list (verified: b'%xt%sce%1%0%[["PTT", 5]]%' yields payload of type list). But _on_packet returns early for any non-dict payload, so state.update_from_packet is never called. GameState._DISPATCH registers 'sce' and _handle_sce (state/manager.py:393-395) explicitly says 'data might be a list directly: [["PTT", 123]]' — that branch is unreachable for standalone sce pushes. Result: silent inventory-state loss with no log line at all.
- **Fix:** Relax the guard to `isinstance(packet.payload, (dict, list))` and let _update_state/state handlers decide per-command, or normalize list payloads to a wrapper dict at the Packet layer and adjust handlers accordingly.

### login() failure leaves an open connection and two live background threads with no cleanup
- **Where:** `src/empire_core/client/client.py:199`
- **Why:** login() implicitly connects (line 191-192), then any failure in the 5-step sequence — version-check EmpireTimeoutError (line 197-199), LoginCooldownError (line 253), LoginError (line 255) — propagates while the websocket, recv thread, and keepalive thread keep running; the keepalive pings an unauthenticated session every 60s indefinitely. The documented usage pattern (docstring lines 81-84: login(); ...; close()) never runs close() when login() raises, so a plain user of the library leaks a socket + threads per failed login attempt. Only AccountPool compensates by calling _safe_close() in its except handlers; direct users get no such protection and nothing in the docstring warns them.
- **Fix:** Wrap the login sequence in try/except and call self.close() (or at least connection.disconnect()) before re-raising fatal errors — or, if keeping the connection alive for retry is intentional, document explicitly that close() must be called after a failed login().

### Raw pydantic ValidationError leaks to callers of send(wait=True)/request(), contradicting the documented PacketError contract
- **Where:** `src/empire_core/client/client.py:320`
- **Why:** client.send calls parse_response(command, payload) with no exception handling; model_cls.model_validate raises pydantic.ValidationError on any server field-type drift (e.g. a gam response with one movement missing 'AT' — reproduced at runtime). client.request()'s docstring promises 'PacketError: The response could not be parsed', but the ValidationError propagates before the isinstance check. A public library exposing undocumented third-party exception types on untrusted network input forces every consumer (dreambot services) to defensively catch pydantic internals.
- **Fix:** Wrap parse_response calls in try/except ValidationError and re-raise as PacketError (chaining the original), both in client.send and in services that call model_validate directly (services/alliance.py:202).

### get_movements() ignores the gam response error code and returns stale state as fresh data
- **Where:** `src/empire_core/client/client.py:364`
- **Why:** connection.request() returns the packet without checking error_code (only client.send(wait=True) raises CommandError). get_movements() discards the response entirely and returns state.get_all_movements(). If the server rejects gam (e.g. session invalidated), the caller gets the previous — possibly empty or stale — movement list with no exception, indistinguishable from a successful 'no movements' answer.
- **Fix:** Capture the response packet and `if response.error_code != 0: raise CommandError("gam", response.error_code)` before reading state.

### Only gaa error code 337 is handled; any other server error makes a chunk look legitimately empty
- **Where:** `src/empire_core/client/map_scanner.py:89`
- **Why:** For a non-zero error code other than 337 (e.g. COOLING_DOWN=95, MAP_NOT_AVAILABLE=142, rate limiting), Packet._parse_xt still produces a dict payload ({"raw": ""}), so `isinstance(response.payload, dict)` passes, AI defaults to [], and _process_chunk returns ok=True/has_content=False. The chunk is not added to failed_chunks, BFS stops expanding there, and scan_kingdom returns a silently truncated result that claims to be complete — defeating the whole failed_chunks contract.
- **Fix:** Treat any `response.error_code != 0` as a failed chunk (return _ChunkResult(ok=False, ...)) or raise CommandError("gaa", response.error_code), keeping 337 as the special fatal case.

### MapAreaItem.from_list is unguarded in _scan_chunk; one garbage AI entry aborts an entire kingdom scan
- **Where:** `src/empire_core/client/map_scanner.py:112`
- **Why:** MapAreaItem.from_list feeds raw array elements into pydantic int fields; a non-numeric element (e.g. data[1]='abc', reproduced: ValidationError) propagates out of _scan_chunk and up through scan_kingdom, aborting a scan that can take minutes and discarding all chunks already collected. The neighbouring OI loop (line 102-108) wraps MapObject.model_validate in try/except — the AI loop got no such protection, so the defensive intent is inconsistent within the same function.
- **Fix:** Wrap MapAreaItem.from_list in the same try/except-continue pattern used for MapObject three lines above, and log the skipped entry.

### scan_kingdom timeout drops the remaining BFS queue without recording it in failed_chunks
- **Where:** `src/empire_core/client/map_scanner.py:180`
- **Why:** The docstring promises 'Chunks that fail even after a retry are reported in ScanResult.failed_chunks so callers can tell a partial scan from a complete one', but the overall-timeout break (lines 178-181) discards everything still in `queue` without adding it to failed_chunks. scan_chunks does the right thing (failed_chunks.extend(todo[i:]) at line 302). Consumers trust this: dreambot-v3 services/empire.py gates caching of content_chunks on `if res.content_chunks and not res.failed_chunks` (line 288), so a timed-out partial scan is cached as the authoritative chunk set and regions are silently and persistently missed. With ~400+ chunks at 0.2s pacing plus RTT, a full scan realistically approaches the 300s default timeout.
- **Fix:** On the timeout break, extend failed_chunks with the unvisited queue contents (e.g. failed_chunks.extend(c for c in queue if c not in visited)) before breaking, mirroring scan_chunks; same for the connection-lost break.

### Shared mutable module-level default_config aliased into every client constructed without a config
- **Where:** `src/empire_core/config.py:67`
- **Why:** EmpireClient.__init__ does `self.config = config or default_config` (client.py:100), so all default-constructed clients alias the same mutable pydantic instance. Any mutation (`client.config.default_zone = ...`, or a future library-internal write) silently changes zone/timeouts/credentials for every other default client in the process — nasty to debug in a multi-account tool like dreambot, which runs many clients. EmpireConfig is not frozen, so nothing prevents this.
- **Fix:** Use `self.config = config or EmpireConfig()` (cheap, per-client), or declare `model_config = ConfigDict(frozen=True)` on EmpireConfig and keep the shared default.

### Single-slot on_disconnect forces consumers to monkey-patch connection internals to observe disconnects
- **Where:** `src/empire_core/network/connection.py:84`
- **Why:** Connection.on_disconnect is a single assignable attribute that EmpireClient claims for itself in __init__ (client.py:114). The only way dreambot can get disconnect notifications is to reach through client.connection, capture the original, and install a wrapper (dreambot empire.py:354-369). This couples the bot to the client's internal wiring: if EmpireCore ever (re)assigns on_disconnect during login()/reconnect, or moves the handler, the bot's wrapper is silently clobbered and its fast-reconnect path (ConnectionMonitor._on_service_disconnect) stops firing with no error. A published library must own this seam.
- **Fix:** Add a public multi-listener API on EmpireClient (add_disconnect_listener/remove_disconnect_listener) that survives internal rewiring, and treat client.connection as private (rename to _connection once consumers migrate).

### connect()/disconnect() have no mutual exclusion; concurrent connect() leaks a socket and can produce two live recv loops
- **Where:** `src/empire_core/network/connection.py:116`
- **Why:** connect() is check-then-act: two threads can both pass 'if self.connected' (line 98), each open a websocket, and each execute the non-atomic self._generation += 1 (line 116). Under the GIL the read-modify-write can interleave so both connections compute the SAME generation, in which case both recv loops pass the 'generation == self._generation' guard and route packets from two different sockets into shared waiters/subscribers. Even without the interleave, the loser's websocket is overwritten at self.ws and never closed (leaked socket + server-side session). Reconnect logic in a consumer plus a user-initiated call is enough to trigger this.
- **Fix:** Add a lifecycle lock held across connect() and disconnect() (state checks, generation bump, thread starts, ws swap). Close any previous self.ws before replacing it.

### connect() leaks raw websocket-client/socket exceptions through the public API
- **Where:** `src/empire_core/network/connection.py:144`
- **Why:** connect() re-raises the original exception, so client.login() surfaces websocket.WebSocketException, ConnectionRefusedError, socket.timeout, SSL errors, etc. Meanwhile send() wraps the same class of failure in NetworkError. A user of the published library writing `except EmpireError` (or `except NetworkError`) around login() will not catch a connection-refused, and must import websocket internals to handle it — the exact 'inconsistent exception types for the same failure class' problem.
- **Fix:** In connect()'s except block, `raise NetworkError(f"Connection to {self.url} failed: {e}") from e` instead of bare `raise`.

### Raw outbound frames logged at DEBUG with no credential redaction — login password escapes only by accidental truncation
- **Where:** `src/empire_core/network/connection.py:200`
- **Why:** send() logs the first 100 chars of every frame. The lli login frame (client/client.py:237) carries "PW": "<plaintext password>"; I measured PW at index 244, so today it is cut off purely because LOGIN_DEFAULTS happens to put 13 keys before NOM/PW and the truncation is 100. Reorder the payload, shorten the defaults, or bump the truncation while debugging (the library's own examples/debug_packets.py enables level=DEBUG globally) and the password lands in logs. A credentials-bearing wire protocol needs deliberate redaction, not lucky slicing.
- **Fix:** Redact by command: skip or mask the body for auth frames (lli, core_reg, scp) — e.g. log only the command id and byte length for those, or strip the PW key before logging. Keep the truncation as defense in depth.

### A single unparseable frame kills the receive thread and tears down the whole connection
- **Where:** `src/empire_core/network/connection.py:325`
- **Why:** Packet.from_bytes raises on two realistic inputs: a frame that is only null bytes (ValueError 'Empty packet', packet.py:44 — the recv loop's `if not data: continue` does not catch b'\x00') and any binary frame with invalid UTF-8 (UnicodeDecodeError from data.decode('utf-8'), packet.py:42). Both were reproduced at runtime. In _recv_loop the parse happens inside the outer try, and the catch-all `except Exception: ... break` exits the loop, cancels all waiters, and fires on_disconnect — so one malformed packet is treated identically to a dead socket. For dreambot this forces a full re-login, which GGE rate-limits (error 453 LOGIN_COOLDOWN), turning one bad frame into minutes of outage.
- **Fix:** Wrap the Packet.from_bytes/_route_packet block in its own try/except that logs and `continue`s (only socket-level exceptions should break the loop), and make Packet.from_bytes total: decode with errors='replace' and return a raw-wrapper Packet for empty input instead of raising.

### Any exception while parsing one frame kills the entire connection
- **Where:** `src/empire_core/network/connection.py:325`
- **Why:** The recv loop's catch-all does `break` on any exception, then cancels all waiters and fires on_disconnect. Packet.from_bytes raises ValueError('Empty packet') for a frame that is just b'\x00' (truthy, so the `if not data: continue` guard does not catch it), and any future parse quirk in _parse_xml/_parse_xt does the same — one malformed frame tears down a healthy session and fails every in-flight request. It also uses logger.error(f"...{e}") with no traceback, so diagnosing why the connection died is guesswork.
- **Fix:** Split handling: catch parse errors (ValueError, json/ET errors) per-message with logger.exception and `continue`; only `break` on socket-level errors (OSError, WebSocketException). Use logger.exception in the fatal branch.

### Connection lifecycle state (ws/_running/_closing/_generation) is mutated without a lock; stale recv-thread epilogue races connect() and can kill a fresh reconnect
- **Where:** `src/empire_core/network/connection.py:332`
- **Why:** connect(), disconnect(), and the recv-thread epilogue all read-modify lifecycle fields with no mutex. Concrete race: old recv thread passes the generation check at line 332 (generations still equal), then a reconnecting thread runs connect() (lines 113-116: self.ws = ws; self._running = True; self._generation += 1); the stale thread then executes line 337 'self._running = False', line 338 cancels the NEW session's waiters (failing an in-flight login with ConnectionClosedError), and fires a spurious on_disconnect. The new recv thread sees _running False and exits, so the just-established connection is torn down. Symmetrically, disconnect() running concurrently with connect() can _cleanup() and null the new ws after connect() returns success. Window is small but sits exactly on the unexpected-drop -> reconnect path that a supervisor (e.g. dreambot's connection_monitor) exercises repeatedly. The class docstring advertises 'Thread-safe operations'.
- **Fix:** Add a threading.Lock guarding all lifecycle transitions: connect(), disconnect(), and the recv epilogue should acquire it; the epilogue must re-check generation while holding the lock before touching _running/waiters/on_disconnect.

### Request/response correlation is FIFO by command id only — concurrent identical commands or unsolicited pushes get cross-delivered
- **Where:** `src/empire_core/network/connection.py:384`
- **Why:** _route_packet matches responses purely by cmd_id, popping the oldest waiter (waiters_list.pop(0)). Two threads issuing the same command concurrently (e.g. two get_player_info('gdi') calls for different players from a bot's thread pool) get whichever response arrives first, regardless of which request it answers. Worse, waiters also consume server-PUSHED packets of the same cmd_id (the game pushes gam/gdi-style updates unsolicited), so request() can return a packet that answers nothing. get_player_details_bulk works around this with a queue, which shows the authors hit the problem, but every single-shot request in services/* remains exposed.
- **Fix:** Where the payload allows it, verify the response matches the request (e.g. check PID in gdi responses) before completing a waiter, and pass unmatched packets to the next waiter/subscribers. At minimum serialize requests per cmd_id with a per-command lock and document the constraint.

### AccountPool is hard-coupled to a global singleton registry that lazily reads credentials from CWD
- **Where:** `src/empire_core/pool.py:50`
- **Why:** AccountPool takes no accounts; all_accounts returns the module-global `accounts` registry (pool.py:11), which on first touch auto-loads CWD-relative accounts.json plus every EMPIRE_ACCOUNT_* env var (accounts.py:173-175, 91-99). Consequences for a public library: (1) constructing a pool implicitly reads credential files from whatever directory the process happens to start in; (2) two pools can never use different account sets; (3) tests must monkeypatch a module global. Hidden global credential state is not an API a production library should ship.
- **Fix:** Accept dependencies explicitly: AccountPool(registry: AccountRegistry | None = None) or AccountPool(accounts: list[Account]), defaulting to the singleton only for convenience. Also make AccountRegistry.load() require an explicit path rather than probing os.getcwd().

### AccountPool.lease() collapses every failure into None, swallowing the causes
- **Where:** `src/empire_core/pool.py:147`
- **Why:** The per-candidate `except Exception` logs and continues, and after the loop lease() returns None — the same value as 'no accounts configured'. LoginError, NetworkError, and outright programming bugs (TypeError/AttributeError in get_client or login) are all reduced to a log line. Callers cannot distinguish 'pool exhausted, back off' from 'credentials wrong, page a human' from 'bug in library', and a typo-level bug manifests as a permanent mysterious None in production.
- **Fix:** Return None only when there are no candidates; when all candidates fail, raise a dedicated PoolError/LoginError chaining the last exception (`raise ... from last_exc`), or at minimum narrow the catch to (LoginError, NetworkError).

### AllianceInfo.model_post_init raises raw TypeError on non-list AMI entries, escaping model_validate un-wrapped
- **Where:** `src/empire_core/protocol/models/alliance.py:252`
- **Why:** Reproduced: AllianceInfo.model_validate({'AID': 1, 'AMI': [5]}) raises TypeError("object of type 'int' has no len()") — pydantic does not wrap model_post_init exceptions in ValidationError, so callers that (correctly) catch ValidationError still crash. member_info is typed as bare `list`, so element shape is completely unvalidated; the AMI array is exactly the kind of positional server array whose format has already drifted once (see the wrapped-list workaround in MemberCastle.from_list line 54).
- **Fix:** Guard the loop: `if isinstance(ami_entry, (list, tuple)) and len(ami_entry) >= 5 and isinstance(ami_entry[0], int)`, and skip otherwise.

### GetMapAreaResponse.get_moving_flags() and MapAreaItem.is_moving_flag are stale/wrong; the correct parsing lives only in the bot
- **Where:** `src/empire_core/protocol/models/map.py:228`
- **Why:** is_moving_flag (map.py:138) is true for EVERY owned type-1 entry, and from_list sets owner_id = data[3] for type-1 — which, per the consumer's reverse engineering (dreambot empire.py:63-69), is the CASTLE id, not the player id. So get_moving_flags() returns essentially every castle in the area keyed by the wrong id, and its own docstring contradicts MapItemType.CASTLE ('Player main castle'). dreambot had to hardcode raw indices (field 4 = player id, field 19 = relocating flag) to get correct behavior, meaning the library's flagship map feature is unusable as shipped and the real protocol knowledge lives outside the library.
- **Fix:** Update MapAreaItem for the 20-field type-1 layout: add player_id (raw_data[4]) and is_relocating (raw_data[19]) properties, make get_moving_flags() filter on is_relocating and key by player_id, and fix the stale '1: Moving castle flag' docstring. Then delete dreambot's MOVING_OWNER_FIELD/MOVING_FLAG_FIELD constants.

### No frame de-batching: a WS frame containing two null-terminated packets silently corrupts the first and swallows the second
- **Where:** `src/empire_core/protocol/packet.py:42`
- **Why:** from_bytes strips only trailing nulls, so b'%xt%gam%...%\x00%xt%acm%...%\x00' parses as a single 'gam' packet whose payload degrades to {'raw': '{"M": []}%\x00%xt%acm%...'} (reproduced at runtime) — the gam payload is lost AND the acm packet is never routed, with no error logged. SmartFoxServer's wire protocol is null-delimited and can batch messages; the code already acknowledges the terminator by stripping it, but assumes exactly one packet per frame. To verify against the live server: log any recv() frame where data.rstrip(b'\x00').find(b'\x00') != -1.
- **Fix:** In _recv_loop (or a Packet.iter_from_bytes helper), split the frame on b'\x00', parse each non-empty segment as its own packet, and route each one.

### local_player/players have no locked read path and are merged field-by-field in place, exposing torn reads
- **Where:** `src/empire_core/state/manager.py:169`
- **Why:** There is no query method for local_player, players, or inventory — the library's own code reads state.local_player unlocked (services/alliance.py:218, client.py:536 via get_castles is fine but local_player is not), and dreambot does the same (services/birder.py:243, services/incomings.py:133). Meanwhile the receive thread mutates the shared Player object in place: the gbd re-login merge sets fields one setattr at a time (lines 169-170), and _handle_sce mutates local_player.inventory in place (line 401). A user thread can read a half-merged player (new LVL, old XP), and iterating local_player.inventory concurrently with an sce packet raises RuntimeError. The public-bare-attribute API design actively invites these unlocked reads.
- **Fix:** Add locked snapshot accessors (get_local_player() returning a model_copy, get_inventory() returning a dict copy), make the raw dicts private (_players, _castles, _movements), and swap rather than mutate the Player (build fresh, assign under lock).

### Stale-movement pruning runs only inside _handle_gam, so movements drift and accumulate when gam is never received
- **Where:** `src/empire_core/state/manager.py:255`
- **Why:** _prune_stale_movements() is invoked solely at the top of _handle_gam (line 255). Movements also enter state via pushed 'mov' packets (_handle_mov, line 364) and are removed only by explicit atv/ata/mrm packets. If an arrival packet is missed (brief socket error, disconnect window) and the consumer relies on push callbacks rather than polling gam, dead movements persist indefinitely: get_incoming_attacks() keeps reporting attacks that already landed, and the movements dict grows without bound in a long-running process. Compounding this, state is intentionally kept across reconnects (client.py:166-173) but nothing re-requests gam after re-login, so every reconnect leaves a window of phantom in-flight movements until the next user-initiated gam plus the 300s grace.
- **Fix:** Prune in _handle_mov and _handle_movement_arrived as well (or on every update_from_packet call / in the query methods), and trigger a gam resync after re-login so movement state is rebuilt from the server after a gap.

### Movement parse failures are swallowed at DEBUG level, silently dropping incoming attacks
- **Where:** `src/empire_core/state/manager.py:506`
- **Why:** _parse_movement catches Exception, logs at logger.debug, and returns None; _store_movement is then never called. If a game update changes the Movement schema (pydantic ValidationError), every movement — including incoming attacks, the core alerting feature dreambot depends on — silently disappears, and nothing appears in logs at default INFO level. The bot would report 'no incoming attacks' while under attack.
- **Fix:** Log at warning/error (rate-limited if noisy) with logger.exception so schema drift is visible in production; consider a counter/metric for parse failures.

### The sync refactor is half-done: storage/ is a dead asyncio island, yet aiosqlite and sqlmodel are hard runtime deps
- **Where:** `src/empire_core/storage/database.py:4`
- **Why:** database.py is fully asyncio (asyncio.Queue, asyncio.create_task, async engine) and its own docstring says 'EXPERIMENTAL: not yet wired into the client' with 'no schema-migration story'. Nothing in the sync library can call it without the caller owning an event loop, and nothing does. Meanwhile pyproject.toml lines 19-20 pin sqlmodel>=0.0.14 and aiosqlite>=0.19.0 as mandatory dependencies — every installer of a 'synchronous' library pulls SQLAlchemy's async stack for code that is unreachable. For a public release this is dependency bloat plus a misleading API surface (GameDatabase is importable and looks supported).
- **Fix:** Either finish the refactor (a sync sqlite3/SQLModel storage backend matching the library's threading model) or excise storage/ to an optional extra: move deps to [project.optional-dependencies] storage=[...] and guard the import. Also note the unbounded asyncio.Queue write queue — bound it if the module stays.

### MapObjectType and protocol MapItemType are two divergent enums for the same ID space; KingdomType duplicates Kingdom
- **Where:** `src/empire_core/utils/enums.py:7`
- **Why:** utils/enums.MapObjectType and protocol/models/map.MapItemType agree on 1=CASTLE, 3=CAPITAL, 4=OUTPOST, 22=METRO, 23=KINGS_TOWER, 26=MONUMENT, 28=LABORATORY — strongly suggesting the same server ID space — but contradict each other at 2 (DUNGEON vs EMPTY_CASTLE_SLOT), 7 (TREASURE_DUNGEON vs KHAN_TENT), and 12 (KINGDOM_CASTLE vs EXTERNAL_KINGDOM). At least one mapping is wrong, and dreambot classifies incoming-attack targets with MapObjectType while the scanner filters with MapItemType, so a mislabeled value produces wrong classifications. Likewise KingdomType (utils) duplicates Kingdom (protocol) minus BERIMOND=10, and the top-level package exports the utils copies while every API signature takes the protocol ones. Duplicated tables of protocol constants will keep drifting.
- **Fix:** Keep a single authoritative enum per ID space in protocol/models (verify the conflicting values 2/7/12 against live packets), re-export it from utils/enums as an alias for backward compatibility, and delete the duplicate definitions.

### get_active_events() returns [] on CDN failure, indistinguishable from 'no events active'
- **Where:** `src/empire_core/utils/events.py:153`
- **Why:** The catch-all turns any metadata-fetch failure (DNS outage, CDN 500, JSON change) into an empty list — the same value as a genuinely quiet day. A consumer branching on event presence (dreambot event features) silently disables itself during outages, and _build_events_index failures also poison behavior for callers who did get valid event IDs from the live server. Error-as-empty-collection is exactly the anti-pattern a published typed library should avoid.
- **Fix:** Let the exception propagate wrapped in NetworkError (callers already handle exceptions from client calls), or add a raise_on_error flag / return a result object distinguishing 'empty' from 'unavailable'.

### Zero test coverage for the services layer, the client login/send path, and protocol response parsing beyond chat
- **Where:** `tests/test_smoke.py:6`
- **Why:** tests/ is 805 lines covering packet framing, state-manager movements, the model registry/chat encoding, map scanner, connection, and accounts pool — all good. But grep confirms not a single test touches AllianceService/CastleService/ArmyService/LordsService/RankingService/SpyService, the EmpireClient login sequence (the 6-step handshake with its gbd-waiter race handling), send/request/execute semantics (CommandError vs bool contracts the README documents), get_player_details_bulk's handler registration/cleanup, or parsing of real alliance (AMI arrays), castle (dcl), or gdi payloads. These are exactly the layers dreambot depends on in production, and the layers most likely to break when GGE changes payloads.
- **Fix:** Add a FakeConnection (the pool tests already stub a client, so the pattern exists) and test: full login sequence including lli error codes 453/401, service request/execute error mapping, and golden-payload parse tests for each registered response model using captured server payloads.


## 🟡 Minor (42)

### examples/ are private debug scripts, not curated examples for a public library
- **Where:** `examples/test_adi.py:38`
- **Why:** test_adi.py hardcodes 'Robber Baron NPC coords from the issue report' (214, 1259) — context meaningless to a public user; debug_packets.py monkeypatches internals (client._on_packet / client.connection.on_packet), teaching users to rely on private API; and the test_*.py names collide conceptually with pytest conventions (only excluded from collection by testpaths config). For a library about to be published, examples/ is the first thing users copy.
- **Fix:** Replace with small curated examples (login + movements, alliance chat, kingdom scan) using only public API, and move the debug scripts to a scripts/ or dev/ directory.

### Stale config: 'temporarily disabled' CLI references a module that no longer exists, dead PSR v7 'branch' key, leftover async test plumbing
- **Where:** `pyproject.toml:27`
- **Why:** Three bits of drift: (1) the commented [project.scripts] points at empire_core.cli:app but no cli module exists anywhere in src/ — it's deleted, not 'temporarily disabled', so the comment misleads contributors about re-enabling it; (2) [tool.semantic_release] branch = "master" (line 71) is v7 syntax silently ignored by the installed PSR 10.5.3 (verified via --noop run; the default branch group already matches master); (3) pytest-asyncio dev dep and asyncio_mode = "auto" remain although zero tests are async post-sync-refactor. None break anything today, but each is a trap during the next refactor.
- **Fix:** Delete the CLI comment block (restore it when a CLI module actually exists), remove branch = "master", and drop pytest-asyncio + asyncio_mode from the dev extra and pytest config.

### Ruff ignore list is mostly dead weight, and B904 hides three real exception-chaining losses in login()
- **Where:** `pyproject.toml:52`
- **Why:** Running ruff with the ignored rules enabled shows F841, B007, and E701 have zero violations — they suppress nothing and just weaken future linting. E501 is ignored while line-length=120 is configured, making the setting unenforced. B904 hides exactly 3 real hits, all in client.py login (lines 199, 214, 246): 'except EmpireTimeoutError: raise EmpireTimeoutError(...)' without 'from e', which discards the original traceback context users need when debugging login timeouts.
- **Fix:** Delete F841/B007/E701/E501 from the ignore list, fix the 3 B904 sites with 'raise EmpireTimeoutError("Version check timed out") from e', then drop B904 too.

### __version__ = version(__package__) makes bare-source imports crash with PackageNotFoundError
- **Where:** `src/empire_core/__init__.py:25`
- **Why:** importlib.metadata.version() requires installed distribution metadata. The project itself relies on metadata-less imports (pytest config sets pythonpath=["src"]), and anyone vendoring the source or using PYTHONPATH gets 'PackageNotFoundError: empire_core' at import of the top-level package — the whole library becomes unimportable, not just versionless. Verify: python -c 'import sys; sys.path.insert(0,"src"); import empire_core' in a venv without empire-core installed.
- **Fix:** Wrap in try/except PackageNotFoundError with a fallback (e.g. __version__ = "0.0.0.dev0"), and add "pyproject.toml:project.version" awareness only in semantic-release (already configured).

### Plaintext accounts.json loaded with no file-permission check or hardening guidance
- **Where:** `src/empire_core/accounts.py:107`
- **Why:** _load_from_file opens whatever accounts.json exists in CWD with zero warning if it is group/world-readable, and neither README.md nor accounts.json.template mentions chmod 600 or the security model. accounts.json is gitignored (good), but a public library storing plaintext passwords should at least warn on loose permissions — this is what keyring-less tools like pgpass do.
- **Fix:** After resolving target_path, `mode = os.stat(target_path).st_mode; if mode & 0o077: logger.warning(...)` (POSIX only), and add a 'Securing credentials' note to README and the template.

### AccountRegistry lazy-load in getters is unsynchronized
- **Where:** `src/empire_core/accounts.py:173`
- **Why:** Every getter does `if not self._loaded: self.load()`, and load() starts with `self._accounts = []` (line 71). Two threads hitting get_all() concurrently (the exact threaded context AccountPool invites) can both run load(), one clearing the list while the other iterates it — transient empty results or duplicated accounts. Verify by calling get_all() from two threads with a slow filesystem; fold into the pool locking work.
- **Fix:** Guard load() with a threading.Lock and double-checked _loaded flag, or require an explicit load() call and raise if not loaded.

### EmpireClient (and Connection, GameDatabase, pool lease) has no context-manager support
- **Where:** `src/empire_core/client/client.py:72`
- **Why:** For a library intended for public release, the only cleanup story is a manually paired close(). There is no __enter__/__exit__ anywhere in the package (grep for __enter__/__exit__/__del__/atexit returns nothing), so every exception between construction/login and close() leaks a socket and threads unless callers write try/finally themselves. This is precisely the ergonomic gap that context managers exist to close, and every comparable client library (requests.Session, websockets, sqlalchemy engines) ships one.
- **Fix:** Add __enter__ returning self and __exit__ calling close() on EmpireClient (and Connection); optionally have __enter__ perform login(). Add async context-manager support to GameDatabase.

### client._handlers is mutated from user threads while the recv thread reads it, relying on GIL atomicity
- **Where:** `src/empire_core/client/client.py:137`
- **Why:** get_player_details_bulk registers/removes handlers (lines 662, 682-683) on the plain dict self._handlers while the recv thread reads it in _on_packet (line 151). Today CPython's GIL makes the individual dict/list ops atomic and the list(handlers) copy defensive, so this happens to work — but it is undocumented, unprotected by any lock (unlike _waiters/_subscribers in Connection, which do get locks), and breaks under free-threaded Python (PEP 703 builds) which the 3.13 toolchain here is one flag away from.
- **Fix:** Mirror the Connection pattern: guard _handlers with a threading.Lock in _register_handler, a new _unregister_handler, and the read in _on_packet (copy under lock).

### login() is typed -> bool but can never return False, leaving callers with dead falsy-checks
- **Where:** `src/empire_core/client/client.py:175`
- **Why:** Every failure path raises (ValueError, EmpireTimeoutError, LoginError, LoginCooldownError); the only return is `return True`. The bool signature invites `if not client.login()` checks that are dead code — pool.py:133 already has one (`if login and not client.login(): raise LoginError(...)`), and examples check client.is_logged_in after login 'failure' that cannot happen without an exception.
- **Fix:** Change the signature to `-> None` (raise-only contract), and remove the unreachable branch in pool.lease().

### login() raises ValueError for missing credentials instead of a typed EmpireError
- **Where:** `src/empire_core/client/client.py:186`
- **Why:** README's error-handling section promises typed exceptions all inheriting from EmpireError, and pool.lease() catches LoginError specially — but missing credentials escape as a builtin ValueError, so a caller writing `except EmpireError` (the advertised catch-all) misses this login failure mode.
- **Fix:** Raise LoginError("Username and password are required") instead of ValueError.

### Timeout re-raises without 'from' discard the original error context (B904 ignored globally)
- **Where:** `src/empire_core/client/client.py:199`
- **Why:** Three login steps catch EmpireTimeoutError and raise a fresh one without `from e` (lines 199, 214, 246). The original message ('Timeout waiting for apiOK') and chain are replaced by implicit-context 'During handling of the above exception, another exception occurred' noise in logs. The blanket B904 ignore in pyproject hides these; ruff confirms exactly these three sites.
- **Fix:** Use `except EmpireTimeoutError as e: raise EmpireTimeoutError("Version check timed out") from e` at all three sites, then remove B904 from the ruff ignore list (F841 currently has zero hits and can be un-ignored for free).

### Hardcoded conm_value duplicates LOGIN_DEFAULTS['CONM']
- **Where:** `src/empire_core/client/client.py:201`
- **Why:** login() hardcodes conm_value = 1150008 for the zone-login pword while the XT login takes CONM from LOGIN_DEFAULTS (config.py:21, same literal). If one is ever updated (e.g. after a game client bump) the two login steps silently send different client-version fingerprints, an easy-to-miss login breakage.
- **Fix:** Use conm_value = LOGIN_DEFAULTS['CONM'] (or hoist a CONM constant into config.py used by both).

### close() shuts down the state callback executor before disconnecting, so a late packet can silently recreate a leaked executor
- **Where:** `src/empire_core/client/client.py:272`
- **Why:** close() runs state.shutdown() (executor -> None) and only then connection.disconnect(). In that window the recv thread is still routing packets; a movement/attack packet reaching GameState triggers _dispatch_callback, whose lazy-creation branch (state/manager.py lines 73-76: 'if self._callback_executor is None: self._callback_executor = ThreadPoolExecutor(...)') builds a brand-new ThreadPoolExecutor after shutdown. Nothing ever shuts that one down, leaking a non-daemon worker thread for the life of the process on every occurrence.
- **Fix:** Reverse the order in EmpireClient.close(): disconnect the connection (joining the recv thread) first, then call state.shutdown(). Alternatively add a _shutdown flag to GameState that _dispatch_callback checks instead of lazily recreating the executor.

### subscribe_alliance_chat leaks raw Packet objects while a typed chat subscription already exists
- **Where:** `src/empire_core/client/client.py:484`
- **Why:** EmpireClient.subscribe_alliance_chat hands consumers raw connection Packets and documents the payload dict shape, while AllianceService.on_chat_message (services/alliance.py:302) delivers parsed AllianceChatMessageResponse with decoded_text. Two overlapping APIs for the same event, and the raw one is what dreambot picked — which is why protocol keys ('CM'/'PN'/'MT') and a divergent decoder ended up in bot code. A published library should not expose the wire format as its convenience API.
- **Fix:** Deprecate subscribe_alliance_chat/unsubscribe_alliance_chat (or reimplement them to deliver AllianceChatMessageResponse) and point consumers at client.alliance.on_chat_message.

### Flagship public methods scan_kingdom/scan_chunks have no return type annotation
- **Where:** `src/empire_core/client/client.py:598`
- **Why:** The README's headline feature returns Any: scan_kingdom (line 598-607) and scan_chunks (line 609-619) omit '-> ScanResult', so even consumers who vendor the source get no completion or checking on result.items/result.content_chunks. mypy --disallow-untyped-defs reports 22 such errors across the public surface: subscribe_alliance_chat/unsubscribe_alliance_chat take a bare 'callback' (client.py:484/496), AllianceService.__init__(self, client) is untyped (services/alliance.py:66), AccountPool.__init__ and AccountRegistry.load/get are untyped (pool.py:42, accounts.py:61-125). The repo's own mypy config passes only because it sets no strictness flags, so the 'fully typed' guarantee is unenforced.
- **Fix:** Annotate the 22 defs (mypy --disallow-untyped-defs --disallow-incomplete-defs lists them all: scan_* '-> ScanResult', callbacks as Callable[[Packet], None], client: 'EmpireClient'). Then add disallow_untyped_defs = true (at least for src/) to [tool.mypy] so CI enforces the branding.

### Chunk retry catches broad Exception while first attempt catches narrow transport errors
- **Where:** `src/empire_core/client/map_scanner.py:85`
- **Why:** The first attempt correctly catches only (EmpireTimeoutError, NetworkError); the retry catches Exception, so a programming error (AttributeError, pydantic bug) raised during the retry is logged as a 'failed chunk' and swallowed instead of surfacing — masking real bugs as network flakiness in scan logs.
- **Fix:** Catch the same (EmpireTimeoutError, NetworkError) tuple in the retry and let everything else propagate.

### MapObject validation failures dropped with zero logging
- **Where:** `src/empire_core/client/map_scanner.py:107`
- **Why:** `except Exception: continue` around MapObject.model_validate silently discards objects. If GGE changes the OI schema, owner/alliance data quietly vanishes from every scan with no trace in logs — unlike the neighboring movement parser which at least debug-logs. Impossible to diagnose from production logs.
- **Fix:** Narrow to pydantic.ValidationError and log the failure (debug with the raw dict, or a rate-limited warning counter).

### Inverted sentinel semantics: item_types=None means castles-only, [] means scan everything
- **Where:** `src/empire_core/client/map_scanner.py:153`
- **Why:** None defaults to [MapItemType.CASTLE] while an empty list disables filtering entirely — the more-restrictive-looking value is the least restrictive. dreambot depends on this quirk ('item_types or []' at empire.py:234/280 deliberately converts None to 'all types', silently inverting the library default). Any reasonable normalization of [] in the library (e.g. treating it as 'match nothing' or as the None default) would silently change every bot scan's contents.
- **Fix:** Make the API explicit: item_types=None -> no filter (all types), and require a non-empty list to filter; raise on []. Update dreambot to pass None instead of [].

### config.ServerError duplicates GGEError with contradictory code meanings
- **Where:** `src/empire_core/config.py:11`
- **Why:** Two parallel error-code vocabularies exist: ServerError.INVALID_CREDENTIALS=401 conflicts with GGEError.REWARD_ID_NOT_FOUND=401, and SESSION_EXPIRED=440 conflicts with C2_CONFIRMATION_REQUIRED=440 — at least one table is wrong. Only LOGIN_COOLDOWN is actually used (client.py:249). A maintainer reading config.py will mislabel server errors; CommandError messages would print the GGEError name for a code config claims means something else.
- **Fix:** Delete the ServerError class and use GGEError.LOGIN_COOLDOWN at the one call site; if 401/440 truly have login-phase-specific meanings, document that on the lli handling instead.

### Hard-coded AID tracking/install id shared by every library user
- **Where:** `src/empire_core/config.py:30`
- **Why:** LOGIN_DEFAULTS ships "AID": "1745592024940879420" with a comment admitting it is a static install/tracking id captured from a browser session — presumably the author's own. On public release, every consumer presents an identical device fingerprint to Goodgame's servers, making all library users trivially correlatable (and mass-bannable), and it publishes an identifier tied to the author's session.
- **Fix:** Generate a random AID per install (persist alongside accounts.json) or expose it on EmpireConfig with a randomized default; do not ship a single shared literal.

### ActionError is dead code: never raised and not exported
- **Where:** `src/empire_core/exceptions.py:58`
- **Why:** grep shows ActionError is defined once and referenced nowhere else in src/ or tests/, and it is missing from empire_core.__init__.__all__ (which exports all other exceptions). A user writing `except ActionError` gets a handler that can never fire; the class only creates false expectations about the API surface.
- **Fix:** Delete ActionError, or actually raise it from service action methods (e.g. BaseService.execute) and export it.

### connected property is a TOCTOU: self.ws can be nulled between the None check and the attribute access
- **Where:** `src/empire_core/network/connection.py:89`
- **Why:** 'self.ws is not None and self.ws.connected' reads self.ws twice; a concurrent disconnect()/_cleanup() setting self.ws = None between the reads raises AttributeError. Callers include the keepalive thread inside its except handler (line 441 'if not self.connected: break'), where the AttributeError would escape the handler and kill the keepalive thread with an unhandled-exception traceback, and MapScanner's abort checks (map_scanner.py lines 77, 203), where it would surface as a spurious crash to the scanning caller. Window is small but the pattern is unsound in a class whose whole point is cross-thread use.
- **Fix:** Snapshot once: 'ws = self.ws; return ws is not None and ws.connected and self._running'.

### lease(username=...) bypasses active flag, tag filter, and is case-sensitive unlike the rest of the API
- **Where:** `src/empire_core/pool.py:107`
- **Why:** The username path filters only on exact-case username and busy-status, so a deactivated account (active=False) can still be leased by name, and 'Bob' != 'bob' here while AccountRegistry.get_by_username (accounts.py:191) and has_tag are case-insensitive. Inconsistent matching semantics across one small API surface is the kind of thing that produces 2am surprises.
- **Fix:** In the username branch, also check acc.active (and tag if provided) and compare with .lower() to match registry semantics.

### Dead guard for a login() False return that cannot happen
- **Where:** `src/empire_core/pool.py:133`
- **Why:** EmpireClient.login() either raises or returns True — there is no False path (client.py:265 is the only return). The `if login and not client.login(): raise LoginError('Login returned False...')` branch is unreachable dead code that documents a wrong contract, and login()'s bool return type is vestigial, inviting other callers to write the same meaningless check.
- **Fix:** Change login() to return None (documenting that it raises on failure), and reduce the pool code to `if login: client.login()`.

### Packet.payload annotation omits list, but _parse_xt deliberately parses JSON-array payloads
- **Where:** `src/empire_core/protocol/packet.py:22`
- **Why:** Line 98 checks raw_payload.startswith("[") and json.loads it, so payload can be a list at runtime, contradicting the declared 'dict[str, Any] | ET.Element | None'. mypy misses it because payload_data is inferred from json.loads (Any). Consumers who trust the annotation (e.g. writing packet.payload.get(...) after a None-check) get a type-checker-approved AttributeError on array-payload commands; it also means the isinstance(payload, dict) guards scattered through client.py silently drop array responses.
- **Fix:** Widen the annotation to 'dict[str, Any] | list[Any] | ET.Element | None' (and annotate payload_data), or normalize arrays into a wrapper dict like the non-JSON 'raw' case so the current annotation becomes true.

### Packet parsing raises bare ValueError although PacketError exists for exactly this
- **Where:** `src/empire_core/protocol/packet.py:44`
- **Why:** exceptions.py defines PacketError as 'raised when packet parsing fails', but the actual parser raises ValueError; PacketError is only used for a response-type mismatch in client.request(). Same pattern in client.py:186 (ValueError for missing credentials instead of LoginError) and client.py:538. Builtin exceptions escape the public API for library-domain failures, so `except EmpireError` misses them and the hierarchy's promise is broken.
- **Fix:** Raise PacketError('Empty packet') in Packet.from_bytes; raise LoginError (or a ConfigError subclass of EmpireError) for missing credentials.

### Non-integer XT status field silently becomes error_code=0 (success)
- **Where:** `src/empire_core/protocol/packet.py:87`
- **Why:** Reproduced: b'%xt%gam%1%abc%{...}%' yields error_code 0. A garbled or format-shifted status field is indistinguishable from a successful response, so client.send's `error_code != 0` check passes and the payload is parsed as if valid — malformed input masquerading as success rather than being flagged.
- **Fix:** On ValueError, set error_code to a sentinel (e.g. -1) or mark the packet as malformed so routing/logging can distinguish 'no error' from 'unparseable status'.

### SpyResult payload fields are typed Any in a library marketed as 'fully typed'
- **Where:** `src/empire_core/services/spy.py:24`
- **Why:** spy_data, battle_data, and target are `Any` (populated via getattr fallbacks at lines 148-150), so the flagship 'Fully typed Python API' (pyproject description, README title) hands consumers untyped blobs at exactly the API surface dreambot's spy_worker consumes — no IDE help, no mypy coverage, silent attribute typos.
- **Fix:** Type them against the BattleSpyDataResponse model fields (e.g. spy_data: SpyData | None) and drop the getattr fallbacks in favor of explicit optional model fields.

### players dict is a misleading dead structure — only the local player is ever stored
- **Where:** `src/empire_core/state/manager.py:38`
- **Why:** self.players: dict[int, Player] suggests a growing map of players seen, but the only writer is _parse_player_info, which stores the gpi (local player) entry; no other-player data ever lands here. API consumers will iterate it expecting world players and get one entry, while the real per-player data flows through service responses that bypass state entirely. Either it is dead weight or an unimplemented feature — both are bad for a published library.
- **Fix:** Remove the dict and keep only local_player, or actually populate it from gdi/ranking responses with an explicit size bound/eviction policy so it cannot grow unboundedly if it becomes a real cache.

### Callback executor can be resurrected after shutdown because close() shuts state down before disconnecting the connection
- **Where:** `src/empire_core/state/manager.py:75`
- **Why:** EmpireClient.close() calls state.shutdown() (client.py:272) BEFORE connection.disconnect() (client.py:273). In that window the recv thread can still deliver a packet whose handler calls _dispatch_callback, which lazily recreates the ThreadPoolExecutor (manager.py:74-75) — a pool that is then never shut down (leaked worker threads per close/reopen cycle). The executor's submission queue is also unbounded, so a packet flood with slow callbacks grows memory without limit.
- **Fix:** Disconnect the connection first, then shut the state down; or add a _shutdown flag checked in _dispatch_callback that refuses to recreate the executor after shutdown(). Consider a bounded queue with drop-and-log semantics.

### _parse_currencies and _parse_vip reset values to 0 on partial payloads instead of preserving previous state
- **Where:** `src/empire_core/state/manager.py:185`
- **Why:** gcu.get("C1", 0) / vip.get("VP", 0) overwrite gold/rubies/VIP with 0 when the sub-packet exists but omits a key, unlike _parse_xp which deliberately preserves prior values (gxp.get("LVL", self.local_player.LVL)). A partial gcu/vip payload silently zeroes the player's currency in state — drift that looks like data, not absence. Verify by capturing whether the server ever sends gcu without both C1 and C2.
- **Fix:** Use the same preserve-on-missing pattern as _parse_xp: gcu.get("C1", self.local_player.gold), etc.

### Stale alliance never cleared when the player leaves an alliance
- **Where:** `src/empire_core/state/manager.py:212`
- **Why:** _parse_alliance_info early-returns when gal is missing or has no AID, so once local_player.alliance is set it can never become None again. After the player leaves/is kicked and a fresh gbd arrives without alliance data, state.local_player.alliance and AID keep reporting the old alliance forever — silent drift. Verify by re-logging an account after leaving an alliance and checking state.local_player.alliance.
- **Fix:** When gbd is processed and gal lacks an AID, explicitly set self.local_player.alliance = None and AID = None instead of returning early.

### Castle stale-drop is skipped entirely when no owned castles are parsed
- **Where:** `src/empire_core/state/manager.py:247`
- **Why:** The 'if seen_ids:' guard means that if a gcl update parses zero owned castles (player lost their last castle, owner_id mismatch, or a payload format change makes the len(raw_ai) > 10 check fail), the removal branch never runs and ghost castles persist in self.castles and local_player.castles indefinitely. It also masks parse regressions: a format change silently freezes the castle list instead of failing loudly.
- **Fix:** Distinguish 'gcl present but empty' (drop all) from 'gcl absent/unparseable' (keep, log warning); at minimum log at warning level when a gcl yields zero owned castles while state has some.

### Arrival/recall callbacks receive only the MID after the Movement is already removed from state
- **Where:** `src/empire_core/state/manager.py:381`
- **Why:** _handle_movement_arrived dispatches callbacks asynchronously via the executor and then immediately pops the movement, so by the time a callback runs, get_movement_by_id(mid) returns None. Callbacks are typed Callable[[int], None] — consumers get an opaque integer and cannot recover what arrived (target, type, units). This forces every consumer to maintain a shadow copy of movements (dreambot's incomings service does exactly this), duplicating the state manager's job.
- **Fix:** Pass the popped Movement object to the callbacks (pop first, then dispatch with the object), changing the signature to Callable[[Movement], None] or Callable[[int, Movement | None], None].

### No freshness metadata on cached state — users cannot distinguish live data from login-time leftovers
- **Where:** `src/empire_core/state/manager.py:546`
- **Why:** Castle resources/units are populated only when a dcl packet happens to arrive (often just once at login via gbd), and Player gold/rubies/inventory only on gcu/sce pushes — yet get_castles() and state.local_player hand this data out with no last-updated timestamp, no 'synced' flag, and no documented staleness contract. Movement has created_at/last_updated (world_models.py:88-89) but Castle, Resources, and Player have nothing. A consumer reading castle.resources.wood hours into a session has no way to know it reflects login time; for a published library this silently-stale cache is a correctness trap.
- **Fix:** Stamp a last_updated (monotonic or wall-clock) on Castle/Resources/Player at each packet merge, expose it in the models, and document which packets refresh which fields plus how to force a refresh (e.g., a resync()/refresh_castles() method).

### Top-level-exported state models use raw wire field names (OID, N, X, KID) as canonical public attributes
- **Where:** `src/empire_core/state/models.py:87`
- **Why:** Castle/Player/Alliance/Movement expose server abbreviations as their real fields with snake_case properties bolted on, while protocol models (CastleInfo) do the reverse (snake_case fields + Field(alias=...)). The inconsistency leaks: client.py:592 reads castle.KID/castle.X, examples/test_adi.py reads main_castle.X, and the library exports two different castle types where '.name' vs '.castle_name' differ. Consumers coupling to wire names (Movement.MID, .T, .PT) means any protocol rename is a public API break, and the API reads like a packet dump.
- **Fix:** Adopt the protocol-model convention in state models: snake_case fields with Field(alias="OID") etc. (populate_by_name is already enabled), keep the old attribute names as deprecated properties for one release, and migrate internal callers.

### Two incompatible public classes named Movement (state.world_models vs protocol.models.map)
- **Where:** `src/empire_core/state/world_models.py:40`
- **Why:** empire_core.__init__ exports state.world_models.Movement (raw GGE attribute names: MID, T, PT, TID...), while empire_core.protocol.models exports a different Movement (map.py:260, pythonic names movement_id/movement_type via aliases) in its __all__. dreambot imports the state one and writes movement.MID/movement.T (incomings.py:169-174); a consumer who innocently imports Movement from protocol.models gets a type that fails every one of those attribute accesses. For a published library this is a naming collision that guarantees confusion and wrong-type bugs at the seam.
- **Fix:** Rename one of them (e.g. protocol.models.map.Movement -> MovementInfo, or make the state model wrap/extend the protocol model) and give the surviving Movement pythonic property aliases (movement_id, type) so consumers stop coding against raw two-letter field names.

### A single failed commit silently discards an entire write batch (up to 51 operations); unbounded queue accepts writes after close()
- **Where:** `src/empire_core/storage/database.py:147`
- **Why:** The writer batches up to 51 queued operations into one session; any exception during merge/commit rolls back and drops the whole batch with only a log line — no retry, no requeue, no dead-letter — so one transient 'database is locked' error loses up to 51 snapshots/map-object updates. Separately, after close() stops the writer, save_player_snapshot/save_map_objects still happily put() onto the unbounded queue, silently accumulating memory with data that will never be written. (Module is marked EXPERIMENTAL, which mitigates urgency.)
- **Fix:** On commit failure, retry the batch once or re-queue items with a retry counter; in save_* methods raise (or at least warn) when _running is False; consider a bounded queue with backpressure.

### events.py CDN caches lack the lock and failure backoff that troops.py has, and never expire
- **Where:** `src/empire_core/utils/events.py:36`
- **Why:** Sibling module troops.py guards its module cache with _fetch_lock and a 300s _FAILURE_RETRY_INTERVAL precisely because 'every access re-issues blocking HTTP requests' on failure. events.py has neither: during a CDN outage every get_active_events() call re-issues up to two blocking HTTP requests (10s + 30s timeouts) from whatever thread calls it, concurrent callers double-fetch, and on the happy path the index is cached forever, so a long-running bot never sees events added to the CDN data after first fetch unless it passes force_refresh.
- **Fix:** Mirror troops.py: guard the caches with a threading.Lock, record _last_failure_at with a retry interval, and consider a TTL (e.g. 24h) on the cached index/translations.

### Module-level CDN caches are unsynchronized check-then-fetch shared across threads
- **Where:** `src/empire_core/utils/events.py:74`
- **Why:** _cached_events_index and _cached_translations are module globals filled via check-then-fetch (lines 74, 104) with no lock. Two threads calling client.get_active_events() concurrently (e.g. from a bot thread pool) both see the cache empty and both perform the multi-second CDN downloads. The race is benign (last-writer-wins on equivalent data) but wastes bandwidth and makes first-call latency unpredictable; a shared client-per-account bot hits it on startup.
- **Fix:** Guard the cache fill with a module-level threading.Lock (double-checked), or use functools.lru_cache on a keyed fetch function which is internally locked.

### test_models.py only tests the registry and error-shaped payloads; no malformed-nested-payload coverage
- **Where:** `tests/test_models.py:55`
- **Why:** test_error_payload_parses_for_registered_models proves {'E': 21} parses, but nothing exercises the realistic corruption cases: a gam 'M' list with one movement missing required fields (currently discards the batch), MapAreaItem.from_list / MemberCastle.from_list / PlayerCastle.from_list with short or non-numeric arrays, AllianceInfo with non-list AMI entries (raw TypeError today), RankingEntry with unknown layouts, or ChatMessageData with missing PN/PID. Every from_list positional-array parser — the most format-drift-prone code in the package — has zero direct tests.
- **Fix:** Add a malformed-payload test class per model module: assert lenient models skip bad list elements, assert from_list helpers never raise on lists of wrong arity/types, and pin the intended exception type (PacketError vs ValidationError) for strict request/response parsing.

### test_packet.py has no coverage for the packet-parser failure modes that actually raise
- **Where:** `tests/test_packet.py:41`
- **Why:** The suite covers happy paths plus one short packet and one malformed-XML case, but none of: invalid UTF-8 bytes (UnicodeDecodeError), a b'\x00'-only frame (ValueError 'Empty packet'), multi-packet frames with embedded nulls, non-numeric request-id/status fields ('%xt%gam%1%abc%...'), JSON-array payloads (payload becomes a list), truncated packets like b'%xt%gam%1%' (exactly 4 parts), or junk that is neither XML nor XT. The two raising paths — the ones that kill the recv loop — are precisely the untested ones.
- **Fix:** Add parametrized tests asserting from_bytes never raises (once made total) and pins the behavior for each input class above, including that payload type for '[...]' payloads is explicit and intentional.


## 💡 Suggestions (8)

### get_player_details_bulk sends an unpaced burst of gdi requests
- **Where:** `src/empire_core/client/client.py:665`
- **Why:** All unique player ids are fired back-to-back with no delay. The library's own map-scanner docs state the server drops connections that sustain high request rates (hence chunk_delay=0.2 there). dreambot funnels arbitrary member lists through this method (services/empire.py:507); a 100-member alliance means a 100-request burst on a connection other services share. Verify by bulk-fetching a large id list and watching for disconnects/error 21 responses.
- **Fix:** Add a `send_delay: float = 0.05`-style pacing parameter (time.sleep between sends) mirroring chunk_delay, or batch ids with small inter-batch delays.

### CommandError does not expose the resolved GGEError enum member
- **Where:** `src/empire_core/exceptions.py:52`
- **Why:** CommandError stores the raw int code and bakes the GGEError name into the message string only. Callers wanting to branch (`if e.code == GGEError.NOT_ENOUGH_RESOURCES`) must import GGEError from the protocol layer and call from_code themselves; alliance.py and map_scanner.py already hardcode magic ints (114, 337) with comments instead. Also note from_code maps unknown codes to GENERAL_ERROR, so log messages can mislabel genuinely new server codes (the numeric code in parentheses mitigates this).
- **Fix:** Store `self.error = GGEError.from_code(code)` on CommandError and re-export GGEError from empire_core.__init__; replace the magic-int comparisons with enum members.

### disconnect() ignores join(timeout=2.0) results — a stuck recv thread silently outlives 'Disconnected'
- **Where:** `src/empire_core/network/connection.py:165`
- **Why:** If a subscriber callback blocks the recv thread (see the inline-callback finding), join(timeout=2.0) returns with the thread still alive and disconnect() logs 'Disconnected' anyway. The generation guard makes this eventually safe, but the caller has no signal that a thread leaked; repeated reconnects under a stuck callback accumulate live threads. Verify by joining and checking is_alive() afterward.
- **Fix:** After the timed join, check thread.is_alive() and log a warning naming the thread (they are helpfully named EmpireCore-Recv/Keepalive), so leaks are observable in production logs.

### AccountPool's login-per-lease model is unusable for the game's one-session rule; the real pool logic lives in the bot
- **Where:** `src/empire_core/pool.py:84`
- **Why:** AccountPool.lease() creates and logs in a fresh EmpireClient per lease. dreambot's own comments (empire.py:742-745) explain why that fails in production: 'GGE allows one session per account — every extra login kicks the previous one... until login cooldowns pile up.' Consequently the library's exported pool has zero consumers, and dreambot ships its own persistent-connection EmpirePool (connect-all-at-startup, tag lookup, reconnect+cooldown handling) — generic connection-lifecycle logic that belongs in the library for any long-running consumer.
- **Fix:** Replace or supplement AccountPool with a persistent pool modeled on dreambot's EmpirePool (long-lived logged-in clients, get_by_tag, per-account reconnect with cooldown tracking, disconnect listeners), then have the bot consume it.

### AccountPool offers no context-managed lease, so a caller exception between lease() and release() permanently leaks the account slot and a live connected client
- **Where:** `src/empire_core/pool.py:165`
- **Why:** lease()'s own failure paths are handled correctly (busy discarded, client closed), but once a lease is handed out there is no scoping mechanism: if the caller raises before reaching release() (and didn't write try/finally), the username stays in _busy forever, the client's socket and threads stay alive, and — since the pool has no lease timeout or reaper — the account is permanently unavailable until process restart. For the primary consumer (a long-running Discord bot) this is a slow-burn availability leak.
- **Fix:** Add 'with pool.leased(tag=...) as client:' via contextlib.contextmanager that guarantees release() in finally, and/or return a lease handle object implementing __enter__/__exit__; optionally add a max-lease-age reaper as a safety net.

### xml.etree parses network-controlled XML without entity-expansion hardening
- **Where:** `src/empire_core/protocol/packet.py:57`
- **Why:** ET.fromstring runs on whatever the server (or a MITM on a downgraded/compromised connection) sends during the handshake phase. stdlib ElementTree is documented as vulnerable to billion-laughs/quadratic-blowup entity expansion, which would hang or OOM the recv thread. Risk is low (single wss endpoint, XML only used for handshake), but for a publicly published library the hardening is one line.
- **Fix:** Use defusedxml.ElementTree.fromstring, or reject payloads containing '<!DOCTYPE'/'<!ENTITY' before parsing, and cap accepted XML size.

### No size bound on inbound frames before json.loads
- **Where:** `src/empire_core/protocol/packet.py:100`
- **Why:** The recv loop hands arbitrarily large frames straight to json.loads on the recv thread; an oversized (multi-hundred-MB) payload from a misbehaving server stalls packet routing for every waiter and can balloon memory. Not exploitable in practice against the official server, but a cheap guard fits the 'robust long-running service' goal since a stalled recv thread blocks all request() callers until timeout.
- **Fix:** Reject (log and drop) frames above a sane threshold (e.g. 16 MB) in _recv_loop before calling Packet.from_bytes.

### get_troop_ids() returns empty set on CDN failure, silently changing count semantics
- **Where:** `src/empire_core/utils/troops.py:80`
- **Why:** On any fetch failure the function returns set(), and count_troops() then counts every unit including equipment ('If we couldn't get troop IDs, count everything'). Downstream troop counts silently inflate during CDN outages with no way for the caller to know the numbers are degraded. The backoff and comment show this is deliberate, but the degradation is invisible to callers.
- **Fix:** Return None (vs set()) to distinguish 'unavailable' from 'empty', or expose a `troop_data_available()` check; at minimum document the inflated-count fallback on count_troops().


---

# dreambot-v3

## Executive summary

- **db-seam** — The seam is the weakest part of both codebases: dreambot treats empire-core as a grab-bag of internals rather than a library — deep module imports in a dozen files, pervasive ._client bypasses of its own facade, re-implemented protocol knowledge (chat decoding, gaa field indices, support-send payloads) that has already diverged from the library, in one case into a live bug. The editable-path/unbounded-version setup plus blanket exception swallowing has let real signature drift ship silently (get_player_details is broken in production today, and reconnects orphan the incoming-attack pipeline). Empire-core shares the blame: its top-level API omits the types consumers actually need, ships duplicate enums and duplicate Movement models, a broken get_moving_flags, and no multi-listener disconnect hook — so the bot had little choice but to reach inside. Fixing the library API surface and adding a thin contract test in the bot would eliminate most of this class of failure.
- **db-async** — The async bridge is used far more consistently than in a typical sync-library-in-a-discord-bot codebase: virtually every DB call goes through the *_async helpers, every EmpireClient call through run_sync/to_thread, and thread-to-loop hops correctly use run_coroutine_threadsafe. The remaining defects are concentrated and serious, though: two blocking Twilio HTTPS calls and one blocking GGE round-trip sit directly on the event loop inside the incoming-attack alert path (the bot's most latency-critical feature), and the bridge itself has systemic gaps — 300-second scans share the tiny default executor with every DB query, per-invocation locks/semaphores fail to actually serialize shared connections against empire-core's FIFO-by-command response matching, and the 5-connection MySQL pool throws rather than queues under the unbounded to_thread concurrency the design invites.
- **db-database** — The DB layer is small, readable, and consistently parameterized — no SQL injection exists anywhere in src/ (the two dynamic IN-clauses only join %s placeholders), and execute()/execute_many() correctly commit/rollback per call. The gaps are production-robustness ones: a fixed 5-connection pool whose acquisition fails fast with no retry, zero timeouts anywhere, multi-statement writes (member-state replacement, ping-target rewrite) that can half-apply because the shipped-but-unused transaction helpers are never called, plus a broken LAST_INSERT_ID helper and a non-functional yoyo.ini. Migrations are MariaDB-dialect (unquoted `rank`, IF NOT EXISTS index/column DDL) while everything else advertises MySQL, and one query (move_detector on db_linked_accounts.player_id) filters on a column no code populates.
- **db-security** — The verification flow itself is chat-based (not SMS/OTP), so classic SMS-pumping and code brute-force are largely non-applicable, and game passwords are correctly stored with reversible Fernet encryption (they must be replayed to log in, so hashing is not an option). The serious problems are on the telephony/PII side: /call is completely unauthenticated and un-throttled, and its message is interpolated into TwiML unescaped, together giving any guild member a harassment + toll-fraud vector against real phone numbers; and those phone numbers are stored in plaintext despite the project already having encryption infrastructure. Secondary issues are raw-exception leakage into Discord replies and unauthenticated data-intel commands. Fixing the /call authorization, TwiML escaping, and phone-at-rest encryption should be prerequisites for a production deployment.
- **db-robustness** — The service layer shows genuine robustness engineering — create_logged_task everywhere it matters, exponential backoff in the tracker and property-scanner loops, per-account reconnect serialization, and careful reconnect-storm avoidance — but the recovery story has one fatal gap: reconnecting replaces the EmpireClient (and its GameState), silently killing the incoming-attack callbacks that are the bot's primary purpose, and the fire-and-forget run_coroutine_threadsafe pattern means that failure (and others in the alert path) produces zero log output. Secondary risks cluster around unguarded concurrency (per-job spy locks), a non-resilient one-shot on_ready bootstrap, and an event-loop-blocking Twilio call in the hottest path.
- **db-discord** — Discord fundamentals are half-done: there is a global tree error handler and the data cog defers defensively, but the view layer universally abuses timeout=None without bot.add_view (unbounded ViewStore growth plus dead components after every restart), several handlers do slow DB/game/REST work before acknowledging the interaction, and no view implements on_error or on_timeout, so failures surface as stuck or 'interaction failed' UI. The standout risks are the /call command — completely ungated, event-loop-blocking, and vulnerable to TwiML injection with real monetary/abuse consequences — and the fragile on_ready bootstrap where a single uncaught exception permanently leaves the bot online with no cogs loaded.
- **db-general** — dreambot-v3 is a competent hobby-grade bot with some genuinely good hygiene (typed helpers, create_logged_task, centralized config timeouts, clean shutdown path) but it is not yet a robust production service: the deployment story leaks credentials into image layers, exposes an unauthenticated DB admin UI, and depends on an editable-install layout that will drift from the published empire-core. The runtime has several single-points-of-silent-failure — an unguarded on_ready bootstrap that can permanently disable the bot, name-collision channel deletion, a non-queuing DB pool, and never-expiring view objects — plus duplicated/dead code (channels.py double definitions, triplicated rank tables) and a roadmap file that contradicts the shipped code. Fixing the two criticals and the on_ready/Docker findings would move it most of the way to production-ready.


## 🔴 Critical (7)

### GGE account credentials (accounts.json) baked into Docker image layers
- **Where:** `Dockerfile:23`
- **Why:** `COPY accounts.json* ./` copies the real credentials file (gitignored precisely because it holds account passwords) into an image layer. Anyone with access to the image (registry push, shared tarball, CI cache) can extract every GGE account password with `docker save`. There is also no .dockerignore in the repo. The copy is entirely redundant: docker-compose.yml already bind-mounts ./accounts.json over /app/accounts.json at runtime.
- **Fix:** Delete the `COPY accounts.json* ./` line and rely on the volume mount (or a Docker secret). Add a .dockerignore that excludes accounts.json, .env, .git, and __pycache__.

### /call has no permission check or rate limiting — any member can spam real phone calls to any registered member
- **Where:** `src/dreambot/cogs/twilio.py:22`
- **Why:** The `call` slash command is decorated only with `@app_commands.command` and `@app_commands.describe` (no `@app_commands.checks`, no role/admin gate, no cooldown). `user: discord.Member` is arbitrary, so any guild member can target ANY other registered member and place real outbound Twilio voice calls (cogs/twilio.py:44-67). Repeated invocation is unbounded, enabling call-pumping harassment of a victim's real phone number and running up the bot owner's Twilio bill (toll fraud). The success path also replies publicly (interaction.response.defer() then followup.send(f"Calling {user.mention}...") at line 61,70), leaking which members have a phone configured.
- **Fix:** Gate the command with a role/admin check (e.g. @app_commands.checks.has_role(...) or app_is_bot_admin() as used by /config and /bird), restrict targets to the caller or callers with a privileged role, and add a per-caller/per-target cooldown (@app_commands.checks.cooldown). Make responses ephemeral so phone existence isn't disclosed.

### get_player_details passes stale positional args; every call raises TypeError and silently returns None
- **Where:** `src/dreambot/services/empire.py:476`
- **Why:** The bot calls run_sync(self._client.get_player_details, player_id, True, EMPIRE_REQUEST_TIMEOUT_SECONDS) but EmpireCore's signature is get_player_details(self, player_id, timeout=5.0) (client/client.py:625) — 4 positional args against a max of 3. Every invocation raises TypeError, which the blanket 'except Exception' at line 480 swallows into a log line and a None return. Downstream: birder.py:170 _check_bird_status always gets None, so the 'target has no active bird' safety gate (birder.py:104) is silently bypassed and troops are sent unprotected; move_detector.py:222 can never resolve mover names. This is the exact editable-path-dep failure mode: the library signature drifted (the old form evidently had a wait flag) and nothing broke at install time.
- **Fix:** Call with keyword args: run_sync(lambda: self._client.get_player_details(player_id, timeout=EMPIRE_REQUEST_TIMEOUT_SECONDS)). Stop catching bare Exception around seam calls — let TypeError crash loudly — and add a smoke test that exercises each EmpireClient method the bot wraps against the real signatures.

### Incoming-attack callbacks are registered on the initial client's GameState and orphaned after the first reconnect
- **Where:** `src/dreambot/services/incomings.py:118`
- **Why:** setup_incomings runs once at startup (bot.py:104) and registers on_incoming_attack/on_movement_recalled/on_movement_arrived on empire._client.state. But EmpireService._connect_locked (empire.py:347) builds a brand-new EmpireClient — and thus a brand-new GameState() — on every reconnect (self._client = self.account.get_client()). After the main account's first disconnect/reconnect cycle, the callbacks live on the discarded GameState and the new one dispatches to nobody: attack alerts, Twilio calls, and arrival/recall updates silently stop while the bot appears healthy. EmpireCore even documents that state 'is intentionally left running so registered callbacks keep working after a re-login' (client.py:169) — the bot defeats that by discarding the whole client instead of re-logging-in the same one.
- **Fix:** Either reuse the same EmpireClient across reconnects in EmpireService (call login() again on the existing client, matching the library's design), or have EmpireService own state-callback registration the same way it re-wires subscribe_alliance_chat in _connect_locked, re-registering all handler callbacks on the new client after every reconnect.

### Per-job service locks let two concurrent /spy jobs use the same GGE account simultaneously
- **Where:** `src/dreambot/services/spy_worker.py:453`
- **Why:** service_locks is built fresh inside every start_spy_job call, and cogs/spy.py:208 launches jobs with create_logged_task and no guard against a second invocation. Two users running /spy alliance concurrently get two disjoint lock sets over the same accounts, so castle.select + execute_instant_spy from job A interleave with job B on one connection. empire.py:118-124 documents exactly why this is unsafe: connection waiters are matched by command name FIFO, so two concurrent same-command requests on one connection receive each other's responses — wrong source castle selected, cross-matched spy results attributed to the wrong target.
- **Fix:** Move the per-account locks to module level (or onto EmpireService, like _scan_lock), or add a module-level 'job running' guard/queue so a second /spy invocation is rejected or queued.

### TwiML/XML injection: user-supplied call message interpolated into TwiML without escaping
- **Where:** `src/dreambot/services/twilio.py:53`
- **Why:** `make_call` builds TwiML by f-string interpolation of the caller-controlled `message` (and `minutes`) straight into a `<Say>` element: say_text embeds `message`, then `twiml_say = f'<Say voice="Polly.Amy">{say_text}</Say>...'`. Because `/call` passes the raw slash-command `message` arg here (cogs/twilio.py:63-67) and is itself unauthenticated, any member can inject TwiML markup, e.g. message='</Say><Dial>+1900XXXXXXX</Dial><Say>', causing Twilio to execute arbitrary verbs (<Dial>/<Play>/<Record>) during the call — enabling premium-rate toll fraud on the owner's Twilio account and call abuse. The auto-alert path also feeds a game-derived castle name into the same sink (incomings.py:704-705).
- **Fix:** Never build TwiML by string interpolation of untrusted input. Use twilio.twiml.voice_response.VoiceResponse to construct verbs (it XML-escapes text), or at minimum xml.sax.saxutils.escape() the message/target_name before embedding, and strip/deny angle brackets.

### delete_alliance_channel deletes any guild channel whose name collides with the sanitized alliance name
- **Where:** `src/dreambot/utils/channels.py:463`
- **Why:** The lookup iterates ALL text channels in the guild with only a name match, not scoped to the Tracking category (get_alliance_channel even comments 'or anywhere if just name match'). Untracking an alliance named 'General' sanitizes to 'general' and deletes the guild's #general channel; an alliance named 'Logs' would delete the bot's #logs channel. Since the loop doesn't break, every matching channel is deleted. That is irreversible data loss of a Discord channel and its history.
- **Fix:** Restrict both get_alliance_channel and delete_alliance_channel to channels inside the Tracking category (check channel.category), and ideally store the created channel's ID in db_tracked_alliance instead of matching by name.


## 🟠 Major (32)

### Dev runs editable ../EmpireCore while the production image resolves empire-core from PyPI — silent version drift
- **Where:** `Dockerfile:15`
- **Why:** pyproject tool.uv.sources pins empire-core to the local editable path, but the Dockerfile sets UV_NO_SOURCES=1 so the image installs empire-core from PyPI (uv.lock records registry source, empire_core-0.28.0 wheel). Any dreambot code written against unpublished local EmpireCore changes passes all local testing and then AttributeErrors at runtime in production. It also makes uv.lock flip-flop between `editable` and `registry` sources depending on which environment last ran `uv lock`, producing noisy diffs and ambiguity about what is actually deployed.
- **Fix:** Make the release flow explicit: publish EmpireCore first, pin `empire-core==X.Y.Z` in dreambot, and add a CI check (or verify_install-style smoke test in the image build) that imports the APIs dreambot uses. Alternatively build the wheel from ../EmpireCore into the image for lockstep deploys.

### Adminer exposed on 0.0.0.0:8080 with DB root password defaulting to 'secret' (and root == app password)
- **Where:** `docker-compose.yml:40`
- **Why:** `ports: "8080:8080"` publishes the Adminer DB admin UI on every host interface. Combined with MYSQL_ROOT_PASSWORD: ${DB_PASSWORD:-secret} — the root password silently defaults to 'secret' if the env var is missing, and is identical to the app user's password — anyone who can reach the host gets a one-form login to full root DB access (member phone numbers, encrypted GGE credentials, Twilio data). A dev convenience container has no place in the production compose file.
- **Fix:** Move adminer to docker-compose.dev.yml, or bind it to loopback ("127.0.0.1:8080:8080"). Use a separate MYSQL_ROOT_PASSWORD with no default (compose fails fast if unset: ${DB_ROOT_PASSWORD:?}).

### Unbounded 'empire-core>=0.28' on a 0.x editable path dep with zero seam tests — breakage surfaces only at runtime
- **Where:** `pyproject.toml:12`
- **Why:** The dep is an editable path (tool.uv.sources -> ../EmpireCore) with an open-ended >=0.28 constraint, and dreambot-v3 has no test suite at all (only scripts/test_moving_flags.py, a manual script). Under 0.x semantics every minor is potentially breaking, and the editable install means whatever is checked out next door is what runs — the constraint gates nothing. The get_player_details signature drift (already shipped, see critical finding) proves reasonable library changes break the bot silently at runtime, masked by broad except blocks.
- **Fix:** Pin a compatible range (empire-core>=0.28,<0.29) and bump deliberately; add a small contract-test module in dreambot that imports every empire_core symbol the bot uses and asserts the signatures it calls (inspect.signature), run in CI against the pinned version.

### on_ready sets _bootstrapped=True before the fallible bootstrap, so one startup exception leaves the bot permanently half-initialized
- **Where:** `src/dreambot/bot.py:65`
- **Why:** The guard flag is set at line 65, before ensure_channels, initialize_commander_stats (a GGE CDN HTTP fetch), GameData.initialize, pool.connect_all, and cog loading. If any of these raises (a transient CDN or Discord API error is enough), discord.py swallows the on_ready exception into its default error logger and the bot stays online with no GGE connections, no monitor, no incomings handler, and no cogs — and because _bootstrapped is already True, the re-fired on_ready after the next gateway reconnect skips bootstrap forever. Recovery requires a manual restart, and nothing alerts anyone.
- **Fix:** Run the bootstrap in a try/except: on failure reset _bootstrapped (or use an 'in progress' sentinel plus retry with backoff), log loudly, and consider moving one-time initialization to setup_hook per discord.py guidance so it isn't tied to on_ready at all.

### Cogs are loaded at the end of a long on_ready bootstrap; one uncaught exception permanently disables all commands
- **Where:** `src/dreambot/bot.py:124`
- **Why:** `_bootstrapped = True` is set at line 65, then ~60 lines of fallible work run (ensure_channels, guild.create_role catching only Forbidden — an HTTPException propagates — GGE connect_all, monitor.start(), setup_alliance_tracker) before extensions load at line 124. If any of those raises, the on_ready handler dies, cogs never load, and because the guard is already set no reconnect will retry — the bot sits online with zero working listeners/commands and only a log line to show for it. discord.py explicitly recommends loading extensions in setup_hook, before login.
- **Fix:** Move bot.load_extension calls (and ideally the GGE bootstrap) into `async def setup_hook()` on a Bot subclass, and wrap each independent bootstrap step (channels, roles, tracker, monitor) in its own try/except so one failure cannot suppress the rest.

### EmpireService facade bypassed via ._client in 8+ files, so reconnect/cooldown guards and the stable seam are routinely skipped
- **Where:** `src/dreambot/bot.py:308`
- **Why:** bot.py:308, incomings.py:118/132/142/206/277/328/411, alliance_chat.py:81, spy_worker.py:155, birder.py:70/277, views/data.py:105, and views/config.py:258/668 all reach into service._client to touch EmpireClient (and its .state/.connection) directly. Consequences: (1) references and callback registrations go stale when reconnect swaps _client (the incomings critical above is one instance); (2) every site re-invents null/hasattr guards (getattr(client, 'alliance', None) etc.); (3) there is no single choke point to adapt when empire-core's API changes, so a library refactor means auditing a dozen call sites instead of one wrapper.
- **Fix:** Make _client genuinely private: expose the handful of needed operations on EmpireService (typed accessors for alliance/ranking/spy services, state snapshots, castle list) and route all cogs/views/services through them. If a raw-client escape hatch is truly needed, make it one explicit property with a documented staleness contract.

### /bird Details embed field concatenates one line per castle with no 1024-char cap
- **Where:** `src/dreambot/cogs/birder.py:137`
- **Why:** Each result line is roughly 40-80 chars ('✅ **{castle}**: Sent 1,234 units...'); an account with ~15+ castles pushes the field value past Discord's 1024-char field limit, so edit_original_response raises HTTPException 400 and the command's outer except reports 'An unexpected error occurred' — precisely for the power users the command exists for. BirdsView.create_embed (views/data.py:49) shows the codebase knows to slice to 1024; this site doesn't.
- **Fix:** Truncate the joined value to 1024 chars (as BirdsView does) or split the lines across multiple fields/embeds.

### /call command invokes the sync Twilio SDK directly inside the async command handler
- **Where:** `src/dreambot/cogs/twilio.py:63`
- **Why:** Same defect as incomings._make_call: `success = self.twilio.make_call(...)` inside `async def call` blocks the event loop for the duration of the Twilio HTTPS request (unbounded, since the default Twilio http client has no timeout). Any user running /call freezes every other command, alert, and the Discord heartbeat until the API responds. The deferred interaction (line 61) hides the latency from the caller but not from the rest of the bot.
- **Fix:** success = await asyncio.to_thread(self.twilio.make_call, to=member["phone"], minutes=minutes, message=message)

### _save_member_states runs DELETE and upsert as two separate autocommitted transactions
- **Where:** `src/dreambot/services/alliance_tracker.py:487`
- **Why:** The stale-member DELETE (lines 482-495) and the INSERT ... ON DUPLICATE KEY UPDATE (line 515) each go through execute_async/execute_many_async, which acquire different pooled connections and commit independently. If the process dies or the insert fails between them (e.g. the PoolError above, DB restart), the member table is half-applied: departed members are gone but current state was not written, so the next poll emits duplicate join/change alerts and lost bird/moving state. Ironically db.py ships transaction()/transaction_async (db.py:222/255) built for exactly this, and they have zero call sites.
- **Fix:** Wrap the DELETE + executemany upsert in a single transaction_async([...]) call (or the transaction() context manager) so member-state replacement is atomic.

### Birder hand-rolls SendSupportRequest/SelectCastleRequest with magic protocol values instead of using CastleService
- **Where:** `src/dreambot/services/birder.py:375`
- **Why:** The bot builds SendSupportRequest(WT=12, BPC=1, HBW=-1, PTT=1, SD=0, LID=...) and sends SelectCastleRequest directly (birder.py:292), duplicating the exact defaults and semantics EmpireCore already encapsulates in client.castle.send_support (services/castle.py:151, same WT/BPC/HBW/PTT/SD fields with documented meanings) and client.castle.select (castle.py:91). The magic lord sentinel -14 (birder.py:363) is likewise a library constant (castle.py:163). If the library ever adjusts these fields for a game update, the birder's copies silently diverge and troops get sent with wrong parameters.
- **Fix:** Rewrite _send_support_from_castle to call client.castle.select() and client.castle.send_support(..., lord_id=current_lord_id); drop the protocol-model imports and the -14 literal (expose it as a named constant in EmpireCore if needed).

### Reverse-engineered gaa packet field indices (player id = field 4, relocation flag = field 19) hardcoded in the bot
- **Where:** `src/dreambot/services/empire.py:68`
- **Why:** scan_kingdom_moving_flags (empire.py:578-582) indexes item.raw_data[4] and raw_data[19] with a 15-line comment documenting the server's 20-field castle entry layout. This is pure wire-protocol knowledge that belongs in empire_core.protocol.models.map (which currently gets it wrong — see the paired EmpireCore finding). Any GGE-side layout change must now be discovered and fixed in the bot, not the library, and every other library consumer will re-derive the same indices.
- **Fix:** Move the field knowledge into MapAreaItem as typed properties (player_id, is_relocating) and have the bot consume those; keep the bot free of raw_data indexing.

### _on_alliance_chat re-implements chat decoding inline with the replacement order the library explicitly documents as wrong
- **Where:** `src/dreambot/services/empire.py:310`
- **Why:** The bot parses raw packet payload keys (CM/PN/PID/MT) and chains .replace() calls doing '&percnt;'->'%' first and '%5C'->'\\' last. EmpireCore's decode_chat_text (protocol/models/base.py:389-391) decodes '%5C' BEFORE '&percnt;' with a comment explaining why: a user who types a literal '%5C' (wire-encoded '&percnt;5C') gets double-decoded into a backslash under the bot's order. The library already ships the correct decoder AND a typed subscription (client.alliance.on_chat_message delivering AllianceChatMessageResponse.decoded_text, services/alliance.py:302); the bot uses neither, so the duplicated protocol knowledge has already diverged into a bug.
- **Fix:** Replace _on_alliance_chat's hand parsing with client.alliance.on_chat_message and msg.decoded_text (or at minimum call decode_chat_text from empire_core.protocol.models), and delete the inline replace chain.

### Attack alert coroutine can die silently before its try/except, permanently suppressing the alert
- **Where:** `src/dreambot/services/incomings.py:244`
- **Why:** _on_incoming_attack inserts the MID into _active_incomings (line 228) and then schedules _alert_incoming_with_sdi via asyncio.run_coroutine_threadsafe with the returned Future discarded (line 235). The first statements of that coroutine — _is_attacker_ignored (two MySQL queries) and ensure_connected — run outside any try/except; only the later _alert_incoming call has its own handler. A transient DB error therefore raises out of the coroutine, the exception is stored in the discarded concurrent Future and never logged anywhere, and because the MID is already tracked, the duplicate-check at line 181 ensures the attack is never re-alerted. Net effect: a DB hiccup at the wrong moment silently swallows an attack alert — the bot's core function — with zero log output.
- **Fix:** Wrap the whole body of _alert_incoming_with_sdi in try/except with logging (and remove the MID from _active_incomings on failure so a later packet can re-alert), and add a run_coroutine_threadsafe wrapper analogous to create_logged_task that attaches a done-callback logging Future exceptions (also applies to empire.py:363, incomings.py:191/301).

### Attack-alert path performs a blocking GGE network round-trip directly on the event loop via _get_online_status_emoji
- **Where:** `src/dreambot/services/incomings.py:564`
- **Why:** _get_online_status_emoji is a sync method called without to_thread from async _alert_incoming (line 564) and _update_incoming_embed (line 617). Internally (line 421) it calls alliance_service.get_member(player_id, no_cache=True), which in empire-core (services/alliance.py get_member -> get_members -> client.request) sends a GetAllianceInfoRequest and blocks on threading.Event.wait for up to the 5s default timeout. Every incoming-attack alert and every embed update therefore freezes the entire bot — Discord heartbeat, other alerts, Twilio calls — for up to ~5s, precisely during attack waves when many alerts fire back-to-back. The neighboring _query_defender_count was correctly wrapped in asyncio.to_thread; this one was missed.
- **Fix:** Wrap the lookup in the executor like the SDI query: `online_status = await asyncio.to_thread(self._get_online_status_emoji, info.defender_id)` at both call sites (564 and 617), and make _get_online_status_emoji's docstring say it blocks.

### Blocking Twilio HTTPS call on the event loop in async _make_call, with no HTTP timeout
- **Where:** `src/dreambot/services/incomings.py:705`
- **Why:** TwilioService.make_call (services/twilio.py:56, self.client.calls.create) is a synchronous HTTPS request via the requests-based Twilio SDK, and TwilioService constructs Client() with the default http_client whose timeout is None. Calling it directly inside `async def _make_call` freezes the entire event loop for the full API round-trip — and indefinitely if the connection stalls, since there is no timeout. This is in the incoming-attack alert path, so a slow Twilio API turns every urgent attack alert into a bot-wide stall.
- **Fix:** Change to `await asyncio.to_thread(twilio.make_call, phone, minutes, message)` and construct the Twilio Client with an explicit timeout (e.g. TwilioHttpClient(timeout=10)).

### Moving-flags cache can never transition to empty, so stale 'castle moving' state persists indefinitely
- **Where:** `src/dreambot/services/move_detector.py:60`
- **Why:** `if flags: self._moving_flags_cache = flags` only replaces the cache when the scan returns a non-empty dict, but scan_kingdom_moving_flags returns {} both on failure and when the last mover has genuinely settled. Once populated, the cache can only shrink when some other mover appears; in a quiet kingdom, players who finished relocating stay flagged as moving for hours or days. Downstream, alliance_tracker._fetch_alliance_members keeps setting member.moving_to from these stale flags, so CASTLE_MOVING 'finished' transitions never fire and the tracked DB state is wrong.
- **Fix:** Distinguish failure from genuinely-empty: have scan_kingdom_moving_flags return None on scan failure and a (possibly empty) dict on success, then assign the cache unconditionally on success.

### Query filters on db_linked_accounts.player_id, but no code path ever populates that column
- **Where:** `src/dreambot/services/move_detector.py:158`
- **Why:** Schema drift between the query and the writers: the only INSERT into db_linked_accounts (views/registration.py:629) supplies (discord_id, username, encrypted_password) and never sets player_id; no UPDATE touches it anywhere in src. Only rows backfilled by migration 0011's INSERT...SELECT have player_id. So move warnings for linked accounts silently never fire for any account added through the Add Game Account modal — a feature that appears to work only for legacy data.
- **Fix:** Resolve the player_id at link time (empire search_player_by_name is already used elsewhere, e.g. AddIgnoredAttackerModal) and store it on insert, or join db_linked_accounts.username against known player names instead of the always-NULL player_id.

### Spy retry/exhaustion logic keyed on string-matching library-manufactured reason tags and substring '105'
- **Where:** `src/dreambot/services/spy_worker.py:62`
- **Why:** SpyResult.reason values ('no_spies_available', 'spy_caught', 'ssi_failed_<tag>', 'sne_timeout_or_error') are free-form strings assembled inside empire_core/services/spy.py; spy_worker classifies them via startswith/substring tables (_FEATHER_EXHAUSTION_REASONS, _TRANSIENT_FAILURE_PREFIXES) to decide whether to retry a target or permanently drop an account from the run. A library rename breaks classification silently. Worse, '"105" in raw' matches ANY reason containing 105 (e.g. a CommandError code 1050 rendered as 'csm_failed_1050', or coordinates embedded in an exception string), wrongly marking the account feather-exhausted and requeueing its targets.
- **Fix:** Make SpyResult.reason a typed enum (or add SpyResult.error_code: int and SpyResult.is_exhausted/is_transient properties) in EmpireCore, and have spy_worker branch on those instead of strings; replace '"105" in raw' with an exact error-code comparison.

### Spy worker ignores ensure_connected() result — a dead account keeps consuming and burning targets from the shared queue
- **Where:** `src/dreambot/services/spy_worker.py:153`
- **Why:** `await service.ensure_connected()` discards the bool. If the account cannot reconnect (e.g. login cooldown, which ensure_connected enforces by returning False immediately), the worker still calls execute_instant_spy, which raises; the reason normalizes to 'not_connected', which _is_transient_failure treats as retryable, so the worker burns 3 attempts (each with a 1-2s pre-sleep) and appends the target to failed_targets. Because the kingdom queue is shared, this broken worker keeps pulling targets that healthy workers on other accounts could have served — a mid-job disconnect on one account converts a slice of the run into permanent failures instead of redistributing.
- **Fix:** Check the return value: if ensure_connected() is False, requeue the target (queue.put_nowait) and break out of the worker like the feather-exhaustion path does; also re-fetch service.spy after a reconnect since the SpyService bound at line 148 belongs to the pre-reconnect client for the remaining attempts of that target.

### All sync work shares asyncio's small default executor, so 300-second kingdom scans starve DB queries and commands
- **Where:** `src/dreambot/utils/async_utils.py:33`
- **Why:** run_sync and every *_async DB helper use asyncio.to_thread, i.e. the default ThreadPoolExecutor sized min(32, cpu_count+4) — 5-6 threads on the 1-2 vCPU containers this compose file targets (no cpu limits, no set_default_executor anywhere). Kingdom scans hold a thread for up to timeout=300s each: property_scanner gathers up to 4 concurrent _scan_for_account tasks (property_scanner.py:174), the move-detector pooled scan adds one thread per tracking account every 45s, and spy jobs one per spy account. During overlap, every query_async/execute_async and to_thread'd GGE call queues behind multi-minute scans — commands time out, incoming alerts stall, and the bot looks hung while technically alive. Verify by logging executor queue depth or ThreadPoolExecutor._work_queue.qsize() under a property scan on a 2-core host.
- **Fix:** Give long-running scans a dedicated ThreadPoolExecutor (loop.run_in_executor(scan_pool, ...)) sized to the number of scan accounts, or call loop.set_default_executor(ThreadPoolExecutor(max_workers=32)) at startup so short DB/GGE calls never queue behind scans.

### General attackBonus (effectTypeID 36) is never added to ranged — the promised duplication code path is dead
- **Where:** `src/dreambot/utils/commander_stats.py:174`
- **Why:** _type_to_mapping stores typeID 36 as AttackCategory.MELEE with a comment saying 'we'll duplicate to ranged in calculate()'. But nothing ever writes to general_attack_by_cap: _accumulate_effects receives the `general_attack` parameter and never touches it (its own comment at lines 276-279 admits 'For simplicity, we'll just use the category as stored'), and the account-effects loop also writes only raw_stats. So the loop at line 244 that adds general attack to both melee and ranged iterates an always-empty dict. Any commander with a general attackBonus shows an understated Ranged bonus in attack alerts — wrong intel in the bot's flagship feature. It also merges typeID-36 values into the melee cap bucket, distorting cap application.
- **Fix:** Give typeID 36 its own AttackCategory.GENERAL (or a flag on EffectMapping), route it into general_attack_by_cap in both _accumulate_effects and the account-effects loop, then keep the existing dual-add loop. Add a unit test with a typeID-36 effect asserting melee == ranged.

### No connection or query timeout on any DB call — a hung MySQL server permanently exhausts the pool
- **Where:** `src/dreambot/utils/db.py:43`
- **Why:** The pool is created without connection_timeout (mysql-connector's DEFAULT_CONFIGURATION['connection_timeout'] is None, verified in constants.py:74), so sockets block indefinitely. A network partition, DB failover, or long lock wait blocks the to_thread worker forever while it holds a pooled connection. Five such hung queries and every subsequent DB call raises PoolError until the process is restarted — the long-running bot's worst failure mode, and query_async callers await these threads forever with no asyncio timeout either.
- **Fix:** Pass connection_timeout (e.g. 10) to MySQLConnectionPool, set a server-side cap via init_command/session variable (SET SESSION max_statement_time / max_execution_time), and consider asyncio.wait_for around the to_thread wrappers as a last-resort bound.

### MySQL pool_size=5 with unbounded to_thread concurrency: get_connection raises PoolError instead of queueing
- **Where:** `src/dreambot/utils/db.py:45`
- **Why:** mysql.connector's MySQLConnectionPool.get_connection() raises PoolError('Failed getting connection; pool exhausted') immediately when all connections are checked out — it does not block. Every query/execute helper runs on its own executor thread with no concurrency cap, and the tracker loop, property scanner, incomings alerts, verification, and user commands all issue DB calls concurrently; a burst of more than 5 simultaneous queries makes the 6th raise, which surfaces as random command failures and (in the tracker) triggers the exponential backoff path for what is really a self-inflicted burst. Verify by firing 8 concurrent query_async calls in a test.
- **Fix:** Raise pool_size (e.g. 10-16, at most the executor size), and/or gate DB access with an asyncio.Semaphore(pool_size) in the *_async wrappers, or retry get_connection with a short backoff on PoolError.

### get_last_insert_id() is broken by design: reads LAST_INSERT_ID() on a different pooled connection
- **Where:** `src/dreambot/utils/db.py:217`
- **Why:** LAST_INSERT_ID() is per-session. execute() returns its connection to the pool after commit, and pool_reset_session=True issues COM_RESET_CONNECTION on return, which clears last_insert_id. query_one() then grabs a (reset) connection, so this helper returns 0 — or, if reset ever fails, an unrelated session's stale value. It currently has zero call sites, so it is a dead landmine: the first person who uses it for an FK insert writes wrong IDs silently.
- **Fix:** Delete it (and get_last_insert_id_async), or make execute() return cursor.lastrowid (available on the same cursor before the connection is released) via a variant like execute_returning_id().

### Every interactive view uses timeout=None without persistent-view registration — unbounded view accumulation on a long-running bot
- **Where:** `src/dreambot/views/config.py:33`
- **Why:** BotConfigView, SpySettingsView, SpyRoleSelectView, AddAllianceSelectView, RemoveAllianceView, BirdsView (views/data.py:22), EventRolesView (views/roles.py:12) and five views in registration.py all pass timeout=None, and `grep add_view` shows no bot.add_view call anywhere. discord.py keeps a non-persistent view in its internal view store until it times out or is stopped — with timeout=None that is never, so every /config, /data, /setup invocation leaks a View plus its captured embeds/search results for the life of the process. And since none are registered as persistent views, their components still die on restart, so timeout=None buys nothing.
- **Fix:** Give ephemeral/interactive views a finite timeout (e.g. 300-900s) with an on_timeout that disables components, or implement true persistent views (stable custom_ids + bot.add_view in setup_hook) for the ones that must survive restarts.

### Views and scripts reach into EmpireService private internals (_client, _run_sync)
- **Where:** `src/dreambot/views/config.py:258`
- **Why:** views/config.py (lines 258, 265, 668, 672), views/data.py (lines 105, 108, 846) and scripts/test_moving_flags.py (lines 38, 43-48) all access `empire._client` / `service._run_sync` and then getattr sub-services off the raw client. This couples UI code to EmpireCore's private client wiring: any internal refactor of EmpireService (the whole point of making empire-core publishable) silently breaks the /config and /data views, and the getattr(...,'ranking', None) guards hide the breakage as 'service not available' instead of failing loudly. bot.py's memory command does the same (service._client at line 308).
- **Fix:** Add public accessors/facade methods on EmpireService (e.g. search_alliances(), get_highscore(), members()) and use those from views; keep _client strictly private to services/empire.py.

### RankingDashboardView strips the view for 'Fetching Data...' then fetches with no error handling — an exception leaves a permanently dead message
- **Where:** `src/dreambot/views/data.py:535`
- **Why:** _metric_callback, _alliance_filter_callback, and clear_alliance_filter edit the message with view=None, then await fetch_ranking_report, whose search_alliances/get_members/get_highscore calls raise on a dropped GGE connection (only the per-member loop swallows exceptions). If it raises, edit_original_response is never reached: the message is stuck on 'Fetching Data...' with zero components and the user gets no error (default View.on_error only logs). fetch of a 50-member alliance is also serialized behind a Semaphore(1), so this window is long (tens of seconds to minutes). No view in the codebase overrides on_error.
- **Fix:** Wrap the fetch in try/except, restoring the view with an error embed on failure; implement on_error on these views (or a shared base view) to surface failures and re-attach components.

### Known 'hgh'/'gai' response cross-matching is only guarded per-invocation, not per-connection
- **Where:** `src/dreambot/views/data.py:778`
- **Why:** empire-core matches responses to waiters FIFO by command id (network/connection.py _route_packet), and its own docs warn that search_alliances and get_highscore share 'hgh' and cannot be correlated. dreambot serializes hgh only with a Semaphore(1) that is local to one _fetch_alliance_member_rankings call; concurrent entry points on the same pooled main account — another user's ranking view, spy _resolve_alliance (cogs/spy.py:52), birds view (views/data.py:81), config view (views/config.py:678), plus 'gai' collisions between incomings._refresh_alliance_members/_get_online_status_emoji and views' get_members — run unserialized. When two same-command requests overlap, responses are swapped: users see the wrong alliance's members/rankings and empire-core's _members cache is poisoned, which then feeds wrong activity tiers into attack alerts. The EmpireService._scan_lock comment shows the team knows about this failure mode but guarded only gaa scans.
- **Fix:** Add per-command asyncio.Locks on EmpireService (like _scan_lock) and route all hgh ('search_alliances'/'get_highscore') and gai ('get_members'/'get_local_members'/'get_alliance_info') calls through them, so requests sharing a command id are serialized per connection.

### Every interactive view uses timeout=None but is never registered with bot.add_view — unbounded memory growth and dead components after restart
- **Where:** `src/dreambot/views/registration.py:52`
- **Why:** SettingsView, PingEditor, UnlinkAccountView, UnlinkIdentityView, IgnoredAttackersView (registration.py), BirdsView (data.py:22), BotConfigView/SpySettingsView/SpyRoleSelectView/AddAllianceSelectView/RemoveAllianceView (config.py), and EventRolesView (roles.py:12) all pass timeout=None. discord.py's ViewStore holds a strong reference to a view until it stops or times out; timeout=None views therefore accumulate forever — one leaked view (plus captured DB rows) per /setup, /config, /data birds invocation and per sub-navigation (IgnoredAttackersView even instantiates a fresh view per select at line 698). Meanwhile `grep add_view` finds no bot.add_view call, so after a restart every one of these buttons/selects answers 'This interaction failed' anyway — the worst of both persistence models.
- **Fix:** Give these views a finite timeout (e.g. 10-15 min) with on_timeout disabling components, or make them true persistent views (stable custom_ids on every component, state loaded from DB in the callback, registered via bot.add_view in setup_hook).

### Phone numbers (PII) stored in plaintext at rest despite available Fernet encryption
- **Where:** `src/dreambot/views/registration.py:364`
- **Why:** Members' real phone numbers are written to db_member.phone in cleartext (UPDATE db_member SET phone = %s) and the column is a plain VARCHAR(20) (migrations/0000_initial_schema.sql:7). The codebase already has cryptography/Fernet infrastructure (utils/security.py) which it uses for game passwords, yet PII phone numbers — the most sensitive data the bot holds — are unencrypted. A DB dump, backup leak, or SQL-injection elsewhere exposes every member's E.164 phone number. This is a GDPR/PII-at-rest exposure a production service should not ship.
- **Fix:** Encrypt phone at rest with the existing Fernet cipher (add encrypt_phone/decrypt_phone alongside encrypt_password), decrypt only in the call path (incomings._make_call, cogs/twilio.call). Widen the column to hold ciphertext and add a migration to encrypt existing rows.

### Ping-target editor deletes all subscriptions before re-inserting, non-transactionally
- **Where:** `src/dreambot/views/registration.py:472`
- **Why:** PingEditor.user_select issues DELETE FROM db_ping_targets (line 472) and then a separate execute_many_async INSERT (line 477) on different connections/transactions. If the insert fails (pool exhausted, DB blip, duplicate-key edge), the user's entire subscription list is silently wiped — data loss triggered by a routine settings edit, with no error surfaced because the exception propagates out of the interaction handler.
- **Fix:** Use transaction_async([(delete_sql, params, False), (insert_sql, rows, True)]) so clear+reinsert is atomic; alternatively diff the selection and only insert/delete the changed rows.

### AddIgnoredAttackerModal.on_submit does a GGE network round-trip before acknowledging the interaction
- **Where:** `src/dreambot/views/registration.py:738`
- **Why:** Modal submissions have the same 3-second acknowledgement deadline as commands. `await empire.search_player_by_name(name)` is a request/response over the game websocket (backed by the sync client); if the game server is slow or the connection is reconnecting, the subsequent interaction.response.send_message/edit_message at lines 742/758 fails with 404 Unknown interaction and the user's input is silently lost.
- **Fix:** defer() (thinking) first in on_submit, then perform the player search and respond via followup/edit_original_response.


## 🟡 Minor (37)

### Docker build runs `uv sync` without --locked, so uv.lock is not actually enforced
- **Where:** `Dockerfile:19`
- **Why:** Without --locked/--frozen, uv will quietly re-resolve and rewrite the lockfile inside the image whenever pyproject.toml and uv.lock disagree (which happens routinely here because the lock flips between editable and registry sources for empire-core). Two builds of the same commit can then contain different dependency versions — the lockfile provides no reproducibility guarantee.
- **Fix:** Use `uv sync --locked --no-install-project --no-dev` (and `uv sync --locked --no-dev` for the second step) so the build fails loudly when the lock is stale.

### TODO.md is rotting — multiple items marked 'Not Started' are fully implemented
- **Where:** `TODO.md:90`
- **Why:** Cross-checked against the code: 'Discord → Game relay' and 'Game → Discord relay' are marked ⬜ but services/alliance_chat.py implements both (_broadcast_to_discord, send_to_game) with a cogs/chat.py on_message bridge and an enable/disable toggle in /config; 'Mass spy command' and 'Spy results channel' (lines 65-67) are marked ⬜ but /spy alliance exists (cogs/spy.py:76) with spy_worker, SpySettingsService risk/threshold/exclusions/roles, and a spy-reports channel; 'Bot logs channel' (line 142) is marked ⬜ while channels.py defines a managed 'logs' channel. A roadmap that contradicts the code misleads contributors and hides what is actually pending.
- **Fix:** Do a sweep updating the legend markers (chat bridge ✅, mass spy ✅/🟡, spy results channel ✅, logs channel 🟡), or move the roadmap into tracked issues so it cannot silently drift.

### Personal debugging scratch files committed at repo root with hardcoded home-directory paths
- **Where:** `get_bsd_example.py:3`
- **Why:** get_bsd_example.py opens /home/eschnitzler/gbd_output.json (exists only on the author's machine); verify_install.py greps the installed empire_core source for 'roundTrip'/'vck' strings; scripts/test_moving_flags.py hardcodes /home/eschnitzler/EmpireCore/accounts.json and a real account name ('Heimlina', line 22). None run anywhere but the author's box, they use print() instead of logging, and they leak deployment details (real account names, paths) into a repo intended to back a production service.
- **Fix:** Delete get_bsd_example.py and verify_install.py (or move them under scripts/ behind env-var-configured paths); parameterize scripts/test_moving_flags.py via argparse/env vars and strip the real account name.

### Schema and queries are MariaDB-only dialect despite MySQL branding everywhere
- **Where:** `migrations/0004_alliance_tracking.py:28`
- **Why:** Unquoted `rank` column (reserved word in MySQL 8.0.2+; also used unquoted in alliance_tracker.py:421 SELECT and :518 INSERT), `CREATE INDEX IF NOT EXISTS` (0004:50, 0007:23, 0008), and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (0001, 0002, 0009, 0013) are all syntax errors on real MySQL. It works today only because docker-compose.yml pins mariadb:10.11, but every other signal (mysql-connector-python dep, mysql:// URL, MYSQL_* env vars, 'mysql wrapper' docstring) tells an operator MySQL is fine — pointing DB_HOST at MySQL 8 fails migration 0004 and every member-state query.
- **Fix:** Backtick-quote `rank` (or rename to alliance_rank) in migrations and queries, replace IF NOT EXISTS index/column DDL with plain statements (migrations run once under yoyo's ledger anyway), or explicitly document/enforce MariaDB as the only supported engine.

### Dead tables: db_bot_managed_accounts and db_location_capture have no readers or writers
- **Where:** `migrations/0014_bot_managed_accounts.sql:2`
- **Why:** Neither table name appears anywhere under src/ (grep confirms zero references); db_location_capture (migration 0007) was superseded by the in-memory _reported_captures set in property_scanner.py. Dead schema misleads anyone reasoning about the data model and accretes in backups/migrations forever.
- **Fix:** Add a migration dropping both tables (with the create statements as the rollback step), or document why they are reserved for future use.

### Two MySQL drivers shipped: mysql-connector-python for the app, pymysql only as yoyo's implicit dependency
- **Where:** `pyproject.toml:14`
- **Why:** pymysql is imported nowhere in src/ — it exists solely because yoyo's mysql:// backend hardcodes driver_module = 'pymysql' (verified in yoyo/backends/core/mysql.py:19). Neither is dead, but the coupling is invisible: nothing in pyproject or yoyo.ini says why pymysql is required, so it is one 'cleanup' away from breaking startup migrations, and the two drivers can disagree on type conversions between migration DML (0011's INSERT...SELECT) and app queries.
- **Fix:** Standardize on pymysql (it satisfies both yoyo and a small pooled wrapper via pymysql + DictCursor), dropping mysql-connector-python; at minimum add a comment on the pymysql dependency: 'required by yoyo mysql:// backend'.

### Raw exception text echoed to Discord users leaks internal/DB details
- **Where:** `src/dreambot/bot.py:160`
- **Why:** The global app-command error handler sends f"An error occurred: {error}" to the user, and several handlers echo raw exceptions: cogs/birder.py:79/155 (f"❌ Connection error for '{username}': {e}", f"...: {str(e)}"), views/registration.py:539/591/701/764 (f"❌ Failed ...: {e}"), views/config.py:726 (f"Failed to search: {e}", non-ephemeral). Raw exceptions can surface SQL fragments, table/column names, stack context, and connection strings to end users, aiding attackers and, in the birder path where a decrypted password is in scope, risking credential exposure in an unexpected error message.
- **Fix:** Log the full exception server-side (logger.exception) and reply with a generic message plus a correlation id. Never interpolate raw {e}/{error} into user-facing content.

### /memory command iterates gc.get_objects() with sys.getsizeof on the event loop
- **Where:** `src/dreambot/bot.py:286`
- **Why:** gc.get_objects() on a long-running bot returns hundreds of thousands to millions of objects; the tight for-loop calling sys.getsizeof on each (plus tracemalloc.take_snapshot()/statistics above it) is pure CPU with no awaits, blocking the loop for multiple seconds. During that stall, heartbeats, alerts, and commands freeze — ironically the diagnostic command degrades the thing it inspects. Owner-only, so impact is bounded, but it is exactly a tight loop starving the loop.
- **Fix:** Move the snapshot/statistics and the gc.get_objects sizing loop into asyncio.to_thread (both are thread-safe reads), keeping only the Discord sends on the loop.

### Migration DB URL built with unescaped credentials
- **Where:** `src/dreambot/bot.py:334`
- **Why:** run_migrations() f-strings DB_PASSWORD straight into a URL. A password containing '@', '/', ':' or '%' breaks urlsplit-based parsing in yoyo, so the bot fails at startup with a confusing connection error. Verify by setting DB_PASSWORD='p@ss/word' and starting the bot.
- **Fix:** Use urllib.parse.quote(os.environ['DB_PASSWORD'], safe='') (and for user/host) when building the URL.

### Migrations path Path(__file__).parent.parent.parent only works because uv installs the project editable
- **Where:** `src/dreambot/bot.py:337`
- **Why:** From an editable install, __file__ is under src/dreambot so three .parents lands at the repo/app root where migrations/ was COPYed. Under any non-editable install (pip install dreambot, uv sync --no-editable, building the wheel — which per pyproject packages only src/dreambot), the path resolves to a site-packages ancestor with no migrations directory, and yoyo silently finds zero migrations, letting the bot start against an unmigrated schema and crash later on missing tables. Same editable-only trap as the cogs_path glob at line 119 (glob just returns nothing from a wheel without the .py files... it works today only via editable layout).
- **Fix:** Ship migrations as package data (src/dreambot/migrations + importlib.resources) or make the path explicit via a MIGRATIONS_PATH env var that the Dockerfile sets; fail hard if the directory is empty/missing.

### _shutdown never stops the incomings/alliance-chat/verification handlers or in-flight spy jobs
- **Where:** `src/dreambot/bot.py:368`
- **Why:** _shutdown stops only the monitor and tracker before disconnect_all(). IncomingsHandler, AllianceChatService, and VerificationHandler keep their callbacks registered on clients being torn down, and a running spy job (fire-and-forget task from cogs/spy.py:208) keeps calling execute_instant_spy against closing connections during the drain, producing spurious error logs and a noisy, nondeterministic shutdown. None of the cogs define cog_unload, so a cog reload also detaches nothing.
- **Fix:** Have _shutdown call get_incomings_handler().stop(), get_alliance_chat_service().stop(), get_verification_handler().stop(), and track/cancel outstanding spy job tasks (keep them in a module-level set in spy_worker) before disconnect_all().

### /bird cog tears down via client.connection.disconnect instead of client.close(), skipping state shutdown
- **Where:** `src/dreambot/cogs/birder.py:95`
- **Why:** The cog reaches into client.connection for both connect (line 69 — redundant, login() already connects) and disconnect. client.close() (EmpireCore client.py:269) additionally calls state.shutdown() to stop the GameState callback executor and clears is_logged_in; bypassing it means any lazily-created executor threads outlive the throwaway per-command client in a long-running bot, and future cleanup added to close() will be silently skipped.
- **Fix:** Use client.login() / client.close() only; remove the direct connection.connect/disconnect calls.

### Alliance-chat bridge deletes and reposts the user's message before confirming delivery to the game
- **Where:** `src/dreambot/cogs/chat.py:66`
- **Why:** on_message deletes the original, reposts a formatted copy, then calls service.send_to_game last with no error handling. If the game connection is down, send_to_game raises (swallowed by discord.py's listener error logging): Discord shows the message as bridged while it never reached the game, and the user gets no feedback. The original content is already destroyed so nothing can be retried.
- **Fix:** Send to the game first (or wrap in try/except); only delete/repost after success, and post a visible '⚠️ not delivered to game' notice on failure.

### /data birds, /data property, /data rankings have no authorization check
- **Where:** `src/dreambot/cogs/data.py:49`
- **Why:** None of the three DataCog commands (birds:49, property:72, rankings:107) apply any role/admin check, so any member of any guild the bot is in can pull tracked-alliance intelligence (support/bird status, capital/metro ownership, rankings). This isn't member PII, but it exposes competitively sensitive scouting data with no gate, unlike the analogous /spy command which enforces _is_authorized. For a production deployment this should be an explicit access decision rather than open-by-default.
- **Fix:** Decide the intended audience and enforce it (e.g. app_is_bot_admin() or a configurable authorized-role check like SpySettingsService.get_roles), consistent with /spy and /config.

### /spy alliance asserts interaction.guild is not None but is not marked guild-only
- **Where:** `src/dreambot/cogs/spy.py:83`
- **Why:** SpyCog has no @app_commands.guild_only() and commands are synced globally, so the command is invocable from DMs where interaction.guild is None; the bare `assert` then raises AssertionError, surfacing as 'An error occurred: ...' from the tree handler. Asserts are also stripped under python -O. Same pattern in the config views (assert interaction.guild_id is not None).
- **Fix:** Decorate the cog/commands with @app_commands.guild_only() (or set allowed_contexts) and replace the asserts with a graceful 'server only' reply.

### channel_created_note is dead logic — never shown because settings['channel_id'] is set just before the check
- **Where:** `src/dreambot/cogs/spy.py:199`
- **Why:** When the spy channel is auto-created, line 112 assigns settings["channel_id"] = channel.id; line 199 then tests `if not settings.get("channel_id")`, which is now always falsy, so the '(auto-created #channel)' note can never appear. Harmless today but it hides the auto-creation from admins and will confuse anyone editing this code.
- **Fix:** Capture a boolean `was_auto_created = channel_id is None` before mutating settings and use that in the message.

### Dead constant EXCLUSIVES_CHANNEL and hardcoded personal guild ID in config.py
- **Where:** `src/dreambot/config.py:8`
- **Why:** EXCLUSIVES_CHANNEL (a raw Discord snowflake) is referenced nowhere in the codebase — dead code. TEST_GUILD_ID is a hardcoded snowflake for "Colossus's server" used in bot.py sync and verification.py guild ordering; any other deployment silently gets global-only sync and arbitrary guild ordering. Server-specific IDs belong in the environment, not the source.
- **Fix:** Delete EXCLUSIVES_CHANNEL; read TEST_GUILD_ID from an env var (TEST_GUILD_ID=... in .env) with a None default that disables test-guild fast sync.

### Dead duplicated moving-flags code in AllianceTracker
- **Where:** `src/dreambot/services/alliance_tracker.py:315`
- **Why:** _get_cached_moving_flags (315-335), _parse_moving_coords (305-313), and the _moving_flags_cache/_last_moving_scan fields (74-75) duplicate MoveDetector.get_cached_moving_flags and are never called anywhere (verified by grep). Leftover from the MoveDetector extraction; a future editor could 'fix' the wrong copy — notably this dead copy lacks the pooled-scan path the live one relies on.
- **Fix:** Delete _get_cached_moving_flags, _parse_moving_coords, _moving_flags_cache, and _last_moving_scan from AllianceTracker.

### stop() cannot cancel in-flight _on_service_disconnect handlers, which can re-login an account during shutdown
- **Where:** `src/dreambot/services/connection_monitor.py:55`
- **Why:** Disconnect callbacks are scheduled from the receive thread via run_coroutine_threadsafe with the future discarded (empire.py:363) and never tracked by the monitor. stop() removes future callbacks and cancels the loop task, but an already-scheduled handler is mid `await asyncio.sleep(15.0)`; if _shutdown's disconnect_all() completes inside that window, the handler wakes and calls _check_service -> ensure_connected() -> a fresh GGE login after the bot has 'logged out', leaving an orphaned session and receive/keepalive threads. Narrow window, but shutdown races are exactly when a disconnect event is likely pending. Verify by dropping a connection ~5s before SIGINT and watching for a post-'All accounts disconnected' login in logs.
- **Fix:** Track handler tasks in a set (create them via create_logged_task from a small sync trampoline), cancel them in stop(), and/or add a self._stopped flag checked at the top of _check_service.

### Reconnect attempts have no client-side backoff (and the error path double-sleeps)
- **Where:** `src/dreambot/services/connection_monitor.py:62`
- **Why:** The monitor retries ensure_connected() every 30s indefinitely; the only throttle is a server-announced login cooldown (empire.py:376-387). During a prolonged GGE outage every account gets a full connect+login attempt every 30s forever, plus additional attempts from the tracker/scanner paths that also call ensure_connected. Separately, the except branch at line 68 sleeps CONNECTION_MONITOR_INTERVAL_SECONDS and then the loop's own sleep at line 62 runs again, doubling the interval after any error.
- **Fix:** Add exponential backoff per account in _check_service (e.g. min(30 * 2**attempts, 600)) reusing the existing _reconnect_attempts counter, and drop the extra sleep in the except branch.

### Cancelling a scan releases _scan_lock while the scan thread keeps running, voiding the lock's guarantee
- **Where:** `src/dreambot/services/empire.py:229`
- **Why:** asyncio.to_thread work cannot be cancelled: when tracker.stop()/property_scanner.stop() cancels a task blocked in `async with self._scan_lock: return await run_sync(self._client.scan_chunks, ...)`, the CancelledError releases _scan_lock immediately but the executor thread keeps issuing gaa chunk requests for up to the 300s scan timeout. Any scan started afterwards on the same account runs concurrently with the orphan — exactly the FIFO cross-matching of chunk responses the lock exists to prevent (per its own comment, lines 118-124). The orphan also delays interpreter shutdown, since asyncio.run joins default-executor threads. Trigger is narrow (tracker restart / shutdown), hence minor, but the invariant break is real.
- **Fix:** Have stop() await the in-flight scan future (shield it and join) before returning, or add a cooperative cancel flag/threading.Event the client checks between chunk requests so the thread exits promptly on cancellation.

### Cooldown fallback regex-parses the library's exception message text
- **Where:** `src/dreambot/services/empire.py:379`
- **Why:** After handling LoginCooldownError properly via e.cooldown, _connect_locked falls back to re.search(r"Retry in (\d+)s", str(e)) for any other exception. 'Retry in {n}s' is an implementation detail of LoginCooldownError.__init__ (EmpireCore exceptions.py:34); if the library rewords the message the fallback silently stops extracting cooldowns. Since the typed exception already carries the value, the string path only masks cases where the library failed to raise the typed error.
- **Fix:** Drop the regex fallback; if wrapped cooldown errors are a real case, fix EmpireCore to raise/propagate LoginCooldownError consistently instead of parsing prose.

### hasattr() version-probing of EmpireClient methods instead of relying on the pinned dependency
- **Where:** `src/dreambot/services/empire.py:506`
- **Why:** get_player_details_bulk guards with hasattr(self._client, 'get_player_details_bulk') 'for backward compatibility', and the same pattern appears in birder.py:229/278 (hasattr(client, 'lords'/'army'/'castle')) and several getattr(..., None) sites. These guards paper over version skew instead of failing fast, and the fallback path they protect is itself broken (it calls the drifted get_player_details). They also add a maintenance trap: a typo'd attribute name silently selects the fallback forever.
- **Fix:** Delete the hasattr/getattr probes and call the methods directly; version compatibility belongs in the dependency pin plus a contract test, not runtime reflection.

### Dead get_moving_flags wrapper calls scan_map_area with a stale extra positional arg (would TypeError if ever used)
- **Where:** `src/dreambot/services/empire.py:535`
- **Why:** EmpireService.get_moving_flags passes (x1, y1, x2, y2, kingdom, True, EMPIRE_REQUEST_TIMEOUT_SECONDS) but EmpireClient.scan_map_area (client.py:550) takes only (x1, y1, x2, y2, kingdom, timeout) — the leftover 'True' is a second signature drift like get_player_details. No caller exists (move_detector/alliance_tracker use scan_kingdom_moving_flags), so today it's dead code that would raise TypeError (swallowed to {}) the moment someone revives it — and it also delegates to the library's broken response.get_moving_flags().
- **Fix:** Delete the method, or fix the call to keyword args and route through the corrected library get_moving_flags once that is repaired.

### Deprecated asyncio.get_event_loop() used to capture the loop in three handler start() methods
- **Where:** `src/dreambot/services/incomings.py:115`
- **Why:** incomings.py:115, alliance_chat.py:55, and verification.py:29 use asyncio.get_event_loop() inside a running loop. It works today but is deprecated (DeprecationWarning since 3.10, slated to become an error), and if start() is ever called from a non-async context it silently captures/creates the wrong loop, making every run_coroutine_threadsafe dispatch a no-op or cross-loop bug.
- **Fix:** Use asyncio.get_running_loop() in all three start() methods (it raises immediately if misused, which is what you want).

### update_settings does a non-atomic read-modify-write of guild settings
- **Where:** `src/dreambot/services/spy_settings.py:36`
- **Why:** It SELECTs current settings, merges in-Python, then upserts all four columns. Two concurrent updates (e.g. two admins, or channel + threshold changed in quick succession) interleave and the loser's field is silently reverted — a classic lost update. Low stakes (guild config) but trivially avoidable.
- **Fix:** Upsert only the provided columns: build the ON DUPLICATE KEY UPDATE clause from the non-None kwargs (still fully parameterized), eliminating the read step.

### gather() without return_exceptions leaks the poster and status-updater tasks if any worker escapes
- **Where:** `src/dreambot/services/spy_worker.py:529`
- **Why:** If a worker task raises outside its inner try (e.g. malformed target dict KeyError at `target["x"]`, or task_done bookkeeping), `await asyncio.gather(*all_worker_tasks)` re-raises immediately without cancelling siblings, done_event is never set, and _results_poster loops forever on its 2s timeout while _status_updater keeps editing the status message every 5s — two permanently leaked tasks per failed job, plus no summary posted (create_logged_task at cogs/spy.py:208 at least logs the escape).
- **Fix:** Use `await asyncio.gather(*all_worker_tasks, return_exceptions=True)` (logging any exceptions), and set done_event in a finally block so poster/updater always terminate.

### Permission-sync failures swallowed with bare `except discord.DiscordException: pass`
- **Where:** `src/dreambot/utils/channels.py:179`
- **Why:** Four sites (lines 179-180, 232-233, 271-272, 389-390) silently drop failures when moving a channel into the category or applying managed permission overwrites. If the bot lacks Manage Channels, private channels (attack-alerts, spy-reports) can quietly keep wrong permissions — a security-relevant misconfiguration with zero log trace, making 'why can everyone see spy-reports' undebuggable.
- **Fix:** Replace each silent pass with logger.warning including guild, channel, and the exception, mirroring the logging already done in the create paths.

### Duplicate definitions: CategoryConfig declared twice and get_or_create_tracking_category defined twice with different behavior
- **Where:** `src/dreambot/utils/channels.py:368`
- **Why:** CategoryConfig is defined at lines 46-51 and again at 54-61; get_or_create_tracking_category is defined at line 149 (config-driven via CATEGORIES['Tracking']) and again at line 368 (hand-rolled), and the second silently shadows the first — so the CATEGORIES['Tracking'] entry is dead configuration. Anyone editing the first definition will see no effect at runtime.
- **Fix:** Delete the duplicate dataclass and one of the two function definitions, keeping the config-driven variant.

### Lazy pool initialization is racy across to_thread workers
- **Where:** `src/dreambot/utils/db.py:42`
- **Why:** _get_pool() does an unlocked check-then-create on a module global. All DB entry points run in asyncio.to_thread worker threads, so two first-queries can interleave, each constructing a MySQLConnectionPool (5 connections each); one pool is orphaned with its sockets left to GC. Harm is bounded (leaked connections until GC) but it is a genuine race in the layer's foundation.
- **Fix:** Guard creation with a module-level threading.Lock, or eagerly initialize the pool once during bot startup (before any to_thread call).

### GameData CDN fetches have no timeout and initialization failure is swallowed with no retry
- **Where:** `src/dreambot/utils/game_data.py:43`
- **Why:** Both session.get calls run with aiohttp's default 5-minute total timeout (commander_stats.py in the same codebase correctly passes ClientTimeout(10)/ClientTimeout(60) — inconsistent). Worse, the whole initialize() is wrapped in `except Exception: logger.error(...)` leaving initialized=False; the bot then runs forever with an empty allowed_unit_ids set and nothing ever retries, so whatever filtering depends on it silently misbehaves until a full restart. Verify by blocking the CDN host and watching startup proceed normally.
- **Fix:** Pass aiohttp.ClientTimeout(total=10/60) like commander_stats.py, and either retry initialization in the background or surface a visible degraded-mode warning (e.g. in the /config dashboard).

### Rank/kingdom tables and format_coords duplicated across three utils modules
- **Where:** `src/dreambot/utils/location_utils.py:69`
- **Why:** RANK_NAMES exists identically in emojis.py:54-65 and location_utils.py:69-80; kingdom name/emoji maps are duplicated (emojis.KINGDOMS vs location_utils.KINGDOM_NAMES/KINGDOM_EMOJIS); and format_coords exists twice with different signatures/output (coords.py:1 returns 'x:y', location_utils.py:159 returns 'emoji x:y'). A GGE rank-ID change must now be fixed in two places, and a caller importing the wrong format_coords gets different output — both are actively imported (views/data.py uses coords.format_coords, services use both modules).
- **Fix:** Make emojis.py (or a new game_constants.py) the single source for rank/kingdom tables; keep exactly one format_coords with an optional kingdom_id parameter and update imports.

### Select menus built from unbounded lists exceed Discord's 25-option limit
- **Where:** `src/dreambot/views/config.py:838`
- **Why:** RemoveAllianceView builds one SelectOption per tracked alliance with max_values=len(options); with more than 25 tracked alliances the edit_message call is rejected with HTTPException 400 (max 25 options / max_values <= 25), so 'Remove Alliance' becomes unusable exactly when the list is largest. Same pattern in registration.py UnlinkAccountView (line 499, one option per linked account) and IgnoredAttackersView (line 653).
- **Fix:** Slice to 25 options (as SpyRoleSelectView and AddAllianceSelectView already do) and paginate, and clamp max_values to min(len(options), 25).

### Finite-timeout views (PropertiesView 300s, RankingDashboardView 600s) never disable their components on timeout
- **Where:** `src/dreambot/views/data.py:162`
- **Why:** Neither view stores the sent message nor implements on_timeout, so after the timeout the buttons/selects stay fully rendered but every click yields Discord's 'This interaction failed'. For a paginated dashboard users will hit this constantly on older messages.
- **Fix:** Store the message (view.message = await interaction.followup.send(..., view=view) pattern via `msg = await ...; view.message = msg`), and implement on_timeout to disable children and edit the message.

### /setup and /config run 4-7 sequential DB/service queries before the first interaction response, without defer
- **Where:** `src/dreambot/views/registration.py:122`
- **Why:** SettingsView.create_and_show awaits get_member, an optional INSERT/UPDATE, get_linked_accounts, get_ping_targets, get_ignored_attackers before response.send_message; BotConfigView.create_and_show (views/config.py:54-87) similarly awaits tracker stats plus three SpySettings queries. Under DB latency or an event loop stalled by the bot's other blocking work (e.g. the sync Twilio call), this misses the 3-second deadline and the command dies with Unknown interaction. The data cog already defers defensively; these do not.
- **Fix:** defer(ephemeral=True) at the top of create_and_show and send the settings embed via followup.send.

### View error paths use the wrong interaction response channel
- **Where:** `src/dreambot/views/registration.py:591`
- **Why:** UnlinkIdentityView.confirm's except sends interaction.followup.send, but if execute_async raised before refresh() the interaction was never acknowledged, so the followup webhook 404s and the user sees 'interaction failed' instead of the error. Conversely UnlinkAccountView.account_select's except (line 538) calls interaction.response.send_message, which raises InteractionResponded if the failure occurred inside refresh() after edit_message succeeded. Both error messages can therefore never reach the user in the very cases they exist for.
- **Fix:** In except blocks branch on interaction.response.is_done(): use response.send_message when not done, followup.send otherwise (or a small shared helper).

### yoyo.ini env-var placeholders use ${VAR} syntax that yoyo never interpolates
- **Where:** `yoyo.ini:3`
- **Why:** yoyo's config reader uses configparser BasicInterpolation with os.environ as defaults, i.e. %(DB_USER)s syntax; ${DB_USER} passes through literally. Verified: read_config('yoyo.ini') returns 'mysql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}/${DB_NAME}'. Any CLI use (yoyo apply/rollback/list — the entire reason this file exists) fails to connect to host '${DB_HOST}'. It works in production only because bot.py:333 builds its own URL and ignores this file.
- **Fix:** Change to database = mysql://%(DB_USER)s:%(DB_PASSWORD)s@%(DB_HOST)s/%(DB_NAME)s (yoyo merges os.environ into interpolation defaults), and verify with `yoyo list`.


## 💡 Suggestions (7)

### No on_command_error for prefix commands — owner-command failures only reach stderr
- **Where:** `src/dreambot/bot.py:167`
- **Why:** The owner prefix commands (sync, gge, movements, memory) call live GGE services that raise on disconnect (e.g. main_service.get_movements()). Without an on_command_error handler the invoker gets no reply at all; the default handler just prints a traceback to stderr, which in the Docker deployment is easy to miss. Verify by running '@bot movements' while the GGE account is disconnected.
- **Fix:** Add a small bot.event on_command_error that ctx.send()s a short error for CommandInvokeError (and ignores CommandNotFound/NotOwner), mirroring the app-command handler.

### Ad-hoc loop.run_in_executor(None, ...) instead of the project's run_sync bridge
- **Where:** `src/dreambot/cogs/birder.py:69`
- **Why:** The birder cog is the only place bypassing utils/async_utils.run_sync in favor of interaction.client.loop.run_in_executor(None, ...) (lines 69, 71, 95). Functionally equivalent today (same default executor), but it forks the bridging idiom: if the project ever tunes the executor or adds instrumentation/cancellation handling in run_sync, this path silently misses it, and reviewers must reason about two patterns.
- **Fix:** Replace the three run_in_executor(None, ...) calls with await run_sync(client.connection.connect), await run_sync(client.login), await run_sync(client.connection.disconnect).

### post_local_move_warnings resolves player details for every mover in the kingdom each poll
- **Where:** `src/dreambot/services/move_detector.py:80`
- **Why:** _resolve_mover_names issues a sequential get_player_details GGE request (5s timeout each) for all moving flags before proximity filtering, every 60s poll. During relocation-heavy events with dozens of kingdom-wide movers this adds dozens of unnecessary game requests per cycle and can stretch the poll by minutes, even when no mover is near an alliance castle.
- **Fix:** Compute the proximity-filtered mover set first (it only needs coordinates), then resolve names/alliances only for movers that will actually appear in a warning, ideally via get_player_details_bulk.

### Hand-rolled row-to-dict conversion instead of the driver's dictionary cursor
- **Where:** `src/dreambot/utils/db.py:80`
- **Why:** query()/query_one() fetch tuples and rebuild dicts via _row_to_dict on every row; mysql-connector supports conn.cursor(dictionary=True) which does this natively (and slightly faster), removing _row_to_dict and the cursor.description handling entirely.
- **Fix:** Use cursor = conn.cursor(dictionary=True) and return cursor.fetchall()/fetchone() directly; delete _row_to_dict.

### Single shared ENCRYPTION_KEY from .env guards all stored game credentials with no rotation path
- **Where:** `src/dreambot/utils/security.py:8`
- **Why:** All linked-account game passwords are encrypted under one symmetric Fernet key read from ENCRYPTION_KEY at import. A single .env leak or process-memory disclosure exposes every stored credential, and there is no key-rotation mechanism (rotating the key silently breaks decrypt_password for all existing rows). This concentrates risk and makes incident response hard. Given the bot stores replayable game credentials, key handling deserves explicit hardening.
- **Fix:** Document that .env must be tightly access-controlled; consider Fernet.MultiFernet for rotation, restrict file perms, and load the key from a secrets manager in production. Add a re-encrypt-on-rotate routine.

### Raw highscore protocol constants (LT=11, LID=1) hardcoded in a Discord view
- **Where:** `src/dreambot/views/config.py:278`
- **Why:** views/config.py calls ranking_service.get_highscore(11, str(sv), 1) with a comment decoding the magic numbers ('top 25 alliances by might (LT=11, LID=1)'). Highscore list-type ids are game-protocol knowledge; scattering them through UI code means the next GGE list-id shuffle requires hunting through bot views, and other library users must rediscover the same values.
- **Fix:** Add a HighscoreType enum (and named kingdom/list params) to EmpireCore's RankingService and call get_highscore(HighscoreType.ALLIANCE_MIGHT, ...) from the bot.

### Verification token is only 32 bits of entropy and never expires
- **Where:** `src/dreambot/views/registration.py:81`
- **Why:** Verification codes are `"dbot-" + str(uuid.uuid4())[:8]` — the first 8 hex chars = 32 bits of randomness — and persist in db_member.verification_code indefinitely until consumed (no TTL/expiry). Delivery is via in-game chat (not SMS) so online brute force is impractical, but a permanent, low-entropy linking token is weaker than it should be and a stale code that leaks (e.g. via the ephemeral embed being screenshotted/shared) stays valid forever, letting someone else claim the link.
- **Fix:** Use the full uuid4 hex (or secrets.token_hex(8)+) and store an expires_at; reject/rotate codes older than a short window and regenerate on each /setup open.


---

## Refuted during verification (not real / not actionable)

*These were flagged by a finder but knocked down by the adversarial verifier — recorded for transparency so they aren't re-raised.*

- `EmpireCore src/empire_core/network/connection.py:337` — Recv-loop teardown races a concurrent connect(): old thread can stomp _running=False and cancel the new connection's waiters
  - Traced all connect() callers: dreambot's connection_monitor reconnect (the claimed trigger) always builds a fresh EmpireClient/Connection via Account.get_client() (accounts.py:44, empire.py _connect_locked), so an old recv thread cannot touch the new session's flags, and disconnect-driven reconnects only start after on_disconnect fires at line 340, i.e. after the line 337-338 writes complete. The residual same-Connection race window is a few bytecodes wide against an uncorrelated network-handshake completion, and the near orderings are benign (empty waiter-cancel before login sends anything); at most this is a defensive-lifecycle-lock suggestion, not a reachable critical race.
- `EmpireCore src/empire_core/network/connection.py:111` — 1-second socket timeout is shared with sends: spurious send failures under backpressure and possible frame corruption on partial write
  - Verified websocket-client 1.9.0's send_frame loop and the shared 1s timeout exist as claimed, but the failure scenario is unreachable in practice: the map scanner is strictly sequential request/response with 0.2s pacing (one ~few-hundred-byte frame in flight), so the send timeout only fires on a fully-stalled (already dead) connection, and the worst-case mid-frame corruption merely causes a server-side drop that the existing recv-loop/on_disconnect path already recovers from; the tradeoff is deliberately documented at lines 30-32.
- `EmpireCore src/empire_core/pool.py:126` — AccountPool advertises 'concurrent GGE operations' but is check-then-act non-thread-safe: two threads can double-lease one account
  - The same docstring explicitly disclaims thread safety (lines 37-39), so the race is only reachable by violating the documented contract — and no caller in either repo uses AccountPool from threads (dreambot-v3 uses its own asyncio EmpirePool; the only consumers are single-threaded tests). The reviewer's "lock must span login()" argument is also wrong: lease(login=False) lets callers lock only the bookkeeping. An internal lock is optional public-release polish, not a reachable major bug.
- `EmpireCore src/empire_core/network/connection.py:148` — WebSocket fd is never closed after an unexpected disconnect; disconnect() early-returns and the recv-loop epilogue skips cleanup
  - Verified against the pinned websocket-client 1.9.0: WebSocket._recv (_core.py:579-587) closes the fd itself (sock.close(); sock=None; connected=False) whenever the peer closes the stream, which covers both CLOSE-frame and FIN drops before connection.py's epilogue runs — so no CLOSE_WAIT/fd leak on the claimed paths; the reviewer's "library does not close the fd" verification is wrong. Only an RST/OSError leaves one dead fd in the stale ws object (kernel state CLOSED, freed on reconnect or GC), which is at most a minor idempotent-cleanup hygiene item, not the claimed major leak.
- `EmpireCore src/empire_core/network/connection.py:413` — No liveness detection: a half-open TCP connection is never noticed, so 'connected' stays True forever and on_disconnect never fires
  - Traced the claimed half-open scenario through websocket-client: _open_socket applies SO_KEEPALIVE + TCP_KEEPIDLE=30/KEEPINTVL=10/KEEPCNT=3, so the kernel aborts a blackholed connection in ~60s; the resulting OSError propagates through ws.recv() (only socket.timeout maps to WebSocketTimeoutException), hits _recv_loop's generic except at line 325, breaks, sets _running=False and fires on_disconnect (lines 336-342) — so 'connected stays True forever / on_disconnect never fires' is false, and dreambot's connection_monitor already reconnects off that hook.
- `EmpireCore src/empire_core/protocol/models/map.py:306` — All-or-nothing list validation: one malformed movement entry discards the entire gam response
  - Traced both gam paths: push and request movements flow through GameState._handle_gam (state/manager.py:253), which skips malformed entries per-element (continue on missing MID, try/except in _parse_movement) — GetMovementsResponse is never instantiated on any live path (no "gam" handler is registered, Client.get_movements sends a raw packet and returns state-parsed movements, dreambot uses that same path), so the claimed attack-alert data loss is unreachable; the map.py model's flat schema doesn't even match the real nested gam wire format, making it dead/mismatched code rather than the claimed batch-poisoning vector.
- `dreambot-v3 src/dreambot/cogs/spy.py:114` — /spy alliance defers only after DB auth queries and potentially creating a Discord channel/category
  - Checked spy.py, utils/channels.py, utils/roles.py, services/spy_settings.py, and bot.py: ensure_channels pre-creates the category/role/spy-reports channel for every guild at startup (before cogs load) and on guild join, so the claimed first-use creation cascade before defer() is an unreachable edge case in practice; is_bot_admin is in-memory (not a DB call) leaving 1-2 fast queries pre-defer, and deferring first would break the ephemeral permission-denied vs public-report response design.
