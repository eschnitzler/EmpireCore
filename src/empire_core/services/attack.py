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
    FillOptions,
    Flank,
    Inventory,
    attacker_flank_effects,
    commander_bonuses,
    general_skill_bonuses,
    legend_skill_value,
    npc_camp_defence,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import is_legendary_fight
from empire_core.exceptions import GameDataNotLoadedError
from empire_core.protocol.models import AttackType, AttackWave, Commander, CreateAttackRequest

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
            support_tools: Support tool WOD IDs
            collector_booster: Collector event booster entries
            timeout: Timeout in seconds

        Returns:
            True when the server accepted the attack, False when it rejected it

        Raises:
            ValueError: No wave carries any units
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures
        """
        filled_waves = [w for w in waves if w.is_complete()]
        if not filled_waves:
            raise ValueError("Attack has no units in any wave")

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

    def fill_waves(
        self,
        castle_id: int,
        *,
        level: int | None = None,
        camp_victories: int | None = None,
        camp_kingdom_id: int = 0,
        area_type: int | None = None,
        player_target: bool | None = None,
        defence: dict[Flank, DefenderFlankEffects] | None = None,
        attacker: AttackerFlankEffects | None = None,
        commander: Commander | None = None,
        conquer: bool = False,
        wave_bonus: int = 0,
        general_skill_ids: list[int] | None = None,
        legend_skill_ids: list[int] | None = None,
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

        if defence is None and camp_victories is not None:
            defence = npc_camp_defence(game_data, camp_victories, camp_kingdom_id)

        if general_skill_ids:
            general = general_skill_bonuses(game_data, general_skill_ids)
            resolver = EffectResolver(game_data)
            flank_bonus_percent += resolver.flank_unit_bonus(general, area_type=area_type, player_target=player_target)
            front_bonus_percent += resolver.front_unit_bonus(general, area_type=area_type, player_target=player_target)

        if attacker is None and commander is not None:
            attacker = attacker_flank_effects(
                EffectResolver(game_data),
                commander_bonuses(commander),
                area_type=area_type,
                player_target=player_target,
            )

        legendary = is_legendary_fight(attacker_level, level, target_is_player=target_is_player)
        if legendary and legend_skill_ids:
            flank_bonus_percent += legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFlank")
            front_bonus_percent += legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFront")
            wave_bonus += int(legend_skill_value(game_data, legend_skill_ids, "additionalWave"))

        units = self.client.army.get_units(castle_id=castle_id, timeout=timeout)
        pool = {u.unit_id: u.count for u in units if game_data.is_unit(u.unit_id)}

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
        )
