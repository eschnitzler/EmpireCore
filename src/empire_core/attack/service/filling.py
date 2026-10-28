"""Filling a whole attack."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from empire_core.army.spy_army import SpyArmy
from empire_core.attack.filling import _pool, _target_defense
from empire_core.attack.service.sending import SendingMixin
from empire_core.attack.service.waves import WavesMixin
from empire_core.attack.targeting import _read_target, _row_item, _Target
from empire_core.combat import (
    Bonus,
    FilledAttack,
    FillOptions,
    TargetRead,
    fill_yard_wave,
    min_attack_soldiers,
    minimum_owner_level,
    owner_id_from_row,
    robber_baron_camp_level,
    yard_capacity,
)
from empire_core.commanders.models.roster import Commander
from empire_core.enums import Flank, Kingdom, MapItemType
from empire_core.events.models import GlobalEffectTimer
from empire_core.exceptions import AttackBelowMinimumError, CommandError
from empire_core.gamedata import EnumOrInt
from empire_core.map.models.items import MapAreaItem

if TYPE_CHECKING:
    from empire_core.gamedata import GeneralSkill, LegendSkill, RaidBoss, Tool

logger = logging.getLogger(__name__)


class FillAttackMixin(WavesMixin, SendingMixin):
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
        defender_legend_skill_ids: Sequence[EnumOrInt["LegendSkill"]] | None = None,
        commander: Commander | None = None,
        general_skill_ids: Sequence[EnumOrInt["GeneralSkill"]] | None = None,
        legend_skill_ids: Sequence[EnumOrInt["LegendSkill"]] | None = None,
        global_effects: Iterable[GlobalEffectTimer] | None = None,
        support_tools: Sequence[Tool | int | None] | None = None,
        conquer: bool = False,
        active_raid_boss_id: EnumOrInt["RaidBoss"] | None = None,
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
                    camp = next(
                        (c for c in (item.daimyo_castle_id, item.daimyo_township_id) if c is not None),
                        item.victory_count,
                    )
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
