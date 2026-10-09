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
from empire_core.attack.models.info import AttackInfoResponse
from empire_core.attack.models.presets import (
    PRESET_NAME_MAX_LENGTH,
    AttackPreset,
    GetPresetsRequest,
    GetPresetsResponse,
    PresetArmy,
    RenamePresetRequest,
    SavePresetRequest,
)
from empire_core.attack.models.send import CreateAttackRequest
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
    camp_level,
    fill_yard_wave,
    global_unit_attack_bonuses,
    is_npc_player,
    is_npc_pvp_player,
    legend_skill_value,
    min_attack_soldiers,
    minimum_owner_level,
    npc_camp_defense,
    owner_id_from_row,
    support_tool_waves,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import ALIEN_INVASION_AREA_TYPES, OTHER_PLAYER_INFO_AREA_TYPES, LegendaryFight
from empire_core.commanders.models.roster import Commander
from empire_core.enums import AttackType, CombatEffectType, Flank, GGEError, Kingdom, LootPriority, MapItemType
from empire_core.events.models import GlobalEffectBuffEvent, GlobalEffectEvent, GlobalEffectTimer
from empire_core.exceptions import (
    AttackBelowMinimumError,
    AttackInProgressError,
    CommandError,
    GameDataNotLoadedError,
)
from empire_core.gamedata import WodAmount, WodAmountMapping
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.text import SMARTFOX_INVALID_CHARS, is_smartfox_valid
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.gamedata import CurrencyId, GameData, GlobalEffect, Tool

logger = logging.getLogger(__name__)


class AttackService(BaseService):
    """
    Send attacks, fill their waves, and read the attack pre-calculation.

    Reached as client.attack.
    """

    def send_attack(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        waves: list[AttackWave],
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
        timeout: float = 5.0,
        *,
        spend_rubies: bool = False,
    ) -> bool:
        """
        Send an attack from a castle to a target position.

        Waves without units are dropped, matching the game client. Setting
        ``feathers`` forces the horse field to -1, again as the client does.

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
            waves: Attack waves, front to back
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

        Returns:
            True when the server accepted the attack, False when it rejected it,
            such as with MOVEMENT_HAS_NO_UNITS (100) for too few units

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
                ``client.load_game_data()`` has not been called; or a horse is picked without feathers
                before it was called
            ValueError: No wave carries any units, a container is overfull, or the horse or
                slowdown costs rubies and ``spend_rubies`` is False
            UnknownCastleError: No ``kingdom_id`` given and no area of yours in
                the castle list is at the source position
            AmbiguousCastleError: No ``kingdom_id`` given and areas of yours sit
                at the source position in several kingdoms
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures

        Client: ``CastleAttackData.sendAttack`` (bundle line 133852) sends the
        source area's ``kingdomID`` as ``KID``
        """
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

        def send() -> bool:
            try:
                self.client.send(request, wait=True, timeout=timeout)
            except CommandError as e:
                if e.error is GGEError.ATTACK_IN_PROGRESS:
                    raise AttackInProgressError(e.command, e.code, e.payload) from e
                logger.warning(f"Action '{request.get_command()}' rejected: {e}")
                return False
            return True

        return self.client.commanders.premium_send(commander_id, use_premium_commander, send, spend_rubies=spend_rubies)

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
                outpost, capital or metropolis
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

    # =========================================================================
    # Presets
    # =========================================================================

    def get_presets(self, timeout: float = 5.0) -> list[AttackPreset]:
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

    def save_preset(self, index: int, army: PresetArmy | AttackWave, timeout: float = 5.0) -> bool:
        """
        Save an army into an unlocked preset slot.

        A wave is saved as the client saves one: its filled slots, without
        support tools.

        Args:
            index: The preset slot, an ``AttackPreset.index`` from :meth:`get_presets`
            army: The army, a ``PresetArmy`` or a wave
            timeout: Timeout in seconds

        Returns:
            True when the server accepted it, False when it refused it.

        Client: ``C2SUpdatePreDefinedAttackSetupVO`` (bundle line 141820), sent by
        ``FightPresetData.savePresetArmy`` (bundle line 141780) from
        ``AttackDialogPresets.handleSavePresetRequested`` (bundle line 101661), which
        saves only an unlocked slot
        """
        preset = army if isinstance(army, PresetArmy) else PresetArmy.from_wave(army)
        return self.execute(SavePresetRequest.create(index, preset), timeout=timeout)

    def rename_preset(self, index: int, name: str, timeout: float = 5.0) -> bool:
        """
        Rename a preset slot.

        Args:
            index: The preset slot, an ``AttackPreset.index`` from :meth:`get_presets`
            name: The new name, at most 15 characters, none of ``SMARTFOX_INVALID_CHARS``
            timeout: Timeout in seconds

        Returns:
            True when the server accepted it, False when it refused it.

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
        return self.execute(RenamePresetRequest(index=index, name=name), timeout=timeout)

    def fill_waves(
        self,
        castle_id: int,
        *,
        level: int | None = None,
        camp_victories: int | None = None,
        camp_kingdom_id: Kingdom = Kingdom.GREEN,
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
            camp_victories: An NPC camp's victory count, to derive its defense
                from the game data - see ``MapAreaItem.victory_count``
            camp_kingdom_id: Kingdom the camp sits in
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
                effects; NPC camps are area type 2
            player_target: True when attacking a player, False for an NPC.
                Decides which PvP- or PvE-only effects count; when not given it
                follows ``owner_id`` (``getFilterStrategyAttackOrDefence``)
            defense: Explicit per-flank defense, overriding ``camp_victories``
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
                ``skl`` or ``client.game_data.legend_skill(tree, group, level)``.
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
                running now, None when none is; ``client.game_data.raid_boss(name)``
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
            GameDataNotLoadedError: ``client.load_game_data()`` has not been called
            ValueError: No level was given and none is known for the player
            UnknownCastleError: No ``inventory`` given and ``castle_id`` is not in your castle list
            AmbiguousCastleError: No ``inventory`` given and ``castle_id`` repeats across your kingdoms
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Wave filling needs the items payload: call client.load_game_data() first")

        player = self.client.state.get_local_player()
        attacker_level = player.level if player else 0
        if attacker_legend_level is None:
            attacker_legend_level = player.legendary_level if player else 0
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

        if defense is None and camp_victories is not None:
            defense = npc_camp_defense(game_data, camp_victories, camp_kingdom_id)

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
            game_data, commander, area_effects=area_bonuses, general_skill_ids=general_skill_ids
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
                    legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFlank")
                )
                front_bonus_percent += int(
                    legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFront")
                )
            if legendary.extra_wave:
                wave_bonus += int(legend_skill_value(game_data, legend_skill_ids, "additionalWave"))
            if legendary.flank_tools:
                tool_bonus += legend_skill_value(game_data, legend_skill_ids, "additionalAttackToolAmountFlank")
        # initWaves: int() of effect 156 over the merged list plus the support
        # tools' ADDITIONAL_WAVE. Its add-while-below, then remove-while-above
        # loops settle on the floor of that total.
        extra_waves = int(
            resolver.accumulate(
                merged, CombatEffectType.ADDITIONAL_WAVE, area_type=area_type, player_target=player_target
            )
        ) + support_tool_waves(game_data, tools)
        wave_bonus += math.floor(extra_waves)

        unit_attack_bonuses = self._unit_attack_bonuses(game_data, self._global_effects(global_effects), attacker_level)

        if inventory is None:
            inventory = self.read_inventory(castle_id, timeout=timeout)

        return solve_waves(
            inventory,
            game_data,
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
            space_id=camp_kingdom_id if space_id is None else space_id,
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
        return global_unit_attack_bonuses(game_data, running, player_level=player_level, boosts=boosts) or None

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
            UnknownCastleError: ``castle_id`` is not in your castle list
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Reading an inventory needs the items payload: call load_game_data() first")
        response = self.client.army.get_units_response(castle_id, timeout=timeout)
        return _pool(game_data, _merged(response.units, response.stronghold))

    def fill_attack(
        self,
        castle_id: int,
        *,
        target_x: int | None = None,
        target_y: int | None = None,
        kingdom_id: Kingdom | None = None,
        source_x: int | None = None,
        source_y: int | None = None,
        target_level: int | None = None,
        target_is_player: bool = False,
        target_owner_id: int | None = None,
        target_owner_legend_level: int | None = None,
        camp_victories: int | None = None,
        camp_kingdom_id: Kingdom = Kingdom.GREEN,
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
        ``target_level`` or ``camp_victories`` is required, as before.

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
            target_x: Target's map x, which lets this method read the rest
            target_y: Target's map y
            kingdom_id: Kingdom the target sits in; the source castle's when not
                given
            source_x: Attacking castle's x, needed for the pre-calculation;
                looked up from the castle list when not given
            source_y: Attacking castle's y
            target_level: The target owner's level, which sizes each flank.
                Read from the map when coordinates are given, or derived from
                ``camp_victories`` for a camp
            target_is_player: True for a player's castle or outpost
            target_owner_id: The target owner's player id, which decides the
                legend skills; taken from ``target_row`` when not given
            target_owner_legend_level: The target owner's legend level. Read
                from the owner records of a one-tile scan when coordinates are
                given, 0 otherwise
            camp_victories: An NPC camp's victory count
            camp_kingdom_id: Kingdom the camp sits in
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
                is modeled as fortification alone, with no defending army
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
                running now, None when none is; see ``client.game_data.raid_boss(name)``
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
            AmbiguousCastleError: So, and ``castle_id`` repeats across your kingdoms
            ValueError: ``area_type`` is not an area type, or the target's has no
                pre-calculation modelled
            EmpireTimeoutError / ConnectionClosedError / PacketError: A read of the target failed
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Wave filling needs the items payload: call client.load_game_data() first")

        target = _Target(
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
            camp_victories=camp_victories,
            camp_kingdom_id=Kingdom(camp_kingdom_id),
            spy_army=spy_army,
            castellan=defending_castellan,
            defender_legend_skill_ids=defender_legend_skill_ids,
            area_bonuses=area_bonuses,
            conquer=conquer,
        )
        if target_x is not None and target_y is not None:
            _read_target(self, target, castle_id=castle_id, timeout=timeout)

        if target.level is None:
            if target.camp_victories is None:
                if target_x is None or target_y is None:
                    raise ValueError(
                        "Pass target_x and target_y to read the target, or target_level, "
                        "or camp_victories to derive the level from"
                    )
                item = _row_item(target.row)
                if item is None:
                    reason = "neither the map nor a pre-calculation has a row for it"
                elif item.is_invasion_camp:
                    camp = item.camp_id if item.camp_id is not None else item.victory_count
                    reason = f"the items payload describes no camp {camp} for area type {int(item.item_type)}"
                else:
                    reason = f"the map row for area type {target.area_type} carries no owner level"
                raise ValueError(
                    f"Nothing at {target.x}:{target.y} says what level to fill for: {reason}. "
                    "Pass target_level to fill it anyway"
                )
            target.level = camp_level(target.camp_victories, target.camp_kingdom_id)
        if target.area_type is None:
            row_item = _row_item(target.row)
            target.area_type = row_item.item_type if row_item is not None else None

        defense = _target_defense(game_data, target)

        general_id = commander.general_id if commander is not None else None
        if general_skill_ids is None and general_id is not None and general_id >= 0:
            try:
                general_skill_ids = self.client.skills.get_generals(timeout=timeout).skill_ids(general_id)
            except CommandError as e:
                logger.warning(f"Could not read the general's skills, sizing without them: {e}")
                target.unread[TargetRead.GENERAL_SKILLS] = e
        if legend_skill_ids is None:
            try:
                legend_skill_ids = self.client.skills.get_skills(timeout=timeout).legend_skill_ids
            except CommandError as e:
                logger.warning(f"Could not read the player's skills, sizing without them: {e}")
                target.unread[TargetRead.LEGEND_SKILLS] = e

        owner_id = target_owner_id if target_owner_id is not None else owner_id_from_row(target.row)
        # One inventory read for both passes: the waves deduct what they take,
        # so the courtyard draws from what they left.
        pool = (
            _pool(game_data, target.inventory)
            if target.inventory is not None
            else self.read_inventory(castle_id, timeout=timeout)
        )
        global_effects = self._global_effects(global_effects)
        waves = self.fill_waves(
            castle_id,
            level=target.level,
            landmark_min_level=landmark_min_level,
            camp_kingdom_id=target.camp_kingdom_id,
            space_id=target.kingdom_id,
            conquer=conquer,
            tool_bonus=tool_bonus,
            area_bonuses=target.area_bonuses,
            inventory=pool,
            defense=defense,
            commander=commander,
            general_skill_ids=general_skill_ids,
            legend_skill_ids=legend_skill_ids,
            global_effects=global_effects,
            support_tools=support_tools,
            target_is_player=target.is_player,
            owner_id=owner_id,
            owner_legend_level=target.owner_legend_level or 0,
            under_conquer_control=under_conquer_control,
            active_raid_boss_id=active_raid_boss_id,
            area_type=target.area_type,
            player_target=target.is_player if owner_id is None else None,
            options=options,
            timeout=timeout,
        )

        player = self.client.state.get_local_player()
        attacker_level = player.level if player else 0
        # getMaxUnitsInReinforcementWave reads the area's own defense level when
        # the target is under conquer control, and its owner's otherwise.
        yard_level = (
            minimum_owner_level(target.level, target.area_type, landmark_min_level=landmark_min_level)
            if under_conquer_control
            else target.level
        )
        yard = fill_yard_wave(
            pool,
            game_data,
            yard_capacity(attacker_level, yard_level, bonus=yard_bonus, boost=yard_boost),
            defender=(defense or {}).get(Flank.YARD),
            options=options,
            # The courtyard runs the same pick as a flank, so a buffed unit is
            # worth as much here as it is out front.
            unit_attack_bonuses=self._unit_attack_bonuses(game_data, global_effects, attacker_level),
        )
        # Client: CastleFightScreenVO.targetOwnerLevel (bundle line 30562)
        owner_level = (
            target.level
            if under_conquer_control
            else minimum_owner_level(target.level, target.area_type, landmark_min_level=landmark_min_level)
        )
        attack = FilledAttack(
            waves=waves,
            yard=yard,
            min_soldiers=min_attack_soldiers(owner_level, target.area_type, landmark_min_level=landmark_min_level),
            unread=target.unread,
        )
        if attack.wave_unit_count() < attack.min_soldiers:
            raise AttackBelowMinimumError(attack.min_soldiers, attack.wave_unit_count(), attack)
        return attack
