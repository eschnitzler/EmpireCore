"""
Attack service for EmpireCore.

Provides APIs for sending attacks.
"""

from __future__ import annotations

import logging

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    EffectResolver,
    FilledAttack,
    FillOptions,
    Flank,
    Inventory,
    WaveCapacity,
    attacker_flank_effects,
    camp_level,
    commander_bonuses,
    fill_yard_wave,
    fortification_bonuses,
    general_skill_bonuses,
    global_unit_attack_bonuses,
    legend_skill_value,
    minimum_owner_level,
    npc_camp_defence,
    spied_castle_defence,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import is_legendary_fight
from empire_core.exceptions import GameDataNotLoadedError
from empire_core.protocol.models import (
    AttackType,
    AttackWave,
    Commander,
    CreateAttackRequest,
    GetAttackInfoRequest,
    GetAttackInfoResponse,
)
from empire_core.protocol.models.map import MapAreaItem
from empire_core.services.spy_army import SpyArmy

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("attack")
class AttackService(BaseService):
    """
    Service for attack operations.

    Accessible via client.attack after auto-registration.
    """

    def send_attack(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        waves: list[AttackWave],
        commander_id: int,
        kingdom_id: int = 0,
        attack_type: int = AttackType.ATTACK,
        wait_time: int = 0,
        horses_type: int = -1,
        feathers: bool = False,
        boost_with_coins: bool = False,
        share_battle_view: bool = False,
        loot_priority: int = 0,
        slowdown: int = 0,
        yard_wave: list[list[int]] | None = None,
        capacity: WaveCapacity | None = None,
        yard_capacity: int | None = None,
        support_tools: list[int] | None = None,
        collector_booster: list | None = None,
        timeout: float = 5.0,
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
        ``-14`` (the no-commander sentinel of ``cds``) also passes validation
        here, but no accepted ``-14`` send has been captured, and players report
        it can cost rubies depending on VIP level, so it is not used as a
        default.

        Args:
            source_x: Source absolute X coordinate
            source_y: Source absolute Y coordinate
            target_x: Target absolute X coordinate
            target_y: Target absolute Y coordinate
            waves: Attack waves, front to back
            kingdom_id: Source kingdom ID (0=Green, 1=Sand, 2=Ice, 3=Fire)
            commander_id: Commander to lead the attack, from client.commanders
            attack_type: See AttackType (default: a normal attack)
            wait_time: Wait time before the troops return
            horses_type: Horse type for the speed bonus (-1 = none)
            feathers: Use feathers for the speed boost
            boost_with_coins: Pay coins to speed up travel
            share_battle_view: Let others watch the battle
            loot_priority: Resource ID to prioritise when looting
            slowdown: Slowdown offset in seconds
            yard_wave: Courtyard wave as [unit_id, count] pairs
            capacity: The capacities these waves were sized against. Given one,
                an overfull army is refused here rather than by the server
            yard_capacity: The courtyard's capacity, checked the same way
            support_tools: Support tool WOD IDs
            collector_booster: Collector event booster entries
            timeout: Timeout in seconds

        Returns:
            True when the server accepted the attack, False when it rejected it

        Raises:
            ValueError: No wave carries any units, or a container is overfull
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures
        """
        filled_waves = [w for w in waves if w.is_complete()]
        if not filled_waves:
            raise ValueError("Attack has no units in any wave")

        if capacity is not None:
            # The client refuses to send an overfull army and shows a dialog
            # instead; without this the server rejects it with no explanation.
            problems = wave_limit_violations(filled_waves, capacity, yard=yard_wave, yard_capacity=yard_capacity)
            if problems:
                raise ValueError("Attack exceeds what a wave may carry: " + "; ".join(problems))

        request = CreateAttackRequest(
            SX=source_x,
            SY=source_y,
            TX=target_x,
            TY=target_y,
            A=filled_waves,
            KID=kingdom_id,
            LID=commander_id,
            ATT=attack_type,
            WT=wait_time,
            HBW=-1 if feathers else horses_type,
            PTT=1 if feathers else 0,
            BPC=1 if boost_with_coins else 0,
            AV=1 if share_battle_view else 0,
            LP=loot_priority,
            SD=slowdown,
            RW=yard_wave or [],
            AST=support_tools or [],
            BKS=collector_booster or [],
        )
        return self.execute(request, timeout=timeout)

    def get_attack_info(
        self,
        target_x: int,
        target_y: int,
        source_x: int,
        source_y: int,
        kingdom_id: int = 0,
        timeout: float = 10.0,
    ) -> GetAttackInfoResponse:
        """
        Get the attack pre-calculation for a castle target.

        This is what the game's own attack dialog asks for: the target's map
        row, the attacker's inventory and commanders, and the attacker's
        effects already scoped to this target.

        A camp answers a different command, ``adi``; see
        ``GetTargetInfoRequest``.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            source_x: Attacking castle's X coordinate
            source_y: Attacking castle's Y coordinate
            kingdom_id: Kingdom both sit in
            timeout: Timeout in seconds

        Raises:
            CommandError: The server rejected the request, e.g. INVALID_AREA
                for a target that is not a castle
        """
        request = GetAttackInfoRequest(TX=target_x, TY=target_y, SX=source_x, SY=source_y, KID=kingdom_id)
        return self.request(request, GetAttackInfoResponse, timeout=timeout)

    def fill_waves(
        self,
        castle_id: int,
        *,
        level: int | None = None,
        camp_victories: int | None = None,
        camp_kingdom_id: int = 0,
        area_type: int | None = None,
        landmark_min_level: int = 0,
        player_target: bool | None = None,
        defence: dict[Flank, DefenderFlankEffects] | None = None,
        attacker: AttackerFlankEffects | None = None,
        commander: Commander | None = None,
        conquer: bool = False,
        wave_bonus: int = 0,
        general_skill_ids: list[int] | None = None,
        legend_skill_ids: list[int] | None = None,
        global_effect_ids: list[int] | list[list[int]] | None = None,
        target_is_player: bool = False,
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
        whichever of the target's defences is proportionally weaker.

        Only units are placed. The game's button also fills tool slots, which
        needs the tool effect tables resolved, so waves from here carry no
        siege tools yet.

        Args:
            castle_id: Castle whose troops to draw from
            level: The *target owner's* level, which is what sizes a wave
            camp_victories: An NPC camp's victory count, to derive its defence
                from the game data - see ``MapAreaItem.victory_count``
            camp_kingdom_id: Kingdom the camp sits in
            landmark_min_level: A capital's or metropolis's own defence level,
                which the client reads from its landmark at runtime
            area_type: The target's area type, which scopes the general's
                effects; NPC camps are area type 2
            player_target: True when attacking a player, False for an NPC
            defence: Explicit per-flank defence, overriding ``camp_victories``
            attacker: Attacker multipliers; built from ``commander`` when
                omitted, and unbuffed if neither is given
            commander: The commander leading the attack, whose equipment and
                effects supply the attack multipliers used to score units
            conquer: A conquest attack carries extra waves
            wave_bonus: Extra waves from the ADDITIONAL_WAVE legend skill
            general_skill_ids: Unlocked skill ids of the general leading the
                attack, from ``gie``; its unit-limit skills size the wave
            legend_skill_ids: The player's unlocked legend skills, from
                ``skl``. They only contribute in a legendary fight - a capped
                attacker against a capped player - which is also where the two
                extra waves come from
            target_is_player: True when the target belongs to a player, which
                a legendary fight requires
            global_effect_ids: Global effects currently running, from ``bie``;
                either ids or the raw ``[id, seconds_left, strength]`` rows,
                which carry the live strength.
                These are the only thing that buffs a unit's attack value
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
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Wave filling needs the items payload: call client.load_game_data() first")

        player = self.client.state.get_local_player()
        attacker_level = player.level if player else 0
        if level is None:
            raise ValueError("A wave is sized by the level of whoever owns the target; pass level=")
        # Some targets defend at a level of their own: a monument is built for
        # level 70 however low its owner is.
        level = wave_level(level, area_type, landmark_min_level=landmark_min_level)

        if defence is None and camp_victories is not None:
            defence = npc_camp_defence(game_data, camp_victories, camp_kingdom_id)

        resolver = EffectResolver(game_data)
        # getUnitsOnTheFlankBonusForAreaType accumulates over the commander's
        # own equipment - relics and gems included - and its assigned general,
        # then adds the legend skill separately. Each part is truncated on its
        # own, which is why they are not summed first.
        if commander is not None:
            own = commander_bonuses(commander)
            flank_bonus_percent += int(resolver.flank_unit_bonus(own, area_type=area_type, player_target=player_target))
            front_bonus_percent += int(resolver.front_unit_bonus(own, area_type=area_type, player_target=player_target))
        if general_skill_ids:
            general = general_skill_bonuses(game_data, general_skill_ids)
            flank_bonus_percent += int(
                resolver.flank_unit_bonus(general, area_type=area_type, player_target=player_target)
            )
            front_bonus_percent += int(
                resolver.front_unit_bonus(general, area_type=area_type, player_target=player_target)
            )

        if attacker is None and commander is not None:
            attacker = attacker_flank_effects(
                resolver,
                commander_bonuses(commander),
                area_type=area_type,
                player_target=player_target,
            )

        legendary = is_legendary_fight(attacker_level, level, target_is_player=target_is_player)
        if legendary and legend_skill_ids:
            flank_bonus_percent += legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFlank")
            front_bonus_percent += legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFront")
            wave_bonus += int(legend_skill_value(game_data, legend_skill_ids, "additionalWave"))

        unit_attack_bonuses = (
            global_unit_attack_bonuses(game_data, global_effect_ids, player_level=attacker_level)
            if global_effect_ids
            else None
        )

        units = self.client.army.get_units(castle_id=castle_id, timeout=timeout)
        # Tools belong in the pool too: the flanks place them. Boost items are
        # tools by their slot types but no strategy picks them, and the soldier
        # pass ignores anything that is not a unit.
        pool = {u.unit_id: u.count for u in units if game_data.is_unit(u.unit_id) or game_data.is_tool(u.unit_id)}

        return solve_waves(
            Inventory(pool),
            game_data,
            level=level,
            attacker_level=attacker_level,
            conquer=conquer,
            wave_bonus=wave_bonus,
            flank_bonus_percent=flank_bonus_percent,
            front_bonus_percent=front_bonus_percent,
            tool_bonus=tool_bonus,
            attacker=attacker,
            defence=defence,
            options=options,
            unit_attack_bonuses=unit_attack_bonuses,
            area_type=area_type,
            space_id=camp_kingdom_id,
            target_is_player=target_is_player,
        )

    def fill_attack(
        self,
        castle_id: int,
        *,
        target_level: int | None = None,
        target_is_player: bool = False,
        camp_victories: int | None = None,
        camp_kingdom_id: int = 0,
        target_row: list | None = None,
        area_type: int | None = None,
        landmark_min_level: int = 0,
        under_conquer_control: bool = False,
        spy_army: SpyArmy | None = None,
        commander: Commander | None = None,
        general_skill_ids: list[int] | None = None,
        legend_skill_ids: list[int] | None = None,
        global_effect_ids: list[int] | list[list[int]] | None = None,
        yard_bonus: float = 0.0,
        yard_boost: float = 0.0,
        options: FillOptions | None = None,
        timeout: float = 5.0,
    ) -> FilledAttack:
        """
        Build a complete attack: every wave, plus the courtyard wave.

        Works out what it can rather than asking for it. A camp's defenders and
        its walls come from its victory count; a castle's fortification comes
        from the structure levels in its map row. The commander supplies the
        attack multipliers and the fortification reductions, its general sizes
        the flanks, and legend skills apply when the fight is legendary.

        Args:
            castle_id: Castle whose troops to draw from
            target_level: The target owner's level, which sizes each flank.
                Derived from ``camp_victories`` when attacking a camp, since a
                camp's level follows from how often it has been beaten
            target_is_player: True for a player's castle or outpost
            camp_victories: An NPC camp's victory count
            camp_kingdom_id: Kingdom the camp sits in
            target_row: The target's raw map row, for a castle's structures.
                Its first field is the area type, so passing the row is enough
            landmark_min_level: A capital's or metropolis's own defence level
            under_conquer_control: True when the target is held under conquer
                control, which sizes the courtyard from the area's own defence
                level rather than its current owner's
            spy_army: A spied castle's defenders per flank, from
                ``get_attack_info(...).spy_army()``. Without it a castle target
                is modelled as fortification alone, with no defending army
            area_type: The target's area type, which scopes effects and decides
                which tools may be carried; taken from ``target_row`` when not
                given
            commander: The commander leading the attack
            general_skill_ids: Its general's unlocked skills
            legend_skill_ids: The player's legend skills
            global_effect_ids: Global effects currently running
            yard_bonus: Absolute courtyard capacity bonus, effect type 179
            yard_boost: Courtyard capacity boost, effect type 180
            options: Which flanks to fill and which units to allow
            timeout: Timeout for the inventory request

        Returns:
            The waves and the courtyard wave, ready for :meth:`send_attack`
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Wave filling needs the items payload: call client.load_game_data() first")

        if target_level is None:
            if camp_victories is None:
                raise ValueError("Pass target_level, or camp_victories to derive it from")
            target_level = camp_level(camp_victories, camp_kingdom_id)

        if target_row is not None and area_type is None:
            area_type = MapAreaItem.from_list(target_row).item_type

        defence: dict[Flank, DefenderFlankEffects] | None = None
        if camp_victories is not None:
            defence = npc_camp_defence(game_data, camp_victories, camp_kingdom_id)
        elif target_row is not None:
            item = MapAreaItem.from_list(target_row)
            wall, gate, moat = fortification_bonuses(
                game_data,
                wall_level=item.wall_level,
                gate_level=item.gate_level,
                moat_level=item.moat_level,
            )
            if spy_army is not None:
                # Each flank's own stacks, so a defending tool raises only the
                # fortification of the flank it stands on.
                defence = spied_castle_defence(game_data, spy_army, wall_bonus=wall, gate_bonus=gate, moat_bonus=moat)
            else:
                # Without a spy report the defending army is unknown, so only
                # the target's fortification is modelled. Only the middle flank
                # meets the gate.
                defence = {
                    flank: DefenderFlankEffects(
                        wall_bonus=wall,
                        gate_bonus=gate if flank is Flank.MIDDLE else 0.0,
                        moat_bonus=moat,
                    )
                    for flank in Flank
                }

        waves = self.fill_waves(
            castle_id,
            level=target_level,
            landmark_min_level=landmark_min_level,
            defence=defence,
            commander=commander,
            general_skill_ids=general_skill_ids,
            legend_skill_ids=legend_skill_ids,
            global_effect_ids=global_effect_ids,
            target_is_player=target_is_player,
            area_type=area_type,
            player_target=target_is_player,
            options=options,
            timeout=timeout,
        )

        player = self.client.state.get_local_player()
        attacker_level = player.level if player else 0
        # getMaxUnitsInReinforcementWave reads the area's own defence level when
        # the target is under conquer control, and its owner's otherwise.
        yard_level = (
            minimum_owner_level(target_level, area_type, landmark_min_level=landmark_min_level)
            if under_conquer_control
            else target_level
        )
        remaining = self.client.army.get_units(castle_id=castle_id, timeout=timeout)
        pool = {u.unit_id: u.count for u in remaining if game_data.is_unit(u.unit_id)}
        for wave in waves:
            payload = wave.model_dump(by_alias=True)
            for flank in ("L", "M", "R"):
                for wod_id, count in payload[flank]["U"]:
                    pool[wod_id] = max(0, pool.get(wod_id, 0) - count)

        yard = fill_yard_wave(
            Inventory(pool),
            game_data,
            yard_capacity(attacker_level, yard_level, bonus=yard_bonus, boost=yard_boost),
            defender=(defence or {}).get(Flank.YARD),
            options=options,
            # The courtyard runs the same pick as a flank, so a buffed unit is
            # worth as much here as it is out front.
            unit_attack_bonuses=(
                global_unit_attack_bonuses(game_data, global_effect_ids, player_level=attacker_level)
                if global_effect_ids
                else None
            ),
        )
        return FilledAttack(waves=waves, yard=yard)
