"""
The in-game titles of the server's events, from the game's language CDN.

Usage:
    titles = get_event_titles("de")
    titles.get(83)  # the long-term point event's title

The titles are cosmetic: a CDN outage gives the titles last fetched, or none, and is
retried after a pause.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

# CDN endpoint for translations
_LANG_META_URL = "https://langserv.public.ggs-ep.com/12/fr/@metadata"
_LANG_DATA_URL = "https://langserv.public.ggs-ep.com/12@{version}/{lang}/*"

# Shared by every thread that asks; reads and writes happen under _fetch_lock, so
# two callers on a cold cache do not both run the multi-second download.
_fetch_lock = threading.Lock()
_cached_translations: dict[str, dict[str, str]] = {}  # lang -> translations

# Wall-clock stamp (time.time()) of the last successful fetch per language.
_translations_fetched_at: dict[str, float] = {}
# Cached translations are refreshed after this long.
_CACHE_TTL = 86400.0

# After a failed fetch, the CDN is not asked again for this many seconds.
_FAILURE_RETRY_INTERVAL = 300.0
_last_translations_failure_at: dict[str, float] = {}

_TITLE_PREFIX = "event_title_"


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


def _get_translations(lang: str = "en", force_refresh: bool = False) -> dict[str, str]:
    """
    Fetch and cache the GGS translation dictionary.

    A failure is not fatal: the last cached dict (or an empty one) is
    returned, a warning is logged, and the CDN is not retried for
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
            logger.warning(f"Failed to fetch translations, event titles fall back to the event names: {e}")
            return cached if cached is not None else {}

        _cached_translations[lang] = translations
        _translations_fetched_at[lang] = time.time()
        _last_translations_failure_at.pop(lang, None)
        logger.info(f"Loaded {len(translations)} '{lang}' translations from GGS CDN")
        return translations


def get_event_titles(lang: str = "en", force_refresh: bool = False) -> dict[int, str]:
    """
    The in-game title of every event, by event id, in ``lang``.

    Fetched from the GGS language CDN and cached for 24 hours. A failed fetch
    gives the titles last fetched, or an empty dict, and is not retried for
    five minutes.

    Args:
        lang: Language code (default: "en")
        force_refresh: Fetch from the CDN even when the cached titles are fresh

    Client: the event dialogs show ``"event_title_"+eventId`` (``ASeasonEventVO.seasonNameString``,
    bundle line 31389)
    """
    translations = _get_translations(lang=lang, force_refresh=force_refresh)
    titles: dict[int, str] = {}
    for key, text in translations.items():
        if key.startswith(_TITLE_PREFIX) and key[len(_TITLE_PREFIX) :].isdigit():
            titles[int(key[len(_TITLE_PREFIX) :])] = text
    return titles


__all__ = ["get_event_titles"]
