"""Season camps, the Samurai Invasion's daimyo and past special server runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from empire_core.enums import Kingdom
from empire_core.events.service.base import EventsBaseMixin
from empire_core.gamedata import EventDifficultyId, PartPayPriceId
from empire_core.gamedata.ids.events import Event

if TYPE_CHECKING:
    from empire_core.gamedata import PrebuiltCastle, TreasureMapId

from empire_core.events.models import SeasonEvent
from empire_core.events.progression_models import (
    DaimyoAreasResponse,
    DaimyoContractsResponse,
    DaimyoWarEffortsResponse,
    GetDaimyoAreasRequest,
    GetDaimyoContractsRequest,
    GetDaimyoWarEffortsRequest,
    SeasonJoinEventRequest,
    SelectEventDifficultyRequest,
    SelectEventDifficultyResponse,
    UnlockEventRequest,
    UnlockEventResponse,
)
from empire_core.events.season_models import JoinSeasonCampRequest, SelectSeasonCampRequest
from empire_core.events.special_server_models import GetPreviousSpecialServerRunsRequest, PreviousSpecialServerRuns


class SeasonsMixin(EventsBaseMixin):
    def join_season_camp(self, event: Event, *, timeout: float = 5.0) -> None:
        """Enter a running season event's map at your camp there.

        Raises:
            EventNotRunningError: The event is not running
            ValueError: It is no season event, or names no map
            CommandError: The server refused

        Client: ``SeasonCampPanelButton.onButtonClicked`` (bundle line 108195) sends ``C2SJoinCampVO``
        with the running season event's map; ``JEACommand`` (bundle line 131625).
        """
        self.execute(JoinSeasonCampRequest(map_id=self._season_map(event)), timeout=timeout)

    def unlock_season_camp(
        self, camp: PrebuiltCastle, *, ruby_price: bool = False, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """Start on a season event's map with one of its prebuilt camps, e.g. ``PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP``.

        The camp names the map: the first of its spaces. A camp whose only price is rubies is bought with
        them; one priced in resources is bought with those, or with ``ruby_price`` at its ruby price, as the
        client's two buttons offer. Rubies spent need ``spend_rubies``; buying with resources,
        ``spend_rubies`` pays any missing ones with rubies.

        Raises:
            ValueError: The camp starts a kingdom, not a season event's map, needs a higher level, has no ruby
                price for ``ruby_price``, or costs rubies without ``spend_rubies``
            GameDataNotLoadedError: The game data cannot be loaded
            StateNotLoadedError: No login has brought your level
            CommandError: The server refused

        Client: ``AUnlockPrebuiltCastle.buyPrebuiltCastle`` (bundle line 55482) sends ``csc`` for a castle with
        no space in ``WorldConst.WORLD_IDS``; ``UnlockPrebuiltCastleForRubies`` (bundle line 55514) sets ``OC2``
        for the castle ``CastleKingdomCastleDetails.getSublayerForCastle`` (bundle line 97911) shows as premium;
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35238) sends ``PWR``;
        ``CSCCommand`` (bundle line 128343).
        """
        row = self._prebuilt_castle(camp)
        if row.kingdom is not None or not row.space_ids:
            raise ValueError(f"prebuilt castle {int(camp)} is no season camp")
        rubies = self._castle_rubies(row, ruby_price)
        self._require_spend_rubies(spend_rubies, f"the camp costs {rubies} rubies" if rubies else None)
        request = SelectSeasonCampRequest(
            prebuilt_camp_id=row.prebuilt_castle_id,
            pay_with_rubies=spend_rubies and not rubies,
            ruby_camp=rubies > 0,
            space_id=row.space_ids[0],
        )
        self.execute(request, timeout=timeout)

    def open_season_map(self, event: Event) -> None:
        """Tell the server you opened a running season event's map, as the client does each time it shows it.

        The client reads no answer, so none is waited for.

        Raises:
            EventNotRunningError: The event is not running
            ValueError: It is no season event, or names no map

        Client: ``CastleSeasonMapScreen.show`` (bundle line 108619) sends ``C2SSeasonJoinEventVO`` with the map
        """
        self.send(SeasonJoinEventRequest(map_id=self._season_map(event)))

    def _season_map(self, event: Event) -> TreasureMapId | int:
        found = self._require_running(event)
        if not isinstance(found, SeasonEvent) or found.map_id is None:
            raise ValueError(f"{Event(event).name} is no season event with a map")
        return found.map_id

    def pay_toward_unlock(
        self,
        part_price_id: PartPayPriceId,
        *,
        wood: int = 0,
        stone: int = 0,
        coins: int = 0,
        castle_id: int = -1,
        kingdom: Kingdom = Kingdom.GREEN,
        ruby_payment: Literal["wood", "stone", "coins"] | None = None,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """Pay towards something priced in parts: a season map's obstacle, a treasure map node or a slum level.

        ``part_price_id`` is the price's row in ``GameData.part_pay_prices``, which the obstacle, node
        (``TreasureMapNodeDef.part_price_id``) or slum level names. Goods come from ``castle_id`` in
        ``kingdom``: the client pays a slum level from the joined castle, a treasure hunt node from your main
        castle in the hunt's kingdom, and a season obstacle from no castle (-1) in the green kingdom.
        ``ruby_payment`` instead pays that resource's missing amount in rubies, and needs ``spend_rubies``.

        Raises:
            ValueError: ``ruby_payment`` without ``spend_rubies``, or with goods; no goods and no ``ruby_payment``
            CommandError: The server refused; the client shows nothing for ``ALREADY_UNLOCKED`` and ``NO_EVENT``

        Client: ``CastleSlumDonateDialog.onClick`` (bundle line 87707), ``CastleTreasureMapDonateDialog.onClick``
        (bundle line 67887), ``CastleSeasonBaseRepairDialog.onClick`` (bundle line 37624),
        ``CastleTreasureMapUnlockObstacleDialog.onClick`` (bundle line 67849), ``ULECommand.executeCommand``
        (bundle line 129307)
        """
        if ruby_payment is not None:
            if wood or stone or coins:
                raise ValueError("pay either goods or one resource's missing amount in rubies")
            self._require_spend_rubies(spend_rubies, f"paying the missing {ruby_payment} costs rubies")
            wood, stone, coins = (int(ruby_payment == name) for name in ("wood", "stone", "coins"))
        elif not (wood > 0 or stone > 0 or coins > 0):
            raise ValueError("nothing to pay")
        request = UnlockEventRequest(
            castle_id=castle_id,
            kingdom=kingdom,
            wood=wood,
            stone=stone,
            coins=coins,
            part_price_id=part_price_id,
            pay_with_rubies=ruby_payment is not None,
        )
        self.request(request, UnlockEventResponse, timeout=timeout)

    def select_difficulty(
        self,
        event: Event | int,
        difficulty_id: EventDifficultyId,
        *,
        unlock_with_rubies: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """Choose a running event's difficulty.

        ``difficulty_id`` is the difficulty's row in ``GameData.event_difficulties``, or 0 for the
        event without difficulty scaling. A locked difficulty is opened with ``unlock_with_rubies`` for its
        ruby price, which needs ``spend_rubies``. The event's ``difficulty_id`` changes with its next update.

        Raises:
            EventNotRunningError: The event is not running
            ValueError: ``unlock_with_rubies`` without ``spend_rubies``
            CommandError: The server refused

        Client: ``EventDifficultyConfirmDialog.onClick`` (bundle line 98770),
        ``EventDifficultyConfirmRewardsDialog.onClick`` (bundle line 98787), ``DifficultyScalingSelectDialog.onClick``
        (bundle line 30389), ``SEDECommand.executeCommand`` (bundle line 128462)
        """
        self._require_running(event)
        self._require_spend_rubies(
            spend_rubies, "unlocking a difficulty costs its ruby price" if unlock_with_rubies else None
        )
        request = SelectEventDifficultyRequest(
            event_id=int(event), difficulty_id=difficulty_id, unlock_with_rubies=unlock_with_rubies
        )
        self.request(request, SelectEventDifficultyResponse, timeout=timeout)

    def get_daimyo_areas(self, *, timeout: float = 5.0) -> DaimyoAreasResponse:
        """Request the samurai invasion's daimyo castles and townships; the running event keeps them too.

        Raises:
            EventNotRunningError: The samurai invasion is not running
            CommandError: The server refused

        Client: ``CastleAllianceSamuraiInvasionDialogDaimyoSublayer.show`` (bundle line 99060),
        ``GDACommand.executeCommand`` (bundle line 128283)
        """
        self._require_running(Event.SAMURAI_INVASION)
        return self.request(GetDaimyoAreasRequest(), DaimyoAreasResponse, timeout=timeout)

    def get_daimyo_contracts(self, *, timeout: float = 5.0) -> DaimyoContractsResponse:
        """Request your alliance's daimyo contracts; the running samurai invasion keeps them too.

        Raises:
            EventNotRunningError: The samurai invasion is not running
            CommandError: The server refused

        Client: ``CastleAllianceSamuraiInvasionDialogDaimyoSublayer.show`` (bundle line 99060),
        ``GDCCommand.executeCommand`` (bundle line 128298)
        """
        self._require_running(Event.SAMURAI_INVASION)
        return self.request(GetDaimyoContractsRequest(), DaimyoContractsResponse, timeout=timeout)

    def get_daimyo_war_efforts(self, *, timeout: float = 5.0) -> DaimyoWarEffortsResponse:
        """Request your war efforts against the daimyo; the running samurai invasion keeps them too.

        Raises:
            EventNotRunningError: The samurai invasion is not running
            CommandError: The server refused

        Client: ``CastleAllianceSamuraiInvasionDialogDaimyoSublayer.show`` (bundle line 99060),
        ``GDWCommand.executeCommand`` (bundle line 128313)
        """
        self._require_running(Event.SAMURAI_INVASION)
        return self.request(GetDaimyoWarEffortsRequest(), DaimyoWarEffortsResponse, timeout=timeout)

    def get_previous_special_server_runs(self, *, timeout: float = 5.0) -> PreviousSpecialServerRuns:
        """Request when the Outer Realms and Beyond the Horizon last ran.

        Client: ``CastleHighscoreDialog.getGlobalServerInfo`` (bundle line 27707), ``GPRCommand.executeCommand``
        (bundle line 128892)
        """
        return self.request(GetPreviousSpecialServerRunsRequest(), PreviousSpecialServerRuns, timeout=timeout)
