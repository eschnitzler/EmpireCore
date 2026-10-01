"""Local player tracking: gpi/gxp/gcu/vip/gho/uap, alliance (gal), special currencies (sce), events and spies."""

import logging
import math
import time
from typing import Any

from empire_core.gamedata.ids.events import Event
from empire_core.protocol.js import js_int, js_number, js_number_or_none, js_truthy
from empire_core.spy.models import MaxSpiesResponse
from empire_core.state.base import StateBase
from empire_core.state.models import Alliance, Player

logger = logging.getLogger(__name__)


LEVEL_CAP = 70
LEGEND_LEVEL_CAP = 950
_LEVEL_CAP_XP = LEVEL_CAP * LEVEL_CAP * 30
# The parts an event's VO rebuilds on every sei, and those it rebuilds only when the entry has them
_PARTS_ALWAYS_REBUILT = {80: ("SP", "A"), 85: ("FB", "FR", "A")}
_PARTS_REBUILT_WHEN_SENT = {71: ("SP", "A"), 72: ("SP", "A"), 103: ("SP", "A")}
_clock = time.monotonic


def _global_effects_end(effects: Any, now: float) -> float:
    """When the last of a global effect event's effects ends, 0 for none.

    ``GE`` holds ``[effect_id, seconds_left, strength]`` per effect.
    """
    end = 0.0
    for effect in effects if isinstance(effects, list) else ():
        if isinstance(effect, list) and len(effect) > 1:
            # JavaScript's seconds * 1000: null counts as 0, NaN never wins
            seconds = 0 if effect[1] is None else js_number_or_none(effect[1])
            if seconds is not None:
                end = max(end, now + seconds)
    return end


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    body = data.get(key)
    return body if isinstance(body, dict) else {}


def xp_for_level(level: int) -> int:
    """Total XP at which ``level`` starts. Client: ``PlayerConst.getXPFromLevel``."""
    return min(_LEVEL_CAP_XP, level * level * 30)


def legend_level_for_xp(xp: int) -> int:
    """Legend level reached with ``xp`` total XP. Client: ``PlayerConst.getLegendLevelFromXP``."""
    past_cap = xp - _LEVEL_CAP_XP
    if past_cap < 0:
        return 0
    return min(LEGEND_LEVEL_CAP, max(1, math.floor(((past_cap + 2750) / 3000) ** (1 / 1.19))))


def xp_for_legend_level(legend_level: int) -> int:
    """Total XP at which ``legend_level`` starts. Client: ``PlayerConst.getXPFromLegendLevel``."""
    if legend_level < 1:
        return 0
    legend_level = min(LEGEND_LEVEL_CAP, legend_level)
    return math.ceil(3000 * legend_level**1.19) - 2750 + _LEVEL_CAP_XP


def level_progress(level: int, xp: int) -> tuple[int, int, int]:
    """Legend level and the XP at which the current and next level start.

    Client: ``CastleUserData.parse_GXP``, which ignores the LL, XPFCL and
    XPTNL the server sends alongside and computes them from LVL and XP.
    """
    legend = legend_level_for_xp(xp) if level >= LEVEL_CAP else 0
    if legend > 0:
        return legend, xp_for_legend_level(legend), xp_for_legend_level(legend + 1)
    return 0, xp_for_level(level), xp_for_level(level + 1)


def _as_int(value: Any, previous: int) -> int:
    """The value as an int, or ``previous`` when it is missing or unreadable."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return previous


class PlayerState(StateBase):
    def _parse_player_sections(self, data: dict[str, Any]) -> None:
        """Parse the gpi/gxp/gcu/vip/gho/uap/gac sections as ONE atomic player update.

        `local_player` is handed out to user code and read without the lock,
        so a field-by-field merge would let a reader observe a half-merged
        player. A re-login gbd spreads its fields across sections (identity
        in gpi, level/XP in gxp, currency in gcu, VIP in vip), so merging
        gpi atomically but editing the other sections' fields one at a time
        would still expose "new name, old level". The complete field mapping
        is therefore built across *all* sections first and swapped in with a
        single store (see :meth:`_swap_model_fields`), which keeps the
        identity-map behavior — references held by user code stay live —
        while never exposing an intermediate state.

        gxp, gcu, vip and gho are partial updates: a key they omit keeps its
        previous value (this packet's gpi value if it carried one, else the
        existing state) rather than resetting to zero.

        Client: ``CastleUserData.parse_GPI`` / ``parse_GXP`` / ``parse_GHO`` /
        ``parse_UAP``, ``CurrencyData.parseGCU``, ``CastleVIPData.parse_VIP``.
        """
        fresh: Player | None = None
        pid = None
        player = self.local_player
        gpi = _section(data, "gpi")
        if gpi:
            pid = gpi.get("PID")
            if pid is not None:
                player = self.players.get(pid)
                if player is None:
                    player = Player(**gpi)
                else:
                    fresh = Player(**gpi)
        if player is None:
            return

        merged = dict(player.__dict__)
        updated: set[str] = set()

        if fresh is not None:
            gpi_fields = fresh.model_fields_set & set(Player.model_fields)
            for field_name in gpi_fields:
                merged[field_name] = getattr(fresh, field_name)
            updated |= gpi_fields

        if gxp := _section(data, "gxp"):
            level = _as_int(gxp.get("LVL"), merged["level"])
            xp = _as_int(gxp.get("XP"), merged["xp"])
            legend, current, following = level_progress(level, xp)
            merged.update(
                level=level,
                xp=xp,
                legendary_level=legend,
                xp_for_current_level=current,
                xp_to_next_level=following,
            )
            updated |= {"level", "xp", "legendary_level", "xp_for_current_level", "xp_to_next_level"}

        if gcu := _section(data, "gcu"):
            merged["coins"] = gcu.get("C1", merged["coins"])
            merged["rubies"] = gcu.get("C2", merged["rubies"])
            updated |= {"coins", "rubies"}

        if vip := _section(data, "vip"):
            merged["vip_points"] = vip.get("VP", merged["vip_points"])
            merged["vip_level"] = vip.get("VRL", merged["vip_level"])
            merged["vip_time_left"] = vip.get("VRS", merged["vip_time_left"])
            updated |= {"vip_points", "vip_level", "vip_time_left"}

        if gho := _section(data, "gho"):
            merged["honor"] = gho.get("H", merged["honor"])
            merged["ranking"] = gho.get("RP", merged["ranking"])
            updated |= {"honor", "ranking"}

        protection = dict(merged["beginner_protection"])
        for key in ("uap", "gac"):
            uap = _section(data, key)
            if isinstance(uap.get("KID"), int) and isinstance(uap.get("NS"), int):
                protection[uap["KID"]] = uap["NS"] > 0
        if protection != merged["beginner_protection"]:
            merged["beginner_protection"] = protection
            updated.add("beginner_protection")

        if updated:
            self._swap_model_fields(player, merged, updated)

        if pid is not None:
            self.players[pid] = player
            self.local_player = player
            logger.debug(f"Local player: {player.name} (ID: {pid})")

    def _parse_special_currencies(self, data: dict[str, Any]) -> None:
        """Apply the login data's sce section (special currencies)."""
        sce = data.get("sce", [])
        if not (sce and self.local_player):
            return
        total = self._apply_special_currencies(sce)
        logger.debug(f"Parsed {total} special currencies")

    def _apply_special_currencies(self, entries: Any) -> int:
        """Merge ``[[currency_key, amount], ...]`` entries into the special currencies.

        The dict is rebuilt and swapped rather than updated in place: user
        threads read ``local_player.special_currencies`` without the lock, and
        iterating a dict the receive thread is writing raises
        "dictionary changed size during iteration".

        Client: ``CurrencyData.parseSCE`` (bundle line 141182), which sets each
        ``int(amount)`` on the generic currency with that key in the item data, so
        an unreadable amount is 0 and ``"12.7"`` is 12. The library keeps keys the
        item data lacks, which the client ignores.

        Returns:
            The number of special currencies known afterwards.
        """
        player = self.local_player
        if player is None or not isinstance(entries, list):
            return 0
        updated = dict(player.special_currencies)
        for entry in entries:
            if isinstance(entry, list) and entry:
                updated[str(entry[0])] = js_int(entry[1] if len(entry) > 1 else None)
        player.special_currencies = updated
        return len(updated)

    def _parse_alliance_info(self, data: dict[str, Any]) -> None:
        """Parse alliance membership from gal sub-packet.

        Two cases are deliberately distinguished:

        * no "gal" key at all — this packet carries no alliance information,
          so existing state is left alone;
        * "gal" present without a usable AID — the server is telling us the
          player is in no alliance, so a stale alliance (left, kicked,
          disbanded) is cleared.

        The alliance and the player's AID land in one swap, since a push can
        change them while user threads read the player.

        Client: ``CastleUserData.parse_GAL``.
        """
        player = self.local_player
        if player is None or "gal" not in data:
            return

        gal = _section(data, "gal")
        try:
            aid = int(gal["AID"]) if gal.get("AID") is not None else 0
        except (TypeError, ValueError):
            aid = 0

        alliance: Alliance | None = None
        if aid > 0:
            try:
                alliance = Alliance(**gal)
            except Exception as e:
                logger.warning(f"Could not parse alliance: {e}")
                return
            logger.debug(f"Alliance: {alliance.name}")
        elif player.alliance is not None:
            logger.debug("Alliance cleared: gal section reports no alliance")

        merged = dict(player.__dict__)
        merged["alliance"] = alliance
        merged["AID"] = aid if alliance is not None else None
        self._swap_model_fields(player, merged, {"alliance", "AID"})

    def _parse_max_spies(self, data: dict[str, Any]) -> None:
        """Apply a gbd's ``gms`` section, or a ``gms`` push.

        Client: ``CastleSpyData.parse_GMS`` (bundle line 139979), which skips a falsy section
        and reads ``MS`` and ``BS`` of anything else through ``int()``.
        """
        gms = data.get("gms")
        if js_truthy(gms):
            self.max_spies = MaxSpiesResponse.model_validate(gms if isinstance(gms, dict) else {})

    def _handle_sce(self, data: Any) -> None:
        """Handle a "get special currency" push: ``[[currency_key, amount], ...]``.

        Client: ``SCECommand.exec`` / ``CurrencyData.parseSCE``.
        """
        entries = data if isinstance(data, list) else []

        if entries and self.local_player:
            self._apply_special_currencies(entries)
            self._player_updated_at = time.time()
            logger.debug(f"Updated {len(entries)} special currencies from sce")

    def _handle_sei(self, data: Any) -> None:
        """Handle 'Send Event Information': each entry updates its event, or adds it.

        Events the packet does not name stay active until a see ends them or their
        time runs out. An entry's ``RS`` (seconds left), when truthy, sets when the
        event ends; an event never given an end has ended, as in the client, except
        the kingdoms league and global effect events, whose end their own fields set
        (see :meth:`_handle_tei`). An entry's ``LID``, when truthy, becomes its
        event's league. The invasions' boards take their league from a part (``SP``,
        ``A``, ``FB``, ``FR``), rebuilt at league 1 and then given its truthy
        ``LID``: the samurai and Berimond invasions rebuild every part on every
        entry, the alien, red alien and nomad invasions only the parts the entry has.
        An entry whose ``EID`` reads as 0 or below is skipped; the client drops ids
        its events table lacks, the library keeps every other id.

        Client: ``CastleSpecialEventData.parse_SEI`` (bundle line 139800), which reads
        ``int(a.EID)``, and ``parseServerEventData`` (bundle line 139811);
        ``ASpecialEventVO.parseBasicsFromParamObject`` (bundle line 2958) reads ``RS``;
        ``AScoreEventVO.parseBasicsFromParamObject`` (bundle line 14967) reads
        ``t.LID&&(this._leagueID=int(t.LID))`` over a default of 1 (bundle line 14965);
        the parts: ``SamuraiInvasionEventVO.parseData`` (bundle line 55680),
        ``FactionInvasionEventVO.parseData`` (bundle line 116044),
        ``AAlienInvasionEventVO.parseData`` (bundle line 58910),
        ``AllianceNomadInvasionEventVO.parseData`` (bundle line 114287);
        ``FactionEventVO.parseParamObject`` (bundle line 7364) reads ``UL``
        """
        events = data.get("E") if isinstance(data, dict) else None
        if isinstance(events, list):
            now = _clock()
            for event in events:
                if isinstance(event, dict):
                    self._apply_event_entry(js_int(event.get("EID")), event, now)
        self._drop_ended_events()

    def _apply_sei(self, data: dict[str, Any]) -> None:
        """Apply the ``sei`` a reply carries, stamped as a sei."""
        if "sei" in data:
            self._packet_times["sei"] = time.time()
            self._handle_sei(data["sei"])

    def _handle_tei(self, data: Any) -> None:
        """Handle 'trigger event info': each ``TE`` entry updates or adds its event, keyed by ``TRID``.

        The trigger events are the kingdoms league (601) and the global effect events
        (610, 612); they join the same running events as the sei ones, and a see or a
        tee ends them. They carry no ``RS``: the kingdoms league runs while ``KLRD``
        (days left) is over 1, and with one day or less it ends with the running event
        whose ``KL`` is set (or never, at one day, without one); a global effect event
        ends with the last of its effects (``GE``), and the boost event (612) when the
        global effect event (610) running as it arrives ends.

        Client: ``TEICommand`` (bundle line 128410) and ``CastleSpecialEventData.parseTEI``
        (bundle line 139905), which reads ``int(a.TRID)``; the gbd's ``tei`` is applied
        before its ``sei`` (``GBDCommand.exec``, bundle line 129381);
        ``ATriggerEventVO.parseBasicsFromParamObject`` (bundle line 39815);
        ``SeasonLeagueEventVO.parseParamObject`` and ``endTimestamp`` (bundle lines
        118059-118063); ``SeasonLeagueData.getActiveSeasonEventVO`` (bundle line 142582)
        and ``SpecialEventSeasonLeagueComponent.parseServerData`` (bundle line 64551) for
        ``KL``; ``GlobalEffectEventVO.parseParamObject`` (bundle lines 116399-116413);
        ``GlobalEffectBuffEventVO.parseParamObject`` (bundle lines 116381-116383)
        """
        entries = data.get("TE") if isinstance(data, dict) else None
        if not isinstance(entries, list) or not entries:
            return
        now = _clock()
        for entry in entries:
            if isinstance(entry, dict):
                self._apply_event_entry(js_int(entry.get("TRID")), entry, now)
        self._drop_ended_events()

    def _handle_tee(self, data: Any) -> None:
        """Handle 'trigger event end': the trigger event it names (``TRID``) has ended.

        Client: ``TEECommand`` (bundle line 128395) and ``CastleSpecialEventData.parseTEE``
        (bundle line 139915): ``int(e&&e.TRID?e.TRID:-1)``, removed when 0 or above
        """
        trid = data.get("TRID") if isinstance(data, dict) else None
        eid = js_int(trid if js_truthy(trid) else -1)
        if eid >= 0:
            self._forget_event(eid)
            self._drop_ended_events()

    def _apply_event_entry(self, eid: int, event: dict[str, Any], now: float) -> None:
        if eid <= 0:
            return
        if eid not in self._active_event_ids:
            self._active_event_ids.append(eid)
        if js_truthy(remaining := event.get("RS")) and math.isfinite(seconds := js_number(remaining)):
            self.event_end_times[eid] = now + seconds
        if eid == Event.SEASON_LEAGUE:
            self._season_league_days[eid] = js_int(event.get("KLRD"))
        elif eid == Event.GLOBAL_EFFECT:
            self.event_end_times[eid] = _global_effects_end(event.get("GE"), now)
        elif eid == Event.GLOBAL_EFFECT_BUFF:
            effects = self.event_end_times.get(Event.GLOBAL_EFFECT, 0.0)
            running = Event.GLOBAL_EFFECT in self._active_event_ids
            self.event_end_times[eid] = max(effects, now) if running else 0.0
        if js_truthy(event.get("KL")):
            self._season_mode_events.add(eid)
        else:
            self._season_mode_events.discard(eid)
        if js_truthy(league := event.get("LID")):
            self.event_league_ids[eid] = js_int(league)
        self.event_unlocked[eid] = js_truthy(event.get("UL"))
        rebuilt = _PARTS_ALWAYS_REBUILT.get(eid, ())
        sent = tuple(p for p in _PARTS_REBUILT_WHEN_SENT.get(eid, ()) if js_truthy(event.get(p)))
        for part in (*rebuilt, *sent):
            entry = event.get(part)
            league = entry.get("LID") if isinstance(entry, dict) else None
            self.event_part_league_ids[(eid, part)] = js_int(league) if js_truthy(league) else 1

    def _handle_see(self, data: Any) -> None:
        """Handle a 'special event end' push: the event it names has ended.

        Client: ``CastleSpecialEventData.parse_SEE`` (bundle line 139826), from ``SEECommand``
        (bundle line 128364), looks the ``EID`` up as sent; ``removeEventById`` (bundle line
        139838) destroys the event, so one added again starts over
        """
        eid = data.get("EID") if isinstance(data, dict) else None
        if isinstance(eid, (int, float)) and not isinstance(eid, bool):
            self._forget_event(eid)
            self._drop_ended_events()

    def _forget_event(self, eid: float) -> None:
        self._active_event_ids = [e for e in self._active_event_ids if e != eid]
        self.event_end_times.pop(eid, None)  # type: ignore[call-overload]
        self.event_league_ids.pop(eid, None)  # type: ignore[call-overload]
        self.event_unlocked.pop(eid, None)  # type: ignore[call-overload]
        self._season_league_days.pop(eid, None)  # type: ignore[call-overload]
        self._season_mode_events.discard(eid)  # type: ignore[arg-type]
        for key in [key for key in self.event_part_league_ids if key[0] == eid]:
            del self.event_part_league_ids[key]

    def _season_league_end(self, eid: int, now: float) -> float:
        # SeasonLeagueEventVO.endTimestamp is read on demand: KLRD days from now, so it never
        # counts down, or with a day or less the end of the running event whose KL is set
        days = self._season_league_days.get(eid, 0)
        if days > 1:
            return math.inf
        season = next((e for e in self._active_event_ids if e in self._season_mode_events and e != eid), None)
        if season is not None:
            return self.event_end_times.get(season, 0.0)
        return math.inf if days == 1 else now + days * 86400

    def _drop_ended_events(self) -> None:
        # CastleSpecialEventData.executeUpdateForEvents (bundle line 139833): remainingEventTimeInSeconds<=0
        now = _clock()
        while True:
            for eid in self._season_league_days:
                self.event_end_times[eid] = self._season_league_end(eid, now)
            ended = [e for e in self._active_event_ids if self.event_end_times.get(e, 0.0) <= now]
            if not ended:
                return
            for eid in ended:
                self._forget_event(eid)

    @property
    def active_event_ids(self) -> list[int]:
        """The running events, sei and trigger events alike, in the order they were first named; a copy."""
        with self._lock:
            self._drop_ended_events()
            return list(self._active_event_ids)

    def get_event_league_id(self, event_id: int, part: str | None = None) -> int | None:
        """The league (``LID``) the sei packets last gave an event, or None when they never gave one.

        ``part`` names one of the entry's parts instead: ``SP``, ``A``, ``FB`` or ``FR``.
        """
        with self._lock:
            if part is None:
                return self.event_league_ids.get(event_id)
            return self.event_part_league_ids.get((event_id, part))

    def is_event_unlocked(self, event_id: int) -> bool:
        """Whether the event's last sei entry had a truthy ``UL``; Berimond is locked without it."""
        with self._lock:
            return self.event_unlocked.get(event_id, False)

    def get_local_player(self) -> Player | None:
        """Get a snapshot of the local player, or None before login.

        Returns a copy taken under the lock, with detached ``special_currencies``,
        ``castles`` and ``beginner_protection`` containers, so several fields can be read consistently
        while the receive thread is updating state. ``state.local_player``
        remains available for direct access but is a live object.

        The Castle objects inside the snapshot are the live ones, as with
        ``get_castles()``.
        """
        with self._lock:
            player = self.local_player
            if player is None:
                return None
            return player.model_copy(
                update={
                    "special_currencies": dict(player.special_currencies),
                    "castles": dict(player.castles),
                    "beginner_protection": dict(player.beginner_protection),
                }
            )

    def get_special_currencies(self) -> dict[str, int]:
        """Get a snapshot of the special currencies (sce currency key -> amount).

        These are the generic currencies from ``sce`` (``PTT``, ``MS1``,
        ``LWT``, ...), not items. Empty before login, or if no sce packet has
        arrived yet — use ``get_last_packet_time("sce")`` to tell those apart
        from "empty".
        """
        with self._lock:
            if self.local_player is None:
                return {}
            return dict(self.local_player.special_currencies)

    def get_max_spies(self) -> MaxSpiesResponse | None:
        """The spies you own before boosts, from ``gms``; None until the login gbd brings it.

        The model is replaced, never edited, on each ``gms``, so the one returned stays as it was.
        ``client.spy.total_spies()`` adds the boosts.
        """
        with self._lock:
            return self.max_spies

    def get_player_last_updated(self) -> float | None:
        """When any local-player field was last refreshed, or ``None``.

        Player fields arrive in the login gbd and again as a push whenever the
        server changes them (gpi, gxp, gcu, vip, gal, gcl, gho, uap, glu, mir,
        sce). A stamp far in the past means no push has arrived since, not
        that the values were re-confirmed.
        """
        with self._lock:
            return self._player_updated_at
