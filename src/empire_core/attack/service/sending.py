"""Sending an attack and reading its pre-calculation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from empire_core.army.models.units import AttackWave
from empire_core.attack.models.info import AttackInfoResponse
from empire_core.attack.models.send import (
    CreateAttackRequest,
    CreateAttackResponse,
    DaimyoTauntRequest,
    DaimyoTauntResponse,
    HorizonAttackRequest,
    HorizonAttackResponse,
    OuterRealmsAttackRequest,
    OuterRealmsAttackResponse,
    TreasureHuntAttackRequest,
    TreasureHuntAttackResponse,
)
from empire_core.attack.models.target_info import (
    GetCollectorAttackInfoRequest,
    GetCollectorAttackInfoResponse,
    GetTreasureNodeAttackInfoRequest,
    GetTreasureNodeAttackInfoResponse,
)
from empire_core.attack.targeting import _precalculation
from empire_core.combat import FilledAttack, WaveCapacity, wave_limit_violations
from empire_core.enums import AttackType, GGEError, Kingdom, LootPriority, MapItemType
from empire_core.exceptions import AttackBelowMinimumError, AttackInProgressError, CommandError
from empire_core.gamedata import TreasureMapNodeId, WodAmount, WodAmountMapping
from empire_core.movements.models import NO_HORSE
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.attack.pacing import AttackSendPacer
    from empire_core.gamedata import CurrencyId, Horse, Tool, TreasureMapId


class SendingMixin(ServiceMixin):
    if TYPE_CHECKING:
        pacer: AttackSendPacer

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
        horse_booster_id: Horse | None = None,
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
        collector_attack: bool = False,
        *,
        horizon: bool = False,
        outer_realms: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> CreateAttackResponse:
        """
        Send an attack from a castle to a target position and return the server's reply.

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
            horse_booster_id: The horse for the speed bonus, None for none
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
            collector_attack: A collector event attack (``ICA`` 1), as the client sends one
                after its collector booster dialog
            horizon: Send it as ``abgcam``, as the client does on the Beyond the Horizon
                server while the event scores alliance collector points and the target is a castle or
                capital; the reply is then a ``HorizonAttackResponse``. Such an attack has no auto-skip cooldown
            outer_realms: Send it as ``cam``, as the client does on the Outer Realms while
                its event scores collector points and the target is a castle; the reply is then a
                ``OuterRealmsAttackResponse``. Such an attack has no auto-skip cooldown, and
                ``collector_attack`` is not sent: the client always sends ``ICA`` 0 there
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
            ValueError: Both ``horizon`` and ``outer_realms`` are set, areas of yours sit
                at the source position in several kingdoms and no
                ``kingdom_id`` is given, no wave carries any units, a container is overfull, or the horse or
                slowdown costs rubies and ``spend_rubies`` is False
            CommandError: The server refused the attack, such as with ``MOVEMENT_HAS_NO_UNITS``
                for too few units
            UnknownCastleError: No ``kingdom_id`` given and no area of yours in
                the castle list is at the source position
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures

        Client: ``CastleAttackData.sendAttack`` (bundle line 133901) and
        ``sendAttackPlayerAllianceBattleground`` (bundle line 133895) and ``sendAttackTempServer`` (bundle
        line 133898) send the source area's ``kingdomID`` as ``KID``; ``CastlePostAttackDialog.sendAttack``
        (bundle line 38381) picks between them
        """
        if horizon and outer_realms:
            raise ValueError("an attack is sent on Beyond the Horizon or on the Outer Realms, not both")
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
        response_type = (
            HorizonAttackResponse if horizon else OuterRealmsAttackResponse if outer_realms else CreateAttackResponse
        )
        request = (
            HorizonAttackRequest if horizon else OuterRealmsAttackRequest if outer_realms else CreateAttackRequest
        )(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            waves=filled_waves,
            kingdom_id=kingdom_id,
            commander_id=commander_id,
            attack_type=attack_type,
            wait_time=wait_time,
            horse_booster_id=NO_HORSE if feathers or horse_booster_id is None else horse_booster_id,
            feathers=1 if feathers else 0,
            use_premium_commander=1 if use_premium_commander else 0,
            share_battle_view=1 if share_battle_view else 0,
            loot_priority=loot_priority,
            slowdown=slowdown,
            yard_wave=yard,
            support_tools=tuple(support_tools or ()),
            collector_booster=dict((collector_booster or {}).items()),
            send_anyway=1 if send_anyway else 0,
            collector_attack=1 if collector_attack and not outer_realms else 0,
        )

        def send() -> CreateAttackResponse:
            self.pacer.wait()
            try:
                return self.request(request, response_type, timeout=timeout)
            except CommandError as e:
                if e.error is GGEError.ATTACK_IN_PROGRESS:
                    raise AttackInProgressError(e.command, e.code, e.payload) from e
                raise

        return self.client.commanders.premium_send(commander_id, use_premium_commander, send, spend_rubies=spend_rubies)

    def send_treasure_hunt_attack(
        self,
        map_id: TreasureMapId | int,
        node_id: TreasureMapNodeId,
        waves: list[AttackWave],
        commander_id: int,
        horse_booster_id: Horse | None = None,
        feathers: bool = False,
        use_premium_commander: bool = False,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> TreasureHuntAttackResponse:
        """
        Attack a node of a treasure map and return the server's reply.

        Waves without units are dropped, as the client does. Paced with ``send_attack`` by
        ``config.attack_send_interval``. Led by the premium commander, the
        attack is refused before sending when it may cost rubies, unless ``spend_rubies`` is True;
        see ``client.commanders.premium_send``. So is a horse that costs rubies, unless paid with
        feathers.

        Args:
            map_id: The treasure map
            node_id: The node to attack on that map
            waves: Attack waves, front to back
            commander_id: Commander to lead the attack, a ``Commander.commander_id`` from
                ``client.commanders.get_commanders()``
            horse_booster_id: The horse for the speed bonus, None for none; sent as none with feathers
            feathers: Pay for the horse with feathers
            use_premium_commander: Lead with the premium commander (``commander_id`` -14)
            spend_rubies: Send even when the premium commander or the horse costs rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: No wave carries any units, or the horse costs rubies and ``spend_rubies``
                is False
            PremiumCommanderCostError: The premium commander leads, may cost rubies, and
                ``spend_rubies`` is False
            CommandError: The server refused the attack, ``CANT_START_NEW_ARMIES`` included,
                which the client drops without a message

        Client: ``CastleTreasureMapData.sendTreasureHuntAttack`` (bundle line 140467), from
        ``CastlePostAttackDialog.sendTreasureHuntAttack`` (bundle line 38377); ``THMCommand``
        (bundle line 126135)
        """
        filled_waves = [w for w in waves if w.is_complete()]
        if not filled_waves:
            raise ValueError("Attack has no units in any wave")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, 0))
        request = TreasureHuntAttackRequest(
            commander_id=commander_id,
            horse_booster_id=NO_HORSE if feathers or horse_booster_id is None else horse_booster_id,
            use_premium_commander=1 if use_premium_commander else 0,
            map_id=map_id,
            node_id=node_id,
            feathers=1 if feathers else 0,
            waves=filled_waves,
        )

        def send() -> TreasureHuntAttackResponse:
            self.pacer.wait()
            return self.request(request, TreasureHuntAttackResponse, timeout=timeout)

        return self.client.commanders.premium_send(commander_id, use_premium_commander, send, spend_rubies=spend_rubies)

    def taunt_daimyo(
        self,
        township_x: int,
        township_y: int,
        samurai_medal_boosters: int = 0,
        shogun_point_boosters: int = 0,
        *,
        timeout: float = 5.0,
    ) -> DaimyoTauntResponse:
        """
        Taunt a daimyo into attacking one of your townships and return the attack it started.

        Args:
            township_x: The township's map x
            township_y: The township's map y
            samurai_medal_boosters: Samurai medal boosters to spend on the attack
            shogun_point_boosters: Shogun point boosters to spend on the attack
            timeout: Timeout in seconds

        Raises:
            ValueError: A booster amount is negative
            CommandError: The server refused the taunt

        Client: ``SamuraiDaimyoBoosterSelectDialog.onOkButton`` (bundle line 55929),
        ``LDTCommand`` (bundle line 128324)
        """
        if samurai_medal_boosters < 0 or shogun_point_boosters < 0:
            raise ValueError("booster amounts cannot be negative")
        request = DaimyoTauntRequest(
            township_x=township_x,
            township_y=township_y,
            samurai_medal_boosters=samurai_medal_boosters,
            shogun_point_boosters=shogun_point_boosters,
        )
        return self.request(request, DaimyoTauntResponse, timeout=timeout)

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
        self, map_id: TreasureMapId | int, node_id: TreasureMapNodeId, *, timeout: float = 10.0
    ) -> GetTreasureNodeAttackInfoResponse:
        """
        Get the attack pre-calculation for a node of a treasure map.

        Raises:
            CommandError: The server rejected the request

        Client: ``C2SAttackInfoTreasureDungeonVO`` (bundle line 33261), ``TAICommand`` (bundle line 129012).
        """
        request = GetTreasureNodeAttackInfoRequest(map_id=map_id, node_id=node_id)
        return self.request(request, GetTreasureNodeAttackInfoResponse, timeout=timeout)
