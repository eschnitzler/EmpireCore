"""
The titles you hold, worked out from your points and ranks as the client does.

Client: ``CastleTitleData`` (bundle lines 21000-21130)
"""

from __future__ import annotations

from empire_core.enums import TitleSystem
from empire_core.gamedata import GameData

from .models.progress import FactionPointsResponse, GloryPointsResponse, TitleRanksResponse


def titles_in_order(game_data: GameData, system: TitleSystem) -> list[int]:
    """
    A title system's title ids, from its first title along each title's next one.

    Client: ``CastleTitleData.setupNextTitles`` (bundle line 21016) and ``orderTitlesInSystem``
    (bundle line 21058)
    """
    rows = [row for row in game_data.titles.values() if row.title_system == system.value]
    next_ids = {row.previous_title_id: row.title_id for row in game_data.titles.values() if row.previous_title_id != -1}
    first: int | None = None
    for row in rows:
        if row.previous_title_id < 0:
            first = row.title_id
    ordered: list[int] = []
    title_id = first
    while title_id is not None and title_id in game_data.titles and len(ordered) <= len(rows):
        ordered.append(title_id)
        title_id = next_ids.get(title_id)
    return ordered


def held_titles(game_data: GameData, system: TitleSystem, points: float | None, top_rank: int | None) -> list[int]:
    """
    The glory or Berimond titles you hold, lowest first.

    Each title in order is held while its points threshold is reached, or for a top-X
    title while your rank is above 0 and within its top X; the first one missed ends the list.

    Args:
        game_data: Loaded tables
        system: :attr:`TitleSystem.GLORY` or :attr:`TitleSystem.FACTION`
        points: Your glory points (``ufa`` ``CF``) or Berimond points (``ufp`` ``CFP``); None before they arrived
        top_rank: The system's ``uar`` top rank (``CTXT``); None before it arrived

    Client: ``CastleTitleData.setupThisUsersTitlesinSystem`` (bundle line 21048), with ``TitleVO.isTopXTitle``
    """
    held: list[int] = []
    for title_id in titles_in_order(game_data, system):
        row = game_data.titles[title_id]
        if row.top_x > 0:
            reached = top_rank is not None and top_rank > 0 and row.top_x >= top_rank
        else:
            reached = points is not None and row.threshold <= points
        if not reached:
            break
        held.append(title_id)
    return held


def island_title_chain(game_data: GameData, island_title_id: int) -> list[int]:
    """
    The island titles you hold with one: it and every title below it, lowest first.

    Args:
        game_data: Loaded tables
        island_title_id: Your current Storm Islands title, -1 or an unknown id for none

    Client: ``CastleTitleData.getUsersTitleVectorFromSystem`` for ``ISLAND_TITLE`` (bundle line 21119)
    """
    chain: list[int] = []
    title_id: int | None = island_title_id
    while title_id is not None and title_id in game_data.titles and title_id not in chain:
        chain.insert(0, title_id)
        title_id = game_data.titles[title_id].previous_title_id
    return chain


def player_title_ids(
    game_data: GameData,
    glory: GloryPointsResponse | None,
    faction: FactionPointsResponse | None,
    ranks: TitleRanksResponse | None,
) -> list[int]:
    """
    Every title you hold, as the client lists them: glory, then Berimond, then Storm Islands.

    Args:
        game_data: Loaded tables
        glory: ``client.state.get_glory_points()``
        faction: ``client.state.get_faction_points()``
        ranks: ``client.state.get_title_ranks()``

    Client: ``CastleTitleData.thisUsersTitles`` (bundle line 21073)
    """
    glory_points = glory.glory_points if glory is not None else None
    faction_points = faction.faction_points if faction is not None else None
    return [
        *held_titles(game_data, TitleSystem.GLORY, glory_points, ranks.glory.top_rank if ranks else None),
        *held_titles(game_data, TitleSystem.FACTION, faction_points, ranks.faction.top_rank if ranks else None),
        *island_title_chain(game_data, ranks.island_title.held_title_id if ranks else -1),
    ]


__all__ = ["held_titles", "island_title_chain", "player_title_ids", "titles_in_order"]
