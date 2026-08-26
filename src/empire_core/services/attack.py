"""
Attack service for EmpireCore.

Provides APIs for sending attacks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

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
    npc_camp_defense,
    sceat_skill_bonuses,
    spied_castle_defense,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.combat import fill_waves as solve_waves
from empire_core.combat.capacity import is_legendary_fight
from empire_core.exceptions import EmpireError, GameDataNotLoadedError
from empire_core.gamedata import GameData
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


@dataclass
class _Target:
    """
    What an attack needs to know about where it is going.

    Every field is either supplied by the caller or read from the server, and
    :meth:`AttackService._read_target` only ever fills the gaps.
    """

    x: int
    y: int
    kingdom_id: int | None = None
    source_x: int | None = None
    source_y: int | None = None
    row: list | None = None
    area_type: int | None = None
    level: int | None = None
    is_player: bool = False
    camp_victories: int | None = None
    camp_kingdom_id: int = 0
    spy_army: SpyArmy | None = None
    castellan: Commander | None = None
    area_bonuses: list[Bonus] | None = None

    def wants_precalculation(self) -> bool:
        """Whether ``aci`` would answer anything still missing."""
        return any(value is None for value in (self.row, self.spy_army, self.castellan, self.area_bonuses))


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
        space_id: int | None = None,
        area_type: int | None = None,
        landmark_min_level: int = 0,
        area_bonuses: list[Bonus] | None = None,
        inventory: Inventory | None = None,
        player_target: bool | None = None,
        defense: dict[Flank, DefenderFlankEffects] | None = None,
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
        whichever of the target's defenses is proportionally weaker.

        Only units are placed. The game's button also fills tool slots, which
        needs the tool effect tables resolved, so waves from here carry no
        siege tools yet.

        Args:
            castle_id: Castle whose troops to draw from
            level: The *target owner's* level, which is what sizes a wave
            camp_victories: An NPC camp's victory count, to derive its defense
                from the game data - see ``MapAreaItem.victory_count``
            camp_kingdom_id: Kingdom the camp sits in
            space_id: Kingdom the target sits in, which some tools are limited
                to; the camp's kingdom when not given
            landmark_min_level: A capital's or metropolis's own defense level,
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
            defense: Explicit per-flank defense, overriding ``camp_victories``
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

        if defense is None and camp_victories is not None:
            defense = npc_camp_defense(game_data, camp_victories, camp_kingdom_id)

        resolver = EffectResolver(game_data)
        commander_own = commander_bonuses(commander) if commander is not None else []
        # getUnitsOnTheFlankBonusForAreaType accumulates over the commander's
        # own equipment - relics and gems included - its assigned general, and
        # the area effects, then adds the legend skill separately. Each source is
        # truncated on its own, which is why they are not summed first.
        sources = (
            commander_own,
            area_bonuses or [],
            general_skill_bonuses(game_data, general_skill_ids) if general_skill_ids else [],
            # Hall of Legends skills, which apply whatever the target is.
            sceat_skill_bonuses(game_data, sceat_skill_ids) if sceat_skill_ids else [],
        )
        for bonuses in sources:
            if not bonuses:
                continue
            flank_bonus_percent += int(
                resolver.flank_unit_bonus(bonuses, area_type=area_type, player_target=player_target)
            )
            front_bonus_percent += int(
                resolver.front_unit_bonus(bonuses, area_type=area_type, player_target=player_target)
            )

        if attacker is None and commander_own:
            attacker = attacker_flank_effects(resolver, commander_own, area_type=area_type, player_target=player_target)

        legendary = is_legendary_fight(attacker_level, level, target_is_player=target_is_player)
        if legendary and legend_skill_ids:
            flank_bonus_percent += legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFlank")
            front_bonus_percent += legend_skill_value(game_data, legend_skill_ids, "additionalUnitAmountOnFront")
            wave_bonus += int(legend_skill_value(game_data, legend_skill_ids, "additionalWave"))
            tool_bonus += legend_skill_value(game_data, legend_skill_ids, "additionalAttackToolAmountFlank")

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
            defense=defense,
            options=options,
            unit_attack_bonuses=unit_attack_bonuses,
            area_type=area_type,
            space_id=camp_kingdom_id if space_id is None else space_id,
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

    def _read_target(self, target: "_Target", *, castle_id: int, timeout: float) -> None:
        """
        Fill in whatever the caller did not supply about a target.

        Each request is made only when something it would answer is still
        missing, so a fully specified target costs nothing.
        """
        castles = getattr(self.client.state, "get_castles", list)() or []
        source = next((c for c in castles if getattr(c, "OID", None) == castle_id), None)
        home_kingdom = source.KID if source is not None else 0
        if target.kingdom_id is None:
            target.kingdom_id = home_kingdom
        if target.source_x is None:
            target.source_x = source.X if source is not None else 0
        if target.source_y is None:
            target.source_y = source.Y if source is not None else 0

        if target.wants_precalculation():
            self._read_precalculation(target, timeout=timeout)

        item = MapAreaItem.from_list(target.row) if target.row else None
        if item is None:
            return
        if target.area_type is None:
            target.area_type = item.item_type
        if item.item_type == MapItemType.DUNGEON:
            # A camp's level follows from how often it has been beaten, and the
            # row carries the count.
            if target.camp_victories is None:
                target.camp_victories = item.victory_count
            target.camp_kingdom_id = target.camp_kingdom_id or (item.camp_kingdom_id or 0)
        elif target.level is None:
            # A player's level is not in the row; it sits in the owner records a
            # scan returns beside it.
            target.level = self._owner_level(target, item.owner_id, timeout)
            target.is_player = target.is_player or target.level is not None
            if target.level is not None:
                # Scanning moves the client off the attacking castle, and the
                # inventory read that follows is castle-scoped.
                try:
                    self.client.castle.select(castle_id, kingdom_id=home_kingdom, timeout=timeout)
                except EmpireError as e:
                    logger.debug(f"Could not return to castle {castle_id} after scanning: {e}")

    def _target_defense(self, game_data: GameData, target: "_Target") -> dict[Flank, DefenderFlankEffects] | None:
        """
        What defends the target, per flank.

        A camp's defenders and walls come from the items payload. A castle's
        fortification comes from the structure levels in its map row, and its
        defenders from the spy block when one is available - each flank's own
        stacks, so a defending tool raises only the flank it stands on.
        """
        if target.camp_victories is not None:
            return npc_camp_defense(game_data, target.camp_victories, target.camp_kingdom_id)
        if target.row is None:
            return None

        item = MapAreaItem.from_list(target.row)
        wall, gate, moat = fortification_bonuses(
            game_data,
            wall_level=item.wall_level,
            gate_level=item.gate_level,
            moat_level=item.moat_level,
        )
        if target.spy_army is not None:
            return spied_castle_defense(
                game_data,
                target.spy_army,
                wall_bonus=wall,
                gate_bonus=gate,
                moat_bonus=moat,
                castellan=target.castellan,
                area_type=target.area_type,
            )
        # Without a spy report the defending army is unknown, so only the
        # target's fortification is modeled. Only the middle flank meets the
        # gate.
        return {
            flank: DefenderFlankEffects(
                wall_bonus=wall,
                gate_bonus=gate if flank is Flank.MIDDLE else 0.0,
                moat_bonus=moat,
            )
            for flank in Flank
        }

    def _read_precalculation(self, target: "_Target", *, timeout: float) -> None:
        """Take the target's row, defenders, castellan and area effects from ``aci``."""
        try:
            info = self.get_attack_info(
                target_x=target.x,
                target_y=target.y,
                source_x=target.source_x or 0,
                source_y=target.source_y or 0,
                kingdom_id=target.kingdom_id or 0,
                timeout=timeout,
            )
        except EmpireError as e:
            logger.debug(f"Could not read the attack pre-calculation for {target.x}:{target.y}: {e}")
            return
        if target.row is None:
            target.row = info.target_row()
        if target.spy_army is None:
            target.spy_army = info.spy_army()
        if target.castellan is None:
            target.castellan = info.defending_castellan()
        if target.area_bonuses is None:
            target.area_bonuses = info.attacker_bonuses()

    def _owner_level(self, target: "_Target", owner_id: int, timeout: float) -> int | None:
        """The level of whoever owns a tile, from a one-tile scan."""
        try:
            # Not every kingdom id the game uses is in the enum - event
            # kingdoms go well past it - and the request only needs the number.
            area = self.client.scan_map_area(
                target.x,
                target.y,
                target.x,
                target.y,
                kingdom=cast(Kingdom, target.kingdom_id or 0),
                timeout=timeout,
            )
        except (EmpireError, ValueError) as e:
            logger.debug(f"Could not read the owner level at {target.x}:{target.y}: {e}")
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
            logger.debug(f"No owner level came back for {target.x}:{target.y}")
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
        conquer: bool = False,
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
            landmark_min_level: A capital's or metropolis's own defense level
            area_bonuses: Effects on this attack from outside the commander,
                from ``get_attack_info(...).attacker_bonuses()``
            under_conquer_control: True when the target is held under conquer
                control, which sizes the courtyard from the area's own defense
                level rather than its current owner's
            spy_army: A spied castle's defenders per flank, from
                ``get_attack_info(...).spy_army()``. Without it a castle target
                is modeled as fortification alone, with no defending army
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
            conquer: A conquest attack carries two extra waves
            tool_bonus: Extra flank tool capacity on top of the legend skill
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

        target = _Target(
            x=target_x or 0,
            y=target_y or 0,
            kingdom_id=kingdom_id,
            source_x=source_x,
            source_y=source_y,
            row=target_row,
            area_type=area_type,
            level=target_level,
            is_player=target_is_player,
            camp_victories=camp_victories,
            camp_kingdom_id=camp_kingdom_id,
            spy_army=spy_army,
            castellan=defending_castellan,
            area_bonuses=area_bonuses,
        )
        if target_x is not None and target_y is not None:
            self._read_target(target, castle_id=castle_id, timeout=timeout)

        if target.level is None:
            if target.camp_victories is None:
                raise ValueError(
                    "Pass target_x and target_y to read the target, or target_level, "
                    "or camp_victories to derive the level from"
                )
            target.level = camp_level(target.camp_victories, target.camp_kingdom_id)
        if target.row is not None and target.area_type is None:
            target.area_type = MapAreaItem.from_list(target.row).item_type

        defense = self._target_defense(game_data, target)

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
            sceat_skill_ids=sceat_skill_ids,
            global_effect_ids=global_effect_ids,
            target_is_player=target.is_player,
            area_type=target.area_type,
            player_target=target.is_player,
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
            unit_attack_bonuses=(
                global_unit_attack_bonuses(game_data, global_effect_ids, player_level=attacker_level)
                if global_effect_ids
                else None
            ),
        )
        return FilledAttack(waves=waves, yard=yard)
