"""The running events: sei and tei entries, see and tee ends, pep scores, cqs campaigns, and their callbacks;
and the events shutting down (sde)."""

import logging
import time
from collections.abc import Callable, Iterable
from typing import Any, Literal

from pydantic import ValidationError
from typing_extensions import overload

from empire_core.attack.models.alien_camps import AlienRerollCountsResponse
from empire_core.attack.models.taunts import RagePointsResponse
from empire_core.enums import Kingdom
from empire_core.enums.events import LuckyWheelType
from empire_core.events.faction_models import BerimondKingdomStatus
from empire_core.events.minigame_models import (
    ArtifactFoundResponse,
    DonationProgressResponse,
    GachaFreeChestResponse,
    GachaSpinResponse,
    LuckyWheelBuyJackpotResponse,
    LuckyWheelChangeModeResponse,
    LuckyWheelIncreaseWinClassResponse,
    LuckyWheelSpinResponse,
    VoteWorldCupResponse,
)
from empire_core.events.models import (
    AlienInvasionEvent,
    AllianceBonusEvent,
    AllianceTournamentEvent,
    ArtifactEvent,
    BeggingKnightsEvent,
    BerimondEvent,
    CampaignEvent,
    CampaignQuestEvent,
    DiscountSaleEvent,
    DonationEvent,
    EventAnnouncementEvent,
    FactionInvasionEvent,
    FameBoosterEvent,
    FortuneTellerEvent,
    GachaEvent,
    GiftEvent,
    GlobalEffectBuffEvent,
    GlobalEffectEvent,
    GrandTournamentEvent,
    KingdomsLeagueEvent,
    LongTermPointEvent,
    LuckyWheelEvent,
    NomadInvasionEvent,
    PointEvent,
    RaidBossEvent,
    SamuraiInvasionEvent,
    SeasonEvent,
    ShuttingDownEvents,
    SkipForFreeEvent,
    SpecialEvent,
    TempServerEvent,
    TournamentEvent,
    WorldCupEvent,
    event_class,
)
from empire_core.events.special_server_models import CurrentServer, SpecialServerCastles
from empire_core.events.status_models import GrandTournamentQuestStatus, GrandTournamentQuestUpdate, RaidBossStatus
from empire_core.gamedata.ids.events import Event
from empire_core.map.models.areas import KingdomProtection
from empire_core.player.models.protection import StartFactionProtectionResponse
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_int, js_truthy
from empire_core.state.base import StateBase, read_section
from empire_core.utils import callbacks

logger = logging.getLogger(__name__)
_clock = time.monotonic

EventCallback = Callable[[SpecialEvent], Any]
EventsCallback = Callable[[dict[int, SpecialEvent]], Any]


class EventState(StateBase):
    _grand_tournament_generation = 0
    _grand_tournament_action_context: tuple[int, int | None, int] | None = None
    # The gacha event a dge was sent for: its reply names only the gachas row pulled from, which the client
    # maps to the event through game data the library does not load
    _gacha_spin_event: int | None = None

    def _quest_action_context(self) -> tuple[int, int | None, int] | None:
        with self._lock:
            event = self.events.get(Event.GRAND_TOURNAMENT)
            return (
                (
                    self._grand_tournament_generation,
                    self.local_player.AID if self.local_player else None,
                    self.membership_revision,
                )
                if event
                else None
            )

    def _begin_gacha_spin(self, eid: int) -> None:
        with self._lock:
            self._gacha_spin_event = eid

    def _end_gacha_spin(self) -> None:
        with self._lock:
            self._gacha_spin_event = None

    def _begin_quest_action(self) -> tuple[int, int | None, int] | None:
        with self._lock:
            self._grand_tournament_action_context = self._quest_action_context()
            return self._grand_tournament_action_context

    def _end_quest_action(self) -> None:
        with self._lock:
            self._grand_tournament_action_context = None

    on_event_added = callbacks.Event[SpecialEvent]()
    """Register a callback for an event that starts: a ``sei`` or ``tei`` entry for an event not running.

    Called with the event as that entry left it. Runs on the callback thread, in packet
    order (see :class:`GameState`).

    Client: ``CastleSpecialEventEvent.ADD_SPECIALEVENT`` from ``parseServerEventData`` (bundle line 139814)
    """

    on_event_removed = callbacks.Event[SpecialEvent]()
    """Register a callback for an event that ends: a ``see`` or ``tee``, or its time running out.

    Called with the event as it last stood. A disconnect (see :meth:`reset`) fires none.

    Client: ``CastleSpecialEventEvent.REMOVE_SPECIALEVENT`` from ``removeEventById`` (bundle line 139840),
    reached from ``parse_SEE``, ``parseTEE`` and ``executeUpdateForEvents`` (bundle lines 139826, 139915, 139836)
    """

    on_events_updated = callbacks.Event[dict[int, SpecialEvent]]()
    """Register a callback for every ``sei``, non-empty ``tei``, ``pep`` and ``cqs`` applied.

    Called with every running event (a copy of :meth:`get_events`), after the
    :meth:`on_event_added` and :meth:`on_event_removed` callbacks of the same packet.

    Client: ``onEventDataParsed`` (bundle line 139818) sends ``REFRESH_SPECIALEVENT`` for every
    event and ``SERVER_DATA_PARSED``; ``AScoreEventVO.setRankAndPoints`` (bundle line 15044)
    sends ``UPDATE_POINTS`` for a ``pep``; ``CQSCommand.exec`` (bundle line 126495) sends
    ``CAMPAIGN_UPDATED`` for a ``cqs``
    """

    def _handle_sei(self, data: Any) -> None:
        """Handle 'Send Event Information': each entry updates its event, or adds it.

        An entry for a running event is read over it: the raw entries are merged (the parts an
        event rebuilds from every entry are replaced), and each field the event reads only when
        the entry has it keeps its value. Events the packet does not name run on until a see
        ends them or their time runs out. An entry whose ``EID`` reads as 0 or below is skipped;
        the client drops ids its events table lacks, the library keeps every other id. An entry
        the client fails to read (a global effect event's effects without ``SGE``) is skipped.

        Where the library differs: the client also refuses to add a prime sale it cannot offer
        (``canBeAddedToActiveEvents``, e.g. 75 and 90, bundle lines 115951, 118134), which the
        library adds; and an ``RS`` that is not a number gives the client an end it never
        reaches nor passes, where the library keeps the event's earlier end.

        Client: ``CastleSpecialEventData.parse_SEI`` (bundle line 139800), which reads ``int(a.EID)``,
        and ``parseServerEventData`` (bundle line 139811)
        """
        events = data.get("E") if isinstance(data, dict) else None
        self._apply_event_entries(events if isinstance(events, list) else [], "EID")

    def _apply_sei(self, data: dict[str, Any]) -> None:
        """Apply the ``sei`` a reply carries, stamped as a sei."""
        if "sei" in data:
            self._packet_times["sei"] = time.time()
            self._handle_sei(data["sei"])

    def _handle_tei(self, data: Any) -> None:
        """Handle 'trigger event info': each ``TE`` entry updates or adds its event, keyed by ``TRID``.

        The trigger events (the kingdoms league and the global effect events) join the
        other running events; their ends come from their own fields, as their models say.

        Client: ``TEICommand`` (bundle line 128410) and ``CastleSpecialEventData.parseTEI``
        (bundle line 139905), which reads ``int(a.TRID)`` and does nothing for an empty ``TE``;
        ``ATriggerEventVO.parseBasicsFromParamObject`` (bundle line 39815)
        """
        entries = data.get("TE") if isinstance(data, dict) else None
        if isinstance(entries, list) and entries:
            self._apply_event_entries(entries, "TRID")
        else:
            self._events_updated_at = time.time()

    def _apply_event_entries(self, entries: list[Any], key: str) -> None:
        now = _clock()
        events = dict(self.events)
        added: list[SpecialEvent] = []
        for entry in entries:
            if not isinstance(entry, dict) or (eid := js_int(entry.get(key))) <= 0:
                continue
            model = event_class(eid)
            if not model.accepts(entry):
                logger.debug(f"Skipping an entry for event {eid} that the client fails to read")
                continue
            previous = events.get(eid)
            events[eid] = model.from_entry(eid, entry, previous, now, events)
            if isinstance(events[eid], AlienInvasionEvent):
                # AAlienInvasionEventVO.parseData (bundle line 58933) reads the entry with parse_RCE too
                self._handle_rce(entry)
            if previous is None:
                if eid == Event.GRAND_TOURNAMENT:
                    self._grand_tournament_generation += 1
                added.append(events[eid])
        self.events = events
        self._events_updated_at = time.time()
        for event in added:
            self._fire(self.on_event_added, event)
        self._expire_events()
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_see(self, data: Any) -> None:
        """Handle a 'special event end' push: the event it names has ended.

        Client: ``CastleSpecialEventData.parse_SEE`` (bundle line 139826), from ``SEECommand``
        (bundle line 128364), looks the ``EID`` up as sent; ``removeEventById`` (bundle line
        139838) destroys the event, so one added again starts over
        """
        if (event := self._sent_event(data.get("EID") if isinstance(data, dict) else None)) is not None:
            self._remove_event(event.event_id)
        self._events_updated_at = time.time()

    def _handle_tee(self, data: Any) -> None:
        """Handle 'trigger event end': the trigger event it names (``TRID``) has ended.

        Client: ``TEECommand`` (bundle line 128395) and ``CastleSpecialEventData.parseTEE``
        (bundle line 139915): ``int(e&&e.TRID?e.TRID:-1)``, removed when 0 or above
        """
        trid = data.get("TRID") if isinstance(data, dict) else None
        eid = js_int(trid if js_truthy(trid) else -1)
        if eid >= 0:
            self._remove_event(eid)
        self._events_updated_at = time.time()

    def _handle_sde(self, data: Any) -> None:
        """Handle the events shutting down: the list replaces the one before.

        Client: ``CastleSpecialEventData.parse_SDE`` (bundle line 139841)
        """
        if isinstance(data, dict) and "raw" not in data:
            shutting_down = read_or_none(ShuttingDownEvents.model_validate, data, warn=logger, what="an sde push")
            if shutting_down is not None:
                self.shutting_down_events = shutting_down

    def _handle_pep(self, data: Any) -> None:
        """Handle 'point event points': your rank (``OR``), points (``OP``) and the event's most points (``PT``).

        Each event reads them as its client class does: a score event its first of each, an
        invasion one per part in order, Berimond and the lucky wheels the first rank and points,
        the raid boss and the alliance Grand Tournament the first for you and the second for your
        alliance, the alliance tournament the first for your alliance, and ``BLPP`` the raid boss's
        level points. The library reads every value through ``int()``, where the client keeps them
        as sent.

        Client: ``PEPCommand.exec`` (bundle lines 128213-128216), which looks the ``EID`` up as sent,
        and the ``setRankAndPoints`` of each class
        """
        self._events_updated_at = time.time()
        self._expire_events()
        event = self._sent_event(data.get("EID") if isinstance(data, dict) else None)
        if event is None:
            return
        updated = event.with_points(data.get("OR"), data.get("OP"), data.get("PT"))
        if data.get("BLPP") is not None and "boss_level_points" in type(updated).model_fields:
            updated = updated.model_copy(update={"boss_level_points": js_int(data["BLPP"])})
        self.events = {**self.events, event.event_id: updated}
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_cqs(self, data: Any) -> None:
        """Handle a campaign quest status: the running time-limited campaign reads its campaign from it again.

        Client: ``CQSCommand.exec`` (bundle line 126495) does nothing without the campaign running;
        ``TimeLimitedCampaignEventEventVO.parseCQS`` (bundle line 118555)
        """
        self._expire_events()
        campaign = self.events.get(Event.TIME_LIMITED_CAMPAIGN_EVENT)
        if not (isinstance(campaign, CampaignEvent) and isinstance(data, dict)):
            return
        self.events = {**self.events, campaign.event_id: campaign.with_campaign(data, _clock())}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_aqs(self, data: Any) -> None:
        """AQSCommand applies slots only to the named Grand Tournament event (bundle 127419-127420)."""
        self._expire_events()
        event = self._sent_event(data.get("EID") if isinstance(data, dict) else None)
        if not isinstance(event, GrandTournamentEvent):
            return
        try:
            status = GrandTournamentQuestStatus.model_validate(data)
        except ValidationError:
            logger.warning("Unreadable alliance quest status; kept previous event status")
            return
        updated = event.model_copy(update={"quest_status": status})
        self.events = {**self.events, event.event_id: updated}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_grand_tournament_action(self, data: Any) -> None:
        """Apply nested action slots in receive order (bundle 127430-127503)."""
        if not isinstance(data, dict):
            return
        try:
            update = GrandTournamentQuestUpdate.model_validate(data.get("aqs"))
        except ValidationError:
            logger.warning("Unreadable Grand Tournament quest action; kept previous status")
            return
        self._expire_events()
        nested = data.get("aqs")
        event = self._sent_event(nested.get("EID") if isinstance(nested, dict) else None)
        if not isinstance(event, GrandTournamentEvent):
            return
        context = self._grand_tournament_action_context
        if context is None or context != self._quest_action_context():
            return
        previous = event.quest_status
        status = GrandTournamentQuestStatus.model_construct(
            event_id=update.event_id,
            participants=previous.participants if previous is not None else None,
            slots=update.slots,
        )
        self.events = {**self.events, event.event_id: event.model_copy(update={"quest_status": status})}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_fki(self, data: Any) -> None:
        """Handle a Berimond kingdom status, pushed on its own or inside a ``kpi``: kept on the running event.

        Client: ``FKICommand.executeCommand`` (bundle line 127859) and ``CastleKingdomData.parse_KPI``
        (bundle line 134604) hand a set one to the running faction event's ``parse_FKI`` (bundle line 7365)
        """
        self._expire_events()
        event = self.events.get(Event.FACTION)
        if not js_truthy(data) or not isinstance(event, BerimondEvent):
            return
        status = BerimondKingdomStatus.model_validate(data if isinstance(data, dict) else {})
        self.events = {**self.events, event.event_id: event.model_copy(update={"kingdom_status": status})}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_bse(self, data: Any) -> None:
        """Retain the applied reply snapshot independently of subsequent bbs broadcasts."""
        status = self._handle_raid_status(data)
        if status is not None:
            self._raid_boss_receipt = (data, status)

    def _raid_status_reply(self, data: Any) -> RaidBossStatus | None:
        """The status applied for this exact packet payload, under the caller's bse command lock."""
        with self._lock:
            receipt = self._raid_boss_receipt
            return receipt[1] if receipt is not None and receipt[0] is data else None

    def _handle_raid_status(self, data: Any) -> RaidBossStatus | None:
        """BSECommand and BBSCommand target the running raid event (bundle 127523,127538)."""
        self._expire_events()
        event = self.events.get(Event.ALLIANCE_RAIDBOSS_EVENT)
        if not isinstance(event, RaidBossEvent):
            return None
        try:
            status = RaidBossStatus.model_validate(data).with_previous(event.boss_status)
        except ValidationError:
            logger.warning("Unreadable raid boss status; kept previous event status")
            return None
        updated = event.model_copy(update={"boss_status": status})
        self.events = {**self.events, event.event_id: updated}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))
        return status

    def _handle_car(self, data: Any) -> None:
        """Handle the answer to an announcement reward claim: the running announcement's reward is collected.

        Client: ``CARCommand.executeCommand`` (bundle line 125277), ``EventAnnouncementData.parseCAR``
        (bundle line 53117), which fails without the announcement running
        """
        event = self.events.get(Event.EVENT_ANNOUNCEMENT)
        if isinstance(event, EventAnnouncementEvent):
            self.events = {**self.events, event.event_id: event.model_copy(update={"reward_collected": True})}
            self._fire(self.on_events_updated, dict(self.events))

    def _apply_faction_protection(self, blocks: Iterable[KingdomProtection]) -> None:
        """Read a Berimond protection block over the running Berimond event.

        Where the library differs: the client reads it only while it shows Berimond, as the block
        names the kingdom it is for.

        Client: ``CastleUserData.parse_UAP`` (bundle line 9906) hands it to ``FactionEventVO.parse_uap``
        (bundle line 7364)
        """
        event = self.events.get(Event.FACTION)
        berimond = [block for block in blocks if block.kingdom_id == Kingdom.BERIMOND]
        if not (isinstance(event, BerimondEvent) and berimond):
            return
        for block in berimond:
            event = event.with_protection(block, _clock())
        self._replace_event(event)

    def _handle_ffp(self, data: Any) -> None:
        """Apply a faction protection purchase's ``FN`` to the running Berimond event; its ``gcu`` is a nested section.

        Client: ``FFPCommand.executeCommand`` (bundle line 127785), ``CastleSpecialEventData.parse_FN``
        (bundle line 139876), which does nothing without the event or the block
        """
        event = self.events.get(Event.FACTION)
        reply = read_section(StartFactionProtectionResponse, data, "the faction protection")
        if isinstance(event, BerimondEvent) and reply is not None and reply.faction is not None:
            self._replace_event(event.with_faction(reply.faction, _clock()))

    def _handle_rpr(self, data: Any) -> None:
        """Apply a rage points push to the running alliance nomad invasion it names.

        Client: ``RPRCommand.executeCommand`` (bundle line 128217), which looks the ``EID`` up as sent,
        and ``AllianceNomadInvasionEventVO.parse_RPR`` (bundle line 114369)
        """
        rage = read_section(RagePointsResponse, data, "the rage points")
        event = self._sent_event(data.get("EID") if isinstance(data, dict) else None)
        if rage is not None and isinstance(event, NomadInvasionEvent):
            self._replace_event(
                event.model_copy(update={"player_rage": rage.player_rage, "player_total_rage": rage.player_total_rage})
            )

    def _handle_rce(self, data: Any) -> None:
        """Apply an alien reroll counts push over the counts known.

        Client: ``RCECommand.executeCommand`` (bundle line 127142), ``CastleAlienRerollData.parse_RCE``
        (bundle line 133595)
        """
        if (counts := read_section(AlienRerollCountsResponse, data, "the alien reroll counts")) is not None:
            self.alien_reroll_counts = counts.merged_into(self.alien_reroll_counts)

    def _handle_tse(self, data: Any) -> None:
        """Keep which kind of server this session is on.

        Client: ``TSECommand.executeCommand`` (bundle line 128917)
        """
        if (server := read_section(CurrentServer, data, "the server kind")) is not None:
            self.current_server = server

    def _handle_tcc(self, data: Any) -> None:
        """Keep your special server castles and mark the running temporary server event's castle bought or not.

        The client also marks the alliance battleground event's ``castleBought``; with no model for that
        event here, ``special_server_castles`` alone carries the battleground flag.

        Client: ``TCCCommand.executeCommand`` (bundle line 127354)
        """
        if (castles := read_section(SpecialServerCastles, data, "the special server castles")) is None:
            return
        self.special_server_castles = castles
        event = self.events.get(Event.TEMP_SERVER)
        if isinstance(event, TempServerEvent):
            self._replace_event(event.model_copy(update={"castle_bought": castles.temporary_server_castle_bought}))

    def get_current_server(self) -> CurrentServer | None:
        """The kind of server this session is on, from the last ``tse``; None until one came."""
        with self._lock:
            return self.current_server

    def get_special_server_castles(self) -> SpecialServerCastles | None:
        """Your special server castles, from the last ``tcc``; None until one came."""
        with self._lock:
            return self.special_server_castles

    def _handle_lws(self, data: Any) -> None:
        """Apply a spin to the wheel it turned: the sale days wheel for an ``LWET`` of 1, else the lucky wheel.

        Client: ``LWSCommand.executeCommand`` (bundle line 128141)
        """
        reply = read_section(LuckyWheelSpinResponse, data, "a lucky wheel spin")
        if reply is not None:
            sale_days = reply.wheel == LuckyWheelType.SALE_DAYS
            self._apply_lucky_wheel(Event.SALE_DAYS_LUCKY_WHEEL if sale_days else Event.LUCKY_WHEEL, reply)

    def _handle_lwj(self, data: Any) -> None:
        """Apply a jackpot spin to the lucky wheel. Client: ``LWJCommand.executeCommand`` (bundle line 128105)"""
        if (reply := read_section(LuckyWheelBuyJackpotResponse, data, "a lucky wheel jackpot")) is not None:
            self._apply_lucky_wheel(Event.LUCKY_WHEEL, reply)

    def _handle_lwc(self, data: Any) -> None:
        """Apply a win class raise to the lucky wheel. Client: ``LWCCommand.executeCommand`` (bundle line 128090)"""
        if (reply := read_section(LuckyWheelIncreaseWinClassResponse, data, "a lucky wheel win class")) is not None:
            self._apply_lucky_wheel(Event.LUCKY_WHEEL, reply)

    def _handle_lwm(self, data: Any) -> None:
        """Apply a mode change to the lucky wheel. Client: ``LWMCommand.executeCommand`` (bundle line 128122)"""
        if (reply := read_section(LuckyWheelChangeModeResponse, data, "a lucky wheel mode change")) is not None:
            self._apply_lucky_wheel(Event.LUCKY_WHEEL, reply)

    def _apply_lucky_wheel(
        self,
        eid: Event,
        reply: LuckyWheelSpinResponse | LuckyWheelIncreaseWinClassResponse | LuckyWheelChangeModeResponse,
    ) -> None:
        if isinstance(event := self.events.get(eid), LuckyWheelEvent):
            self._replace_event(event.with_reply(reply))

    def _handle_dge(self, data: Any) -> None:
        """Apply a gacha pull to the event it was sent for.

        Client: ``DGECommand.executeCommand`` (bundle line 124175), ``AGachaEventVO.parseGachaEvent`` (bundle line
        15379)
        """
        reply = read_section(GachaSpinResponse, data, "a gacha pull")
        event = self.events.get(self._gacha_spin_event) if self._gacha_spin_event is not None else None
        if reply is not None and isinstance(event, GachaEvent):
            self._replace_event(event.with_gacha_update(reply, _clock()))

    def _handle_cfc(self, data: Any) -> None:
        """Apply a free gacha chest to the event it names.

        Client: ``CFCCommand.executeCommand`` (bundle line 124161), which looks the ``EID`` up as sent
        """
        reply = read_section(GachaFreeChestResponse, data, "a gacha free chest")
        event = self._sent_event(data.get("EID") if isinstance(data, dict) else None)
        if reply is not None and isinstance(event, GachaEvent):
            self._replace_event(event.with_gacha_update(reply, _clock()))

    def _handle_artifact_found(self, data: Any) -> None:
        """Apply the pieces of an artifact found (``saf``) or bought (``sap``) to its running event.

        Client: ``CastleSpecialEventData.handleArtifactPartFound`` (bundle line 139892), which keeps no event it
        does not run
        """
        reply = read_section(ArtifactFoundResponse, data, "the artifact pieces")
        if reply is not None and isinstance(event := self.events.get(reply.event_id), ArtifactEvent):
            self._replace_event(event.model_copy(update={"parts_found": reply.parts_found}))

    def _handle_donation_progress(self, data: Any) -> None:
        """Keep the points per donation item (``gdti``, ``ddi``) on the running imperial patronage.

        Client: ``CastleDonationEventData.parseGDTI`` (bundle line 58869)
        """
        reply = read_section(DonationProgressResponse, data, "the donation progress")
        if reply is not None and isinstance(event := self.events.get(Event.DONATION_EVENT), DonationEvent):
            self._replace_event(event.model_copy(update={"donated_points": reply.items}))

    def _handle_vwc(self, data: Any) -> None:
        """Apply a world cup bet to the running world cup.

        Client: ``VWCCommand.executeCommand`` (bundle line 128541), ``WorldCupEventVO.parse_VWC`` (bundle line 24586)
        """
        reply = read_section(VoteWorldCupResponse, data, "a world cup vote")
        if reply is not None and isinstance(event := self.events.get(Event.WORLD_CUP), WorldCupEvent):
            self._replace_event(event.model_copy(update={"vote": reply.vote, "rubies_spent": reply.rubies_spent}))

    def _replace_event(self, event: SpecialEvent) -> None:
        self.events = {**self.events, event.event_id: event}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))

    def _sent_event(self, eid: Any) -> SpecialEvent | None:
        # The id as sent, compared as the client's Map compares keys: 3.0 is 3, "3" is not
        if not isinstance(eid, (int, float)) or isinstance(eid, bool):
            return None
        return next((event for key, event in self.events.items() if key == eid), None)

    def _remove_event(self, eid: int) -> None:
        event = self.events.get(eid)
        if event is None:
            return
        self.events = {key: value for key, value in self.events.items() if key != eid}
        if eid == Event.ALLIANCE_RAIDBOSS_EVENT:
            self._raid_boss_receipt = None
        self._forget_treasure_map_of(event)
        self._fire(self.on_event_removed, event)
        self._expire_events()

    def _expire_events(self) -> None:
        """Drop the events whose time is up, the kingdoms league's end read anew first.

        Client: ``CastleSpecialEventData.executeUpdateForEvents`` (bundle line 139833):
        ``remainingEventTimeInSeconds<=0``; ``SeasonLeagueEventVO.endTimestamp`` (bundle line 118061)
        is read whenever it is asked for
        """
        now = _clock()
        while self.events:
            events = dict(self.events)
            for eid, event in events.items():
                if isinstance(event, KingdomsLeagueEvent) and (end := event.end_with(events, now)) != event.end_time:
                    events[eid] = event.model_copy(update={"end_time": end})
            ended = [event for event in events.values() if event.end_time <= now]
            if events != self.events:
                self.events = events
            if not ended:
                return
            self.events = {eid: event for eid, event in events.items() if event.end_time > now}
            for event in ended:
                if event.event_id == Event.ALLIANCE_RAIDBOSS_EVENT:
                    self._raid_boss_receipt = None
                self._forget_treasure_map_of(event)
                self._fire(self.on_event_removed, event)

    def get_alien_reroll_counts(self) -> AlienRerollCountsResponse | None:
        """How often you rerolled alien camps, from the last ``rce`` and alien invasion entries; None until one came."""
        with self._lock:
            return self.alien_reroll_counts

    def get_events(self) -> dict[int, SpecialEvent]:
        """The running events by id, in the order they started; a copy.

        Each is the model its type has (:data:`~empire_core.events.models.EVENT_CLASSES`), or a
        plain :class:`~empire_core.events.models.SpecialEvent`. The models never change: a
        later packet replaces them.
        """
        with self._lock:
            self._expire_events()
            return dict(self.events)

    @overload
    def get_event(self, event: Literal[Event.FACTION]) -> BerimondEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.POINT_EVENT]) -> PointEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.BEGGING_KNIGHTS]) -> BeggingKnightsEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.LONG_TERM_POINT_EVENT]) -> LongTermPointEvent | None: ...
    @overload
    def get_event(
        self, event: Literal[Event.ALLIANCE_ALIEN_INVASION, Event.RED_ALLIANCE_ALIEN_INVASION]
    ) -> AlienInvasionEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.ALLIANCE_NOMAD_INVASION]) -> NomadInvasionEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.SAMURAI_INVASION]) -> SamuraiInvasionEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.FACTION_INVASION]) -> FactionInvasionEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.ALLIANCE_RAIDBOSS_EVENT]) -> RaidBossEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.TEMP_SERVER]) -> TempServerEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.DONATION_EVENT]) -> DonationEvent | None: ...
    @overload
    def get_event(
        self,
        event: Literal[
            Event.GACHA_DECO2X2,
            Event.CHRISTMAS_GACHA,
            Event.EASTER_GACHA,
            Event.SUMMER_GACHA,
            Event.ANNIVERSARY_GACHA,
            Event.HALLOWEEN_GACHA,
            Event.BLACK_FRIDAY_GACHA,
            Event.CARNIVAL_GACHA,
        ],
    ) -> GachaEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.SEASON_LEAGUE]) -> KingdomsLeagueEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.GLOBAL_EFFECT]) -> GlobalEffectEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.GLOBAL_EFFECT_BUFF]) -> GlobalEffectBuffEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.ALLI_TOURNAMENT]) -> AllianceTournamentEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.GRAND_TOURNAMENT]) -> GrandTournamentEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.LUCKY_WHEEL, Event.SALE_DAYS_LUCKY_WHEEL]) -> LuckyWheelEvent | None: ...
    @overload
    def get_event(
        self,
        event: Literal[Event.ARTIFACT_19, Event.ARTIFACT_23, Event.ARTIFACT_29, Event.ARTIFACT_30, Event.ARTIFACT_67],
    ) -> ArtifactEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.THORNKING, Event.SEAQUEEN, Event.UNDERWORLD]) -> SeasonEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.FAMEBOOSTER]) -> FameBoosterEvent | None: ...
    @overload
    def get_event(
        self, event: Literal[Event.PRIME_ALLI_BONUS, Event.ALLI_PAYMENT_BONUS]
    ) -> AllianceBonusEvent | None: ...
    @overload
    def get_event(
        self, event: Literal[Event.RELIC_ENCHANTER_PRIME_SALE, Event.SEASON_PASS_PRIME_SALE]
    ) -> DiscountSaleEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.SKIP_FOR_FREE]) -> SkipForFreeEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.GGS_GIFT]) -> GiftEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.EVENT_ANNOUNCEMENT]) -> EventAnnouncementEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.FORTUNE_TELLER]) -> FortuneTellerEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.WORLD_CUP]) -> WorldCupEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.TOURNAMENT]) -> TournamentEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.TIME_LIMITED_CAMPAIGN_EVENT]) -> CampaignEvent | None: ...
    @overload
    def get_event(self, event: Literal[Event.TIME_LIMITED_CAMPAIGN_QUEST_EVENT]) -> CampaignQuestEvent | None: ...
    @overload
    def get_event(self, event: Event | int) -> SpecialEvent | None: ...

    def get_event(self, event: Event | int) -> SpecialEvent | None:
        """A running event, or None when it is not running.

        Typed as the model of its type (:data:`~empire_core.events.models.EVENT_CLASSES`) when
        ``event`` names one, so ``get_event(Event.SAMURAI_INVASION)`` is a
        ``SamuraiInvasionEvent | None``; any other event or a bare id is a ``SpecialEvent``.
        """
        with self._lock:
            self._expire_events()
            return self.events.get(int(event))

    def is_event_active(self, event: Event | int) -> bool:
        """Whether an event runs and has not ended.

        Client: ``CastleSpecialEventData.isEventActive`` (bundle line 139892); the client also
        waits for some events' graphics to load, which the library has none of.
        """
        found = self.get_event(event)
        return found is not None and found.is_active(_clock())

    def get_shutting_down_events(self) -> ShuttingDownEvents | None:
        """The events shutting down, from the last ``sde``; None until one arrived."""
        with self._lock:
            return self.shutting_down_events

    def get_events_last_updated(self) -> float | None:
        """When a sei, tei, see, tee or pep was last applied, wall clock; None before any."""
        with self._lock:
            return self._events_updated_at
