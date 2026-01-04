"""
Troop metadata fetcher - gets valid troop IDs from GGE CDN.

Units with slotTypes are equipment, not troops.
This filters to get only actual combat units.
"""

import logging
from typing import Optional, Set

import requests

logger = logging.getLogger(__name__)

# Cached troop IDs
_troop_ids: Optional[Set[int]] = None


def get_items_version() -> str:
    """Fetch the current items version from GGE CDN."""
    url = "https://empire-html5.goodgamestudios.com/default/items/ItemsVersion.properties"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text.split("=")[-1].strip()


def fetch_items_data(version: str) -> dict:
    """Fetch items data for a specific version."""
    url = f"https://empire-html5.goodgamestudios.com/default/items/items_v{version}.json"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def get_troop_ids(force_refresh: bool = False) -> Set[int]:
    """
    Get the set of valid troop unit IDs.

    Troops are units without slotTypes (equipment has slotTypes).

    Args:
        force_refresh: Force re-fetch from CDN

    Returns:
        Set of wodID values for valid troops
    """
    global _troop_ids

    if _troop_ids is not None and not force_refresh:
        return _troop_ids

    try:
        version = get_items_version()
        items_data = fetch_items_data(version)

        units = items_data.get("units", [])
        # Filter units without slotTypes (those are actual troops)
        troop_ids = set()
        for unit in units:
            if not unit.get("slotTypes"):
                wod_id = unit.get("wodID")
                if wod_id:
                    troop_ids.add(wod_id)

        _troop_ids = troop_ids
        logger.info(f"Loaded {len(troop_ids)} troop IDs from GGE CDN (v{version})")
        return troop_ids

    except Exception as e:
        logger.error(f"Failed to fetch troop metadata: {e}")
        # Return empty set on failure - will count all units
        return set()


def count_troops(units: dict[int, int], troop_ids: Optional[Set[int]] = None) -> int:
    """
    Count only actual troops in a unit dict, excluding equipment.

    Args:
        units: Dict of {unit_id: count}
        troop_ids: Optional set of valid troop IDs (fetched if not provided)

    Returns:
        Total count of actual troops
    """
    if troop_ids is None:
        troop_ids = get_troop_ids()

    # If we couldn't get troop IDs, count everything
    if not troop_ids:
        return sum(units.values())

    return sum(count for uid, count in units.items() if uid in troop_ids)
