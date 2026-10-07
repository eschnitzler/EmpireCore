"""Map area items: the rows of a map area, one per map object, read by their area type's client parser."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import Field, model_validator

from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.base import BasePayload, enum_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals, js_truthy

from .owners import AllianceCrest


class AbgCastleConnection(BasePayload):
    """
    An alliance battle ground castle's line to its tower: a castle row's ``[x, y, is_attackable, tower_points]``.

    The client reads it only on a battle ground server that scores towers.

    Client: ``CastleMapobjectVO.parseAreaInfo`` (bundle lines 18911-18912), ``ABGHelper.isOnABGAndTower``
    (bundle line 2037)
    """

    x: ClientInt = Field(default=0, description="Map x of the other end")
    y: ClientInt = Field(default=0, description="Map y of the other end")
    is_attackable: bool = Field(default=False, description="The castle can be attacked for tower points")
    tower_points: ClientInt = Field(default=0, description="The player's tower points")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        row = dict(zip(("x", "y", "is_attackable", "tower_points"), data, strict=False))
        if "is_attackable" in row:
            row["is_attackable"] = js_truthy(row["is_attackable"])
        return row


class AbgTowerConnection(BasePayload):
    """
    One of an alliance battle ground tower's connections: ``[x, y, player_name, status]``.

    ``is_defeated`` is status 1: the client sums the statuses into ``_defeatedConnections`` and draws
    status 1 in red.

    Client: ``ABGAllianceTowerMapobjectVO.parseConnections`` (bundle lines 32285-32291),
    ``ABGTowerConnectionVO.fillFromConnectionValues`` (bundle line 25482)
    """

    x: ClientInt = Field(default=0, description="Map x of the connected castle")
    y: ClientInt = Field(default=0, description="Map y of the connected castle")
    player_name: str | None = Field(default=None, description="The connected castle's player; None when not sent")
    is_defeated: bool = Field(default=False, description="The connection is defeated")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        row = dict(zip(("x", "y", "player_name", "is_defeated"), data, strict=False))
        if "is_defeated" in row:
            row["is_defeated"] = js_int(row["is_defeated"]) == 1
        if not isinstance(row.get("player_name"), str):
            row["player_name"] = None
        return row


class _Row:
    """A map row with the reads the client's parsers make: as sent, through ``int()``, or ``1 == value``."""

    def __init__(self, data: list[Any]) -> None:
        self.data = data

    def __len__(self) -> int:
        return len(self.data)

    def raw(self, index: int) -> Any:
        return self.data[index] if len(self.data) > index else None

    def as_int(self, index: int) -> int:
        # int(undefined) is 0
        return js_int(self.raw(index))

    def one(self, index: int) -> bool:
        return js_loose_equals(self.raw(index), 1)


def _sabotage_protection(row: _Row) -> bool:
    return js_int(row.raw(19) if len(row) > 19 else 0) == 1


def _interactive(row: _Row) -> dict[str, Any]:
    """``InteractiveMapobjectVO.parseAreaInfo`` (bundle line 3631): castles, outposts and faction camps."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.as_int(4),
        "keep_level": max(row.as_int(5), 1),
        "wall_level": max(row.as_int(6), 1),
        "gate_level": max(row.as_int(7), 1),
        "tower_level": row.as_int(8),
        "moat_level": row.as_int(9),
        "name": row.raw(10),
        "attack_cooldown_seconds": row.as_int(11),
        "sabotage_cooldown_seconds": row.as_int(12),
        "seconds_since_espionage": row.as_int(13),
        "outpost_type": row.as_int(14),
        "occupier_id": row.as_int(15),
        "row_kingdom": row.raw(16),
        "skin_id": row.as_int(17),
        "has_sabotage_protection": _sabotage_protection(row),
    }


def _castle(row: _Row) -> dict[str, Any]:
    """``CastleMapobjectVO.parseAreaInfo`` (bundle line 18910), which ``KingdomCastleMapobjectVO`` inherits."""
    if len(row) <= 4:
        # A free plot, or a castle on the move when the occupier is a player
        return {"is_plot_row": True, "occupier_id": row.raw(3)}
    fields = _interactive(row)
    connection = row.raw(18)
    if isinstance(connection, list) and connection:
        fields["abg_tower_connection"] = AbgCastleConnection.model_validate(connection)
    return fields


def _faction_camp(row: _Row) -> dict[str, Any]:
    """``FactionCampMapobjectVO.parseAreaInfo`` (bundle line 21526); a row of three fields is not on the map."""
    if len(row) <= 3:
        return {}
    return {**_interactive(row), "is_destroyed": js_loose_equals(row.data[-1], 1)}


def _capital(row: _Row) -> dict[str, Any]:
    """``CapitalMapobjectVO.parseAreaInfo`` (bundle line 18729); levels, spy age, occupier and skin as sent."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.as_int(4),
        "keep_level": row.raw(5),
        "wall_level": row.raw(6),
        "gate_level": row.raw(7),
        "tower_level": row.raw(8),
        "moat_level": row.raw(9),
        "name": row.raw(10),
        "attack_cooldown_seconds": row.as_int(11),
        "sabotage_cooldown_seconds": row.as_int(12),
        "seconds_since_espionage": row.raw(13),
        "occupier_id": row.raw(14),
        "skin_id": row.raw(15),
        "row_kingdom": row.raw(16),
        "has_sabotage_protection": _sabotage_protection(row),
    }


def _metropol(row: _Row) -> dict[str, Any]:
    """``MetropolMapobjectVO.parseAreaInfo`` (bundle line 21609): a capital's row, plus its ABG mine."""
    fields = _capital(row)
    if len(row) > 17:
        fields.update(abg_mine_out_seconds=row.as_int(17), abg_max_influence_points=row.as_int(18))
    return fields


def _village(row: _Row) -> dict[str, Any]:
    """``VillageMapobjectVO.parseAreaInfo`` (bundle line 22623)."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.as_int(4),
        "village_type": row.as_int(5),
        "row_kingdom": row.raw(6),
        "seconds_since_espionage": row.raw(7),
        "name": row.raw(8),
    }


def _resource_isle(row: _Row) -> dict[str, Any]:
    """``ResourceIsleMapobjectVO.parseAreaInfo`` (bundle line 34603)."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.raw(4),
        "row_kingdom": row.raw(5),
        "name": row.raw(6),
        "seconds_since_espionage": row.raw(7),
        "isle_id": row.as_int(8),
        "remaining_occupier_seconds": row.raw(9),
    }


def _kings_tower(row: _Row) -> dict[str, Any]:
    """``KingstowerMapobjectVO.parseAreaInfo`` (bundle line 19055)."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.as_int(4),
        "row_kingdom": row.raw(5),
        "seconds_since_espionage": row.raw(6),
        "name": row.raw(7),
    }


def _monument(row: _Row) -> dict[str, Any]:
    """``MonumentMapobjectVO.parseAreaInfo`` (bundle line 21652)."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.raw(4),
        "monument_type": row.as_int(5),
        "landmark_level": row.raw(6),
        "row_kingdom": row.raw(7),
        "seconds_since_espionage": row.raw(8),
        "name": row.raw(9),
    }


def _laboratory(row: _Row) -> dict[str, Any]:
    """``LaboratoryMapobjectVO.parseAreaInfo`` (bundle line 25900)."""
    return {
        "location_id": row.raw(3),
        "owner_id": row.raw(4),
        "landmark_level": row.raw(5),
        "row_kingdom": row.raw(6),
        "seconds_since_espionage": row.raw(7),
        "name": row.raw(8),
    }


def _faction_village(row: _Row) -> dict[str, Any]:
    """``FactionVillageMapobjectVO.parseAreaInfo`` (bundle line 28486)."""
    protectors = row.raw(4)
    return {
        "owner_id": row.raw(3),
        "protector_positions": protectors if isinstance(protectors, list) else [],
        "seconds_since_espionage": row.raw(5),
        "dungeon_level": row.as_int(6),
        "attack_cooldown_seconds": row.as_int(7),
    }


def _faction_tower(row: _Row) -> dict[str, Any]:
    """``FactionTowerMapobjectVO.parseAreaInfo`` (bundle line 22810)."""
    return {
        "owner_id": row.raw(3),
        "is_destroyed": row.one(4),
        "protector_positions": row.raw(5),
        "seconds_since_espionage": row.raw(6),
        "dungeon_level": row.as_int(7),
        "attacks_left": row.as_int(8),
        "special_camp_id": row.raw(9),
    }


def _faction_capital(row: _Row) -> dict[str, Any]:
    """``FactionCapitalMapobjectVO.parseAreaInfo`` (bundle line 22764)."""
    return {
        "owner_id": row.raw(3),
        "protector_positions": row.raw(4),
        "seconds_since_espionage": row.raw(5),
        "dungeon_level": row.as_int(6),
        "is_destroyed": row.one(7),
        "special_camp_id": row.raw(8),
    }


def _dungeon(row: _Row) -> dict[str, Any]:
    """``DungeonMapobjectVO.parseAreaInfo`` (bundle line 22057), which ``TreasureDungeonMapObjectVO`` inherits."""
    return {
        "seconds_since_espionage": row.raw(3),
        "victory_count": row.as_int(4),
        "attack_cooldown_seconds": row.raw(5),
        "row_kingdom": row.raw(6),
    }


def _boss_dungeon(row: _Row) -> dict[str, Any]:
    """``BossdungeonMapobjectVO.parseAreaInfo`` (bundle line 34441)."""
    return {
        "seconds_since_espionage": row.raw(3),
        "dungeon_level": row.as_int(4),
        "attack_cooldown_seconds": row.raw(5),
        "defeater_player_id": row.as_int(6),
        "row_kingdom": row.raw(7),
    }


def _event_dungeon(row: _Row) -> dict[str, Any]:
    """``EventdungeonMapobjectVO.parseAreaInfo`` (bundle line 34488); a row of three fields is not on the map."""
    if len(row) <= 3:
        return {}
    return {"seconds_since_espionage": row.raw(3), "dungeon_level": row.as_int(4), "is_defeated": row.one(5)}


def _wolf_king(row: _Row) -> dict[str, Any]:
    """``WolfkingCastleMapObjectVO.parseAreaInfo`` (bundle line 34409); a row of three fields is not on the map."""
    if len(row) <= 3:
        return {}
    return {
        **_event_dungeon(row),
        "base_wall_bonus": row.raw(6),
        "base_gate_bonus": row.raw(7),
        "base_moat_bonus": row.raw(8),
    }


def _treasure_camp(row: _Row) -> dict[str, Any]:
    """``EventCampMapobjectVO.parseAreaInfo`` (bundle line 26867): field 1 is the treasure map, 22 when unset."""
    return {"map_id": row.raw(1) if js_truthy(row.raw(1)) else 22}


def _attack_area(row: _Row) -> dict[str, Any]:
    """``ShadowareaMapobjectVO`` (bundle line 76548) and ``PlagueareaMapobjectVO`` (bundle line 46016)."""
    return {"attack_cooldown_seconds": row.raw(3), "seconds_since_espionage": row.raw(4)}


def _alien_camp(row: _Row) -> dict[str, Any]:
    """``AAlienInvasionMapobjectVO.parseAreaInfo`` (bundle line 41543); the rest follows only past field 4."""
    fields: dict[str, Any] = {"dungeon_level": row.raw(3)}
    if len(row) > 4:
        fields.update(
            seconds_since_espionage=row.raw(4),
            has_peace_mode=row.one(5),
            base_wall_bonus=row.raw(6),
            base_gate_bonus=row.raw(7),
            base_moat_bonus=row.raw(8),
            already_rerolled=len(row) >= 10 and row.one(9),
            scaling_camp_id=row.raw(10) if len(row) >= 11 else -1,
        )
    return fields


def _isle_dungeon(row: _Row) -> dict[str, Any]:
    """``DungeonIsleMapobjectVO.parseAreaInfo`` (bundle line 76288)."""
    return {
        "row_kingdom": row.raw(3),
        "seconds_since_espionage": row.raw(4),
        "isle_id": row.as_int(5),
        "attack_cooldown_seconds": row.as_int(6),
        "victory_count": row.raw(7),
    }


def _invasion_camp(row: _Row) -> dict[str, Any]:
    """``SamuraiCampMapObjectVO`` (bundle line 76493) and ``NomadCampMapObjectVO`` (bundle line 76379)."""
    if len(row) <= 3:
        return {}
    return {
        "seconds_since_espionage": row.raw(3),
        "victory_count": row.raw(4),
        "attack_cooldown_seconds": row.raw(5),
        "scaling_camp_id": row.raw(8),
        "base_wall_bonus": row.raw(9),
        "base_gate_bonus": row.raw(10),
        "base_moat_bonus": row.raw(11),
    }


def _faction_invasion_camp(row: _Row) -> dict[str, Any]:
    """``FactionInvasionCampMapObjectVO.parseAreaInfo`` (bundle line 76324)."""
    if len(row) <= 3:
        return {}
    return {
        "seconds_since_espionage": row.raw(3),
        "victory_count": row.raw(4),
        "attack_cooldown_seconds": row.raw(5),
        "dungeon_type": row.as_int(7),
    }


def _daimyo(row: _Row) -> dict[str, Any]:
    """``DaimyoCastleMapObjectVO`` (bundle line 19651) and ``DaimyoTownshipMapObjectVO`` (bundle line 21736)."""
    if len(row) <= 3:
        return {}
    return {
        "seconds_since_espionage": row.raw(3),
        "camp_id": row.raw(4),
        "attack_cooldown_seconds": row.raw(5),
        "total_cooldown_seconds": row.as_int(6),
        "skip_cost": row.as_int(7),
        "scaling_camp_id": row.as_int(8),
        "base_wall_bonus": row.raw(9),
        "base_gate_bonus": row.raw(10),
        "base_moat_bonus": row.raw(11),
    }


def _alliance_camp(row: _Row) -> dict[str, Any]:
    """``AAllianceInvasionCampMapObjectVO.parseData`` (bundle line 47392): nomad khan camps, ABG resource towers."""
    if len(row) <= 3:
        return {}
    return {
        "seconds_since_espionage": row.raw(3),
        "camp_id": row.as_int(4),
        "attack_cooldown_seconds": row.raw(5),
        "total_cooldown_seconds": row.as_int(6),
        "skip_cost": row.as_int(7),
        "victory_count": row.raw(8),
        "scaling_camp_id": row.as_int(9),
        "base_wall_bonus": row.raw(10),
        "base_gate_bonus": row.raw(11),
        "base_moat_bonus": row.raw(12),
    }


def _abg_tower(row: _Row) -> dict[str, Any]:
    """``ABGAllianceTowerMapobjectVO.parseAreaInfo`` (bundle line 32279); an alliance, not a player, holds it."""
    crest = row.raw(9)
    return {
        "location_id": row.raw(3),
        "name": row.raw(4),
        "is_attackable": js_truthy(row.raw(5)),
        "victory_count": row.as_int(6),
        "alliance_id": row.as_int(7),
        "alliance_name": row.raw(8),
        "alliance_crest": {"ACLI": crest[0], "ACCS": crest[1]} if isinstance(crest, list) and len(crest) > 1 else None,
        "abg_connections": tuple(readable_list(AbgTowerConnection, row.raw(10), accept=lambda e: isinstance(e, list))),
    }


def _position_only(row: _Row) -> dict[str, Any]:
    """
    ``DummyMapobjectVO`` (bundle line 43578), ``PlaceholderMapobjectVO`` (bundle line 76458) and
    ``AllianceRaidEventPortalMapobjectVO`` (bundle line 41600) read only the position.
    """
    return {}


# The area types WorldmapObjectFactory.mapObjectVOs (bundle line 5357) registers a map object for,
# each with its parser. The factory returns null for any other type, so the client reads no such row.
ROW_PARSERS: dict[MapItemType, Callable[[_Row], dict[str, Any]]] = {
    MapItemType.EMPTY: _position_only,
    MapItemType.CASTLE: _castle,
    MapItemType.DUNGEON: _dungeon,
    MapItemType.CAPITAL: _capital,
    MapItemType.OUTPOST: _interactive,
    MapItemType.TREASURE_DUNGEON: _dungeon,
    MapItemType.TREASURE_CAMP: _treasure_camp,
    MapItemType.SHADOW_AREA: _attack_area,
    MapItemType.VILLAGE: _village,
    MapItemType.BOSS_DUNGEON: _boss_dungeon,
    MapItemType.KINGDOM_CASTLE: _castle,
    MapItemType.EVENT_DUNGEON: _event_dungeon,
    MapItemType.FACTION_CAMP: _faction_camp,
    MapItemType.FACTION_VILLAGE: _faction_village,
    MapItemType.FACTION_TOWER: _faction_tower,
    MapItemType.FACTION_CAPITAL: _faction_capital,
    MapItemType.PLAGUE_AREA: _attack_area,
    MapItemType.ALIEN_CAMP: _alien_camp,
    MapItemType.METROPOL: _metropol,
    MapItemType.KINGS_TOWER: _kings_tower,
    MapItemType.ISLE_RESOURCE: _resource_isle,
    MapItemType.ISLE_DUNGEON: _isle_dungeon,
    MapItemType.MONUMENT: _monument,
    MapItemType.NOMAD_CAMP: _invasion_camp,
    MapItemType.LABORATORY: _laboratory,
    MapItemType.SAMURAI_CAMP: _invasion_camp,
    MapItemType.FACTION_INVASION_CAMP: _faction_invasion_camp,
    MapItemType.DYNAMIC: _position_only,
    MapItemType.RED_ALIEN_CAMP: _alien_camp,
    MapItemType.ALLIANCE_NOMAD_CAMP: _alliance_camp,
    MapItemType.DAIMYO_CASTLE: _daimyo,
    MapItemType.DAIMYO_TOWNSHIP: _daimyo,
    MapItemType.ALLIANCE_BATTLE_GROUND_RESOURCE_TOWER: _alliance_camp,
    MapItemType.ALLIANCE_BATTLE_GROUND_TOWER: _abg_tower,
    MapItemType.WOLF_KING: _wolf_king,
    MapItemType.ARE_PORTAL: _position_only,
}


INVASION_AREA_TYPES = frozenset(
    {
        MapItemType.SAMURAI_CAMP,
        MapItemType.NOMAD_CAMP,
        MapItemType.DAIMYO_CASTLE,
        MapItemType.DAIMYO_TOWNSHIP,
    }
)
"""Invasion event camps: their row gives the camp's own wall, gate and moat protection."""


class MapAreaItem(BasePayload):
    """
    One map row, read field by field as its area type's client parser reads it.

    Every row starts ``[area_type, x, y]``; what follows depends on the type
    (see ``ROW_PARSERS``). A field the type's row does not carry is None. The
    client reads some values through ``int()`` and stores the rest as sent;
    so does this model, so a value of the wrong kind where the client stores
    it as sent makes the row unreadable.

    Client: ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343);
    ``CastleWorldmapData.parseAreaInfos`` (bundle line 18993) places each row
    at ``int(row[1])``, ``int(row[2])``.
    """

    item_type: MapItemType = Field(description="The row's area type")
    x: int = Field(default=0, description="Map x")
    y: int = Field(default=0, description="Map y")
    kingdom: Kingdom = Field(
        default=Kingdom.GREEN,
        description="The kingdom the row names, else the kingdom of the reply it came in",
    )
    is_plot_row: bool = Field(
        default=False,
        description="A castle row of four fields or fewer: a free plot, or a castle on the move",
    )
    location_id: int | None = Field(default=None, description="The map object's id; negative for an unclaimed plot")
    owner_id: int | None = Field(
        default=None,
        description="Player id of the owner the row names; negative for an NPC owner such as an unclaimed outpost",
    )
    name: str | None = Field(default=None, description="The object's name")
    keep_level: int | None = Field(default=None, description="Keep level")
    wall_level: int | None = Field(default=None, description="Wall level")
    gate_level: int | None = Field(default=None, description="Gate level")
    tower_level: int | None = Field(default=None, description="Tower level")
    moat_level: int | None = Field(default=None, description="Moat level")
    attack_cooldown_seconds: int | None = Field(
        default=None, description="Seconds until it can be attacked again; negative once that has passed"
    )
    sabotage_cooldown_seconds: int | None = Field(default=None, description="Seconds until it can be sabotaged again")
    seconds_since_espionage: int | None = Field(
        default=None, description="Seconds since it was last spied; negative when it never was"
    )
    outpost_type: int | None = Field(default=None, description="Outpost type")
    occupier_id: int | None = Field(
        default=None,
        description="Player id of the occupier, -1 for none; on a four-field castle row, the player relocating there",
    )
    skin_id: int | None = Field(default=None, description="Unique id of the castle skin equipment it shows")
    has_sabotage_protection: bool | None = Field(default=None, description="Temporary sabotage protection is on")
    abg_tower_connection: AbgCastleConnection | None = Field(
        default=None, description="On an alliance battle ground: the castle's tower connection"
    )
    abg_mine_out_seconds: int | None = Field(
        default=None, description="Alliance battle ground: seconds until the metropolis is mined out"
    )
    abg_max_influence_points: int | None = Field(
        default=None, description="Alliance battle ground: the metropolis's most influence points"
    )
    is_destroyed: bool | None = Field(default=None, description="The faction object is destroyed")
    village_type: int | None = Field(default=None, description="Village type")
    monument_type: int | None = Field(default=None, description="Monument type")
    landmark_level: int | None = Field(default=None, description="A monument's or laboratory's level")
    isle_id: int | None = Field(default=None, description="Isle blueprint id")
    remaining_occupier_seconds: int | None = Field(default=None, description="Seconds left on the occupier's timer")
    protector_positions: list[Any] | None = Field(
        default=None, description="Positions of the faction object's protectors still standing"
    )
    dungeon_level: int | None = Field(default=None, description="The camp's level as its row gives it")
    attacks_left: int | None = Field(default=None, description="Attacks the faction tower has left")
    special_camp_id: int | None = Field(default=None, description="The faction event camp id")
    victory_count: int | None = Field(default=None, description="How often the camp has been beaten")
    defeater_player_id: int | None = Field(default=None, description="Player id of whoever defeated the boss dungeon")
    is_defeated: bool | None = Field(default=None, description="The dungeon is defeated")
    map_id: int | None = Field(default=None, description="The treasure map a treasure camp leads to")
    has_peace_mode: bool | None = Field(default=None, description="The alien camp is in peace mode")
    already_rerolled: bool | None = Field(default=None, description="The alien camp was already rerolled")
    scaling_camp_id: int | None = Field(
        default=None, description="The difficulty-scaling camp that sets the camp's level; -1 or 0 when none"
    )
    dungeon_type: int | None = Field(default=None, description="The faction king whose invasion camp this is")
    camp_id: int | None = Field(
        default=None, description="The camp's row in its event's camp table (a daimyo rank, an alliance camp)"
    )
    total_cooldown_seconds: int | None = Field(default=None, description="The camp's full cooldown")
    skip_cost: int | None = Field(default=None, description="What skipping the cooldown costs")
    base_wall_bonus: float | None = Field(default=None, description="The camp's wall protection, as a percentage")
    base_gate_bonus: float | None = Field(default=None, description="The camp's gate protection, as a percentage")
    base_moat_bonus: float | None = Field(default=None, description="The camp's moat protection, as a percentage")
    is_attackable: bool | None = Field(default=None, description="The alliance tower can be attacked")
    alliance_id: int | None = Field(default=None, description="Id of the alliance holding the tower")
    alliance_name: str | None = Field(default=None, description="Name of the alliance holding the tower")
    alliance_crest: AllianceCrest | None = Field(default=None, description="Crest of the alliance holding the tower")
    abg_connections: tuple[AbgTowerConnection, ...] | None = Field(
        default=None, description="The alliance tower's connections to the castles around it"
    )
    raw_data: list[Any] = Field(default_factory=list, description="The whole row as sent")

    @classmethod
    def from_list(cls, data: Any, kingdom: Kingdom = Kingdom.GREEN) -> MapAreaItem:
        """
        Read a map row; ``kingdom`` is the kingdom of the reply it came in.

        Raises:
            ValueError: The row is not a list, is empty, or has an area type
                the client reads no row of; ``ValidationError`` is one, for a
                value of the wrong kind
        """
        return cls(**cls.row_values(data, kingdom))

    @staticmethod
    def row_values(data: Any, kingdom: Kingdom = Kingdom.GREEN) -> dict[str, Any]:
        """
        The values :meth:`from_list` builds a map row from, by field name, before they are validated.

        A caller that drops most rows can look at a row's values first and
        build only the rows it keeps.

        Raises:
            ValueError: The row is not a list, is empty, or has an area type
                the client reads no row of
        """
        if not isinstance(data, list) or not data:
            raise ValueError(f"Not a map row: {data!r}")
        area_type = enum_or_none(MapItemType, js_int(data[0]))
        parser = ROW_PARSERS.get(area_type) if area_type is not None else None
        if area_type is None or parser is None:
            raise ValueError(f"The client reads no map row of area type {data[0]!r}")
        row = _Row(data)
        fields = parser(row)
        row_kingdom = fields.pop("row_kingdom", None)
        named = (
            enum_or_none(Kingdom, row_kingdom)
            if isinstance(row_kingdom, int) and not isinstance(row_kingdom, bool)
            else None
        )
        return {
            "item_type": area_type,
            "x": row.as_int(1),
            "y": row.as_int(2),
            "kingdom": kingdom if named is None else named,
            "raw_data": data,
            **fields,
        }

    @property
    def is_occupied(self) -> bool:
        """Whether a player occupies it; the client's ``isOccupied`` is an occupier id above -1."""
        return self.occupier_id is not None and self.occupier_id > -1

    @property
    def is_relocating(self) -> bool:
        """
        Whether this is a castle on the move: a four-field castle row naming the relocating player.

        ``occupier_id`` is that player; the owner record's ``remaining_relocation_time``
        says when it arrives. ``[1, x, y, -1]`` is a free plot instead.

        Client: ``CastleMapobjectVO.parseAreaInfo`` (bundle line 18910) queues such a row
        as a relocation, and ``CastleWorldmapData.getExpiredRelocationObject`` (bundle
        line 19023) ends it once that player's relocation time runs out.
        """
        return self.is_plot_row and self.is_occupied

    @property
    def has_player_owner(self) -> bool:
        """Whether the row names a player as its owner, rather than an NPC or nobody."""
        return self.owner_id is not None and self.owner_id > 0

    @property
    def is_invasion_camp(self) -> bool:
        """Whether this row is an invasion event camp, whose row gives its own protection."""
        return self.item_type in INVASION_AREA_TYPES

    @property
    def is_castle(self) -> bool:
        """Whether this is a castle, capital, outpost, kingdom castle or metropolis."""
        return self.item_type in (
            MapItemType.CASTLE,
            MapItemType.CAPITAL,
            MapItemType.OUTPOST,
            MapItemType.KINGDOM_CASTLE,
            MapItemType.METROPOL,
        )


def parse_area_rows(value: Any, kingdom: Kingdom = Kingdom.GREEN) -> tuple[list[MapAreaItem], int]:
    """
    Map rows as :class:`MapAreaItem`, with how many rows could not be read.

    ``kingdom`` is the kingdom of the reply the rows came in. A row that is not
    a list, is empty, has an area type the client reads no row of, or has a
    value of the wrong kind is counted and skipped, so one bad row costs only
    itself. The client instead stops reading at an empty row.

    Client: ``CastleWorldmapData.parseAreaInfos`` (bundle line 18993) hands
    each row to ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343).
    """
    if not isinstance(value, list):
        return [], 0
    items: list[MapAreaItem] = []
    skipped = 0
    for row in value:
        if isinstance(row, MapAreaItem):
            items.append(row)
            continue
        try:
            items.append(MapAreaItem.from_list(row, kingdom))
        except ValueError:
            skipped += 1
    return items, skipped


__all__ = [
    "INVASION_AREA_TYPES",
    "ROW_PARSERS",
    "MapAreaItem",
    "parse_area_rows",
]
