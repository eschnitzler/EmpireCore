"""Treasure maps (tmp) and the treasure hunt's current map (thi)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from empire_core.events.models import SeasonEvent, SpecialEvent
from empire_core.map.models.treasure_maps import TreasureMap, TreasureMapsResponse
from empire_core.state.base import StateBase
from empire_core.state.login_data import LoginDataResponse

if TYPE_CHECKING:
    from empire_core.gamedata import TreasureMapId

TREASURE_MAP_SECTIONS = ("tmp", "thi")


class TreasureMapState(StateBase):
    def _parse_treasure_maps(self, login: LoginDataResponse) -> set[str]:
        """Apply the ``tmp`` and ``thi`` of a gbd, or the one a push or reply carries; return those not applied.

        Client: ``GBDCommand.exec`` (bundle line 129425) calls ``parse_TMP`` and then ``parse_THI``,
        each of which skips a falsy block
        """
        applied: set[str] = set()
        if login.treasure_maps is not None:
            self._apply_treasure_maps(login.treasure_maps)
            applied.add("tmp")
        if login.treasure_hunt is not None:
            self.treasure_hunt_map_id = login.treasure_hunt.map_id
            applied.add("thi")
        return (login.sent_sections & set(TREASURE_MAP_SECTIONS)) - applied

    def _apply_treasure_maps(self, update: TreasureMapsResponse) -> None:
        """Read a ``tmp``: the maps it sends over those known, or in their place when it is a full list.

        A node the new row leaves out keeps what was known of it; one sent again keeps the goods paid
        towards it when the row sends none, and stays defeated once it fell.

        Client: ``CastleTreasureMapData.parse_TMP`` (bundle line 140451) starts over when it holds no
        maps yet or ``UA`` is 1, then loads each ``TM`` row into the map with its id
        (``TreasureMapVO.loadFromParamObject``, bundle line 140557); ``TMapNodeVO.parseParamObject``
        (bundle line 26940) sets the paid goods only from a truthy ``G``, and ``fillAchivedNodes``
        (bundle line 140577) only ever sets ``isDefeated``
        """
        maps = {} if self.treasure_maps is None or update.is_full_list else dict(self.treasure_maps)
        for sent in update.maps:
            known = maps.get(sent.map_id)
            maps[sent.map_id] = sent if known is None else _merged_map(known, sent)
        self.treasure_maps = maps

    def _forget_treasure_map_of(self, event: SpecialEvent) -> None:
        """Drop the treasure map of a season event that ended.

        Client: ``CastleTreasureMapData.onSpecialEventRemoved`` (bundle line 140426)
        """
        if isinstance(event, SeasonEvent) and self.treasure_maps and event.map_id in self.treasure_maps:
            self.treasure_maps = {key: value for key, value in self.treasure_maps.items() if key != event.map_id}

    def get_treasure_maps(self) -> dict[TreasureMapId | int, TreasureMap] | None:
        """Your treasure maps by map id, from every ``tmp`` so far; None until one arrived. A copy."""
        with self._lock:
            return None if self.treasure_maps is None else dict(self.treasure_maps)

    def get_treasure_hunt_map_id(self) -> TreasureMapId | int | None:
        """The treasure hunt's current map, -1 once no map is left, from the last ``thi``; None until one arrived."""
        with self._lock:
            return self.treasure_hunt_map_id


def _merged_map(known: TreasureMap, sent: TreasureMap) -> TreasureMap:
    nodes = {node.node_id: node for node in known.nodes}
    for node in sent.nodes:
        before = nodes.get(node.node_id)
        if before is not None:
            kept: dict[str, Any] = {}
            if "paid_goods" not in node.model_fields_set:
                kept["paid_goods"] = before.paid_goods
            if before.defeated:
                kept["defeated"] = True
            node = node.model_copy(update=kept) if kept else node
        nodes[node.node_id] = node
    return sent.model_copy(update={"nodes": tuple(nodes.values())})
