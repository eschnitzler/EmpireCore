"""Renaming, abandoning and relocating a castle."""

from __future__ import annotations

from empire_core.castle.models.actions import (
    AbandonCastleRequest,
    AbandonCastleResponse,
    CancelAbandonCastleRequest,
    LeaveAreaRequest,
    RelocateCastleRequest,
    RenameCastleRequest,
)
from empire_core.castle.service.castles import CastlesMixin
from empire_core.enums import MapItemType
from empire_core.exceptions import UnknownCastleError

# PlayerConst.CHANGE_CASTLE_NAME_C2 (dll line 19599)
_RENAME_RUBIES = 2500

# RelocationConst.RELOCATION_COST_C2 (dll line 19674), by relocations made, the last for any more
_RELOCATION_RUBIES = (0, 5000, 20000, 35000)
# CastleListVO.getMainCastleByKingdomID (bundle line 13864)
_MAIN_CASTLE_TYPES = (MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE)


class CastleModificationMixin(CastlesMixin):
    # =========================================================================
    # Castle Modification
    # =========================================================================

    def rename(
        self,
        castle_id: int,
        new_name: str,
        *,
        is_initial_name: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Rename one of your castles.

        Looks the castle up in the castle list for the type and kingdom the
        server needs, so this costs one extra round trip. Pass
        ``is_initial_name=True`` to name a newly acquired castle, such as a
        monument or laboratory, instead of renaming one. A rename costs
        ``PlayerConst.CHANGE_CASTLE_NAME_C2`` (2500) rubies unless a premium account runs;
        see "Spending rubies" in the guides.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            new_name: The new name
            is_initial_name: Name a newly acquired castle instead of renaming one, which is free
            spend_rubies: Allow a rename while no premium account is known to run
            timeout: Timeout in seconds

        Raises:
            ValueError: A rename, no premium account is known to run, and ``spend_rubies`` is False
            UnknownCastleError: ``castle_id`` is not one of your castles.

        Client: ``CastleRenameCastleDialog.showLoaded`` and ``sendCommand`` (bundle lines 57219, 57231)
        price a rename, sent with 1; ``CastleNameCastleDialog.sendCommand`` (bundle line 32589) sends
        the first name with 0 and shows no price; ``CHANGE_CASTLE_NAME_C2`` (dll line 19599)

        Example:
            client.castle.rename(12345, "My Fortress", spend_rubies=True)
        """
        if not is_initial_name:
            if not self.client.state.get_boosts().is_premium_active():
                self._require_spend_rubies(spend_rubies, f"renaming a castle costs {_RENAME_RUBIES} rubies")
        castle = next((c for c in self.get_all(timeout=timeout) if c.castle_id == castle_id), None)
        if castle is None:
            raise UnknownCastleError(castle_id)
        self.execute(
            RenameCastleRequest(
                castle_id=castle_id,
                castle_name=new_name,
                castle_type=castle.castle_type,
                kingdom_id=castle.kingdom_id,
                is_rename=0 if is_initial_name else 1,
            ),
            timeout=timeout,
        )

    def abandon_castle(self, castle_id: int, *, timeout: float = 5.0) -> AbandonCastleResponse:
        """
        Start abandoning one of your castles; it is given up a day later unless cancelled.

        Looks the castle up in the castle list for its kingdom, as :meth:`rename`
        does. Any castle may be abandoned but the kingdom's main castle; a
        faction event's main camp, which the client also counts as one, is
        left to the server. It is free.
        The castle goes after ``OutpostConst.ABANDON_TIME`` (86400 s) and
        :meth:`cancel_abandon` keeps it within ``ABANDON_CANCEL_TIME`` (10800 s).

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            timeout: Timeout in seconds

        Raises:
            ValueError: ``castle_id`` is the main castle of its kingdom
            UnknownCastleError: ``castle_id`` is not one of your castles.
            CommandError: The server refused, as for a castle held too briefly
                (``CastleInfo.no_abandon_seconds`` above 0), which the client
                refuses itself with ``NOT_OWNED_LONG_ENOUGH``

        Client: ``CastleManagementDialog.setDeleteOutpostAndRelocateButton`` (bundle line 24592)
        offers it for any castle but ``CastleListVO.getMainCastleByKingdomID`` (bundle line
        13864), the kingdom's castle of type ``CASTLE`` or ``KINGDOM_CASTLE``;
        ``onAbandonOutpost`` (bundle line 24630) sends ``C2SAbandonOutpostStartVO``;
        ``OutpostConst`` (dll line 19530)

        Example:
            reply = client.castle.abandon_castle(12345)
            print(f"Abandoned in {reply.abandon_seconds} s")
        """
        castles = self.get_all(timeout=timeout)
        castle = next((c for c in castles if c.castle_id == castle_id), None)
        if castle is None:
            raise UnknownCastleError(castle_id)
        main = next(
            (c for c in castles if c.kingdom_id == castle.kingdom_id and c.castle_type in _MAIN_CASTLE_TYPES), None
        )
        if main is castle:
            raise ValueError(f"castle {castle_id} is the main castle of its kingdom and cannot be abandoned")
        return self.request(
            AbandonCastleRequest(castle_id=castle_id, kingdom_id=castle.kingdom_id),
            AbandonCastleResponse,
            timeout=timeout,
        )

    def cancel_abandon(self, castle_id: int, *, timeout: float = 5.0) -> None:
        """
        Keep a castle :meth:`abandon_castle` started to give up.

        Looks the castle up in the castle list for its kingdom. The client
        offers it while ``CastleInfo.cancel_abandon_seconds`` is above 0.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not one of your castles.
            CommandError: The server refused.

        Client: ``CastleManagementDialog.onDeleteOutpostClick`` and ``onCancelAbandoning``
        (bundle lines 24624, 24629) send ``C2SAbandonOutpostCancelVO``

        Example:
            client.castle.cancel_abandon(12345)
        """
        castle = next((c for c in self.get_all(timeout=timeout) if c.castle_id == castle_id), None)
        if castle is None:
            raise UnknownCastleError(castle_id)
        self.execute(CancelAbandonCastleRequest(castle_id=castle_id, kingdom_id=castle.kingdom_id), timeout=timeout)

    def relocate(self, x: int, y: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Move your main castle in the green kingdom to a new position.

        The client offers it on the green kingdom's map, at a free position or a ruin. The first
        relocation is free; the next cost ``RelocationConst.RELOCATION_COST_C2`` (5000, 20000, then
        35000 rubies each), less any ruby discount, and need ``spend_rubies``, as does any relocation
        while no ``gri`` has said how many were made. The cooldown
        (``client.player.relocation``) is left to the server.

        Args:
            x: Map x of the new position
            y: Map y of the new position
            spend_rubies: Allow a relocation that costs rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: The relocation costs rubies, or its price is not known, and ``spend_rubies`` is False
            CommandError: The server refused, as with ``CASTLE_HAS_MOVEMENTS`` while armies are on the way

        Client: ``CastleRelocateDialog.getCost`` and ``onClick`` (bundle line 109656),
        ``SwitchToRelocateWorldmapCommand.execute`` (bundle line 100959), ``RSTCommand.executeCommand``
        (bundle line 126855); ``RelocationConst.getRelocationCost`` (dll line 19674)
        """
        relocation = self.client.state.get_relocation()
        if relocation is None:
            cost = "no relocation count is known yet, so the relocation may cost rubies"
        elif price := _RELOCATION_RUBIES[min(relocation.relocation_count, len(_RELOCATION_RUBIES) - 1)]:
            cost = f"this relocation costs {price} rubies"
        else:
            cost = None
        self._require_spend_rubies(spend_rubies, cost)
        self.execute(RelocateCastleRequest(x=x, y=y), timeout=timeout)

    def leave_area(self) -> None:
        """
        Leave the area you joined last, as the client does when it opens the kingdom overview.

        The client has no handler for a reply, so none is waited for.

        Client: ``CastleKingdomOverviewScreen.show`` (bundle line 108518) sends ``C2SLeaveAreaVO``
        """
        self.send(LeaveAreaRequest())
