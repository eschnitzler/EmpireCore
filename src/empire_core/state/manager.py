"""
GameState - Tracks game state from server packets.
"""

import time
from typing import Any

from empire_core.state.base import MovementEventCallback
from empire_core.state.castles import CastleState
from empire_core.state.movements import MOVEMENT_PARSE_WARN_INTERVAL, MovementState
from empire_core.state.player import PlayerState

__all__ = ["MOVEMENT_PARSE_WARN_INTERVAL", "GameState", "MovementEventCallback"]
# gbd/lli sections stamped under their own id, whether they came in a gbd or as a push.
_TRACKED_SECTIONS = ("gpi", "gxp", "gcu", "vip", "gal", "gcl", "gho", "uap", "gac", "sce", "dcl", "sei")

_PLAYER_SECTIONS = frozenset({"gpi", "gxp", "gcu", "vip", "gal", "gcl", "gho", "uap", "gac", "sce"})

# Pushes whose payload is the body of the gbd section of the same name.
_SECTION_PUSHES = frozenset({"gpi", "gxp", "gcu", "vip", "gal", "gcl", "gho", "uap"})


class GameState(MovementState, CastleState, PlayerState):
    """
    Manages game state parsed from server packets.

    State is mutated by the network receive thread and read from user
    threads, so all mutation and snapshot reads are guarded by a lock.

    The public attributes stay readable directly, but callers that read
    several fields at once (or iterate a container) should use the snapshot
    accessors — ``get_local_player()``, ``get_inventory()``, ``get_castles()``,
    ``get_all_movements()`` — which copy under the lock. Mutation paths swap
    containers instead of editing them in place, so an unlocked reader that
    already holds one never sees it change underneath.

    Callbacks are dispatched in a thread pool to avoid blocking the receive
    loop. This allows callbacks to make blocking calls (like waiting for
    responses).

    Freshness
    ---------
    Nothing here polls the server: every field is as old as the last packet
    that carried it, and some packets arrive only once per session. Cached
    values are therefore *not* automatically current:

    ===================================  ==========================  ===================================
    State                                Refreshed by                Force a refresh with
    ===================================  ==========================  ===================================
    castle name/coords, castle list      ``gcl``, ``mir`` (pushed)    re-login
    castle resources/units/details       ``dcl``                      ``client.castle.get_details(id)``
    player identity/level/XP             ``gpi``/``gxp``/``glu``      re-login
    player gold/rubies, VIP, alliance    ``gcu``/``vip``/``gal``      re-login
    honor, beginner protection           ``gho``/``uap``              re-login
    global inventory                     ``sce`` (pushed)             --
    movements                            ``gam``, ``abr``/``asr``,    ``client.get_movements()``
                                         your sends' replies
                                         (``cra``, ``cds``, ...)
    ===================================  ==========================  ===================================

    Every player section above is sent inside the login gbd and again as a
    push of its own when it changes.

    In practice a castle's ``resources`` often reflects login time and nothing
    else, so use the freshness accessors before trusting them:
    :meth:`get_castle_last_updated` / :meth:`get_castle_age`,
    :meth:`get_player_last_updated`, and :meth:`get_last_packet_time` /
    :meth:`get_packet_times` for per-packet timestamps. All timestamps are
    wall-clock (``time.time()``) seconds, and ``None`` means "never seen",
    which is different from "seen and empty".
    """

    _DISPATCH: dict[str, str] = {
        "gbd": "_handle_gbd",
        "lli": "_handle_gbd",
        "gam": "_handle_gam",
        "dcl": "_handle_dcl",
        "abr": "_handle_movement_push",
        "asr": "_handle_movement_push",
        "cra": "_handle_attack_sent",
        "cam": "_handle_attack_sent",
        "abgcam": "_handle_attack_sent",
        "cds": "_handle_movement_sent",
        "csm": "_handle_movement_sent",
        "cat": "_handle_movement_sent",
        "crm": "_handle_movement_sent",
        "css": "_handle_movement_sent",
        "tde": "_handle_movement_sent",
        "cdd": "_handle_movement_sent",
        "cpm": "_handle_movement_sent",
        "thm": "_handle_thm",
        "ldt": "_handle_ldt",
        "mcm": "_handle_mcm",
        "mrm": "_handle_mrm",
        "mfc": "_handle_mfc",
        "glu": "_handle_glu",
        "mir": "_handle_mir",
        "sce": "_handle_sce",
        "sei": "_handle_sei",
    }

    def update_from_packet(self, cmd_id: str, payload: dict[str, Any]) -> None:
        """Central update router — parses packet and updates state.

        Every packet, handled or not, also advances movements, so arrivals
        fire with the server's traffic rather than only on movement packets.
        """
        handler_name = self._DISPATCH.get(cmd_id)
        with self._lock:
            if cmd_id in _SECTION_PUSHES:
                # An unreadable frame arrives as {"raw": ...}; the client applies a push only on success
                if isinstance(payload, dict) and "raw" not in payload:
                    self._packet_times[cmd_id] = time.time()
                    self._handle_gbd({cmd_id: payload})
            elif handler_name:
                self._packet_times[cmd_id] = time.time()
                getattr(self, handler_name)(payload)
            self._advance_movements()

    def _handle_gbd(self, data: dict[str, Any]) -> None:
        """Apply the login data, or the one section a push wraps in the same shape.

        Client: ``GBDCommand.exec``; the pushes are ``GPICommand``, ``GXPCommand``,
        ``GCUCommand``, ``VIPCommand``, ``GALCommand``, ``GCLCommand``,
        ``GHOCommand`` and ``UAPCommand``.
        """
        self._parse_player_sections(data)
        self._parse_inventory(data)
        self._parse_alliance_info(data)
        self._parse_castles(data)
        if dcl := data.get("dcl"):
            self._handle_dcl(dcl)
        if sei := data.get("sei"):
            self._handle_sei(sei)
        self._stamp_sections(data)

    def _handle_attack_sent(self, data: dict[str, Any]) -> None:
        """Handle the reply to an attack you send: the new movement under ``AAM``.

        Client: ``CRACommand``, ``CAMCommand`` and ``ABGCAMCommand``.
        """
        self._apply_sent_movement(data, data.get("AAM"))

    def _handle_movement_sent(self, data: dict[str, Any]) -> None:
        """Handle the reply to a support, spy, travel, transport, siege or monk you send: the new movement under ``A``.

        Client: ``CDSCommand``, ``CSMCommand``, ``CATCommand``, ``CRMCommand``,
        ``CSSCommand``, ``TDECommand``, ``CDDCommand`` and ``CPMCommand``.
        """
        self._apply_sent_movement(data, data.get("A"))

    def _handle_thm(self, data: dict[str, Any]) -> None:
        """Handle thm, the reply to a treasure hunt you send: the new movement under ``TM``.

        Client: ``THMCommand``.
        """
        self._apply_sent_movement(data, data.get("TM"))

    def _handle_ldt(self, data: dict[str, Any]) -> None:
        """Handle ldt, a daimyo taunt attack: the payload is the movement wrapper itself.

        Client: ``LDTCommand``.
        """
        self._apply_movement_wrappers([data], [])

    def _apply_sent_movement(self, data: dict[str, Any], wrapper: Any) -> None:
        """Apply a send reply's gold and rubies (``gcu``), then store its movement with the owner records (``O``).

        An error reply carries no movement, so it stores nothing.
        """
        if isinstance(gcu := data.get("gcu"), dict):
            self._handle_gbd({"gcu": gcu})
        self._apply_movement_wrappers([wrapper], data.get("O", []))

    def _handle_glu(self, data: Any) -> None:
        """Apply a level-up push's currencies and XP.

        ``L`` (the new level) and ``LL`` (a 0/1 legend level-up flag) only
        drive the client's level-up dialog.

        Client: ``GLUCommand.executeCommand``.
        """
        if isinstance(data, dict):
            self._handle_gbd({key: data[key] for key in ("gcu", "gxp") if key in data})

    def _handle_mir(self, data: Any) -> None:
        """Apply the castle list sent after taking a castle or outpost.

        Client: ``MIRCommand.executeCommand`` / ``CastleUserData.parse_MIR``.
        """
        if isinstance(data, dict) and data.get("gcl"):
            self._handle_gbd({"gcl": data["gcl"]})

    def _stamp_sections(self, data: dict[str, Any]) -> None:
        """Record when each section of a gbd/lli payload, or a section push, was applied.

        A section present but null still counts as applied: "gal": None means
        "you are in no alliance", which is information, not absence of it.
        Sections carrying local-player fields also refresh the player stamp,
        but only once there is a player to attach it to.
        """
        now = time.time()
        for section in _TRACKED_SECTIONS:
            if section in data:
                self._packet_times[section] = now
                if section in _PLAYER_SECTIONS and self.local_player is not None:
                    self._player_updated_at = now

    def get_last_packet_time(self, cmd_id: str) -> float | None:
        """When a packet (or gbd sub-packet) of this kind was last applied.

        Accepts the wire ids this manager tracks — "gbd", "lli", "gam", "dcl",
        "abr", "asr", the send replies ("cra", "cam", "abgcam", "cds", "csm",
        "cat", "crm", "css", "tde", "cdd", "cpm", "thm", "ldt"), "mcm", "mrm",
        "mfc", "glu", "mir", "sce", "sei" — and the player sections "gpi",
        "gxp", "gcu", "vip", "gal", "gcl", "gho" and "uap", stamped whether
        they came inside a gbd or as a push of their own, plus "gac", which
        only comes inside a gbd. A send reply
        is stamped even when the server refused the send. ``None`` means none
        was ever seen; packets this manager ignores are never recorded.
        """
        with self._lock:
            return self._packet_times.get(cmd_id)

    def get_packet_times(self) -> dict[str, float]:
        """Snapshot of every tracked packet/sub-packet timestamp."""
        with self._lock:
            return dict(self._packet_times)
