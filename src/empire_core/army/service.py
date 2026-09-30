"""
Army service for EmpireCore.

Provides high-level APIs for:
- Unit production
- Unit inventory management
- Hospital operations

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
from empire_core.protocol.base import UnitCount
from empire_core.services.base import BaseService


class ArmyService(BaseService):
    """
    Service for army operations.

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
        self.request(SelectCastleRequest(CID=castle_id, KID=kingdom_id), SelectCastleResponse, timeout=timeout)
        return kingdom_id

    # =========================================================================
    # Unit Inventory
    # =========================================================================

    def get_units(self, castle_id: int, timeout: float = 5.0) -> list[UnitCount]:
        """
        Get the available unit inventory for a castle.

        Covers soldiers and tools. Units in production, in the stronghold or in
        the hospital are reported separately - use get_units_response() for
        those.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Returns:
            List of UnitCount objects
        """
        return self.get_units_response(castle_id, timeout=timeout).get_inventory()

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
        request = DismissUnitsRequest(WID=wod_id, A=amount, S=1 if from_stronghold else 0)
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
        pay_with_rubies: bool = False,
        private_offer_id: int = -1,
        timeout: float = 5.0,
    ) -> bool:
        """
        Produce units or tools.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            list_id: SOLDIERS, TOOLS or AUXILIARIES
            wod_id: Unit or tool wod id
            amount: How many to produce
            pay_with_rubies: Pay rubies for missing resources, as the client's
                resource wait dialog does
            private_offer_id: With ``pay_with_rubies``, the id of the active
                resource merchant private offer; -1 when there is none
            timeout: Timeout in seconds

        Client: ``C2SBuyUnitPackageVO`` (bundle line 35277); the ruby path is
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35218)
        """
        if list_id == ProductionListId.HOSPITAL:
            raise ValueError("bup produces soldiers, tools or auxiliaries; the hospital list is healed with heal_units")
        kingdom_id = self._join_castle(castle_id, timeout)
        request = ProduceUnitsRequest(
            LID=list_id,
            WID=wod_id,
            AMT=amount,
            PO=private_offer_id if pay_with_rubies else -1,
            PWR=1 if pay_with_rubies else 0,
            SID=kingdom_id,
            AID=castle_id,
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
        return self.request(GetProductionListRequest(LID=list_id), GetProductionListResponse, timeout=timeout)

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
        request = CancelProductionRequest(LID=list_id, S=position, ST=slot_type)
        return self.execute(request, timeout=timeout)

    def double_production_slot(
        self,
        castle_id: int,
        list_id: ProductionListId,
        slot_type: SlotType,
        position: int,
        timeout: float = 5.0,
    ) -> bool:
        """
        Double the units of a production slot. Costs rubies.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            slot_type: PRODUCTION for the slot producing now, QUEUE for a queued one
            position: 0 for the slot producing now, else the slot's
                ``ProductionSlot.position``

        Client: ``RecruitmentHelper.boostCurrentSlot`` (bundle line 23165)
        """
        kingdom_id = self._join_castle(castle_id, timeout)
        request = DoubleProductionSlotRequest(LID=list_id, S=position, AID=castle_id, SID=kingdom_id, ST=slot_type)
        return self.execute(request, timeout=timeout)

    # =========================================================================
    # Hospital
    # =========================================================================

    def heal_units(self, castle_id: int, wod_id: int, amount: int, timeout: float = 5.0) -> bool:
        """
        Queue wounded units for healing.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitSelectedUnitComponent.onReviveClick`` (bundle line 51105)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(HealUnitsRequest(U=wod_id, A=amount), timeout=timeout)

    def heal_all(self, castle_id: int, ruby_cost: int, timeout: float = 5.0) -> bool:
        """
        Heal every wounded unit at once, for rubies.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            ruby_cost: The price the client would show (see ``HealAllRequest``);
                the server refuses a price that no longer matches the hospital

        Client: ``CastleHospitalReviveAllDialog.reviveAll`` (bundle line 83667)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(HealAllRequest(C2=ruby_cost), timeout=timeout)

    def cancel_heal(self, castle_id: int, position: int, timeout: float = 5.0) -> bool:
        """
        Cancel a hospital slot, by its ``HospitalSlot.position``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.onCurrentSlotCancelled`` (bundle line 83508)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(CancelHealRequest(S=position), timeout=timeout)

    def skip_heal(self, castle_id: int, position: int, timeout: float = 5.0) -> bool:
        """
        Finish a hospital slot now, by its ``HospitalSlot.position``. Costs rubies.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital`` (bundle line 83504)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(SkipHealRequest(S=position), timeout=timeout)

    def dismiss_wounded(self, castle_id: int, wod_id: int, amount: int, timeout: float = 5.0) -> bool:
        """
        Dismiss wounded units of one type instead of healing them.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleHospitalDismissUnitsDialog.dismissUnits`` (bundle line 83737)
        """
        self._join_castle(castle_id, timeout)
        return self.execute(DismissWoundedRequest(U=wod_id, A=amount), timeout=timeout)

    def dismiss_wounded_units(self, castle_id: int, units: Mapping[int, int], timeout: float = 5.0) -> bool:
        """
        Dismiss wounded units of several types at once, as ``{wod_id: amount}``.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``

        Client: ``CastleRecruitDialogHospital.onConfirmDeleteAll`` (bundle line 83498)
        """
        self._join_castle(castle_id, timeout)
        entries = [WoundedUnits(U=wod_id, A=amount) for wod_id, amount in units.items()]
        return self.execute(DismissManyWoundedRequest(UT=entries), timeout=timeout)
