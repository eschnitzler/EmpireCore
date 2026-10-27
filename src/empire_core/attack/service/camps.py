"""Robber baron camps, dungeons, taunts and alien camps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.army.spy_army import SpyArmy
from empire_core.attack.models.alien_camps import (
    AlienRerollCountsResponse,
    HiddenAlienCampsResponse,
    RerollAlienCampRequest,
)
from empire_core.attack.models.dungeon_skips import (
    MinuteSkipDungeonRequest,
    MinuteSkipDungeonResponse,
    SkipDungeonCooldownRequest,
    SkipDungeonCooldownResponse,
    _row_coordinates,
    _row_kingdom,
)
from empire_core.attack.models.taunts import LaunchTauntAttackRequest, LaunchWolfKingTauntRequest
from empire_core.enums import CollectableKind, Kingdom, MapItemType
from empire_core.events.models import AlienInvasionEvent
from empire_core.exceptions import PacketError
from empire_core.gamedata import TreasureMapNodeId
from empire_core.map.models.items import MapAreaItem
from empire_core.map.models.treasure_maps import NO_TREASURE_MAP, NO_TREASURE_MAP_NODE
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import ServiceMixin
from empire_core.utils import callbacks

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, TreasureMapId


class CampsMixin(ServiceMixin):
    def robber_baron_camp_army(self, item: MapAreaItem) -> SpyArmy | None:
        """
        A robber baron camp's defenders, from the game data rather than a spy report.

        Each flank holds the camp row's units, then its tools. None for any
        other target, and for a robber baron camp the items payload lists no
        row for. A treasure map dungeon is not covered: its victory count is its map
        node's, which no map row carries (``TreasureDungeonMapObjectVO.victoryCount``,
        bundle line 22004); look it up with ``GameData.dungeon_defense``.

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded
        """
        if item.item_type != MapItemType.DUNGEON or item.victory_count is None:
            return None
        row = self._require_game_data().dungeon_defense(item.victory_count, item.kingdom)
        return SpyArmy.from_robber_baron_camp(row) if row is not None else None

    def minute_skip_dungeon(
        self,
        x: int,
        y: int,
        minute_skip: Currency | str,
        kingdom_id: Kingdom = Kingdom.GREEN,
        *,
        map_id: TreasureMapId | int = NO_TREASURE_MAP,
        node_id: TreasureMapNodeId = NO_TREASURE_MAP_NODE,
        timeout: float = 5.0,
    ) -> MapAreaItem:
        """Use one held minute-skip item and return the updated dungeon.

        Supply both treasure-map ids for a treasure node; omit both for ordinary camps.
        Not checked here: the client offers no skip on a Berimond invasion camp
        (``FactionInvasionCampMapObjectVO.cooldownCanBeSkipped``, bundle line 76359).
        A treasure node can be skipped although ``TreasureDungeonMapObjectVO.cooldownCanBeSkipped`` is
        false (bundle line 22037): that flag gates only the attack button, and the season map's
        ``SeaQueenDungeonSeasonMapScreenItem`` and ``SeaQueenVillageSeasonMapScreenItem.onClickMapItem``
        (bundle lines 108860, 108883) open the skip dialog for a node on cooldown, at position -1, -1.
        Client: SkippableCooldownMinuteSkipProperties.getMinuteSkipCommand (bundle line 72351),
        C2SMinuteSkipDungeonVO (bundle line 72364), MSDCommand (bundle line 125816).
        """
        self._check_dungeon_node(map_id, node_id)
        self._require_minute_skip(minute_skip)
        response = self.request(
            MinuteSkipDungeonRequest(
                x=x, y=y, minute_skip=minute_skip, kingdom_id=kingdom_id, map_id=map_id, node_id=node_id
            ),
            MinuteSkipDungeonResponse,
            timeout=timeout,
        )
        return self._dungeon_skip_result(response, kingdom_id)

    def skip_dungeon_cooldown(
        self,
        x: int,
        y: int,
        kingdom_id: Kingdom = Kingdom.GREEN,
        *,
        map_id: TreasureMapId | int = NO_TREASURE_MAP,
        node_id: TreasureMapNodeId = NO_TREASURE_MAP_NODE,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> MapAreaItem:
        """Pay to skip the remaining cooldown and return the updated dungeon.

        Requires ruby consent; the price depends on the target and remaining time.
        Supply both treasure-map ids for a treasure node. Replies identify position
        and kingdom, not the treasure node; same-position late replies cannot be distinguished.
        Not checked here: the client offers no skip on a Berimond invasion camp
        (``FactionInvasionCampMapObjectVO.cooldownCanBeSkipped``, bundle line 76359).
        A treasure node can be skipped although ``TreasureDungeonMapObjectVO.cooldownCanBeSkipped`` is
        false (bundle line 22037): that flag gates only the attack button, and the season map's
        ``SeaQueenDungeonSeasonMapScreenItem`` and ``SeaQueenVillageSeasonMapScreenItem.onClickMapItem``
        (bundle lines 108860, 108883) open the skip dialog for a node on cooldown, at position -1, -1.
        Client: SkippableCooldownDialog.skipWithRubies (bundle lines 28239–28241),
        C2SSkipDungeonCooldownVO (bundle line 46116), SDCCommand (bundle line 122367).
        """
        self._check_dungeon_node(map_id, node_id)
        self._require_spend_rubies(spend_rubies, "a full dungeon cooldown skip may cost rubies")
        response = self.request(
            SkipDungeonCooldownRequest(x=x, y=y, kingdom_id=kingdom_id, map_id=map_id, node_id=node_id),
            SkipDungeonCooldownResponse,
            timeout=timeout,
        )
        return self._dungeon_skip_result(response, kingdom_id)

    @staticmethod
    def _check_dungeon_node(map_id: int, node_id: TreasureMapNodeId) -> None:
        if (map_id, node_id) != (-1, -1) and (map_id < 0 or node_id < 0):
            raise ValueError("map_id and node_id must both name a treasure node, or both be -1")

    @staticmethod
    def _dungeon_skip_result(
        response: MinuteSkipDungeonResponse | SkipDungeonCooldownResponse, kingdom: Kingdom
    ) -> MapAreaItem:
        if response.area is None or response.area.attack_cooldown_seconds is None:
            raise PacketError(f"The '{response.command}' reply has no readable dungeon cooldown")
        coordinates = _row_coordinates(response.area)
        if coordinates is None:
            raise PacketError(f"The '{response.command}' dungeon row has no readable coordinates")
        realm = _row_kingdom(response.area, kingdom)
        if realm is None:
            raise PacketError(f"The '{response.command}' dungeon row has no readable kingdom")
        return response.area.model_copy(deep=True, update={"kingdom": Kingdom(realm)})

    # =========================================================================
    # Taunts
    # =========================================================================

    def taunt_nomad_khan(self, *, share_with_alliance: bool = False, timeout: float = 5.0) -> None:
        """
        Taunt the khan of the running alliance nomad invasion into attacking you.

        Args:
            share_with_alliance: Show the attack to your alliance
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleNomadInvasionTauntDialog.tauntKhan`` (bundle line 55677); ``LTACommand`` (bundle line 128204)
        """
        request = LaunchTauntAttackRequest(share_with_alliance=int(share_with_alliance))
        self.execute(request, timeout=timeout)

    def taunt_wolf_king(self, *, timeout: float = 5.0) -> None:
        """
        Taunt the wolf king into attacking you.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``ButtonTauntComponent.onClick`` (bundle line 110098); ``LWTACommand`` (bundle line 124329)
        """
        self.execute(LaunchWolfKingTauntRequest(), timeout=timeout)

    # =========================================================================
    # Alien camps
    # =========================================================================

    @property
    def alien_reroll_counts(self) -> AlienRerollCountsResponse | None:
        """How often you rerolled alien camps, which sets the next reroll's price; None until the server sent it."""
        return self.client.state.get_alien_reroll_counts()

    def reroll_alien_camp(
        self,
        x: int,
        y: int,
        *,
        currency: Currency | CollectableKind = CollectableKind.RUBIES,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Replace an alien invasion camp on the map with another.

        Args:
            x: Map x of the camp
            y: Map y of the camp
            currency: What pays: ``CollectableKind.RUBIES``, or one of a running alien invasion's
                ``reroll_currency_keys`` (``CollectableKind.COINS`` for ``"C1"``, else the ``Currency``)
            spend_rubies: Allow paying with rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: Rubies pay and ``spend_rubies`` is False, or no running alien invasion
                takes ``currency``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleRerollAlienDialog.onSendReroll`` (bundle line 109749) with ``"C2"`` or one of the
        event's ``rerollCurrencyKeys`` (bundle line 109770); ``RAECommand`` (bundle line 127100)
        """
        key = currency.server_key if isinstance(currency, CollectableKind) else currency.value
        if key == CollectableKind.RUBIES.server_key:
            self._require_spend_rubies(spend_rubies, "an alien camp reroll paid with rubies costs rubies")
        else:
            offered = {
                offered_key
                for event in self.client.state.get_events().values()
                if isinstance(event, AlienInvasionEvent)
                for offered_key in event.reroll_currency_keys
            }
            if key not in offered:
                raise ValueError(f"No running alien invasion rerolls camps for {key!r}")
        self.execute(RerollAlienCampRequest(currency_key=key, x=x, y=y), timeout=timeout)

    on_alien_camps_hidden = callbacks.Event[HiddenAlienCampsResponse]()
    """Call ``callback`` with each ``hac`` push: the alien camps the server took off your map.

    Removing a callback not registered is a no-op.
    """

    def _handle_hidden_alien_camps(self, response: BaseResponse) -> None:
        if isinstance(response, HiddenAlienCampsResponse):
            self._fire(self.on_alien_camps_hidden, response)
