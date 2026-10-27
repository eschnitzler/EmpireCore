"""Event minigames."""

from __future__ import annotations

from collections.abc import Mapping

from empire_core.enums import Kingdom
from empire_core.enums.events import WheelOfFortuneType, WorldCupVote
from empire_core.events.minigame_models import (
    BuyArtifactPieceRequest,
    BuyArtifactPieceResponse,
    BuyMaraudersContestPackageRequest,
    CollectorCurrencyResponse,
    ColossusCoinDepositRequest,
    ColossusCoinDepositResponse,
    ColossusDepositRequest,
    ColossusDepositResponse,
    DonateItemsRequest,
    DonateItemsResponse,
    DonationItemAmount,
    DonationItemPoints,
    FortuneTellerReadingRequest,
    FortuneTellerReadingResponse,
    GachaSpinRequest,
    GachaSpinResponse,
    GetCollectorCurrencyRequest,
    GetImperialPatronageProgressRequest,
    ImperialPatronageProgressResponse,
    SkipShadyLadyTargetRequest,
    SkipShadyLadyTargetResponse,
    ValidateShadyLadyTargetRequest,
    VoteWorldCupRequest,
    VoteWorldCupResponse,
    WheelOfFortuneBuyJackpotRequest,
    WheelOfFortuneBuyJackpotResponse,
    WheelOfFortuneChangeModeRequest,
    WheelOfFortuneChangeModeResponse,
    WheelOfFortuneIncreaseWinClassRequest,
    WheelOfFortuneIncreaseWinClassResponse,
    WheelOfFortuneSpinRequest,
    WheelOfFortuneSpinResponse,
)
from empire_core.events.models import GachaEvent, GetEventPointsResponse, TravelingKnightsEvent, WorldCupEvent
from empire_core.events.service.base import EventsBaseMixin
from empire_core.events.service.scores import ScoresMixin
from empire_core.exceptions import EventNotRunningError
from empire_core.gamedata import DonationItemId
from empire_core.gamedata.ids.events import Event

_WOOD_COLOSSI = (Event.COLOSSUS_44, Event.COLOSSUS_57)


class MinigamesMixin(ScoresMixin, EventsBaseMixin):
    # Event minigames

    def spin_wheel_of_fortune(
        self, wheel: WheelOfFortuneType = WheelOfFortuneType.WHEEL_OF_FORTUNE, *, timeout: float = 5.0
    ) -> WheelOfFortuneSpinResponse:
        """
        Spin a Wheel of Fortune, paid with Wheel of Fortune tickets or a free spin; the wheel's event is updated.

        Raises:
            EventNotRunningError: The wheel's event is not running
            CommandError: The server refused, e.g. without tickets

        Client: ``C2SLuckyWheelSpinVO`` (bundle line 59783), ``LWSCommand.executeCommand`` (bundle line 128141)
        """
        self._require_running(
            Event.WHEEL_OF_UNIMAGINABLE_AFFLUENCE
            if wheel == WheelOfFortuneType.WHEEL_OF_UNIMAGINABLE_AFFLUENCE
            else Event.WHEEL_OF_FORTUNE
        )
        return self.request(WheelOfFortuneSpinRequest(wheel=wheel), WheelOfFortuneSpinResponse, timeout=timeout)

    def change_wheel_of_fortune_mode(self, *, timeout: float = 5.0) -> WheelOfFortuneChangeModeResponse:
        """
        Switch the Wheel of Fortune between normal and pro mode; the client offers it to paying players only.

        Client: ``CastleLuckyWheelDialog.changeMode`` (bundle line 116666), ``LWMCommand.executeCommand`` (bundle
        line 128122)
        """
        self._require_running(Event.WHEEL_OF_FORTUNE)
        return self.request(WheelOfFortuneChangeModeRequest(), WheelOfFortuneChangeModeResponse, timeout=timeout)

    def buy_wheel_of_fortune_jackpot(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> WheelOfFortuneBuyJackpotResponse:
        """
        Spin the Wheel of Fortune for a guaranteed jackpot, paid in rubies and tickets by the wheel's mode.

        Raises:
            ValueError: Without ``spend_rubies``
            EventNotRunningError: The Wheel of Fortune is not running

        Client: ``CastleLuckyWheelDialog.clickedBuyJackpot`` (bundle line 116659), ``LuckyWheelData.jackpotC2Price``
        (bundle line 17639), ``LWJCommand.executeCommand`` (bundle line 128105)
        """
        self._require_running(Event.WHEEL_OF_FORTUNE)
        self._require_spend_rubies(spend_rubies, "the jackpot costs rubies")
        return self.request(WheelOfFortuneBuyJackpotRequest(), WheelOfFortuneBuyJackpotResponse, timeout=timeout)

    def increase_wheel_of_fortune_win_class(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> WheelOfFortuneIncreaseWinClassResponse:
        """
        Raise the Wheel of Fortune's win class at once, paid in rubies for the spins it skips.

        Raises:
            ValueError: Without ``spend_rubies``
            EventNotRunningError: The Wheel of Fortune is not running

        Client: ``CastleLuckyWheelIncreaseWinClassDialog.clickedAccept`` (bundle line 117107),
        ``LuckyWheelData.increaseWinClassC2`` (bundle line 17628), ``LWCCommand.executeCommand`` (bundle line 128090)
        """
        self._require_running(Event.WHEEL_OF_FORTUNE)
        self._require_spend_rubies(spend_rubies, "raising the win class costs rubies")
        return self.request(
            WheelOfFortuneIncreaseWinClassRequest(), WheelOfFortuneIncreaseWinClassResponse, timeout=timeout
        )

    def pull_gacha(
        self, event: Event | int, pulls: int = 1, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> GachaSpinResponse:
        """
        Pull a gacha event's chest ``pulls`` times; the event's points and free chest are updated.

        A pull's price is the gacha level's cost list in the game data's gachas table, which the library does
        not load, so it may be rubies: the call needs ``spend_rubies``.

        Raises:
            ValueError: Without ``spend_rubies``, or ``pulls`` below 1
            EventNotRunningError: The event is not running, or is no gacha event

        Client: ``GachaComponentPull.onClick`` (bundle line 57102), ``GachaXmlVO.init`` (bundle line 113936) reads the
        cost list, ``DGECommand.executeCommand`` (bundle line 124175)
        """
        found = self._require_running(event)
        if not isinstance(found, GachaEvent):
            raise EventNotRunningError(int(event))
        self._require_spend_rubies(spend_rubies, "a gacha pull's price can be rubies")
        request = GachaSpinRequest(event_id=int(event), pulls=pulls)
        with self.client.connection.command_lock("dge", timeout=timeout):
            self.client.state._begin_gacha_spin(int(event))
            try:
                return self.request(request, GachaSpinResponse, timeout=timeout)
            finally:
                self.client.state._end_gacha_spin()

    def donate_to_colossus(
        self, castle_id: int, *, wood: int = 0, stone: int = 0, timeout: float = 5.0
    ) -> ColossusDepositResponse:
        """
        Donate wood and stone from one of your castles to the running colossus.

        Raises:
            ValueError: Neither amount is above 0, or the castle is not yours
            EventNotRunningError: No wood and stone colossus is running

        Client: ``CastleColossusDonateDialog.onDonate`` (bundle line 59308), ``CDECommand.executeCommand`` (bundle
        line 127690)
        """
        if not any(self.client.state.get_event(colossus) is not None for colossus in _WOOD_COLOSSI):
            raise EventNotRunningError(Event.COLOSSUS_44)
        if wood <= 0 and stone <= 0:
            raise ValueError("a donation needs wood or stone above 0")
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = ColossusDepositRequest(castle_id=castle_id, kingdom=kingdom, stone=stone, wood=wood)
        return self.request(request, ColossusDepositResponse, timeout=timeout)

    def donate_to_gold_colossus(self, coins: int, *, timeout: float = 5.0) -> ColossusCoinDepositResponse:
        """
        Donate coins to the running coin colossus.

        Client: ``CastleCoinColossusDonateDialog.onDonate`` (bundle line 59272), ``CCDCommand.executeCommand``
        (bundle line 127672)
        """
        self._require_running(Event.GOLD_COLOSSUS)
        return self.request(ColossusCoinDepositRequest(coins=coins), ColossusCoinDepositResponse, timeout=timeout)

    @property
    def donated_points(self) -> tuple[DonationItemPoints, ...] | None:
        """The points each imperial patronage item has earned you, from the last ``gdti`` or ``ddi``; None before
        one or while the event is not running."""
        event = self.client.state.get_event(Event.IMPERIAL_PATRONAGE)
        return event.donated_points if event is not None else None

    def get_imperial_patronage_progress(self, *, timeout: float = 5.0) -> tuple[DonationItemPoints, ...]:
        """
        Ask for the points each imperial patronage item has earned you; kept as :attr:`donated_points`.

        Client: ``DonationEventDialog`` (bundle line 39780), ``GDTICommand.executeCommand`` (bundle line 123604)
        """
        self._require_running(Event.IMPERIAL_PATRONAGE)
        return self.request(
            GetImperialPatronageProgressRequest(), ImperialPatronageProgressResponse, timeout=timeout
        ).items

    def donate_items(
        self, items: Mapping[DonationItemId, int], *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> tuple[DonationItemPoints, ...]:
        """
        Give imperial patronage items, by donation item id and amount; returns the points each has earned.

        A donation item is a resource or a currency (``GameData.donation_items``), which may be rubies: the call
        needs ``spend_rubies``.

        Raises:
            ValueError: No amount is above 0, or ``spend_rubies`` is False

        Client: ``DonationEventDialogDonate.onDonate`` (bundle line 115642), ``DDICommand.executeCommand`` (bundle
        line 123589); ``DonationEventDialogDonateItem.unfilteredAmountInInventory`` (bundle line 115730) gives
        rubies for an item whose resource is ``C2``
        """
        self._require_running(Event.IMPERIAL_PATRONAGE)
        given = tuple(
            DonationItemAmount(donation_item_id=item, amount=amount) for item, amount in items.items() if amount > 0
        )
        if not given:
            raise ValueError("a donation needs an amount above 0")
        self._require_spend_rubies(spend_rubies, "a donation item can be rubies")
        return self.request(DonateItemsRequest(items=given), DonateItemsResponse, timeout=timeout).items

    def give_marauder_packages(
        self,
        castle_id: int,
        *,
        wood_packages: int = 0,
        stone_packages: int = 0,
        food_packages: int = 0,
        timeout: float = 5.0,
    ) -> GetEventPointsResponse:
        """
        Hand resource packages from one of your castles to the marauders' contest, then read your points as the
        client does.

        A package is the event's own amount of the resource, which the sei entry does not carry.

        Raises:
            ValueError: No package count is above 0, or the castle is not yours
            EventNotRunningError: The marauders' contest is not running

        Client: ``C2SBuyBeggingKnightsPackageVO`` (bundle line 114933), sent with each amount divided by the
        package size (bundle line 114916); ``BKPCommand.executeCommand`` (bundle line 128233) asks for the points
        """
        self._require_running(Event.MARAUDERS_CONTEST)
        if max(wood_packages, stone_packages, food_packages) <= 0:
            raise ValueError("pass a package count above 0")
        request = BuyMaraudersContestPackageRequest(
            castle_id=castle_id,
            kingdom=self._require_own_castle(castle_id).kingdom_id,
            wood_packages=wood_packages,
            stone_packages=stone_packages,
            food_packages=food_packages,
        )
        self.execute(request, timeout=timeout)
        return self.get_own_points(Event.MARAUDERS_CONTEST, timeout=timeout)

    def buy_artifact_pieces(
        self, event: Event | int, pieces: int = 1, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> BuyArtifactPieceResponse:
        """
        Buy pieces of a running Traveling Knights event's artifact with rubies; the event's ``parts_found`` is updated.

        Raises:
            ValueError: Without ``spend_rubies``
            EventNotRunningError: The event is not running, or is no Traveling Knights event
            GameDataNotLoadedError: The game data, which names the event's kingdom, cannot be loaded

        Client: ``CastleArtifactBuyPieceDialog`` (bundle lines 114756, 114762) prices the pieces in rubies and sends
        the event's first kingdom (``kIDs``, ``"0"`` when missing, ``ASpecialEventVO.parseBasicsFromXmlNode``,
        bundle line 2960); ``SAPCommand.executeCommand`` (bundle line 127614)
        """
        if not isinstance(self._require_running(event), TravelingKnightsEvent):
            raise EventNotRunningError(int(event))
        self._require_spend_rubies(spend_rubies, "artifact pieces cost rubies")
        kingdoms = self._require_game_data().events[Event(int(event))].kingdoms
        kingdom = Kingdom(kingdoms[0]) if kingdoms else Kingdom.GREEN
        request = BuyArtifactPieceRequest(pieces=pieces, event_id=int(event), kingdom=kingdom)
        return self.request(request, BuyArtifactPieceResponse, timeout=timeout)

    def validate_shady_lady_target(self, *, timeout: float = 5.0) -> None:
        """
        Have the server check your Shady Lady target, as the event's dialog does when it opens; a new target
        arrives in a ``sei``.

        Client: ``CastleBountyhunterEventDialog.applyPropertiesLoaded`` (bundle line 114986),
        ``BRTCommand.executeCommand`` (bundle line 127629)
        """
        self._require_running(Event.SHADY_LADY)
        self.execute(ValidateShadyLadyTargetRequest(), timeout=timeout)

    def skip_shady_lady_target(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> SkipShadyLadyTargetResponse:
        """
        Skip your Shady Lady target for another, paid in rubies; the event's new target comes with the reply.

        Raises:
            ValueError: Without ``spend_rubies``

        Client: ``CastleBountyhunterEventDialog.onClick`` (bundle line 115004), ``targetSkipCostC2`` (bundle line
        114944), ``BSTCommand.executeCommand`` (bundle line 127642)
        """
        self._require_running(Event.SHADY_LADY)
        self._require_spend_rubies(spend_rubies, "skipping the target costs rubies")
        return self.request(SkipShadyLadyTargetRequest(), SkipShadyLadyTargetResponse, timeout=timeout)

    def buy_fortune_teller_reading(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> FortuneTellerReadingResponse:
        """
        Buy today's next fortune teller reading and return its reward.

        Each reading is priced in rubies by the game data's fortune teller classes, which the library does not
        load, so the call needs ``spend_rubies`` even for one that is free.

        Raises:
            ValueError: Without ``spend_rubies``
            GameDataNotLoadedError: The game data, which resolves the rewards, cannot be loaded

        Client: ``FortuneTellerEventDialog.onClick`` and ``updateText`` (bundle lines 59613, 59596),
        ``FortuneTellerClassVO.parseXML`` (bundle line 145167), ``CastleFortuneTellerData.parseFTL`` (bundle line
        145157)
        """
        self._require_running(Event.FORTUNE_TELLER)
        self._require_spend_rubies(spend_rubies, "a reading costs rubies")
        game_data = self._require_game_data()
        reading = self.request(FortuneTellerReadingRequest(), FortuneTellerReadingResponse, timeout=timeout)
        return reading.model_copy(update={"rewards": game_data.reward_list(reading.reward_ids)})

    def vote_world_cup(self, vote: WorldCupVote, *, timeout: float = 5.0) -> VoteWorldCupResponse:
        """
        Bet on the world cup match; no rubies are spent, the bet opens once you spent its price in the event.

        Raises:
            ValueError: You have bet already
            EventNotRunningError: The world cup is not running

        Client: ``CastleWorldCupDialog.updateState`` (bundle line 104658), ``CastleWorldCupDialogNotVotedState``
        (bundle lines 104711-104723), ``VWCCommand.executeCommand`` (bundle line 128541)
        """
        found = self._require_running(Event.WORLD_CUP)
        if isinstance(found, WorldCupEvent) and found.vote >= 0:
            raise ValueError("you have bet on this match already")
        return self.request(VoteWorldCupRequest(vote=vote), VoteWorldCupResponse, timeout=timeout)

    def get_collector_currency(self, player_id: int, *, timeout: float = 5.0) -> int:
        """
        Ask how much of the collector event's currency a player holds, as the attack dialog shows it.

        Client: ``CastleCollectorEventData.getPlayerCollectorAmount`` (bundle line 134000),
        ``PCCCommand.executeCommand`` (bundle line 127657)
        """
        request = GetCollectorCurrencyRequest(player_id=player_id)
        return self.request(request, CollectorCurrencyResponse, timeout=timeout).amount
