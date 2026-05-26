"""
Active event resolver - maps live event IDs from the server to human-readable names.

Fetches static metadata from the GGS CDN (same pattern as troops.py) and cross-references
the event IDs returned by the server's `sei` packet to produce typed GameEvent objects.

Usage:
    # Get raw IDs from the live server connection
    event_ids = client.get_active_event_ids()

    # Resolve to named events (fetches CDN data, cached after first call)
    events = get_active_events(event_ids)

    # Branch on event type
    event_names = {e.internal_name for e in events}
    if "Nomad" in event_names:
        # run nomad tasks ...
        ...
"""

import logging
from dataclasses import dataclass
from typing import Any

import requests

from empire_core.utils.troops import fetch_items_data, get_items_version

logger = logging.getLogger(__name__)

# CDN endpoint for translations
_LANG_META_URL = "https://langserv.public.ggs-ep.com/12/fr/@metadata"
_LANG_DATA_URL = "https://langserv.public.ggs-ep.com/12@{version}/{lang}/*"

# Module-level caches
_cached_events_index: dict[int, dict[str, Any]] | None = None  # event_id -> raw event dict
_cached_translations: dict[str, str] | None = None


@dataclass
class GameEvent:
    """A resolved active game event with human-readable names."""

    id: int
    internal_name: str  # Internal type name, e.g. "Nomad", "AllianceBattleGround"
    display_name: str  # Localized in-game title, e.g. "Nomad Invasion"
    description: str  # Developer comment / short description


def _fetch_translations(lang: str = "en") -> dict[str, str]:
    """Fetch the active translation dictionary from the GGS language CDN."""
    meta_res = requests.get(_LANG_META_URL, timeout=10)
    meta_res.raise_for_status()
    version_no = meta_res.json()["@metadata"]["versionNo"]

    lang_url = _LANG_DATA_URL.format(version=version_no, lang=lang)
    lang_res = requests.get(lang_url, timeout=30)
    lang_res.raise_for_status()
    return lang_res.json()


def _build_events_index(force_refresh: bool = False) -> dict[int, dict[str, Any]]:
    """
    Build and cache an index of event_id -> raw event dict from the GGS CDN.

    Args:
        force_refresh: Bypass cache and re-fetch from CDN.

    Returns:
        Dict mapping event ID (int) to the raw event entry from items data.
    """
    global _cached_events_index

    if _cached_events_index is not None and not force_refresh:
        return _cached_events_index

    version = get_items_version()
    items_data = fetch_items_data(version)

    index: dict[int, dict[str, Any]] = {}
    for event in items_data.get("events", []):
        try:
            event_id = int(event["eventID"])
            index[event_id] = event
        except (KeyError, ValueError):
            continue

    _cached_events_index = index
    logger.info(f"Built events index with {len(index)} entries from GGS CDN (v{version})")
    return index


def _get_translations(lang: str = "en", force_refresh: bool = False) -> dict[str, str]:
    """
    Fetch and cache the GGS translation dictionary.

    Args:
        lang: Language code (default: "en").
        force_refresh: Bypass cache and re-fetch from CDN.

    Returns:
        Dict mapping translation keys to localized strings.
    """
    global _cached_translations

    if _cached_translations is not None and not force_refresh:
        return _cached_translations

    try:
        translations = _fetch_translations(lang=lang)
        _cached_translations = translations
        logger.info(f"Loaded {len(translations)} '{lang}' translations from GGS CDN")
        return translations
    except Exception as e:
        logger.warning(f"Failed to fetch translations, display names will fall back to internal names: {e}")
        return {}


def get_active_events(
    event_ids: list[int],
    lang: str = "en",
    force_refresh: bool = False,
) -> list[GameEvent]:
    """
    Resolve a list of active event IDs to typed GameEvent objects.

    Fetches event metadata and translations from the GGS CDN (results are
    cached after the first call). Pass the IDs from ``client.get_active_event_ids()``.

    Args:
        event_ids: List of active event IDs from the server's sei packet.
        lang: Language code for display names (default: "en").
        force_refresh: Force re-fetch of CDN data, bypassing the cache.

    Returns:
        List of GameEvent objects for the given IDs. IDs not found in the
        CDN data are silently skipped.

    Example:
        event_ids = client.get_active_event_ids()
        events = get_active_events(event_ids)

        event_names = {e.internal_name for e in events}
        if "Nomad" in event_names:
            # handle nomad event ...
            pass
    """
    if not event_ids:
        return []

    try:
        index = _build_events_index(force_refresh=force_refresh)
        translations = _get_translations(lang=lang, force_refresh=force_refresh)
    except Exception as e:
        logger.error(f"Failed to fetch event metadata from CDN: {e}")
        return []

    results: list[GameEvent] = []
    for eid in event_ids:
        raw = index.get(eid)
        if raw is None:
            logger.debug(f"Event ID {eid} not found in CDN data, skipping")
            continue

        internal_name = str(raw.get("eventType") or "Unknown")
        description = (
            str(raw.get("comment1", "") or "").strip()
            or str(raw.get("comment2", "") or "").strip()
            or ""
        )

        title_key = f"event_title_{eid}"
        display_name = translations.get(title_key) or internal_name

        results.append(
            GameEvent(
                id=eid,
                internal_name=internal_name,
                display_name=display_name,
                description=description,
            )
        )

    return results


__all__ = ["GameEvent", "get_active_events"]
