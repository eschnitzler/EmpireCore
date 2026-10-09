"""
Units, recruitment and the hospital of your castles.

Every command here acts on the castle the session has joined, so each method
joins the castle first (``jca``), as the client is inside a castle before it
shows the recruit or hospital dialog.

Action methods return True when the server accepted the action and False
when it rejected it with an error code; transport failures (timeout,
disconnect) raise. Query methods raise on any failure. A refused join raises
before anything is sent.
"""

from __future__ import annotations

from collections.abc import Mapping

from empire_core.army.models.hospital import (
    CancelHealRequest,
    DismissManyWoundedRequest,
    DismissWoundedRequest,
    HealAllRequest,
    HealUnitsRequest,
    SkipHealRequest,
    WoundedUnits,
)
from empire_core.army.models.production import (
    CancelProductionRequest,
    DoubleProductionSlotRequest,
    GetProductionListRequest,
    GetProductionListResponse,
    ProduceUnitsRequest,
    ProductionList,
)
from empire_core.army.models.units import DismissUnitsRequest, GetUnitsRequest, GetUnitsResponse
from empire_core.castle.models.actions import SelectCastleRequest, SelectCastleResponse
from empire_core.enums import Kingdom, ProductionListId, SlotType
from empire_core.gamedata import UnitOrTool
from empire_core.services.base import BaseService


class ArmyService(BaseService):
    """
    Units, recruitment and the hospital of one of your castles.

    Reached as client.army.

    Each method joins the castle it is given first (``jca``), as the client acts
    on the castle it is in. It joins in that castle's ``Castle.kingdom_id`` from
    ``client.state.get_castles()``, and raises ``UnknownCastleError`` for a castle not listed there.
    A castle id listed in several of your kingdoms raises ``AmbiguousCastleError``.

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

    def get_units(self, castle_id: int, timeout: float = 5.0) -> dict[UnitOrTool, int]:
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

    def get_units_response(self, castle_id: int, timeout: float = 5.0) -> GetUnitsResponse:
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
        self,
        castle_id: int,
        wod_id: int,
        amount: int,
        from_stronghold: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Dismiss units of the castle, or of its stronghold.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDismissUnitsDialog.dismissUnits`` (bundle line 84330)
        """
        self._join_castle(castle_id, timeout)
        request = DismissUnitsRequest(wod_id=wod_id, amount=amount, from_stronghold=1 if from_stronghold else 0)
        return self.execute(request, timeout=timeout)

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
    ) -> bool:
        """
        Produce units or tools.

        Spends rubies when the unit or tool has a ruby price (``cost_rubies`` or, on a temporary
        server, ``temp_server_cost_rubies`` in the game data, refused on either kind of server), and
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
            GameDataNotLoadedError: ``spend_rubies`` is False and ``client.load_game_data()`` has not been called

        Client: ``C2SBuyUnitPackageVO`` (bundle line 35277); ``BasicUnitVO.basicCostC2`` (bundle line
        19248); the ruby path is ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35218)
        """
        if list_id == ProductionListId.HOSPITAL:
            raise ValueError("bup produces soldiers, tools or auxiliaries; the hospital list is healed with heal_units")
        if not spend_rubies:
            game_data = self._require_game_data("Pricing a unit")
            row = game_data.get_unit(wod_id) or game_data.get_tool(wod_id)
            if row is None:
                self._require_spend_rubies(spend_rubies, f"wod id {wod_id} is not in the game data and may cost rubies")
            elif max(row.cost_rubies, row.temp_server_cost_rubies) > 0:
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
        return self.execute(request, timeout=timeout)

    def get_production_list(self, castle_id: int, list_id: ProductionListId, timeout: float = 5.0) -> ProductionList:
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
        self,
        castle_id: int,
        list_id: ProductionListId,
        slot_type: SlotType,
        position: int,
        timeout: float = 5.0,
    ) -> bool:
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
        return self.execute(request, timeout=timeout)

    def double_production_slot(
        self,
        castle_id: int,
        list_id: ProductionListId,
        slot_type: SlotType,
        position: int,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> bool:
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
        return self.execute(request, timeout=timeout)

    # =========================================================================
    # Hospital
    # =========================================================================

    def heal_units(
        self, castle_id: int, wod_id: int, amount: int, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> bool:
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
            GameDataNotLoadedError: ``spend_rubies`` is False and ``client.load_game_data()`` has not been called

        Client: ``CastleRecruitSelectedUnitComponent.onReviveClick`` (bundle line 51105), priced at
        ``healingCostC2`` per unit (bundle line 51110)
        """
        if not spend_rubies:
            unit = self._require_game_data("Pricing a heal").get_unit(wod_id)
            if unit is None:
                self._require_spend_rubies(spend_rubies, f"unit {wod_id} is not in the game data and may cost rubies")
            elif unit.healing_cost_rubies > 0:
                self._require_spend_rubies(spend_rubies, f"healing unit {wod_id} costs rubies")
        self._join_castle(castle_id, timeout)
        return self.execute(HealUnitsRequest(wod_id=wod_id, amount=amount), timeout=timeout)

    def heal_all(self, castle_id: int, ruby_cost: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> bool:
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
        return self.execute(HealAllRequest(ruby_cost=ruby_cost), timeout=timeout)

    def cancel_heal(self, castle_id: int, position: int, timeout: float = 5.0) -> bool:
        """
        Cancel a hospital slot, by its ``HospitalSlot.position``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.onCurrentSlotCancelled`` (bundle line 83508)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(CancelHealRequest(position=position), timeout=timeout)

    def skip_heal(self, castle_id: int, position: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> bool:
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
        return self.execute(SkipHealRequest(position=position), timeout=timeout)

    def dismiss_wounded(self, castle_id: int, wod_id: int, amount: int, timeout: float = 5.0) -> bool:
        """
        Dismiss wounded units of one type instead of healing them.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleHospitalDismissUnitsDialog.dismissUnits`` (bundle line 83737)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(DismissWoundedRequest(wod_id=wod_id, amount=amount), timeout=timeout)

    def dismiss_wounded_units(self, castle_id: int, units: Mapping[int, int], timeout: float = 5.0) -> bool:
        """
        Dismiss wounded units of several types at once, as ``{wod_id: amount}``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.onConfirmDeleteAll`` (bundle line 83498)
        """
        self._join_castle(castle_id, timeout)
        entries = [WoundedUnits(wod_id=wod_id, amount=amount) for wod_id, amount in units.items()]
        return self.execute(DismissManyWoundedRequest(units=entries), timeout=timeout)
