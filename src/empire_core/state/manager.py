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
# gbd/lli sub-packets whose freshness is tracked separately from the packet
# that carried them (gold only ever arrives inside a gbd, for instance).
_TRACKED_SECTIONS = ("gpi", "gxp", "gcu", "vip", "gal", "gcl", "sce", "dcl", "sei")

# Sub-packets that carry local-player fields (used for get_player_last_updated)
_PLAYER_SECTIONS = frozenset({"gpi", "gxp", "gcu", "vip", "gal", "gcl", "sce"})


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
    castle name/coords, castle list      ``gcl`` (inside gbd/lli)     re-login
    castle resources/units/details       ``dcl``                      ``client.castle.get_details(id)``
    player identity/level/XP             ``gpi``/``gxp``              re-login
    player gold/rubies, VIP, alliance    ``gcu``/``vip``/``gal``      re-login
    global inventory                     ``sce`` (pushed)             --
    movements                            ``gam``, ``abr``/``asr``     ``client.get_movements()``
    ===================================  ==========================  ===================================

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
        "mcm": "_handle_mcm",
        "mrm": "_handle_mrm",
        "mfc": "_handle_mfc",
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
            if handler_name:
                self._packet_times[cmd_id] = time.time()
                getattr(self, handler_name)(payload)
            self._advance_movements()

    def _handle_gbd(self, data: dict[str, Any]) -> None:
        """Handle 'Get Big Data' packet — initial login data."""
        self._parse_player_sections(data)
        self._parse_inventory(data)
        self._parse_alliance_info(data)
        self._parse_castles(data)
        if dcl := data.get("dcl"):
            self._handle_dcl(dcl)
        if sei := data.get("sei"):
            self._handle_sei(sei)
        self._stamp_sections(data)

    def _stamp_sections(self, data: dict[str, Any]) -> None:
        """Record when each sub-packet of a gbd/lli payload was applied.

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
        "abr", "asr", "mcm", "mrm", "mfc", "sce", "sei" — and the gbd sub-packet keys
        "gpi", "gxp", "gcu", "vip", "gal", "gcl", which carry data that never
        arrives on its own. ``None`` means none was ever seen; packets this
        manager ignores are never recorded.
        """
        with self._lock:
            return self._packet_times.get(cmd_id)

    def get_packet_times(self) -> dict[str, float]:
        """Snapshot of every tracked packet/sub-packet timestamp."""
        with self._lock:
            return dict(self._packet_times)
