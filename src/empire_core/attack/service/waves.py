"""Filling an attack's waves from the inventory."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from empire_core.army.models.units import AttackWave
from empire_core.attack.filling import _pool, _support_tools
from empire_core.attack.targeting import _merged
from empire_core.combat import (
    AttackerFlankEffects,
    Bonus,
    DefenderFlankEffects,
    EffectResolver,
    FillOptions,
    Inventory,
    attack_dialog_bonuses,
    attacker_flank_effects,
    global_unit_attack_bonuses,
    is_npc_player,
    is_npc_pvp_player,
    legend_skill_value,
    minimum_owner_level,
    robber_baron_camp_defense,
    support_tool_waves,
    wave_level,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import ALIEN_INVASION_AREA_TYPES, OTHER_PLAYER_INFO_AREA_TYPES, LegendaryFight
from empire_core.commanders.models.roster import Commander
from empire_core.enums import CombatEffectType, Flank, Kingdom, MapItemType
from empire_core.events.models import GlobalEffectBuffEvent, GlobalEffectEvent, GlobalEffectTimer
from empire_core.gamedata.ids.events import Event
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import GameData, GlobalEffect, Tool


class WavesMixin(ServiceMixin):
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
