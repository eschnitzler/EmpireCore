"""
The game state, kept current from server packets.
"""

import time
from collections.abc import Set as AbstractSet
from typing import Any

from empire_core.state.account import ACCOUNT_SECTIONS, AccountState
from empire_core.state.alliance import AllianceState
from empire_core.state.area import AreaState
from empire_core.state.base import MovementEventCallback
from empire_core.state.castles import CastleState
from empire_core.state.commanders import CommanderState
from empire_core.state.events import EventCallback, EventsCallback, EventState
from empire_core.state.inventory import INVENTORY_SECTIONS, InventoryState
from empire_core.state.movements import MOVEMENT_PARSE_WARN_INTERVAL, MovementState
from empire_core.state.player import PlayerState
from empire_core.state.progress import ProgressState
from empire_core.state.quests import QuestState

__all__ = ["MOVEMENT_PARSE_WARN_INTERVAL", "EventCallback", "EventsCallback", "GameState", "MovementEventCallback"]
# gbd sections stamped under their own id, whether they came in a gbd or as a push.
_TRACKED_SECTIONS = (
    "gpi",
    "gxp",
    "gcu",
    "vip",
    "gal",
    "gcl",
    "gho",
    "uap",
    "gac",
    "sce",
    "dcl",
    "tei",
    "sei",
    "gpc",
    "gms",
    "gli",
    "skl",
    "ain",
    "acl",
    "rei",
    "boi",
    "gmu",
    "ufa",
    "uar",
    "vli",
    "gri",
    "cpi",
    "dql",
    *ACCOUNT_SECTIONS,
    *INVENTORY_SECTIONS,
)

_PLAYER_SECTIONS = frozenset({"gpi", "gxp", "gcu", "vip", "gal", "gcl", "gho", "uap", "gac", "sce"})

# Pushes whose payload is the body of the gbd section of the same name.
_SECTION_PUSHES = frozenset({"gpi", "gxp", "gcu", "vip", "gal", "gcl", "gho", "uap", "gpc", "gms"})

# Replies and pushes whose payload is the body of a gbd section, applied only on success:
# GLICommand, SKLCommand, AINCommand, ACNCommand, CALCommand, ACLCommand (bundle lines 123977,
# 129742, 121462, 121332, 121668, 121302), REICommand, BOICommand, GMUCommand, UFACommand,
# UARCommand, VLICommand, GRICommand, CPICommand (bundle lines 126862, 122629, 129605, 129859,
# 120997, 121145, 129654, 128524), DQLCommand (bundle line 126512), GAICommand, GATPCommand,
# BIECommand, PGLCommand, RWWCommand, NRFCommand (bundle lines 122051, 126126, 122579, 127961,
# 126903, 124002), GGMCommand, GLSCommand, ESLCommand, KPICommand, MPECommand, TXICommand,
# NECCommand, IRCCommand (bundle lines 123957, 124800, 123895, 124684, 125109, 128792, 123294, 123090)
_WHOLE_SECTIONS = {
    "gli": "gli",
    "skl": "skl",
    "ain": "ain",
    "acn": "ain",
    "cal": "ain",
    "acl": "acl",
    **{section: section for section in ("rei", "boi", "gmu", "ufa", "uar", "vli", "gri", "cpi")},
    "dql": "dql",
    **{section: section for section in ACCOUNT_SECTIONS if section != "drt"},
    **{section: section for section in INVENTORY_SECTIONS},
}

# Replies that carry a gbd section under its own key, applied only on success: ARLCommand,
# GLACommand, SEQCommand, SDICommand, STICommand (bundle lines 123658, 124219, 124024, 122353,
# 129100), the attack and conquer info replies through CastleAttackInfoVO.fillFromParamObject
# (bundle line 30633; CastleAttackData, bundle lines 133821-133845), EGOCommand (bundle line
# 122801), ACDCommand, ADOCommand, AKMCommand, ARMCommand (bundle lines 121282, 121347, 121514, 121590),
# RESCommand, MSRCommand (bundle lines 126877, 125830), the booster replies BCSCommand,
# BDSCommand, BISCommand, BMSCommand, BRSCommand, OVSCommand, UPSCommand, BTXCommand (bundle lines
# 122539, 122554, 122599, 122614, 122644, 122659, 125723, 128733), CPMCommand, SBPCommand
# (bundle lines 128539, 128320). The coins and rubies (gcu) wherever the client parses them too,
# and sbp's vip; cpm's gcu comes with its movement. The tax replies TXSCommand and TXCCommand
# (bundle lines 128808, 128748) and BTXCommand bring their txi. The equipment and gem replies
# BGMCommand, CEQCommand, CGECommand, FRCCommand and SEQCommand (bundle lines 123727, 123783,
# 123798, 123912, 124019) bring their esl; the kingdom replies KGTCommand, KSTCommand, KUTCommand,
# MSKCommand and FJFCommand (bundle lines 124654, 124713, 124728, 125795, 127783) their kpi
_NESTED_SECTIONS: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(("arl", "gla", "sdi", "sti"), ("gli",)),
    "seq": ("gli", "gcu", "esl"),
    **dict.fromkeys(("aci", "abi", "acc", "adi", "aii", "ali", "avi", "cci", "coi", "cti", "gti", "cfi"), ("gli",)),
    "ego": ("skl",),
    **dict.fromkeys(("acd", "akm", "arm"), ("ain",)),
    "ado": ("gcu", "ain"),
    "res": ("rei", "gcu"),
    "msr": ("rei",),
    **dict.fromkeys(("bcs", "bds", "bis", "bms", "brs", "ovs", "ups"), ("gcu", "boi")),
    "btx": ("gcu", "boi", "txi"),
    "cpm": ("cpi",),
    "sbp": ("gcu", "cpi", "vip"),
    **dict.fromkeys(("txs", "txc"), ("gcu", "txi")),
    **dict.fromkeys(("bgm", "ceq", "cge", "frc"), ("esl",)),
    **dict.fromkeys(("kgt", "kst", "kut"), ("gcu", "kpi")),
    **dict.fromkeys(("msk", "fjf"), ("kpi",)),
}

# Commands whose state the client applies only from a successful reply: SEICommand, SEECommand,
# TEICommand, TEECommand, PEPCommand, FJFCommand, BSTCommand (bundle lines 128379, 128364,
# 128409, 128394, 128214, 127782, 127608), ACMCommand, AQICommand, UFPCommand, BFSCommand (bundle
# lines 121317, 121557, 121010, 122569), GTPCommand (bundle line 126146), the section replies above;
# a cpm error reply still reaches the movement handler, its cpi only a successful one. Also the castle
# pushes and replies:
# RUECommand, KIKCommand, GSMCommand, RCICommand, CMRCommand, RCCCommand, JAACommand, FBECommand,
# CBXCommand, GDBCommand, GCBCommand, CSLCommand and GABCommand (bundle lines 125647, 123114,
# 125752, 123196, 125737, 123181, 130190, 122880, 123345, 122998, 122968, 122715, 122923); GECCommand
# (bundle line 123927). And the quest ones: QLICommand, QSTCommand, QPGCommand, QFICommand,
# MSPCommand, CQSCommand (bundle lines 126587, 126619, 126603, 126566, 125438, 126495)
_SUCCESS_ONLY = frozenset(
    {"sei", "see", "tei", "tee", "pep", "fjf", "bst", "acm", "aqi", "ufp", "bfs", "gtp", *_WHOLE_SECTIONS}
    | (set(_NESTED_SECTIONS) - {"cpm"})
    | {"rue", "kik", "gsm", "rci", "cmr", "rcc", "jaa", "fbe", "cbx", "gdb", "gcb", "csl", "gab", "gec"}
    | {"qli", "qst", "qpg", "qfi", "msp", "cqs"}
)


class GameState(
    MovementState,
    CastleState,
    AreaState,
    PlayerState,
    EventState,
    CommanderState,
    AllianceState,
    ProgressState,
    QuestState,
    AccountState,
    InventoryState,
):
    """
    Manages game state parsed from server packets.

    State is mutated by the network receive thread and read from user
    threads, so all mutation and snapshot reads are guarded by a lock.

    The public attributes stay readable directly, but callers that read
    several fields at once (or iterate a container) should use the snapshot
    accessors — ``get_local_player()``, ``get_special_currencies()``, ``get_castles()``,
    ``get_all_movements()``, ``get_events()``, ``get_alliance_chat()``, ``get_commanders()``,
    ``get_skills()``, ``get_own_alliance()``, ``get_quests()`` — which copy under the lock, or hand out read-only
    models (``get_research()``, ``get_boosts()`` and the other progress accessors). Mutation paths swap
    containers instead of editing them in place, so an unlocked reader that
    already holds one never sees it change underneath.

    Callbacks (the ``on_*`` registrations) run on one callback thread, never
    on the receive thread: one at a time, in the order their packets were
    applied, so two callbacks never run at once and the events for one
    movement arrive in order. A callback may wait for a reply, but everything
    queued behind it waits too, so hand long work to another thread.

    Freshness
    ---------
    Nothing here polls the server: every field is as old as the last packet
    that carried it, and some packets arrive only once per session. Cached
    values are therefore *not* automatically current:

    ===================================  ==========================  ======================================
    State                                Refreshed by                Force a refresh with
    ===================================  ==========================  ======================================
    castle name/coords, castle list      ``gcl``, ``mir`` (pushed)    re-login
    castle resources/units/details       ``dcl``                      ``client.castle.get_details(id)``
    castle units (also)                  ``rue`` (pushed)             ``client.castle.get_details(id)``
    castle open-gate counter             ``gcl``, ``kik`` (pushed)    re-login
    castle unlocked units and horses     ``gpc`` (pushed)             re-login
    joined area, slum level, discount    ``jaa``, ``csl``/``gab``     ``client.castle.join(id)``
                                         (pushed)
    joined castle's mines                ``gsm`` (pushed), ``jaa``,   ``client.castle.join(id)``
                                         ``cmr``
    joined castle's resource carts       ``rci`` (pushed), ``jaa``,   ``client.castle.join(id)``
                                         ``rcc``
    player identity/level/XP             ``gpi``/``gxp``/``glu``      re-login
    player coins/rubies, VIP, alliance    ``gcu``/``vip``/``gal``      re-login
    honor, beginner protection           ``gho``/``uap``              re-login
    special currencies                   ``sce`` (pushed)             --
    spies owned, before boosts           ``gms`` (pushed)             re-login
    commanders and castellans            ``gli``, the replies that    ``client.commanders.get_all()``
                                         carry one (``arl``, ...)
    legend and sceat skills              ``skl``, ``ego``             ``client.skills.get_skills()``
    your alliance's details, members     ``ain``, ``acn``, ``akm``,   ``client.alliance.get_alliance_info(id)``
                                         ..., ``acm`` (online)
    alliance chat history                ``acl``, ``acm`` (pushed)    --
    research                             ``rei``, ``res``, ``msr``    re-login
    boosters, premium, slots, festival   ``boi``, booster replies,    re-login
                                         ``bfs``
    might points                         ``gmu`` (pushed)             re-login
    glory points                         ``ufa`` (pushed)             re-login
    Berimond points                      ``ufp`` (pushed only)        --
    top-X ranks, Storm Islands title     ``uar`` (pushed)             re-login
    achievements                         ``vli`` (pushed)             re-login
    relocation                           ``gri`` (pushed)             re-login
    plague monks                         ``cpi``, ``cpm``, ``sbp``    re-login
    daily reset                          ``drt`` (login only)         re-login
    attack counter                       ``gai`` (pushed)             re-login
    officers' school training            ``gatp``, ``gtp``            re-login
    boosted global effects               ``bie`` (pushed)             re-login
    gift packages                        ``pgl``                      re-login
    ruby wishing well                    ``rww``                      re-login
    new relics flag                      ``nrf`` (pushed)             re-login
    gems and relic gems                  ``ggm``, ``gec`` (pushed)    re-login
    loot boxes, key progress             ``gls`` (pushed)             re-login
    inventory space                      ``esl``, the crafting and    re-login
                                         selling replies
    kingdoms, transfers between them     ``kpi``, the transfer        re-login
                                         replies
    mercenary missions                   ``mpe``                      re-login
    tax collection                       ``txi``, ``txs``, ``txc``,   ``client.castle.get_tax_info()``
                                         ``btx``
    construction item expiry             ``nec`` (pushed)             re-login
    resource citizen                     ``irc`` (pushed)             --
    running events, scores, ends         ``sei``/``tei`` (pushed),    ``client.events.refresh()``
                                         ``see``/``tee``, ``pep``,
                                         ``fjf``, ``bst``, ``cqs``
    active quests, quest book            ``qli`` (pushed after        --
                                         login), ``qst``, ``qfi``,
                                         ``msp``
    daily quests                         ``dql`` (pushed)             re-login
    movements                            ``gam``, ``abr``/``asr``,    ``client.movements.get_movements()``
                                         your sends' replies
                                         (``cra``, ``cds``, ...)
    ===================================  ==========================  ======================================

    Every player section above is sent inside the login gbd and again as a
    push of its own when it changes. When the connection is lost, or the
    client is closed, everything is reset (see :meth:`reset`). The next
    login's gbd refills the player and castles, and the gam the server pushes
    after it (seen live) the movements; ``get_last_packet_time("gbd")`` and
    ``get_last_packet_time("gam")`` say when.

    In practice a castle's ``resources`` often reflects login time and nothing
    else, so use the freshness accessors before trusting them:
    :meth:`get_castle_last_updated` / :meth:`get_castle_age`,
    :meth:`get_player_last_updated`, :meth:`get_events_last_updated`, and :meth:`get_last_packet_time` /
    :meth:`get_packet_times` for per-packet timestamps. All timestamps are
    wall-clock (``time.time()``) seconds, and ``None`` means "never seen",
    which is different from "seen and empty".
    """

    _DISPATCH: dict[str, str] = {
        "gbd": "_handle_gbd",
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
        "fjf": "_handle_fjf",
        "sce": "_handle_sce",
        "sei": "_handle_sei",
        "see": "_handle_see",
        "tei": "_handle_tei",
        "tee": "_handle_tee",
        "pep": "_handle_pep",
        "bst": "_handle_bst",
        "acm": "_handle_acm",
        "aqi": "_handle_aqi",
        "ufp": "_handle_ufp",
        "bfs": "_handle_bfs",
        "gtp": "_handle_gtp",
        # Castle pushes and the joined area
        "rue": "_handle_rue",
        "kik": "_handle_kik",
        "jaa": "_handle_jaa",
        "gsm": "_handle_gsm",
        "cmr": "_handle_cmr",
        "rci": "_handle_rci",
        "rcc": "_handle_rcc",
        "csl": "_handle_csl",
        "gab": "_handle_gab",
        "fbe": "_handle_fbe",
        "cbx": "_handle_cbx",
        "gdb": "_handle_gdb",
        "gcb": "_handle_gcb",
        # Any map read leaves the joined castle, refused or not
        "gaa": "_handle_gaa",
        "gec": "_handle_gec",
        "qli": "_handle_qli",
        "qst": "_handle_qst",
        "qpg": "_handle_qpg",
        "qfi": "_handle_qfi",
        "msp": "_handle_msp",
        "cqs": "_handle_cqs",
    }

    def update_from_packet(self, cmd_id: str, payload: dict[str, Any], error_code: int = 0) -> None:
        """Central update router — parses packet and updates state.

        ``error_code`` is the packet's status; a command the client reads only
        from a successful reply is skipped, unstamped, when it is not 0.

        Every packet, handled or not, also advances movements, so arrivals
        fire with the server's traffic rather than only on movement packets.
        """
        handler_name = self._DISPATCH.get(cmd_id)
        ok = error_code == 0
        with self._lock:
            if not ok and cmd_id in _SUCCESS_ONLY:
                pass
            elif cmd_id in _SECTION_PUSHES:
                # An unreadable frame arrives as {"raw": ...}; the client applies a push only on success
                if isinstance(payload, dict) and "raw" not in payload:
                    self._packet_times[cmd_id] = time.time()
                    self._handle_gbd({cmd_id: payload})
            elif cmd_id in _WHOLE_SECTIONS:
                # Stamped only when applied: not for an unreadable frame, a block that does not
                # validate, or another alliance's ain
                if isinstance(payload, dict) and "raw" not in payload:
                    section = _WHOLE_SECTIONS[cmd_id]
                    if cmd_id == "acl":
                        if self._parse_chat_history({"acl": payload}, replace=True):
                            self._packet_times["acl"] = time.time()
                    elif section not in self._handle_gbd({section: payload}):
                        self._packet_times[cmd_id] = time.time()
            elif handler_name:
                self._packet_times[cmd_id] = time.time()
                getattr(self, handler_name)(payload)
            if ok and cmd_id in _NESTED_SECTIONS and isinstance(payload, dict):
                if sections := {key: payload[key] for key in _NESTED_SECTIONS[cmd_id] if key in payload}:
                    self._handle_gbd(sections)
            self._advance_movements()
            self._expire_events()

    def _handle_gbd(self, data: dict[str, Any]) -> set[str]:
        """Apply the login data, or the one section a push wraps in the same shape.

        Returns the sections present but not applied, which are not stamped.

        Client: ``GBDCommand.exec``; the pushes are ``GPICommand``, ``GXPCommand``,
        ``GCUCommand``, ``VIPCommand``, ``GALCommand``, ``GCLCommand``,
        ``GHOCommand``, ``UAPCommand``, ``GPCCommand`` and ``GMSCommand`` (bundle line 120555);
        ``GBDCommand.exec`` (bundle line 129381) applies ``gal`` before ``ain`` and ``tei`` before ``sei``.
        """
        self._parse_player_sections(data)
        self._parse_special_currencies(data)
        self._parse_alliance_info(data)
        self._apply_gal_reset(data)
        skipped = {
            section
            for section, applied in (
                ("ain", self._parse_own_alliance(data)),
                ("acl", self._parse_chat_history(data)),
                ("gli", self._parse_commanders(data)),
                ("skl", self._parse_skills(data)),
                ("dql", self._parse_daily_quests(data)),
                # CastleVIPData.parse_VIP (bundle line 47527) ignores a vip that is not set
                ("vip", isinstance(data.get("vip"), dict)),
            )
            if not applied
        }
        skipped |= self._parse_progress(data)
        skipped |= self._parse_account(data)
        skipped |= self._parse_inventory(data)
        self._parse_castles(data)
        self._parse_permanent_castles(data)
        self._parse_max_spies(data)
        if dcl := data.get("dcl"):
            self._handle_dcl(dcl)
        if "tei" in data:
            self._handle_tei(data["tei"])
        if "sei" in data:
            self._handle_sei(data["sei"])
        self._stamp_sections(data, skipped)
        return skipped

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
        """Apply a send reply's coins and rubies (``gcu``), then store its movement with the owner records (``O``).

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

    def _handle_fjf(self, data: Any) -> None:
        """Apply a faction join reply's events (``sei``), then the castle list in its ``mir``.

        Client: ``FJFCommand.executeCommand`` (bundle line 127783):
        ``parse_SEI(i.sei),i.mir&&parse_MIR(i.mir)``.
        """
        if isinstance(data, dict):
            self._apply_sei(data)
            self._handle_mir(data.get("mir"))

    def _handle_bst(self, data: Any) -> None:
        """Apply the reply to a bounty hunter target skip: its coins and rubies, then its ``sei``.

        Client: ``BSTCommand.executeCommand`` (bundle line 127609)
        """
        if isinstance(data, dict):
            if isinstance(gcu := data.get("gcu"), dict):
                self._handle_gbd({"gcu": gcu})
            self._apply_sei(data)

    def _stamp_sections(self, data: dict[str, Any], skipped: AbstractSet[str] = frozenset()) -> None:
        """Record when each section of a gbd payload, or a section push, was applied.

        A section present but null still counts as applied: "gal": None means
        "you are in no alliance", which is information, not absence of it.
        A null "vip" does not: the client ignores it.
        Sections carrying local-player fields also refresh the player stamp,
        but only once there is a player to attach it to.
        """
        now = time.time()
        for section in _TRACKED_SECTIONS:
            if section in data and section not in skipped:
                self._packet_times[section] = now
                if section in _PLAYER_SECTIONS and self.local_player is not None:
                    self._player_updated_at = now

    def get_last_packet_time(self, cmd_id: str) -> float | None:
        """When a packet (or gbd sub-packet) of this kind was last applied.

        Accepts the wire ids this manager tracks — "gbd", "gam", "dcl", "abr", "asr", the send replies ("cra",
        "cam", "abgcam", "cds", "csm", "cat", "crm", "css", "tde", "cdd", "cpm", "thm", "ldt"), "mcm", "mrm",
        "mfc", "glu", "mir", "fjf", "bst", "sce", "see", "tee", "pep", "acm", "aqi", "acn", "cal", "ufp", "bfs",
        the officers' school's "gtp" (only a successful one),
        the quest pushes "qli", "qst", "qpg", "qfi", "msp" and the campaign's "cqs",
        the castle pushes "rue", "kik", "fbe", "cbx", "gdb", "gcb", the gem push "gec", the joined area's "jaa",
        "cmr", "rcc" and the map read "gaa" (refused too) — and the login sections "gpi", "gxp", "gcu", "vip",
        "gal", "gcl", "gho", "uap", "gpc", "gms", "sei", "tei", "gli", "skl", "ain", "acl", "rei", "boi", "gmu",
        "ufa", "uar", "vli", "gri", "cpi", "dql", "gai", "gatp", "bie", "pgl", "rww", "nrf", "ggm", "gls", "esl",
        "kpi", "mpe", "txi", "nec" and "irc", stamped whether they came inside a gbd, as a push of their own or
        inside a reply that carries one ("sei" from a fjf or bst, "gli" from an arl, "ain" from an akm, "rei"
        from a res, "kpi" from a kut, ...), plus "gac" and "drt", which only come inside a gbd. "gsm" and "rci"
        are stamped whenever mines or resource carts are applied, from their push or a jaa, cmr or rcc reply;
        "csl" and "gab" from their push or a jaa, the push even when no area was joined to apply it to. A send
        reply is stamped even when the server refused the send; the commands the client reads only from a
        successful reply (the event ones, the login section ones, the castle ones, the quest ones, "gec", "acm",
        "aqi", "ufp" and "bfs") are not, nor is a login section that was not applied: unreadable, not valid, or
        another alliance's "ain". ``None`` means none was ever seen;
        packets this manager ignores are never recorded.
        """
        with self._lock:
            return self._packet_times.get(cmd_id)

    def get_packet_times(self) -> dict[str, float]:
        """Snapshot of every tracked packet/sub-packet timestamp."""
        with self._lock:
            return dict(self._packet_times)
