"""
Attack service for EmpireCore.

Provides APIs for sending attacks.
"""

from __future__ import annotations

import logging

from empire_core.combat import (
    AttackerFlankEffects,
    Bonus,
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
    sceat_skill_bonuses,
    spied_castle_defence,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import is_legendary_fight
from empire_core.exceptions import EmpireError, GameDataNotLoadedError
from empire_core.protocol.models import (
    AttackType,
    AttackWave,
    Commander,
    CreateAttackRequest,
    GetAttackInfoRequest,
    GetAttackInfoResponse,
)
from empire_core.protocol.models.map import MapAreaItem, MapItemType
from empire_core.services.spy_army import SpyArmy
from empire_core.utils.enums import Kingdom

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
        area_bonuses: list[Bonus] | None = None,
        inventory: Inventory | None = None,
        player_target: bool | None = None,
        defence: dict[Flank, DefenderFlankEffects] | None = None,
        attacker: AttackerFlankEffects | None = None,
        commander: Commander | None = None,
        conquer: bool = False,
        wave_bonus: int = 0,
        general_skill_ids: list[int] | None = None,
        legend_skill_ids: list[int] | None = None,
        sceat_skill_ids: list[int] | None = None,
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
            area_bonuses: Effects that apply to this attack from outside the
                commander, from ``get_attack_info(...).attacker_bonuses()``.
                They carry the flank and front unit-amount bonuses
            inventory: Troops to draw from, read from the castle when not given.
                The waves deduct what they take, so a caller filling more than
                one thing from one pool passes the same object each time
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
        if area_bonuses:
            flank_bonus_percent += int(
                resolver.flank_unit_bonus(area_bonuses, area_type=area_type, player_target=player_target)
            )
            front_bonus_percent += int(
                resolver.front_unit_bonus(area_bonuses, area_type=area_type, player_target=player_target)
            )
        if general_skill_ids:
            general = general_skill_bonuses(game_data, general_skill_ids)
            flank_bonus_percent += int(
                resolver.flank_unit_bonus(general, area_type=area_type, player_target=player_target)
            )
            front_bonus_percent += int(
                resolver.front_unit_bonus(general, area_type=area_type, player_target=player_target)
            )
        if sceat_skill_ids:
            # Hall of Legends skills, which apply whatever the target is.
            sceat = sceat_skill_bonuses(game_data, sceat_skill_ids)
            flank_bonus_percent += int(
                resolver.flank_unit_bonus(sceat, area_type=area_type, player_target=player_target)
            )
            front_bonus_percent += int(
                resolver.front_unit_bonus(sceat, area_type=area_type, player_target=player_target)
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
            defence=defence,
            options=options,
            unit_attack_bonuses=unit_attack_bonuses,
            area_type=area_type,
            space_id=camp_kingdom_id,
            target_is_player=target_is_player,
        )

    def read_inventory(self, castle_id: int, *, timeout: float = 5.0) -> Inventory:
        """
        What a castle can send, as a pool the fill methods draw from.

        Tools belong in it as well as units: the flanks place them. Boost items
        are tools by their slot types but no strategy picks them, and the
        soldier pass ignores anything that is not a unit.

        Args:
            castle_id: Castle whose troops to read
            timeout: Timeout in seconds

        Returns:
            An :class:`Inventory` the fill methods deduct from as they place
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Reading an inventory needs the items payload: call load_game_data() first")
        units = self.client.army.get_units(castle_id=castle_id, timeout=timeout)
        return Inventory(
            {u.unit_id: u.count for u in units if game_data.is_unit(u.unit_id) or game_data.is_tool(u.unit_id)}
        )

    def _read_target(
        self,
        castle_id: int,
        target_x: int,
        target_y: int,
        *,
        kingdom_id: int | None,
        source_x: int | None,
        source_y: int | None,
        target_row: list | None,
        area_type: int | None,
        spy_army: SpyArmy | None,
        defending_castellan: Commander | None,
        area_bonuses: list[Bonus] | None,
        camp_victories: int | None,
        camp_kingdom_id: int,
        target_level: int | None,
        target_is_player: bool,
        timeout: float,
    ) -> tuple[
        list | None,
        int | None,
        SpyArmy | None,
        Commander | None,
        list[Bonus] | None,
        int | None,
        int,
        int | None,
        bool,
    ]:
        """
        Read what the server knows about a target, filling only the gaps.

        Anything the caller passed is kept: each request is made only when
        something it would answer is still missing.
        """
        castles = getattr(self.client.state, "get_castles", list)() or []
        source = next((c for c in castles if getattr(c, "OID", None) == castle_id), None)
        source_kingdom = source.KID if source is not None else 0
        if kingdom_id is None:
            kingdom_id = source_kingdom
        if source_x is None:
            source_x = source.X if source is not None else 0
        if source_y is None:
            source_y = source.Y if source is not None else 0

        wants_precalc = any(value is None for value in (target_row, spy_army, defending_castellan, area_bonuses))
        if wants_precalc:
            try:
                info = self.get_attack_info(
                    target_x=target_x,
                    target_y=target_y,
                    source_x=source_x,
                    source_y=source_y,
                    kingdom_id=kingdom_id,
                    timeout=timeout,
                )
            except EmpireError as e:
                logger.debug(f"Could not read the attack pre-calculation for {target_x}:{target_y}: {e}")
            else:
                target_row = target_row if target_row is not None else info.target_row()
                spy_army = spy_army if spy_army is not None else info.spy_army()
                if defending_castellan is None:
                    defending_castellan = info.defending_castellan()
                if area_bonuses is None:
                    area_bonuses = info.attacker_bonuses()

        item = MapAreaItem.from_list(target_row) if target_row else None
        if item is not None:
            if area_type is None:
                area_type = item.item_type
            if item.item_type == MapItemType.DUNGEON:
                # A camp's level follows from how often it has been beaten, and
                # the row carries the count.
                if camp_victories is None:
                    camp_victories = item.victory_count
                camp_kingdom_id = camp_kingdom_id or (item.camp_kingdom_id or 0)
            elif target_level is None:
                # A player's level is not in the row; it sits in the owner
                # records a scan returns beside it. Scanning moves the client
                # off the attacking castle, so put it back - the inventory read
                # that follows is castle-scoped and fails otherwise.
                target_level = self._owner_level(target_x, target_y, kingdom_id, item.owner_id, timeout)
                target_is_player = target_is_player or target_level is not None
                if target_level is not None:
                    try:
                        self.client.castle.select(castle_id, kingdom_id=source_kingdom, timeout=timeout)
                    except EmpireError as e:
                        logger.debug(f"Could not return to castle {castle_id} after scanning: {e}")

        return (
            target_row,
            area_type,
            spy_army,
            defending_castellan,
            area_bonuses,
            camp_victories,
            camp_kingdom_id,
            target_level,
            target_is_player,
        )

    def _owner_level(self, target_x: int, target_y: int, kingdom_id: int, owner_id: int, timeout: float) -> int | None:
        """The level of whoever owns a tile, from a one-tile scan."""
        try:
            area = self.client.scan_map_area(
                target_x, target_y, target_x, target_y, kingdom=Kingdom(kingdom_id), timeout=timeout
            )
        except (EmpireError, ValueError) as e:
            logger.debug(f"Could not read the owner level at {target_x}:{target_y}: {e}")
            return None
        # A castle row's field 3 is the location id, which is the owner record's
        # object id; the capital-like types put the player id there instead. Try
        # both, then settle for the only record a one-tile scan returned.
        owner = next(
            (o for o in area.objects if owner_id in (o.object_id, o.owner_id) and o.level),
            None,
        )
        if owner is None and len(area.objects) == 1 and area.objects[0].level:
            owner = area.objects[0]
        if owner is None:
            logger.debug(f"No owner level came back for {target_x}:{target_y}")
            return None
        return owner.level

    def fill_attack(
        self,
        castle_id: int,
        *,
        target_x: int | None = None,
        target_y: int | None = None,
        kingdom_id: int | None = None,
        source_x: int | None = None,
        source_y: int | None = None,
        target_level: int | None = None,
        target_is_player: bool = False,
        camp_victories: int | None = None,
        camp_kingdom_id: int = 0,
        target_row: list | None = None,
        area_type: int | None = None,
        landmark_min_level: int = 0,
        under_conquer_control: bool = False,
        area_bonuses: list[Bonus] | None = None,
        spy_army: SpyArmy | None = None,
        defending_castellan: Commander | None = None,
        commander: Commander | None = None,
        general_skill_ids: list[int] | None = None,
        legend_skill_ids: list[int] | None = None,
        sceat_skill_ids: list[int] | None = None,
        global_effect_ids: list[int] | list[list[int]] | None = None,
        yard_bonus: float = 0.0,
        yard_boost: float = 0.0,
        options: FillOptions | None = None,
        timeout: float = 5.0,
    ) -> FilledAttack:
        """
        Build a complete attack: every wave, plus the courtyard wave.

        Give it a target and it reads the rest itself.

        With ``target_x``/``target_y`` it asks the server for the attack
        pre-calculation and takes what that carries: the target's map row and so
        its area type and structures, the spied defenders per flank, the
        defending castellan, and the area effects that widen the flanks. A
        camp's victory count comes out of the same row, and a player's level
        from the owner records beside it. The general's skills and the player's
        own are read with ``gie`` and ``skl``.

        Every one of those can be passed instead, which skips the request that
        would have found it. Pass no coordinates and nothing is read: then
        ``target_level`` or ``camp_victories`` is required, as before.

        Args:
            castle_id: Castle whose troops to draw from
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
            camp_victories: An NPC camp's victory count
            camp_kingdom_id: Kingdom the camp sits in
            target_row: The target's raw map row, for a castle's structures.
                Its first field is the area type, so passing the row is enough
            landmark_min_level: A capital's or metropolis's own defence level
            area_bonuses: Effects on this attack from outside the commander,
                from ``get_attack_info(...).attacker_bonuses()``
            under_conquer_control: True when the target is held under conquer
                control, which sizes the courtyard from the area's own defence
                level rather than its current owner's
            spy_army: A spied castle's defenders per flank, from
                ``get_attack_info(...).spy_army()``. Without it a castle target
                is modelled as fortification alone, with no defending army
            defending_castellan: The castellan holding the target, from
                ``aci``'s ``B`` block. Its equipment raises the fortification
                and multiplies the defenders, differently per flank
            area_type: The target's area type, which scopes effects and decides
                which tools may be carried; taken from ``target_row`` when not
                given
            commander: The commander leading the attack
            general_skill_ids: Its general's unlocked skills. Left out, they
                are read with ``gie`` for the general this commander carries
            legend_skill_ids: The player's legend skills. Left out, they are
                read with ``skl``
            sceat_skill_ids: The player's Hall of Legends skills, read with
                ``skl`` alongside the legend skills when left out
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

        if target_x is not None and target_y is not None:
            (
                target_row,
                area_type,
                spy_army,
                defending_castellan,
                area_bonuses,
                camp_victories,
                camp_kingdom_id,
                target_level,
                target_is_player,
            ) = self._read_target(
                castle_id,
                target_x,
                target_y,
                kingdom_id=kingdom_id,
                source_x=source_x,
                source_y=source_y,
                target_row=target_row,
                area_type=area_type,
                spy_army=spy_army,
                defending_castellan=defending_castellan,
                area_bonuses=area_bonuses,
                camp_victories=camp_victories,
                camp_kingdom_id=camp_kingdom_id,
                target_level=target_level,
                target_is_player=target_is_player,
                timeout=timeout,
            )

        if target_level is None:
            if camp_victories is None:
                raise ValueError(
                    "Pass target_x and target_y to read the target, or target_level, "
                    "or camp_victories to derive the level from"
                )
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

        general_id = commander.general_id if commander is not None else None
        if general_skill_ids is None and general_id is not None and general_id >= 0:
            try:
                general_skill_ids = self.client.skills.get_generals(timeout=timeout).skill_ids(general_id)
            except EmpireError as e:
                logger.debug(f"Could not read the general's skills, sizing without them: {e}")
        if legend_skill_ids is None or sceat_skill_ids is None:
            try:
                own = self.client.skills.get_skills(timeout=timeout)
                if legend_skill_ids is None:
                    legend_skill_ids = own.legend_skill_ids
                if sceat_skill_ids is None:
                    sceat_skill_ids = own.sceat_skill_ids
            except EmpireError as e:
                logger.debug(f"Could not read the player's skills, sizing without them: {e}")

        # One inventory read for both passes: the waves deduct what they take,
        # so the courtyard draws from what they left.
        pool = self.read_inventory(castle_id, timeout=timeout)
        waves = self.fill_waves(
            castle_id,
            level=target_level,
            landmark_min_level=landmark_min_level,
            area_bonuses=area_bonuses,
            inventory=pool,
            defence=defence,
            commander=commander,
            general_skill_ids=general_skill_ids,
            legend_skill_ids=legend_skill_ids,
            sceat_skill_ids=sceat_skill_ids,
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
        yard = fill_yard_wave(
            pool,
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
