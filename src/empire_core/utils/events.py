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

A CDN outage raises :class:`~empire_core.exceptions.NetworkError` rather than
returning an empty list, so callers can tell "metadata unavailable" apart from
"no events are running".
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from empire_core.exceptions import NetworkError
from empire_core.utils.troops import fetch_items_data, get_items_version

logger = logging.getLogger(__name__)

# CDN endpoint for translations
_LANG_META_URL = "https://langserv.public.ggs-ep.com/12/fr/@metadata"
_LANG_DATA_URL = "https://langserv.public.ggs-ep.com/12@{version}/{lang}/*"

# Module-level caches shared by every thread that resolves events. Reads and
# writes happen under _fetch_lock: unsynchronized check-then-fetch let two
# callers on a cold cache both run the multi-second CDN download.
_fetch_lock = threading.Lock()
_cached_events_index: dict[int, dict[str, Any]] | None = None  # event_id -> raw event dict
_cached_translations: dict[str, dict[str, str]] = {}  # lang -> translations

# Wall-clock stamp (time.time(), as in troops.py) of the last successful fetch.
_events_index_fetched_at: float = 0.0
_translations_fetched_at: dict[str, float] = {}
# Cached CDN data is refreshed after this long, so a long-running process
# eventually sees events added to the CDN after it started.
_CACHE_TTL = 86400.0

# After a failed fetch, don't retry the CDN for this many seconds - the same
# guard troops.py uses. Without it every call re-issues blocking HTTP requests
# (10s + 30s timeouts) from whatever thread happens to ask.
_FAILURE_RETRY_INTERVAL = 300.0
_last_index_failure_at: float = 0.0
_last_translations_failure_at: dict[str, float] = {}


@dataclass
class GameEvent:
    """A resolved active game event with human-readable names."""

    id: int
    internal_name: str  # Internal type name, e.g. "Nomad", "AllianceBattleGround"
    display_name: str  # Localized in-game title, e.g. "Nomad Invasion"
    description: str  # Developer comment / short description


def _is_recent(stamp: float, interval: float) -> bool:
    """True when ``stamp`` is set and less than ``interval`` seconds old."""
    return stamp > 0.0 and time.time() - stamp < interval


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
        force_refresh: Fetch from the CDN even when the cached index is fresh.

    Returns:
        Dict mapping event ID (int) to the raw event entry from items data.
        The index is cached for ``_CACHE_TTL`` seconds; if refreshing it fails
        while an older index is cached, that stale index is returned and a
        warning is logged.

    Raises:
        NetworkError: The CDN fetch failed and no index has ever been cached.
            Also raised, without touching the network, while the post-failure
            backoff window (``_FAILURE_RETRY_INTERVAL``) is still open.
    """
    global _cached_events_index, _events_index_fetched_at, _last_index_failure_at

    with _fetch_lock:
        cached = _cached_events_index
        if not force_refresh and cached is not None and _is_recent(_events_index_fetched_at, _CACHE_TTL):
            return cached

        if not force_refresh and _is_recent(_last_index_failure_at, _FAILURE_RETRY_INTERVAL):
            if cached is not None:
                return cached
            raise NetworkError(
                "GGS CDN event metadata is unavailable: the last fetch failed less than "
                f"{_FAILURE_RETRY_INTERVAL:.0f}s ago and is not retried yet"
            )

        try:
            version = get_items_version()
            items_data = fetch_items_data(version)
        except Exception as e:
            _last_index_failure_at = time.time()
            if cached is not None:
                logger.warning(f"Failed to refresh event metadata from GGS CDN, serving cached index: {e}")
                return cached
            raise NetworkError(f"Failed to fetch event metadata from GGS CDN: {e}") from e

        index: dict[int, dict[str, Any]] = {}
        for event in items_data.get("events", []):
            try:
                event_id = int(event["eventID"])
                index[event_id] = event
            except (KeyError, TypeError, ValueError):
                continue

        _cached_events_index = index
        _events_index_fetched_at = time.time()
        _last_index_failure_at = 0.0
        logger.info(f"Built events index with {len(index)} entries from GGS CDN (v{version})")
        return index


def _get_translations(lang: str = "en", force_refresh: bool = False) -> dict[str, str]:
    """
    Fetch and cache the GGS translation dictionary.

    Display names are cosmetic, so unlike the events index a translation
    failure is not fatal: an empty dict is returned (callers fall back to
    internal names), a warning is logged, and the CDN is not retried for
    ``_FAILURE_RETRY_INTERVAL`` seconds.

    Args:
        lang: Language code (default: "en").
        force_refresh: Fetch from the CDN even when the cached data is fresh.

    Returns:
        Dict mapping translation keys to localized strings, or the last cached
        dict (empty if there is none) when the CDN is unavailable.
    """
    with _fetch_lock:
        cached = _cached_translations.get(lang)
        fetched_at = _translations_fetched_at.get(lang, 0.0)
        if not force_refresh and cached is not None and _is_recent(fetched_at, _CACHE_TTL):
            return cached

        failed_at = _last_translations_failure_at.get(lang, 0.0)
        if not force_refresh and _is_recent(failed_at, _FAILURE_RETRY_INTERVAL):
            return cached if cached is not None else {}

        try:
            translations = _fetch_translations(lang=lang)
        except Exception as e:
            _last_translations_failure_at[lang] = time.time()
            logger.warning(f"Failed to fetch translations, display names will fall back to internal names: {e}")
            return cached if cached is not None else {}

        _cached_translations[lang] = translations
        _translations_fetched_at[lang] = time.time()
        _last_translations_failure_at.pop(lang, None)
        logger.info(f"Loaded {len(translations)} '{lang}' translations from GGS CDN")
        return translations


def get_active_events(
    event_ids: list[int],
    lang: str = "en",
    force_refresh: bool = False,
) -> list[GameEvent]:
    """
    Resolve a list of active event IDs to typed GameEvent objects.

    Fetches event metadata and translations from the GGS CDN (results are
    cached for 24h and refreshed afterwards). Pass the IDs from
    ``client.get_active_event_ids()``.

    Args:
        event_ids: List of active event IDs from the server's sei packet.
        lang: Language code for display names (default: "en").
        force_refresh: Force re-fetch of CDN data, bypassing the cache.

    Returns:
        List of GameEvent objects for the given IDs. An empty list means
        ``event_ids`` was empty or none of the IDs appear in the CDN data - it
        never means "the CDN was unreachable", which raises instead. IDs not
        found in the CDN data are skipped with a debug log.

        A failure to fetch *translations* is not fatal: display names then fall
        back to the internal event names.

    Raises:
        NetworkError: Event metadata could not be fetched from the CDN and no
            previously fetched metadata is cached. During the retry backoff
            window this is raised without issuing another request, so callers
            polling in a loop do not hammer the CDN.

    Example:
        event_ids = client.get_active_event_ids()
        try:
            events = get_active_events(event_ids)
        except NetworkError:
            # metadata unavailable - do not treat this as "no events active"
            raise

        event_names = {e.internal_name for e in events}
        if "Nomad" in event_names:
            # handle nomad event ...
            pass
    """
    if not event_ids:
        return []

    index = _build_events_index(force_refresh=force_refresh)
    translations = _get_translations(lang=lang, force_refresh=force_refresh)

    results: list[GameEvent] = []
    for eid in event_ids:
        raw = index.get(eid)
        if raw is None:
            logger.debug(f"Event ID {eid} not found in CDN data, skipping")
            continue

        internal_name = str(raw.get("eventType") or "Unknown")
        description = str(raw.get("comment1", "") or "").strip() or str(raw.get("comment2", "") or "").strip() or ""

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
