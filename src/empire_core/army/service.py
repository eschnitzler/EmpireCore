"""
Units, recruitment and the hospital of your castles.

Every command here acts on the castle the session has joined, so each method
joins the castle first (``jca``), as the client is inside a castle before it
shows the recruit or hospital dialog.

Actions raise ``CommandError`` when the server refuses them; a refused join raises before anything is sent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from empire_core.army.models.hospital import (
    CancelHealRequest,
    DismissManyWoundedRequest,
    DismissWoundedRequest,
    HealAllRequest,
    HealUnitsRequest,
    HospitalFlags,
    HospitalFlagsRequest,
    HospitalFlagsResponse,
    SkipHealRequest,
    WoundedUnits,
)
from empire_core.army.models.production import (
    CancelProductionRequest,
    DoubleProductionSlotRequest,
    GetProductionListRequest,
    GetProductionListResponse,
    MoveProductionSlotRequest,
    MoveProductionSlotResponse,
    ProduceUnitsRequest,
    ProductionList,
    SetRecruitmentModeRequest,
    SkipProductionSlotRequest,
    SkipProductionSlotResponse,
)
from empire_core.army.models.recruitment_loop import (
    DuplicateRecruitmentInfoRequest,
    DuplicateRecruitmentInfoResponse,
    DuplicateRecruitmentLoopRequest,
    RecruitmentCopyDestination,
    RecruitmentCopyTarget,
    RecruitmentLoopSlot,
    UpdateRecruitmentLoopRequest,
)
from empire_core.army.models.units import (
    DismissUnitsRequest,
    GetCampUnitCapacityRequest,
    GetCampUnitCapacityResponse,
    GetUnitsRequest,
    GetUnitsResponse,
    StoreSoldiersRequest,
    StoreSoldiersResponse,
    TakeSoldiersRequest,
    TakeSoldiersResponse,
    UnitInventory,
)
from empire_core.castle.models.actions import SelectCastleRequest, SelectCastleResponse
from empire_core.enums import GGEError, Kingdom, ProductionListId, RecruitmentMode, SlotType
from empire_core.exceptions import CommandError, ProductionSlotsNeededError
from empire_core.gamedata import UnitOrTool
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.gamedata import Unit


class ArmyService(BaseService):
    """
    Units, recruitment and the hospital of one of your castles.

    Reached as client.army.

    Each method joins the castle it is given first (``jca``), as the client acts
    on the castle it is in. It joins in that castle's ``Castle.kingdom_id`` from
    ``client.state.get_castles()``, and raises ``UnknownCastleError`` for a castle not listed there.

    Usage:
        client = EmpireClient(...)

        # Get units
        units = client.army.get_units(castle_id=123)

        # Produce 50 of wod id 620 in the soldier list
        client.army.produce_units(123, ProductionListId.SOLDIERS, wod_id=620, amount=50)
    """

    def _join_castle(self, castle_id: int, timeout: float) -> Kingdom:
        """
        Join the castle and return its kingdom id.

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            CommandError: The server refused to join the castle
        """
        kingdom_id = self._require_own_castle(castle_id).kingdom_id
        self.request(
            SelectCastleRequest(castle_id=castle_id, kingdom_id=kingdom_id), SelectCastleResponse, timeout=timeout
        )
        return kingdom_id

    # =========================================================================
    # Unit Inventory
    # =========================================================================

    def get_units(self, castle_id: int, *, timeout: float = 5.0) -> dict[UnitOrTool, int]:
        """
        Get the available unit inventory for a castle.

        Covers soldiers and tools. Units in production, in the stronghold or in
        the hospital are reported separately - use get_units_response() for
        those.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Returns:
            The castle's units and tools, ``{Unit or Tool: amount}``
        """
        return self.get_units_response(castle_id, timeout=timeout).units

    def get_units_response(self, castle_id: int, *, timeout: float = 5.0) -> GetUnitsResponse:
        """
        Get every unit inventory a castle reports.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Returns:
            The full gui response: available, in production, stronghold, hospital

        Raises:
            CommandError: The server refused to join the castle, so ``gui`` would
                have answered for another one
        """
        self._join_castle(castle_id, timeout)
        return self.request(GetUnitsRequest(), GetUnitsResponse, timeout=timeout)

    def dismiss_units(
        self, castle_id: int, wod_id: int, amount: int, from_stronghold: bool = False, *, timeout: float = 5.0
    ) -> None:
        """
        Dismiss units of the castle, or of its stronghold.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDismissUnitsDialog.dismissUnits`` (bundle line 84330)
        """
        self._join_castle(castle_id, timeout)
        request = DismissUnitsRequest(wod_id=wod_id, amount=amount, from_stronghold=1 if from_stronghold else 0)
        self.execute(request, timeout=timeout)

    def get_camp_unit_capacity(self, camp_id: int, *, timeout: float = 5.0) -> int:
        """
        How many more soldiers a camp of the faction kingdom takes.

        Your own main faction camp or a camp you send support to; no castle is joined first.

        Args:
            camp_id: The camp's area id
            timeout: Timeout in seconds

        Returns:
            The soldiers the camp still takes, never below 0

        Client: ``CastleTransferTroopsToKingdomProperties.additionalDataUpdateCommands`` (bundle line
        37467) and ``CastleTroopSupportDialog.onSupportDefenceInfos`` (bundle line 129177) ask only for
        faction kingdom camps; the reply goes through ``FUCCommand`` (bundle line 127902)
        """
        request = GetCampUnitCapacityRequest(camp_id=camp_id)
        return self.request(request, GetCampUnitCapacityResponse, timeout=timeout).capacity

    # =========================================================================
    # Stronghold
    # =========================================================================

    def store_in_stronghold(self, castle_id: int, unit: Unit, amount: int, *, timeout: float = 5.0) -> UnitInventory:
        """
        Store soldiers of the castle in its stronghold, where they are hidden from attacks.

        The client offers at most the stronghold's free space or the soldiers at home, whichever is
        less, and nothing once the stronghold is full; the server refuses more.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            unit: The soldier to store
            amount: How many to store
            timeout: Timeout in seconds

        Returns:
            The castle's unit inventories after the move

        Client: ``CastleInventoryStrongholdListItemComponent.onClickUnit`` (bundle line 84422), capped
        by ``CastleMilitaryData.currentHiddenSoldierSpace`` and ``isStrongholdFull`` (bundle lines
        138864-138866); the reply goes to ``parse_GUI`` (``STSCommand``, bundle line 125692)
        """
        self._join_castle(castle_id, timeout)
        request = StoreSoldiersRequest(wod_id=unit, amount=amount)
        return self.request(request, StoreSoldiersResponse, timeout=timeout)

    def take_from_stronghold(self, castle_id: int, unit: Unit, amount: int, *, timeout: float = 5.0) -> UnitInventory:
        """
        Take soldiers of the castle out of its stronghold.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            unit: The soldier to take out
            amount: How many to take out
            timeout: Timeout in seconds

        Returns:
            The castle's unit inventories after the move

        Client: ``StrongholdInventoryListItemComponent.takeSoldiers`` (bundle line 84462); the reply
        goes to ``parse_GUI`` (``TASCommand``, bundle line 125707)
        """
        self._join_castle(castle_id, timeout)
        request = TakeSoldiersRequest(wod_id=unit, amount=amount)
        return self.request(request, TakeSoldiersResponse, timeout=timeout)

    # =========================================================================
    # Production
    # =========================================================================

    def produce_units(
        self,
        castle_id: int,
        list_id: ProductionListId,
        wod_id: int,
        amount: int,
        *,
        spend_rubies: bool = False,
        private_offer_id: int = -1,
        timeout: float = 5.0,
    ) -> None:
        """
        Produce units or tools.

        Spends rubies when the unit or tool has a ruby price (``cost_rubies`` or, on a temporary
        server, ``outer_realms_cost_rubies`` in the game data, refused on either kind of server), and
        with ``spend_rubies`` on missing resources; see "Spending rubies" in the guides.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: SOLDIERS, TOOLS or AUXILIARIES
            wod_id: Unit or tool wod id
            amount: How many to produce
            spend_rubies: Allow a ruby price, and pay rubies for missing resources as the
                client's resource wait dialog does
            private_offer_id: With ``spend_rubies``, the id of the active
                resource merchant private offer; -1 when there is none
            timeout: Timeout in seconds

        Raises:
            ValueError: The list is the hospital, or the unit has a ruby price or is not in the
                game data, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded

        Client: ``C2SBuyUnitPackageVO`` (bundle line 35277); ``BasicUnitVO.basicCostC2`` (bundle line
        19248); the ruby path is ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35218)
        """
        if list_id == ProductionListId.HOSPITAL:
            raise ValueError("bup produces soldiers, tools or auxiliaries; the hospital list is healed with heal_units")
        if not spend_rubies:
            game_data = self._require_game_data()
            row = game_data.get_unit(wod_id) or game_data.get_tool(wod_id)
            if row is None:
                self._require_spend_rubies(spend_rubies, f"wod id {wod_id} is not in the game data and may cost rubies")
            elif max(row.cost_rubies, row.outer_realms_cost_rubies) > 0:
                self._require_spend_rubies(spend_rubies, f"wod id {wod_id} costs rubies")
        kingdom_id = self._join_castle(castle_id, timeout)
        request = ProduceUnitsRequest(
            list_id=list_id,
            wod_id=wod_id,
            amount=amount,
            private_offer_id=private_offer_id if spend_rubies else -1,
            pay_with_rubies=1 if spend_rubies else 0,
            kingdom_id=kingdom_id,
            castle_id=castle_id,
        )
        self.execute(request, timeout=timeout)

    def get_production_list(self, castle_id: int, list_id: ProductionListId, *, timeout: float = 5.0) -> ProductionList:
        """
        Get one production list of a castle: the slot producing now and the queue,
        or the hospital slots for ``ProductionListId.HOSPITAL``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``C2SShowPackageListVO`` (bundle line 22860)
        """
        self._join_castle(castle_id, timeout)
        return self.request(GetProductionListRequest(list_id=list_id), GetProductionListResponse, timeout=timeout)

    def cancel_production(
        self, castle_id: int, list_id: ProductionListId, slot_type: SlotType, position: int, *, timeout: float = 5.0
    ) -> None:
        """
        Cancel a production slot.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            slot_type: PRODUCTION for the slot producing now, QUEUE for a queued one
            position: 0 for the slot producing now, else the slot's
                ``ProductionSlot.position``

        Client: ``CastleRecruitDialogUnits.onCancelCurrentSlotConfirmed`` (bundle line 23655)
        """
        self._join_castle(castle_id, timeout)
        request = CancelProductionRequest(list_id=list_id, position=position, slot_type=slot_type)
        self.execute(request, timeout=timeout)

    def double_production_slot(
        self,
        castle_id: int,
        list_id: ProductionListId,
        slot_type: SlotType,
        position: int,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Double the units of a production slot, for rubies; see "Spending rubies" in the guides.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            slot_type: PRODUCTION for the slot producing now, QUEUE for a queued one
            position: 0 for the slot producing now, else the slot's
                ``ProductionSlot.position``
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``RecruitmentHelper.boostCurrentSlot`` (bundle line 23165), after
        ``CastleRecruitDialogUnits.handleBoostSlot`` (bundle line 23692) prices it with
        ``getUnitDoublingCosts`` (bundle line 23546), always in rubies
        """
        self._require_spend_rubies(spend_rubies, "doubling a production slot costs rubies")
        kingdom_id = self._join_castle(castle_id, timeout)
        request = DoubleProductionSlotRequest(
            list_id=list_id, position=position, castle_id=castle_id, kingdom_id=kingdom_id, slot_type=slot_type
        )
        self.execute(request, timeout=timeout)

    def skip_production_slot(
        self,
        castle_id: int,
        list_id: ProductionListId,
        position: int,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> ProductionList | None:
        """
        Finish a production slot now, for rubies; see "Spending rubies" in the guides.

        The live client never sends this: its skip button is for an A/B test group it reports no
        account in, so the server may refuse it.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: SOLDIERS, TOOLS or AUXILIARIES
            position: 0 for the slot producing now, else the slot's ``ProductionSlot.position``
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Returns:
            The list after the skip, or None when the reply carries none

        Raises:
            ValueError: ``spend_rubies`` is False, or the list is the hospital (see ``skip_heal``)

        Client: ``RecruitmentHelper.skipSlot`` (bundle line 23176) from
        ``CastleRecruitDialogUnits.boostCurrentSlot`` (bundle line 23661) when ``_useSkipButton``,
        priced in rubies by ``updateSkipTooltip`` (bundle line 23557); ``_useSkipButton`` needs
        ``ClientConstABTests.takesPartInSkipRecruitingTest`` (bundle line 18700)
        """
        if list_id == ProductionListId.HOSPITAL:
            raise ValueError("hospital slots are finished with skip_heal")
        self._require_spend_rubies(spend_rubies, "finishing a production slot costs rubies")
        self._join_castle(castle_id, timeout)
        request = SkipProductionSlotRequest(list_id=list_id, position=position)
        return self.request(request, SkipProductionSlotResponse, timeout=timeout).production_list

    def move_production_slot(
        self,
        castle_id: int,
        list_id: ProductionListId,
        old_position: int,
        new_position: int,
        *,
        timeout: float = 5.0,
    ) -> ProductionList:
        """
        Move a queued slot to another position of its list.

        Positions are the queue's: a ``ProductionSlot.position``, or a ``HospitalSlot.position`` for
        ``ProductionListId.HOSPITAL``, whose slots the client lets you drag too. The slot producing
        now (``ProductionList.current``) is not in the queue and does not move. The client drags
        only a slot that is neither free nor locked, and never onto a locked one.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: The list the slot is in
            old_position: The slot's position now
            new_position: The position it moves to
            timeout: Timeout in seconds

        Returns:
            The list after the move

        Client: ``UnitBuildListComponent.requestMoveFromServer`` (bundle line 50938) sends the dragged
        slot's position before and after the drop, both indexes into ``QS`` (``parseMilitaryList``) or
        ``PIDL`` (``parseList``, bundle lines 138899, 138907); ``initBuildListItem`` and
        ``switchItemPos`` (bundle lines 16876, 16923) decide what drags; the reply goes to ``parse_SPL``
        (``MUPCommand``, bundle line 125631)
        """
        self._join_castle(castle_id, timeout)
        request = MoveProductionSlotRequest(list_id=list_id, old_position=old_position, new_position=new_position)
        return self.request(request, MoveProductionSlotResponse, timeout=timeout).production_list

    def set_recruitment_mode(
        self, castle_id: int, list_id: ProductionListId, mode: RecruitmentMode, *, timeout: float = 5.0
    ) -> None:
        """
        Set the order a list works through its queue, ``ProductionList.recruitment_mode``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: SOLDIERS, TOOLS or AUXILIARIES
            mode: The mode to set
            timeout: Timeout in seconds

        Raises:
            ValueError: The list is the hospital, which has no recruitment mode

        Client: ``CastleRecruitDialogUnits.onClick`` (bundle line 23686) switches the mode and sends
        ``C2SSetRecruitmentModeVO``; the server answers ``srm`` (``SRMCommand``, registered at bundle line
        120368), which the client does not read (bundle line 126787). ``parse_SPL`` reads ``RM`` only
        for the soldier, tool and auxiliary lists (bundle line 138830)
        """
        if list_id == ProductionListId.HOSPITAL:
            raise ValueError("the hospital list has no recruitment mode")
        kingdom_id = self._join_castle(castle_id, timeout)
        request = SetRecruitmentModeRequest(list_id=list_id, kingdom_id=kingdom_id, castle_id=castle_id, mode=mode)
        self.execute(request, timeout=timeout)

    # =========================================================================
    # Recruitment loops
    # =========================================================================

    def start_recruitment_loop(
        self,
        castle_id: int,
        list_id: ProductionListId,
        loops: int,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Repeat a list's queue ``loops`` times, for rubies; see "Spending rubies" in the guides.

        Reads the list first (``spl``) and sends its queued slots, as the client sends the queue it
        shows. The client opens this only from an ``lri`` it never asks for, so the server may refuse it.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: SOLDIERS, TOOLS or AUXILIARIES
            loops: How many times to repeat the queue, at least 1
            spend_rubies: Allow the loop fee, which is always in rubies; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False, the list is the hospital, or ``loops`` is below 1
            ProductionSlotsNeededError: The list needs more unlocked slots first

        Client: ``AAutoRecruitmentPurchaseDialog.sendConfirmToServer`` (bundle line 60527) with the
        loops picked from 1 up (``updateLoopSelector``) and the queue from
        ``AutoRecruitmentHelper.createAutoRecruitSnapshot`` (bundle line 36599); the fee is
        ``AutoRecruitmentPriceData.getCosts``, in rubies (bundle line 142396)
        """
        if list_id == ProductionListId.HOSPITAL:
            raise ValueError("the hospital list has no recruitment loop")
        if loops < 1:
            raise ValueError("a recruitment loop repeats the queue at least once")
        self._require_spend_rubies(spend_rubies, "a recruitment loop costs rubies")
        self._join_castle(castle_id, timeout)
        production = self.request(GetProductionListRequest(list_id=list_id), GetProductionListResponse, timeout=timeout)
        slots = [RecruitmentLoopSlot.from_slot(slot) for slot in production.queue if slot.wod_id >= 0]
        request = UpdateRecruitmentLoopRequest(list_id=list_id, loops=loops, slots=slots)
        self._execute_needing_slots(request, timeout)

    def get_recruitment_copy_targets(
        self, castle_id: int, list_id: ProductionListId, *, timeout: float = 5.0
    ) -> list[RecruitmentCopyTarget]:
        """
        Your castles a list's queue can be copied to, with what each copy costs.

        Args:
            castle_id: The castle whose queue would be copied, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: SOLDIERS, TOOLS or AUXILIARIES
            timeout: Timeout in seconds

        Returns:
            One entry per castle; ``RecruitmentCopyTarget.can_copy`` is False where the copy is refused

        Client: ``AAutoRecruitmentCopyDialog.requestDRI`` (bundle line 51219), opened from the recruit
        dialog's copy button (``CastleRecruitDialogUnits.onCopyProduction``, bundle line 23709)
        """
        kingdom = self._join_castle(castle_id, timeout)
        request = DuplicateRecruitmentInfoRequest(list_id=list_id, castle_id=castle_id, kingdom=kingdom)
        return self.request(request, DuplicateRecruitmentInfoResponse, timeout=timeout).targets

    def copy_recruitment(
        self,
        castle_id: int,
        list_id: ProductionListId,
        targets: Sequence[RecruitmentCopyTarget],
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Copy a list's queue to other castles, for their ``RecruitmentCopyTarget`` costs.

        Each copy costs the target's resources and its ``doubling_ruby_cost`` in rubies; see
        "Spending rubies" in the guides.

        Args:
            castle_id: The castle whose queue is copied, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: The list ``targets`` came for
            targets: Entries from ``get_recruitment_copy_targets``
            spend_rubies: Allow targets whose ``doubling_ruby_cost`` is above 0
            timeout: Timeout in seconds

        Raises:
            ValueError: No targets, a target the client would not let you pick, or rubies due
                without ``spend_rubies``
            ProductionSlotsNeededError: The list needs more unlocked slots first
            CommandError: ``NOT_ENOUGH_RESOURCES`` and other refusals

        Client: ``AAutoRecruitmentCopyDialog.onOkButton`` (bundle line 51255), enabled once a castle is
        picked (``updateOkButton``); a castle with an ``EID`` cannot be picked
        (``AAutoRecruitmentCopyListItemVE.updateGreyOut``, bundle line 36574); costs summed by
        ``AutoRecruitmentCopyCostSublayer.getCurrentCosts`` (bundle line 83947)
        """
        if not targets:
            raise ValueError("pick at least one castle to copy the queue to")
        refused = [target.castle_id for target in targets if not target.can_copy]
        if refused:
            raise ValueError(f"castles {refused} cannot take the copy; see RecruitmentCopyTarget.refusal")
        rubies = sum(target.doubling_ruby_cost for target in targets)
        self._require_spend_rubies(spend_rubies, f"copying the queue costs {rubies} rubies" if rubies > 0 else None)
        kingdom = self._join_castle(castle_id, timeout)
        request = DuplicateRecruitmentLoopRequest(
            list_id=list_id,
            kingdom=kingdom,
            castle_id=castle_id,
            destinations=[
                RecruitmentCopyDestination(kingdom=target.kingdom, castle_id=target.castle_id) for target in targets
            ],
        )
        self._execute_needing_slots(request, timeout)

    def _execute_needing_slots(
        self, request: UpdateRecruitmentLoopRequest | DuplicateRecruitmentLoopRequest, timeout: float
    ) -> None:
        try:
            self.execute(request, timeout=timeout)
        except CommandError as e:
            if e.error is GGEError.NO_FREE_CONSTRUCTION_SLOT:
                raise ProductionSlotsNeededError(e.command, e.code, e.payload) from e
            raise

    # =========================================================================
    # Hospital
    # =========================================================================

    def heal_units(
        self, castle_id: int, wod_id: int, amount: int, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """
        Queue wounded units for healing.

        A unit whose ``UnitStats.healing_cost_rubies`` is above 0 heals for rubies; see "Spending
        rubies" in the guides. A subscription that waives it is not checked.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            wod_id: The wounded unit's wod id
            amount: How many to heal
            spend_rubies: Allow healing a unit that costs rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: The unit heals for rubies, or is not in the game data, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded

        Client: ``CastleRecruitSelectedUnitComponent.onReviveClick`` (bundle line 51105), priced at
        ``healingCostC2`` per unit (bundle line 51110)
        """
        if not spend_rubies:
            unit = self._require_game_data().get_unit(wod_id)
            if unit is None:
                self._require_spend_rubies(spend_rubies, f"unit {wod_id} is not in the game data and may cost rubies")
            elif unit.healing_cost_rubies > 0:
                self._require_spend_rubies(spend_rubies, f"healing unit {wod_id} costs rubies")
        self._join_castle(castle_id, timeout)
        self.execute(HealUnitsRequest(wod_id=wod_id, amount=amount), timeout=timeout)

    def heal_all(self, castle_id: int, ruby_cost: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Heal every wounded unit at once, for rubies; see "Spending rubies" in the guides.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            ruby_cost: The price the client would show (see ``HealAllRequest``);
                the server refuses a price that no longer matches the hospital
            spend_rubies: Allow a ``ruby_cost`` above 0
            timeout: Timeout in seconds

        Raises:
            ValueError: ``ruby_cost`` is above 0 and ``spend_rubies`` is False

        Client: ``CastleHospitalReviveAllDialog.reviveAll`` (bundle line 83667), with the price from
        ``CastleRecruitDialogHospital.openReviveAllDialog`` (bundle lines 83509-83513)
        """
        self._require_spend_rubies(spend_rubies, f"healing all costs {ruby_cost} rubies" if ruby_cost > 0 else None)
        self._join_castle(castle_id, timeout)
        self.execute(HealAllRequest(ruby_cost=ruby_cost), timeout=timeout)

    def cancel_heal(self, castle_id: int, position: int, *, timeout: float = 5.0) -> None:
        """
        Cancel a hospital slot, by its ``HospitalSlot.position``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.onCurrentSlotCancelled`` (bundle line 83508)
        """
        self._join_castle(castle_id, timeout)
        self.execute(CancelHealRequest(position=position), timeout=timeout)

    def skip_heal(self, castle_id: int, position: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Finish a hospital slot now, by its ``HospitalSlot.position``, for rubies; see "Spending
        rubies" in the guides.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            position: The slot's ``HospitalSlot.position``
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``CastleRecruitDialogHospital.skipCurrentSlot`` (bundle line 83504), priced in rubies
        by ``updateSkipTooltip`` (bundle line 83582)
        """
        self._require_spend_rubies(spend_rubies, "finishing a hospital slot costs rubies")
        self._join_castle(castle_id, timeout)
        self.execute(SkipHealRequest(position=position), timeout=timeout)

    def dismiss_wounded(self, castle_id: int, wod_id: int, amount: int, *, timeout: float = 5.0) -> None:
        """
        Dismiss wounded units of one type instead of healing them.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleHospitalDismissUnitsDialog.dismissUnits`` (bundle line 83737)
        """
        self._join_castle(castle_id, timeout)
        self.execute(DismissWoundedRequest(wod_id=wod_id, amount=amount), timeout=timeout)

    def dismiss_wounded_units(self, castle_id: int, units: Mapping[int, int], *, timeout: float = 5.0) -> None:
        """
        Dismiss wounded units of several types at once, as ``{wod_id: amount}``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.onConfirmDeleteAll`` (bundle line 83498)
        """
        self._join_castle(castle_id, timeout)
        entries = [WoundedUnits(wod_id=wod_id, amount=amount) for wod_id, amount in units.items()]
        self.execute(DismissManyWoundedRequest(units=entries), timeout=timeout)

    def get_hospital_flags(self, castle_id: int, *, timeout: float = 5.0) -> HospitalFlags:
        """
        Get the hospital flags of a castle: whether it admits wounded ruby units.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.show`` (bundle line 83456) sends ``C2SHospitalFlagsVO``
        with ``HRF`` -1
        """
        kingdom_id = self._join_castle(castle_id, timeout)
        request = HospitalFlagsRequest(kingdom_id=kingdom_id, castle_id=castle_id)
        return self.request(request, HospitalFlagsResponse, timeout=timeout)

    def set_hospital_flags(self, castle_id: int, *, admit_ruby_units: bool, timeout: float = 5.0) -> HospitalFlags:
        """
        Set whether a castle's hospital admits wounded ruby units.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            admit_ruby_units: Admit wounded ruby units, the hospital dialog's checkbox
            timeout: Timeout in seconds

        Returns:
            The flags after the change

        Client: ``CastleRecruitDialogHospital.toggleRubyBlock`` (bundle line 83605)
        """
        kingdom_id = self._join_castle(castle_id, timeout)
        request = HospitalFlagsRequest(
            kingdom_id=kingdom_id, castle_id=castle_id, admit_ruby_units=1 if admit_ruby_units else 0
        )
        return self.request(request, HospitalFlagsResponse, timeout=timeout)
