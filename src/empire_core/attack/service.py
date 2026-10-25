"""
Sending attacks, filling their waves the way the game's "Fill waves" button
does, and the saved attack presets.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from empire_core.army.models.units import AttackWave
from empire_core.army.spy_army import SpyArmy
from empire_core.attack.filling import _pool, _support_tools, _target_defense
from empire_core.attack.models.advisor import (
    ActivateAttackAdvisorRequest,
    ActivateAttackAdvisorResponse,
    AttackAdvisorOverviewRequest,
    AttackAdvisorOverviewResponse,
)
from empire_core.attack.models.alien_camps import (
    AlienRerollCountsResponse,
    HiddenAlienCampsResponse,
    RerollAlienCampRequest,
)
from empire_core.attack.models.dungeon_skips import (
    MinuteSkipDungeonRequest,
    MinuteSkipDungeonResponse,
    SkipDungeonCooldownRequest,
    SkipDungeonCooldownResponse,
    _row_coordinates,
    _row_kingdom,
)
from empire_core.attack.models.info import AttackInfoResponse
from empire_core.attack.models.presets import (
    PRESET_NAME_MAX_LENGTH,
    AttackPreset,
    GetPresetsRequest,
    GetPresetsResponse,
    PresetArmy,
    RenamePresetRequest,
    SavePresetRequest,
    UnlockPresetRequest,
)
from empire_core.attack.models.send import CreateAttackRequest
from empire_core.attack.models.target_info import (
    GetCollectorAttackInfoRequest,
    GetCollectorAttackInfoResponse,
    GetTreasureNodeAttackInfoRequest,
    GetTreasureNodeAttackInfoResponse,
)
from empire_core.attack.models.taunts import LaunchTauntAttackRequest, LaunchWolfKingTauntRequest
from empire_core.attack.models.tools import BoughtTools, BuyToolsRequest, BuyToolsResponse
from empire_core.attack.pacing import AttackSendPacer
from empire_core.attack.targeting import _merged, _precalculation, _read_target, _row_item, _Target
from empire_core.combat import (
    AttackerFlankEffects,
    Bonus,
    DefenderFlankEffects,
    EffectResolver,
    FilledAttack,
    FillOptions,
    Inventory,
    TargetRead,
    WaveCapacity,
    attack_dialog_bonuses,
    attacker_flank_effects,
    fill_yard_wave,
    global_unit_attack_bonuses,
    is_npc_player,
    is_npc_pvp_player,
    legend_skill_value,
    min_attack_soldiers,
    minimum_owner_level,
    owner_id_from_row,
    robber_baron_camp_defense,
    robber_baron_camp_level,
    support_tool_waves,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import ALIEN_INVASION_AREA_TYPES, OTHER_PLAYER_INFO_AREA_TYPES, LegendaryFight
from empire_core.commanders.models.roster import Commander
from empire_core.enums import (
    AttackAdvisorType,
    AttackType,
    CollectableKind,
    CombatEffectType,
    Flank,
    GGEError,
    Kingdom,
    LootPriority,
    MapItemType,
)
from empire_core.events.models import AlienInvasionEvent, GlobalEffectBuffEvent, GlobalEffectEvent, GlobalEffectTimer
from empire_core.exceptions import (
    AttackBelowMinimumError,
    AttackInProgressError,
    CommandError,
    PacketError,
)
from empire_core.gamedata import WodAmount, WodAmountMapping
from empire_core.gamedata.ids.events import Event
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseResponse
from empire_core.protocol.text import SMARTFOX_INVALID_CHARS, is_smartfox_valid
from empire_core.services.base import BaseService
from empire_core.utils import callbacks

if TYPE_CHECKING:
    from empire_core.attack.models.counter import AttackCounterResponse
    from empire_core.client.client import EmpireClient
    from empire_core.gamedata import Currency, CurrencyId, GameData, GlobalEffect, Tool

logger = logging.getLogger(__name__)


class AttackService(BaseService):
    """
    Send attacks, fill their waves, and read the attack pre-calculation.

    Reached as client.attack.
    """

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self.pacer = AttackSendPacer(lambda: client.config.attack_send_interval)
        self.on_response("hac", self._handle_hidden_alien_camps)

    @property
    def counter(self) -> AttackCounterResponse | None:
        """Your attack counter, from the last ``gai``; None until one arrived."""
        return self.client.state.get_attack_counter()

    def robber_baron_camp_army(self, item: MapAreaItem) -> SpyArmy | None:
        """
        A robber baron camp's defenders, from the game data rather than a spy report.

        Each flank holds the camp row's units, then its tools. None for any
        other target, and for a robber baron camp the items payload lists no
        row for. A treasure map dungeon is not covered: its victory count is its map
        node's, which no map row carries (``TreasureDungeonMapObjectVO.victoryCount``,
        bundle line 22004); look it up with ``GameData.dungeon_defense``.

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded
        """
        if item.item_type != MapItemType.DUNGEON or item.victory_count is None:
            return None
        row = self._require_game_data().dungeon_defense(item.victory_count, item.kingdom)
        return SpyArmy.from_robber_baron_camp(row) if row is not None else None

    def minute_skip_dungeon(
        self,
        x: int,
        y: int,
        minute_skip: Currency | str,
        kingdom_id: Kingdom = Kingdom.GREEN,
        *,
        map_id: int = -1,
        node_id: int = -1,
        timeout: float = 5.0,
    ) -> MapAreaItem:
        """Use one held minute-skip item and return the updated dungeon.

        Supply both treasure-map ids for a treasure node; omit both for ordinary camps.
        Client: SkippableCooldownMinuteSkipProperties.getMinuteSkipCommand (bundle line 72341),
        C2SMinuteSkipDungeonVO (bundle lines 72354–72357), MSDCommand (bundle lines 125805–125807).
        """
        self._check_dungeon_node(map_id, node_id)
        self._require_minute_skip(minute_skip)
        response = self.request(
            MinuteSkipDungeonRequest(
                x=x, y=y, minute_skip=minute_skip, kingdom_id=kingdom_id, map_id=map_id, node_id=node_id
            ),
            MinuteSkipDungeonResponse,
            timeout=timeout,
        )
        return self._dungeon_skip_result(response, kingdom_id)

    def skip_dungeon_cooldown(
        self,
        x: int,
        y: int,
        kingdom_id: Kingdom = Kingdom.GREEN,
        *,
        map_id: int = -1,
        node_id: int = -1,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> MapAreaItem:
        """Pay to skip the remaining cooldown and return the updated dungeon.

        Requires ruby consent; the price depends on the target and remaining time.
        Supply both treasure-map ids for a treasure node. Replies identify position
        and kingdom, not the treasure node; same-position late replies cannot be distinguished.
        Client: SkippableCooldownDialog.skipWithRubies (bundle lines 28197–28199),
        C2SSkipDungeonCooldownVO (bundle lines 46108–46110), SDCCommand (bundle lines 122356–122360).
        """
        self._check_dungeon_node(map_id, node_id)
        self._require_spend_rubies(spend_rubies, "a full dungeon cooldown skip may cost rubies")
        response = self.request(
            SkipDungeonCooldownRequest(x=x, y=y, kingdom_id=kingdom_id, map_id=map_id, node_id=node_id),
            SkipDungeonCooldownResponse,
            timeout=timeout,
        )
        return self._dungeon_skip_result(response, kingdom_id)

    @staticmethod
    def _check_dungeon_node(map_id: int, node_id: int) -> None:
        if (map_id, node_id) != (-1, -1) and (map_id < 0 or node_id < 0):
            raise ValueError("map_id and node_id must both name a treasure node, or both be -1")

    @staticmethod
    def _dungeon_skip_result(
        response: MinuteSkipDungeonResponse | SkipDungeonCooldownResponse, kingdom: Kingdom
    ) -> MapAreaItem:
        if response.area is None or response.area.attack_cooldown_seconds is None:
            raise PacketError(f"The '{response.command}' reply has no readable dungeon cooldown")
        coordinates = _row_coordinates(response.area)
        if coordinates is None:
            raise PacketError(f"The '{response.command}' dungeon row has no readable coordinates")
        realm = _row_kingdom(response.area, kingdom)
        if realm is None:
            raise PacketError(f"The '{response.command}' dungeon row has no readable kingdom")
        return response.area.model_copy(deep=True, update={"kingdom": Kingdom(realm)})

    def send_attack(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        waves: list[AttackWave] | FilledAttack,
        commander_id: int,
        kingdom_id: Kingdom | None = None,
        attack_type: AttackType = AttackType.ATTACK,
        wait_time: int = 0,
        horse_booster_id: int = -1,
        feathers: bool = False,
        use_premium_commander: bool = False,
        share_battle_view: bool = False,
        loot_priority: LootPriority = LootPriority.NO,
        slowdown: int = 0,
        yard_wave: WodAmountMapping | Sequence[WodAmount] | None = None,
        capacity: WaveCapacity | None = None,
        yard_capacity: int | None = None,
        support_tools: Sequence[Tool | int | None] | None = None,
        collector_booster: Mapping[CurrencyId, int] | Mapping[int, int] | None = None,
        send_anyway: bool = False,
        min_soldiers: int | None = None,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Send an attack from a castle to a target position.

        Waves without units are dropped, matching the game client. Setting
        ``feathers`` forces the horse field to -1, again as the client does.
        Sends from one client are spaced ``config.attack_send_interval`` seconds
        apart (4 by default), since the server refuses an attack that follows the
        previous one sooner; set ``EmpireConfig.attack_send_interval`` to change it.

        ``commander_id`` has no default on purpose. Every id the ``gli`` ``C``
        list reports is a real commander, ``0`` included -- it is the free
        starting one, and a live send with ``LID=0`` comes back with that
        commander under ``AAM.UM.L``. The server validates the id before it
        looks at the army: an id outside the list is ``INVALID_LORD_ID`` (219),
        and a castellan already posted to a castle is ``LORD_IS_USED`` (256).
        ``-14`` is the premium commander (``TravelConst.COMMANDER_PREMIUM``); the
        client sends it with ``BPC`` 1 (``use_premium_commander``), which uses a
        free premium commander or costs rubies, so it is never a default. Led by
        it, the attack is refused before sending when it may cost rubies, unless
        ``spend_rubies`` is True; see ``client.commanders.premium_send``. So is a horse
        that costs rubies, unless paid with feathers, and a slowdown; see "Spending rubies"
        in the guides.

        Known gap: for a conquer attack (``AttackType.CONQUER``, which ``CastleAttackData.sendAttack``,
        bundle line 133852, sends exactly when ``isConquerAttack``, bundle line 30550) the client sends
        ``BPC`` 0 without asking for rubies, whichever commander leads, unless the target is a capital,
        village, kings tower, resource isle, monument or laboratory (``CastlePostAttackDialog.startAttack``,
        bundle line 38360). The target's area type is not known here, so such an attack is checked like
        any other; ``use_premium_commander=False`` with ``spend_rubies=True`` sends what the client sends there.

        Args:
            source_x: Source absolute X coordinate
            source_y: Source absolute Y coordinate
            target_x: Target absolute X coordinate
            target_y: Target absolute Y coordinate
            waves: Attack waves, front to back, or a :meth:`fill_attack` result, which
                also gives ``yard_wave`` and ``min_soldiers`` when those are not passed
            kingdom_id: The source area's kingdom; read from your castle list by
                the source position when not given
            commander_id: Commander to lead the attack, a ``Commander.commander_id`` from
                ``client.commanders.get_commanders()``
            attack_type: See AttackType (default: a normal attack)
            wait_time: Wait time before the troops return
            horse_booster_id: Horse type for the speed bonus (-1 = none)
            feathers: Use feathers for the speed boost
            use_premium_commander: Lead with the premium commander (``commander_id``
                -14). It uses one of your free premium commanders, or costs rubies
                when none is left and no premium account runs
            share_battle_view: Let others watch the battle
            loot_priority: Resource to loot first (``CombatConst.LOOT_PRIO_*``); the
                client offers the choice from player level 20
            slowdown: Seconds the arrival is delayed by; costs rubies
            yard_wave: The courtyard wave, one slot per entry: ``FilledAttack.yard``, or
                ``{Unit.X: 100}``
            capacity: The capacities these waves were sized against. Given one,
                an overfull army, or one below the minimum for its level, is
                refused here rather than by the server
            yard_capacity: The courtyard's capacity, checked the same way
            support_tools: The support tools, one per slot, None (or -1) for an empty one
            collector_booster: Collector event boosters by currency and amount, e.g.
                ``{CurrencyId.SAMURAI_MEDAL_BOOSTER: 5}``
            send_anyway: Send although one of your attacks is already on its way
                there (``FC`` 1), as the client's confirmation dialog does
            min_soldiers: The fewest units the waves must carry together, such
                as ``FilledAttack.min_soldiers`` or
                ``combat.min_attack_soldiers(...)``; taken from ``capacity``
                when not given. Without either nothing is checked
            timeout: Timeout in seconds
            spend_rubies: Send even when the premium commander, the horse or the slowdown costs rubies

        Raises:
            AttackInProgressError: One of your attacks is already on its way
                there; it carries that attack's arrival time and size. Retry
                with ``send_anyway=True`` to send regardless
            AttackBelowMinimumError: The waves carry fewer units than
                ``min_soldiers``, or than the minimum at ``capacity``'s level;
                the client refuses such an attack
            PremiumCommanderCostError: The premium commander leads, may cost rubies,
                and ``spend_rubies`` is False
            GameDataNotLoadedError: The premium commander leads, VIP time runs and
                the game data cannot be loaded; or a horse is picked without feathers
                before it was called
            ValueError: Areas of yours sit at the source position in several kingdoms and no
                ``kingdom_id`` is given, no wave carries any units, a container is overfull, or the horse or
                slowdown costs rubies and ``spend_rubies`` is False
            CommandError: The server refused the attack, such as with ``MOVEMENT_HAS_NO_UNITS``
                for too few units
            UnknownCastleError: No ``kingdom_id`` given and no area of yours in
                the castle list is at the source position
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures

        Client: ``CastleAttackData.sendAttack`` (bundle line 133852) sends the
        source area's ``kingdomID`` as ``KID``
        """
        if isinstance(waves, FilledAttack):
            yard_wave = waves.yard if yard_wave is None else yard_wave
            min_soldiers = waves.min_soldiers if min_soldiers is None else min_soldiers
            waves = waves.waves
        filled_waves = [w for w in waves if w.is_complete()]
        yard = WodAmount.slots(yard_wave or ())
        if not filled_waves:
            raise ValueError("Attack has no units in any wave")

        if capacity is not None:
            # The client refuses to send an overfull army and shows a dialog
            # instead; without this the server rejects it with no explanation.
            problems = wave_limit_violations(filled_waves, capacity, yard=yard, yard_capacity=yard_capacity)
            if problems:
                raise ValueError("Attack exceeds what a wave may carry: " + "; ".join(problems))

        if min_soldiers is None and capacity is not None:
            min_soldiers = capacity.min_soldiers()
        if min_soldiers is not None:
            # Client: AttackDialogStartAttackCheck.onAttack (bundle line 56312)
            soldiers = sum(w.unit_count() for w in filled_waves)
            if soldiers < min_soldiers:
                raise AttackBelowMinimumError(min_soldiers, soldiers)

        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        kingdom_id = self._own_area_kingdom(source_x, source_y, kingdom_id)
        request = CreateAttackRequest(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            waves=filled_waves,
            kingdom_id=kingdom_id,
            commander_id=commander_id,
            attack_type=attack_type,
            wait_time=wait_time,
            horse_booster_id=-1 if feathers else horse_booster_id,
            feathers=1 if feathers else 0,
            use_premium_commander=1 if use_premium_commander else 0,
            share_battle_view=1 if share_battle_view else 0,
            loot_priority=loot_priority,
            slowdown=slowdown,
            yard_wave=yard,
            support_tools=tuple(support_tools or ()),
            collector_booster=dict((collector_booster or {}).items()),
            send_anyway=1 if send_anyway else 0,
        )

        def send() -> None:
            self.pacer.wait()
            try:
                self.execute(request, timeout=timeout)
            except CommandError as e:
                if e.error is GGEError.ATTACK_IN_PROGRESS:
                    raise AttackInProgressError(e.command, e.code, e.payload) from e
                raise

        self.client.commanders.premium_send(commander_id, use_premium_commander, send, spend_rubies=spend_rubies)

    def get_attack_info(
        self,
        target_x: int,
        target_y: int,
        source_x: int,
        source_y: int,
        kingdom_id: Kingdom = Kingdom.GREEN,
        *,
        area_type: MapItemType = MapItemType.CASTLE,
        conquer: bool = False,
        timeout: float = 10.0,
    ) -> AttackInfoResponse:
        """
        Get the attack pre-calculation for a target.

        This is what the game's own attack dialog asks for: the target's map
        row, the attacker's inventory and commanders, and the attacker's
        effects already scoped to this target. Each kind of target answers its
        own command, picked from ``area_type`` as the client does.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            source_x: Attacking castle's X coordinate
            source_y: Attacking castle's Y coordinate
            kingdom_id: Kingdom both sit in
            area_type: The target's area type, the first field of its map row
            conquer: Ask for the conquest pre-calculation instead, for an
                outpost, capital, metropolis or faction camp
            timeout: Timeout in seconds

        Raises:
            ValueError: The client has no pre-calculation this library models
                for that area type
            CommandError: The server rejected the request
        """
        request_type, response_type = _precalculation(area_type, conquer)
        keys = {"KID": kingdom_id, "TX": target_x, "TY": target_y}
        if "source_x" in request_type.model_fields:
            keys.update(SX=source_x, SY=source_y)
        return self.request(request_type(**keys), response_type, timeout=timeout)

    def get_collector_attack_info(
        self,
        target_x: int,
        target_y: int,
        source_x: int,
        source_y: int,
        kingdom_id: Kingdom = Kingdom.GREEN,
        *,
        timeout: float = 10.0,
    ) -> GetCollectorAttackInfoResponse:
        """
        Get the pre-calculation of a collector attack on a castle, with the collector currency it holds.

        Raises:
            CommandError: The server rejected the request

        Client: ``ButtonAttackCollectorComponent.onClick`` (bundle line 109895),
        ``CastleStartAttackDialog.attackCollector`` (bundle line 14836), ``ACCCommand`` (bundle line 122185).
        """
        request = GetCollectorAttackInfoRequest(
            target_x=target_x, target_y=target_y, source_x=source_x, source_y=source_y, kingdom_id=kingdom_id
        )
        return self.request(request, GetCollectorAttackInfoResponse, timeout=timeout)

    def get_treasure_node_attack_info(
        self, map_id: int, node_id: int, *, timeout: float = 10.0
    ) -> GetTreasureNodeAttackInfoResponse:
        """
        Get the attack pre-calculation for a node of a treasure map.

        Raises:
            CommandError: The server rejected the request

        Client: ``C2SAttackInfoTreasureDungeonVO`` (bundle line 33261), ``TAICommand`` (bundle line 129012).
        """
        request = GetTreasureNodeAttackInfoRequest(map_id=map_id, node_id=node_id)
        return self.request(request, GetTreasureNodeAttackInfoResponse, timeout=timeout)

    # =========================================================================
    # Presets
    # =========================================================================

    def get_presets(self, *, timeout: float = 5.0) -> list[AttackPreset]:
        """
        Get your unlocked attack preset slots.

        Example:
            for preset in client.attack.get_presets():
                army = preset.army()
                print(preset.index, preset.name, army.to_wave() if army else None)

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SGetPreDefinedAttackSetupVO`` (bundle line 141803), sent by
        ``FightPresetData.loadDataFromServer`` (bundle line 141779)
        """
        return self.request(GetPresetsRequest(), GetPresetsResponse, timeout=timeout).presets

    def save_preset(self, index: int, army: PresetArmy | AttackWave, *, timeout: float = 5.0) -> None:
        """
        Save an army into an unlocked preset slot.

        A wave is saved as the client saves one: its filled slots, without
        support tools.

        Args:
            index: The preset slot, an ``AttackPreset.index`` from :meth:`get_presets`
            army: The army, a ``PresetArmy`` or a wave
            timeout: Timeout in seconds

        Client: ``C2SUpdatePreDefinedAttackSetupVO`` (bundle line 141820), sent by
        ``FightPresetData.savePresetArmy`` (bundle line 141780) from
        ``AttackDialogPresets.handleSavePresetRequested`` (bundle line 101661), which
        saves only an unlocked slot
        """
        preset = army if isinstance(army, PresetArmy) else PresetArmy.from_wave(army)
        self.execute(SavePresetRequest.create(index, preset), timeout=timeout)

    def rename_preset(self, index: int, name: str, *, timeout: float = 5.0) -> None:
        """
        Rename a preset slot.

        Args:
            index: The preset slot, an ``AttackPreset.index`` from :meth:`get_presets`
            name: The new name, at most 15 characters, none of ``SMARTFOX_INVALID_CHARS``
            timeout: Timeout in seconds

        Raises:
            ValueError: The client's rename dialog would refuse the name

        Client: ``C2SUpdatePresetNameVO`` (bundle line 141794), sent by
        ``RenameFightPresetDialog.sendCommand`` (bundle line 45609) after its
        ``validate`` (bundle line 45606) and its 15-character limit (bundle line 45597)
        """
        if len(name) > PRESET_NAME_MAX_LENGTH or not is_smartfox_valid(name):
            raise ValueError(
                f"Preset names are 1 to {PRESET_NAME_MAX_LENGTH} characters without any of "
                f"{''.join(SMARTFOX_INVALID_CHARS)}, got {name!r}"
            )
        self.execute(RenamePresetRequest(index=index, name=name), timeout=timeout)

    def unlock_preset(self, index: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Unlock an attack preset slot, paying its price from the game data.

        Slots unlock in order: the client marks its first locked slot unlocked whatever ``index`` was.

        Args:
            index: The slot to unlock, the next after the ``AttackPreset.index`` values :meth:`get_presets` returns
            spend_rubies: Allow the rubies the slot costs
            timeout: Timeout in seconds

        Raises:
            ValueError: The slot costs rubies, or is not in the game data, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``FightPresetData.unlockPreset`` (bundle line 141889) after ``CastleConfirmCostsDialog``
        (bundle line 101700) shows the slot's price; ``UASCommand`` (bundle line 122134)
        """
        if not spend_rubies:
            slot = self._require_game_data().attack_slots.get(index)
            if slot is None:
                self._require_spend_rubies(
                    spend_rubies, f"preset slot {index} is not in the game data and may cost rubies"
                )
            elif slot.cost_rubies > 0:
                self._require_spend_rubies(spend_rubies, f"preset slot {index} costs {slot.cost_rubies} rubies")
        self.execute(UnlockPresetRequest(index=index), timeout=timeout)

    # =========================================================================
    # Taunts
    # =========================================================================

    def taunt_nomad_khan(self, *, share_with_alliance: bool = False, timeout: float = 5.0) -> None:
        """
        Taunt the khan of the running alliance nomad invasion into attacking you.

        Args:
            share_with_alliance: Show the attack to your alliance
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleNomadInvasionTauntDialog.tauntKhan`` (bundle line 55677); ``LTACommand`` (bundle line 128204)
        """
        request = LaunchTauntAttackRequest(share_with_alliance=int(share_with_alliance))
        self.execute(request, timeout=timeout)

    def taunt_wolf_king(self, *, timeout: float = 5.0) -> None:
        """
        Taunt the wolf king into attacking you.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``ButtonTauntComponent.onClick`` (bundle line 110098); ``LWTACommand`` (bundle line 124329)
        """
        self.execute(LaunchWolfKingTauntRequest(), timeout=timeout)

    # =========================================================================
    # Attack advisor
    # =========================================================================

    def activate_attack_advisor(
        self, advisor: AttackAdvisorType, *, timeout: float = 5.0
    ) -> ActivateAttackAdvisorResponse:
        """
        Activate an attack advisor, using one of the activation tokens you hold for it.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``AdvisorAttackActivationComponent.onClick`` (bundle line 56251); ``AACommand``
        (bundle line 121193)
        """
        return self.request(
            ActivateAttackAdvisorRequest(advisor=advisor), ActivateAttackAdvisorResponse, timeout=timeout
        )

    def get_attack_advisor_overview(
        self, advisor: AttackAdvisorType, *, timeout: float = 5.0
    ) -> AttackAdvisorOverviewResponse:
        """
        What an attack advisor's attacks won and cost.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SAdvisorAttackOverviewVO`` (bundle line 105059); ``AAOCommand`` (bundle line 121210)
        """
        return self.request(
            AttackAdvisorOverviewRequest(advisor=advisor), AttackAdvisorOverviewResponse, timeout=timeout
        )

    # =========================================================================
    # Tools
    # =========================================================================

    def buy_tools(
        self,
        castle_id: int,
        tool: Tool | int,
        amount: int,
        *,
        map_id: int = -1,
        package_id: int = -1,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> BoughtTools:
        """
        Buy tools into one of your castles for rubies, as the attack and defence screens do.

        Args:
            castle_id: The castle the tools go to
            tool: The tool
            amount: How many
            map_id: The treasure map, when the attack starts from an event camp
            package_id: The event package whose price applies
            spend_rubies: Allow the rubies they cost
            timeout: Timeout in seconds

        Returns:
            The tools bought; the coins and rubies after also reach the state

        Raises:
            ValueError: ``spend_rubies`` is False
            UnknownCastleError: The castle list has no such castle
            PacketError: The reply names no tools bought
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleDefenceBuyUnitsDialog.onClick`` (bundle line 22500), priced with the tool's ``costC2``
        (bundle line 22493); ``IBTCommand`` (bundle line 123574)
        """
        self._require_spend_rubies(spend_rubies, "instantly bought tools cost rubies")
        castle = self._require_own_castle(castle_id)
        request = BuyToolsRequest(
            tool=tool,
            amount=amount,
            x=castle.x,
            y=castle.y,
            map_id=map_id,
            kingdom=castle.kingdom_id,
            package_id=package_id,
        )
        response = self.request(request, BuyToolsResponse, timeout=timeout)
        if response.bought is None:
            raise PacketError("The 'ibt' reply names no tools bought")
        return response.bought

    # =========================================================================
    # Alien camps
    # =========================================================================

    @property
    def alien_reroll_counts(self) -> AlienRerollCountsResponse | None:
        """How often you rerolled alien camps, which sets the next reroll's price; None until the server sent it."""
        return self.client.state.get_alien_reroll_counts()

    def reroll_alien_camp(
        self,
        x: int,
        y: int,
        *,
        currency: Currency | CollectableKind = CollectableKind.RUBIES,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Replace an alien invasion camp on the map with another.

        Args:
            x: Map x of the camp
            y: Map y of the camp
            currency: What pays: ``CollectableKind.RUBIES``, or one of a running alien invasion's
                ``reroll_currency_keys`` (``CollectableKind.COINS`` for ``"C1"``, else the ``Currency``)
            spend_rubies: Allow paying with rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: Rubies pay and ``spend_rubies`` is False, or no running alien invasion
                takes ``currency``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleRerollAlienDialog.onSendReroll`` (bundle line 109749) with ``"C2"`` or one of the
        event's ``rerollCurrencyKeys`` (bundle line 109770); ``RAECommand`` (bundle line 127100)
        """
        key = currency.server_key if isinstance(currency, CollectableKind) else currency.value
        if key == CollectableKind.RUBIES.server_key:
            self._require_spend_rubies(spend_rubies, "an alien camp reroll paid with rubies costs rubies")
        else:
            offered = {
                offered_key
                for event in self.client.state.get_events().values()
                if isinstance(event, AlienInvasionEvent)
                for offered_key in event.reroll_currency_keys
            }
            if key not in offered:
                raise ValueError(f"No running alien invasion rerolls camps for {key!r}")
        self.execute(RerollAlienCampRequest(currency_key=key, x=x, y=y), timeout=timeout)

    on_alien_camps_hidden = callbacks.Event[HiddenAlienCampsResponse]()
    """Call ``callback`` with each ``hac`` push: the alien camps the server took off your map.

    Removing a callback not registered is a no-op.
    """

    def _handle_hidden_alien_camps(self, response: BaseResponse) -> None:
        if isinstance(response, HiddenAlienCampsResponse):
            self._fire(self.on_alien_camps_hidden, response)

    def fill_waves(
        self,
        castle_id: int,
        *,
        level: int | None = None,
        robber_baron_camp_victories: int | None = None,
        robber_baron_camp_kingdom: Kingdom = Kingdom.GREEN,
        space_id: int | None = None,
        area_type: MapItemType | int | None = None,
        landmark_min_level: int = 0,
        area_bonuses: list[Bonus] | None = None,
        inventory: Inventory | None = None,
        player_target: bool | None = None,
        defense: dict[Flank, DefenderFlankEffects] | None = None,
        attacker: AttackerFlankEffects | None = None,
        commander: Commander | None = None,
        conquer: bool = False,
        wave_bonus: int = 0,
        general_skill_ids: Sequence[int] | None = None,
        legend_skill_ids: Sequence[int] | None = None,
        global_effects: Iterable[GlobalEffectTimer] | None = None,
        support_tools: Sequence[Tool | int | None] | None = None,
        target_is_player: bool = False,
        owner_id: int | None = None,
        owner_legend_level: int = 0,
        attacker_legend_level: int | None = None,
        under_conquer_control: bool = False,
        active_raid_boss_id: int | None = None,
        flank_bonus_percent: float = 0.0,
        front_bonus_percent: float = 0.0,
        tool_bonus: float = 0.0,
        options: FillOptions | None = None,
        timeout: float = 5.0,
    ) -> list[AttackWave]:
        """
        Build the waves for an attack from a castle's inventory.

        Sizes itself the way the game's auto-fill does: the number of waves,
        each flank's capacity and its unlocked slots all follow from the
        attacker's level, and each slot takes the stack that best counters
        whichever of the target's defenses is proportionally weaker.

        Only units are placed. The game's button also fills tool slots, which
        needs the tool effect tables resolved, so waves from here carry no
        siege tools yet.

        Client: ``AttackDialogWaveHandler.initWaves`` and ``updateMaxUnitCount``
        (bundle lines 102525-102541), ``CastleAttackArmyVO.init`` (55831) and
        the ``CastleAttackWaveVO`` constructor (99927).

        Args:
            castle_id: Castle whose troops to draw from, one of yours: a ``Castle.id``
                from ``client.state.get_castles()``
            level: The *target owner's* level, which is what sizes a wave
            robber_baron_camp_victories: A robber baron camp's victory count, to derive its defense
                from the game data - see ``MapAreaItem.victory_count``
            robber_baron_camp_kingdom: Kingdom the robber baron camp sits in
            space_id: Kingdom the target sits in, which some tools are limited
                to; the camp's kingdom when not given
            landmark_min_level: A capital's or metropolis's own defense level,
                which the client reads from its landmark at runtime
            area_bonuses: The ``aci`` ``AE`` list, from
                ``get_attack_info(...).attacker_bonuses()``. With entries, it
                replaces the commander's own ``AE`` (see ``commander_bonuses``)
            inventory: Troops to draw from, read from the castle when not given.
                The waves deduct what they take, so a caller filling more than
                one thing from one pool passes the same object each time
            area_type: The target's area type, which scopes the general's
                effects; robber baron camps are area type 2
            player_target: True when attacking a player, False for an NPC.
                Decides which PvP- or PvE-only effects count; when not given it
                follows ``owner_id`` (``getFilterStrategyAttackOrDefence``)
            defense: Explicit per-flank defense, overriding ``robber_baron_camp_victories``
            attacker: Attacker multipliers; built from ``commander``, the
                legend skills and ``support_tools`` when omitted
            commander: The commander leading the attack, whose equipment and
                effects supply the attack multipliers used to score units
            conquer: A conquest attack carries extra waves
            wave_bonus: Extra waves on top of the legend skill, effect type 156
                and the support tools
            support_tools: The support tools the attack will carry, as sent in
                ``AST``: one wod id per slot, -1 for an empty one. They buff
                every flank and can add waves
            general_skill_ids: Unlocked skill ids of the general leading the
                attack, from ``gie``; its unit-limit skills size the wave
            legend_skill_ids: The player's unlocked legend skills, from
                ``skl`` or ``GameData.require().legend_skill(tree, group, level)``.
                Which of them count follows the three rules of
                :class:`~empire_core.combat.capacity.LegendaryFight`
            target_is_player: True when the target belongs to a player
            owner_id: The target owner's player id, see
                :func:`~empire_core.combat.owner_id_from_row`. An alien
                invasion camp's is known from its area type. Without one, no
                legend skill counts
            owner_legend_level: The target owner's legend level, the ``LL`` of
                its owner record in a map scan
            attacker_legend_level: The attacker's legend level; the local
                player's when not given
            under_conquer_control: True when the target is held under conquer
                control; the legend rules then rate its owner by ``level``
                rather than by the area's minimum owner level
            active_raid_boss_id: The boss of the alliance raid-boss event
                running now, None when none is; ``GameData.require().raid_boss(name)``
                finds one by name. Tools tied to other raid bosses are left out
            global_effects: The global effects running, as the timers of
                ``GlobalEffectEvent.effects``; the ``Event.GLOBAL_EFFECT`` event's
                in state when not given. A timer that has ended counts for nothing.
                These are the only thing that buffs a unit's attack value. The
                booster's boost to the ones ``bie`` lists is read from state
            flank_bonus_percent: Extra flank bonus, added to whatever the
                general contributes
            front_bonus_percent: Extra middle bonus, added the same way
            tool_bonus: Extra flank tool capacity
            options: Which flanks to fill and which units to allow
            timeout: Timeout for the inventory request

        Returns:
            One wave per filled wave, ready to pass to :meth:`send_attack`

        Raises:
            GameDataNotLoadedError: the game data cannot be loaded
            ValueError: No level was given and none is known for the player
            UnknownCastleError: No ``inventory`` given and ``castle_id`` is not in your castle list
        """
        game_data = self._require_game_data()

        player = self.client.state.get_local_player()
        attacker_level = player.level
        if attacker_legend_level is None:
            attacker_legend_level = player.legendary_level
        if level is None:
            raise ValueError("A wave is sized by the level of whoever owns the target; pass level=")
        # Client: CastleFightScreenVO.targetOwnerLevel, the owner's own level under
        # conquer control and the area's minimum owner level otherwise
        target_owner_level = (
            level
            if under_conquer_control
            else minimum_owner_level(level, area_type, landmark_min_level=landmark_min_level)
        )
        # Some targets defend at a level of their own: a monument is built for
        # level 70 however low its owner is.
        level = wave_level(level, area_type, landmark_min_level=landmark_min_level)
        if owner_id is None and area_type is not None:
            owner_id = ALIEN_INVASION_AREA_TYPES.get(area_type)

        if defense is None and robber_baron_camp_victories is not None:
            defense = robber_baron_camp_defense(
                robber_baron_camp_victories, robber_baron_camp_kingdom, game_data=game_data
            )

        resolver = EffectResolver(game_data)
        tools = _support_tools(game_data, support_tools)

        # getFilterStrategyAttackOrDefence: an NPC owner filters for PvE
        # effects unless it is an alien invasion or a collector.
        if player_target is None and owner_id is not None:
            player_target = not is_npc_player(owner_id) or is_npc_pvp_player(owner_id)

        legendary = LegendaryFight.evaluate(
            attacker_level=attacker_level,
            attacker_legend_level=attacker_legend_level,
            target_owner_level=target_owner_level,
            wave_level=level,
            owner_id=owner_id,
            owner_legend_level=owner_legend_level,
            area_type=area_type,
            has_other_player_info=area_type in OTHER_PLAYER_INFO_AREA_TYPES,
        )
        merged = attack_dialog_bonuses(
            commander, area_effects=area_bonuses, general_skill_ids=general_skill_ids, game_data=game_data
        )
        if attacker is None:
            attacker = attacker_flank_effects(
                resolver,
                merged,
                area_type=area_type,
                legend_skill_ids=legend_skill_ids or (),
                legendary=legendary.unit_amount,
                support_tools=tools,
            )
        # getUnitsOnTheFlankBonusForAreaType: one int() over the merged list,
        # then the int() of the legend skill on top.
        flank_bonus_percent += int(resolver.flank_unit_bonus(merged, area_type=area_type, player_target=player_target))
        front_bonus_percent += int(resolver.front_unit_bonus(merged, area_type=area_type, player_target=player_target))
        if legend_skill_ids:
            if legendary.unit_amount:
                flank_bonus_percent += int(
                    legend_skill_value(legend_skill_ids, "additionalUnitAmountOnFlank", game_data=game_data)
                )
                front_bonus_percent += int(
                    legend_skill_value(legend_skill_ids, "additionalUnitAmountOnFront", game_data=game_data)
                )
            if legendary.extra_wave:
                wave_bonus += int(legend_skill_value(legend_skill_ids, "additionalWave", game_data=game_data))
            if legendary.flank_tools:
                tool_bonus += legend_skill_value(
                    legend_skill_ids, "additionalAttackToolAmountFlank", game_data=game_data
                )
        # initWaves: int() of effect 156 over the merged list plus the support
        # tools' ADDITIONAL_WAVE. Its add-while-below, then remove-while-above
        # loops settle on the floor of that total.
        extra_waves = int(
            resolver.accumulate(
                merged, CombatEffectType.ADDITIONAL_WAVE, area_type=area_type, player_target=player_target
            )
        ) + support_tool_waves(tools, game_data=game_data)
        wave_bonus += math.floor(extra_waves)

        unit_attack_bonuses = self._unit_attack_bonuses(game_data, self._global_effects(global_effects), attacker_level)

        if inventory is None:
            inventory = self.read_inventory(castle_id, timeout=timeout)

        return solve_waves(
            inventory,
            game_data=game_data,
            level=level,
            attacker_level=attacker_level,
            conquer=conquer,
            wave_bonus=wave_bonus,
            flank_bonus_percent=flank_bonus_percent,
            front_bonus_percent=front_bonus_percent,
            tool_bonus=tool_bonus,
            attacker=attacker,
            defense=defense,
            options=options,
            unit_attack_bonuses=unit_attack_bonuses,
            area_type=area_type,
            space_id=robber_baron_camp_kingdom if space_id is None else space_id,
            target_is_player=target_is_player,
            active_raid_boss_id=active_raid_boss_id,
        )

    def _global_effects(self, global_effects: Iterable[GlobalEffectTimer] | None) -> list[GlobalEffectTimer]:
        """``global_effects``, or the timers of the ``Event.GLOBAL_EFFECT`` event in state when None.

        Client: ``GlobalEffectData.eventVO`` (bundle line 143672), which ``getBonusByEffectType`` reads
        """
        if global_effects is None:
            running = self.client.state.get_event(Event.GLOBAL_EFFECT)
            global_effects = running.effects if isinstance(running, GlobalEffectEvent) else ()
        return list(global_effects)

    def _unit_attack_bonuses(
        self, game_data: GameData, global_effects: list[GlobalEffectTimer], player_level: int
    ) -> dict[int, float] | None:
        """
        The per-unit attack bonuses of the global effects whose timers have not ended, with the booster's boost to
        each one ``bie`` lists; None when no effect buffs a unit.

        An effect whose end has passed counts for nothing, though the event runs on with its last effect. The boost
        is none while the booster event is not running, where the client's ``parse_GIE`` would throw.

        Client: ``GlobalEffectData.getBonusByEffectType`` (bundle lines 143660-143664), ``parse_GIE`` (bundle
        lines 143676-143680)
        """
        now = time.monotonic()
        running = [
            (timer.effect_id, int(timer.end_time - now), timer.strength)
            for timer in global_effects
            if timer.end_time >= now
        ]
        boosted = self.client.state.get_boosted_global_effects()
        booster = self.client.state.get_event(Event.GLOBAL_EFFECT_BUFF)
        boosts: dict[GlobalEffect | int, float] = (
            {effect_id: booster.boost_value(effect_id) for effect_id in boosted.global_effect_ids}
            if boosted is not None and isinstance(booster, GlobalEffectBuffEvent)
            else {}
        )
        return (
            global_unit_attack_bonuses(running, player_level=player_level, boosts=boosts, game_data=game_data) or None
        )

    def read_inventory(self, castle_id: int, *, timeout: float = 5.0) -> Inventory:
        """
        What a castle can send, as a pool the fill methods draw from.

        Tools belong in it as well as units: the flanks place them. Boost items
        are tools by their slot types but no strategy picks them, and the
        soldier pass ignores anything that is not a unit.

        Args:
            castle_id: Castle whose troops to read, one of yours: a ``Castle.id``
                from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Returns:
            An :class:`Inventory` the fill methods deduct from as they place

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded
            UnknownCastleError: ``castle_id`` is not in your castle list
        """
        game_data = self._require_game_data()
        response = self.client.army.get_units_response(castle_id, timeout=timeout)
        return _pool(game_data, _merged(response.units, response.stronghold))

    def fill_attack(
        self,
        castle_id: int,
        *,
        target: MapAreaItem | None = None,
        target_x: int | None = None,
        target_y: int | None = None,
        kingdom_id: Kingdom | None = None,
        source_x: int | None = None,
        source_y: int | None = None,
        target_level: int | None = None,
        target_is_player: bool = False,
        target_owner_id: int | None = None,
        target_owner_legend_level: int | None = None,
        robber_baron_camp_victories: int | None = None,
        robber_baron_camp_kingdom: Kingdom = Kingdom.GREEN,
        target_row: list[Any] | None = None,
        area_type: MapItemType | int | None = None,
        landmark_min_level: int = 0,
        under_conquer_control: bool = False,
        area_bonuses: list[Bonus] | None = None,
        spy_army: SpyArmy | None = None,
        defending_castellan: Commander | None = None,
        defender_legend_skill_ids: Sequence[int] | None = None,
        commander: Commander | None = None,
        general_skill_ids: Sequence[int] | None = None,
        legend_skill_ids: Sequence[int] | None = None,
        global_effects: Iterable[GlobalEffectTimer] | None = None,
        support_tools: Sequence[Tool | int | None] | None = None,
        conquer: bool = False,
        active_raid_boss_id: int | None = None,
        tool_bonus: float = 0.0,
        yard_bonus: float = 0.0,
        yard_boost: float = 0.0,
        options: FillOptions | None = None,
        timeout: float = 5.0,
    ) -> FilledAttack:
        """
        Build a complete attack: every wave, plus the courtyard wave.

        Give it a target and it reads the rest itself.

        With ``target_x``/``target_y`` it asks the server for the attack
        pre-calculation, the command the client uses for the target's area type
        (the conquest one with ``conquer``), and takes what that carries: the
        target's map row and so its structures, the spied defenders per flank, the
        defending castellan, and the area effects that widen the flanks. A
        camp's victory count comes out of the same row, and a player's level
        from the owner records beside it. The general's skills and the player's
        own are read with ``gie`` and ``skl``.

        Every one of those can be passed instead, which skips the request that
        would have found it. Pass no coordinates and nothing is read: then
        ``target_level`` or ``robber_baron_camp_victories`` is required, as before.

        A scan of the target's tile, made when its area type is not known,
        leaves the session on the map, as the client is when it attacks from
        there: the castle is joined again only for the inventory read, and
        only when the pre-calculation did not carry the inventory.

        Each read is best effort against a refusal: the server refuses the
        pre-calculation for a target this player may not hit, and the fill goes
        on with what the other reads found. Each refusal is named in the
        result's ``unread`` with its ``CommandError``, and logged as a warning,
        or at info level for the pre-calculation's ``INVALID_AREA``. A timeout,
        a dropped connection or an unreadable reply raises.

        Args:
            castle_id: Castle whose troops to draw from, one of yours: a ``Castle.id``
                from ``client.state.get_castles()``
            target: The target as a map scan returned it, which gives its position,
                kingdom, map row and area type; pass it or ``target_x``/``target_y``
            target_x: Target's map x, which lets this method read the rest
            target_y: Target's map y
            kingdom_id: Kingdom the target sits in; the source castle's when not
                given
            source_x: Attacking castle's x, needed for the pre-calculation;
                looked up from the castle list when not given
            source_y: Attacking castle's y
            target_level: The target owner's level, which sizes each flank.
                Read from the map when coordinates are given, or derived from
                ``robber_baron_camp_victories`` for a robber baron camp
            target_is_player: True for a player's castle or outpost
            target_owner_id: The target owner's player id, which decides the
                legend skills; taken from ``target_row`` when not given
            target_owner_legend_level: The target owner's legend level. Read
                from the owner records of a one-tile scan when coordinates are
                given, 0 otherwise
            robber_baron_camp_victories: A robber baron camp's victory count
            robber_baron_camp_kingdom: Kingdom the robber baron camp sits in
            target_row: The target's raw map row, for a castle's structures.
                Its first field is the area type, so passing the row is enough
            landmark_min_level: A capital's or metropolis's own defense level
            area_bonuses: Effects on this attack from outside the commander,
                from ``get_attack_info(...).attacker_bonuses()``
            under_conquer_control: True when the target is held under conquer
                control, which sizes the courtyard from the area's own defense
                level rather than its current owner's
            spy_army: A spied castle's defenders per flank, from
                ``get_attack_info(...).spy_army``. Without it a castle target
                is modeled as fortification alone, with no defending army, and
                a robber baron camp as its row in the items payload
                (:meth:`robber_baron_camp_army`)
            defending_castellan: The castellan holding the target, from
                ``get_attack_info(...).defending_castellan()``. Its equipment
                raises the fortification and multiplies the defenders,
                differently per flank
            defender_legend_skill_ids: The defender's legend skills, the
                attack pre-calculation's ``LS`` list. With a spy report they
                raise the defenders and the fortification
            area_type: The target's area type, which scopes effects and decides
                which tools may be carried; taken from ``target_row`` when not
                given
            commander: The commander leading the attack
            general_skill_ids: Its general's unlocked skills. Left out, they
                are read with ``gie`` for the general this commander carries
            legend_skill_ids: The player's legend skills. Left out, they are
                read with ``skl``
            global_effects: The global effects running, as the timers of
                ``GlobalEffectEvent.effects``; the ``Event.GLOBAL_EFFECT`` event's
                in state when not given. The booster's boost to the ones ``bie``
                lists is read from state
            support_tools: The support tools the attack will carry, as sent in
                ``AST``; pass the same list to :meth:`send_attack`
            conquer: A conquest attack carries two extra waves
            active_raid_boss_id: The boss of the alliance raid-boss event
                running now, None when none is; see ``GameData.require().raid_boss(name)``
            tool_bonus: Extra flank tool capacity on top of the legend skill
            yard_bonus: Absolute courtyard capacity bonus, effect type 179
            yard_boost: Courtyard capacity boost, effect type 180
            options: Which flanks to fill and which units to allow
            timeout: Timeout for the inventory request

        Returns:
            The waves and the courtyard wave, ready for :meth:`send_attack`,
            with the minimum the waves had to reach and what could not be read

        Raises:
            AttackBelowMinimumError: The waves could not be filled with the
                fewest units the client lets an attack on this target carry
                (:func:`combat.min_attack_soldiers`); the fill is on the
                error's ``attack``
            UnknownCastleError: ``castle_id`` is not in your castle list and
                its kingdom, position or inventory had to be read from it
            ValueError: ``area_type`` is not an area type, or the target's has no
                pre-calculation modelled; or ``target`` is given with ``target_x``,
                ``target_y`` or ``target_row``
            EmpireTimeoutError / ConnectionClosedError / PacketError: A read of the target failed
        """
        game_data = self._require_game_data()
        options = options or FillOptions()

        if target is not None:
            if target_x is not None or target_y is not None or target_row is not None:
                raise ValueError("Pass target or target_x/target_y/target_row, not both")
            target_x, target_y = target.x, target.y
            target_row = target.raw_data or None
            kingdom_id = target.kingdom if kingdom_id is None else kingdom_id
            area_type = target.item_type if area_type is None else area_type

        read = _Target(
            x=target_x or 0,
            y=target_y or 0,
            kingdom_id=None if kingdom_id is None else Kingdom(kingdom_id),
            source_x=source_x,
            source_y=source_y,
            row=target_row,
            area_type=area_type,
            level=target_level,
            owner_legend_level=target_owner_legend_level,
            is_player=target_is_player,
            robber_baron_camp_victories=robber_baron_camp_victories,
            robber_baron_camp_kingdom=Kingdom(robber_baron_camp_kingdom),
            spy_army=spy_army,
            castellan=defending_castellan,
            defender_legend_skill_ids=defender_legend_skill_ids,
            area_bonuses=area_bonuses,
            conquer=conquer,
        )
        if target_x is not None and target_y is not None:
            _read_target(self, read, castle_id=castle_id, timeout=timeout)

        if read.level is None:
            if read.robber_baron_camp_victories is None:
                if target_x is None or target_y is None:
                    raise ValueError(
                        "Pass target or target_x and target_y to read the target, or target_level, "
                        "or robber_baron_camp_victories to derive the level from"
                    )
                item = _row_item(read.row)
                if item is None:
                    reason = "neither the map nor a pre-calculation has a row for it"
                elif item.is_invasion_camp:
                    camp = item.camp_id if item.camp_id is not None else item.victory_count
                    reason = f"the items payload describes no camp {camp} for area type {int(item.item_type)}"
                else:
                    reason = f"the map row for area type {read.area_type} carries no owner level"
                raise ValueError(
                    f"Nothing at {read.x}:{read.y} says what level to fill for: {reason}. "
                    "Pass target_level to fill it anyway"
                )
            read.level = robber_baron_camp_level(read.robber_baron_camp_victories, read.robber_baron_camp_kingdom)
        if read.area_type is None:
            row_item = _row_item(read.row)
            read.area_type = row_item.item_type if row_item is not None else None

        defense = _target_defense(game_data, read)

        general_id = commander.general_id if commander is not None else None
        if general_skill_ids is None and general_id is not None and general_id >= 0:
            try:
                generals = self.client.commanders.get_generals(timeout=timeout)
                general_skill_ids = next((g.skill_ids for g in generals if g.general_id == general_id), ())
            except CommandError as e:
                logger.warning(f"Could not read the general's skills, sizing without them: {e}")
                read.unread[TargetRead.GENERAL_SKILLS] = e
        if legend_skill_ids is None:
            try:
                legend_skill_ids = self.client.player.get_skills(timeout=timeout).legend_skill_ids
            except CommandError as e:
                logger.warning(f"Could not read the player's skills, sizing without them: {e}")
                read.unread[TargetRead.LEGEND_SKILLS] = e

        owner_id = target_owner_id if target_owner_id is not None else owner_id_from_row(read.row)
        # One inventory read for both passes: the waves deduct what they take,
        # so the courtyard draws from what they left.
        pool = (
            _pool(game_data, read.inventory)
            if read.inventory is not None
            else self.read_inventory(castle_id, timeout=timeout)
        )
        global_effects = self._global_effects(global_effects)
        waves = self.fill_waves(
            castle_id,
            level=read.level,
            landmark_min_level=landmark_min_level,
            robber_baron_camp_kingdom=read.robber_baron_camp_kingdom,
            space_id=read.kingdom_id,
            conquer=conquer,
            tool_bonus=tool_bonus,
            area_bonuses=read.area_bonuses,
            inventory=pool,
            defense=defense,
            commander=commander,
            general_skill_ids=general_skill_ids,
            legend_skill_ids=legend_skill_ids,
            global_effects=global_effects,
            support_tools=support_tools,
            target_is_player=read.is_player,
            owner_id=owner_id,
            owner_legend_level=read.owner_legend_level or 0,
            under_conquer_control=under_conquer_control,
            active_raid_boss_id=active_raid_boss_id,
            area_type=read.area_type,
            player_target=read.is_player if owner_id is None else None,
            options=options,
            timeout=timeout,
        )

        attacker_level = self.client.state.get_local_player().level
        # getMaxUnitsInReinforcementWave reads the area's own defense level when
        # the target is under conquer control, and its owner's otherwise.
        yard_level = (
            minimum_owner_level(read.level, read.area_type, landmark_min_level=landmark_min_level)
            if under_conquer_control
            else read.level
        )
        yard = fill_yard_wave(
            pool,
            yard_capacity(attacker_level, yard_level, bonus=yard_bonus, boost=yard_boost) if options.fill_yard else 0,
            defender=(defense or {}).get(Flank.YARD),
            options=options,
            # The courtyard runs the same pick as a flank, so a buffed unit is
            # worth as much here as it is out front.
            unit_attack_bonuses=self._unit_attack_bonuses(game_data, global_effects, attacker_level),
            game_data=game_data,
        )
        # Client: CastleFightScreenVO.targetOwnerLevel (bundle line 30562)
        owner_level = (
            read.level
            if under_conquer_control
            else minimum_owner_level(read.level, read.area_type, landmark_min_level=landmark_min_level)
        )
        attack = FilledAttack(
            waves=waves,
            yard=yard,
            min_soldiers=min_attack_soldiers(owner_level, read.area_type, landmark_min_level=landmark_min_level),
            unread=read.unread,
        )
        if attack.wave_unit_count() < attack.min_soldiers:
            raise AttackBelowMinimumError(attack.min_soldiers, attack.wave_unit_count(), attack)
        return attack
