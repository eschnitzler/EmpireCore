"""
The game's texts: every string the client shows, from its language file on the GGS CDN.

Usage:
    from empire_core.texts import text

    text("errorCode_120")                 # "This player's level is too low."
    text("travelSpeedBonusPerField", 5, 10, lang="de")

The language file (about 30k keys in English) is fetched on the first call that asks
for a text in that language, cached for 24 hours, and after a failed fetch left alone
for five minutes; until then a text falls back to its key, as the client's does.
Nothing here touches the network unless a caller asks for a text.

Client: ``BasicFrameOne.initLocalizationModule`` (dll line 32213) loads the file into a
case-insensitive ``GlobalizeTextProcessor``, read through ``Localize.text`` (bundle line 3278).
"""

import logging
import re
import threading
import time
from collections.abc import Mapping

import requests

logger = logging.getLogger(__name__)

LANG_META_URL = "https://langserv.public.ggs-ep.com/12/fr/@metadata"
LANG_DATA_URL = "https://langserv.public.ggs-ep.com/12@{version}/{lang}/*"

CACHE_TTL = 86400.0
"""Seconds a fetched language file is used before it is fetched again."""

RETRY_AFTER_FAILURE = 300.0
"""Seconds a failed fetch is not retried, as for the items."""

# Readers of _texts take no lock: the error path must never wait on a download.
_fetch_lock = threading.Lock()
_texts: dict[str, dict[str, str]] = {}
_fetched_at: dict[str, float] = {}
_failed_at: dict[str, float] = {}

_PLACEHOLDER = re.compile(r"\{(\d+)\}")


def _is_recent(stamp: float, interval: float) -> bool:
    return stamp > 0.0 and time.time() - stamp < interval


def fetch_texts(lang: str = "en") -> dict[str, str]:
    """
    The current language file for ``lang`` from the CDN, uncached, keys as the file has them.

    Raises:
        requests.RequestException: The CDN failed
    """
    meta = requests.get(LANG_META_URL, timeout=10)
    meta.raise_for_status()
    version = meta.json()["@metadata"]["versionNo"]
    response = requests.get(LANG_DATA_URL.format(version=version, lang=lang), timeout=30)
    response.raise_for_status()
    texts: dict[str, str] = response.json()
    return texts


def _normalised(texts: Mapping[str, object]) -> dict[str, str]:
    """
    Lower-cased keys without ``@metadata``; of keys differing only in case the later wins.

    Client: ``GlobalizeTextProcessor.setTexts`` (dll line 22936) via ``objectToLowerCase``.
    """
    return {key.lower(): str(value) for key, value in texts.items() if key != "@metadata"}


def get_texts(lang: str = "en", force_refresh: bool = False) -> Mapping[str, str]:
    """
    Every text in ``lang``, keyed by the lower-cased text id; fetched on first use and cached.

    A failure is not fatal: the texts last fetched (or none) are returned, a warning is
    logged, and the CDN is not asked again for five minutes. Concurrent callers on a cold
    cache share one download.

    Args:
        lang: Language code (default: "en")
        force_refresh: Fetch from the CDN even when the cached texts are fresh
    """
    with _fetch_lock:
        cached = _texts.get(lang)
        if not force_refresh and cached is not None and _is_recent(_fetched_at.get(lang, 0.0), CACHE_TTL):
            return cached
        if not force_refresh and _is_recent(_failed_at.get(lang, 0.0), RETRY_AFTER_FAILURE):
            return cached if cached is not None else {}
        try:
            texts = _normalised(fetch_texts(lang))
        except Exception as e:
            _failed_at[lang] = time.time()
            logger.warning(f"Failed to fetch the '{lang}' texts, texts fall back to their keys: {e}")
            return cached if cached is not None else {}
        _texts[lang] = texts
        _fetched_at[lang] = time.time()
        _failed_at.pop(lang, None)
        logger.info(f"Loaded {len(texts)} '{lang}' texts from the GGS CDN")
        return texts


def fill(template: str, *args: object) -> str:
    """
    ``template`` with ``{0}``, ``{1}``, ... replaced by ``args``, as the client inserts them.

    Each argument goes in as its plain string, with no number formatting; a placeholder
    without an argument stays as it is.

    Client: ``doReplacements`` (dll line 23045), called by ``GlobalizeTextProcessor.getText``
    (dll line 22950)
    """

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index >= len(args):
            return match.group(0)
        value = args[index]
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)

    return _PLACEHOLDER.sub(replace, template)


def text(key: str, *args: object, lang: str = "en") -> str:
    """
    The game's text for ``key`` in ``lang`` with its placeholders filled, or ``key`` itself when there is none.

    Fetches the language file on first use (see :func:`get_texts`); a CDN outage gives the key.

    Args:
        key: The text id, any case (``"errorCode_120"``, ``"currency_name_1MinSkip"``)
        args: Values for the ``{0}``, ``{1}``, ... placeholders
        lang: Language code (default: "en")

    Client: ``Localize.text`` (bundle line 3278) -> ``GlobalizeTextProcessor.text``
    (dll line 22952): a missing key reads as the key; right-to-left reordering is not done.
    """
    found = get_texts(lang).get(key.lower())
    return fill(found, *args) if found else key


def cached_text(key: str, *args: object, lang: str = "en") -> str | None:
    """
    Like :func:`text`, but only from texts already loaded: never fetches and never waits.

    Returns:
        The filled text, or None when ``lang`` is not loaded or has no text for ``key``
    """
    found = _texts.get(lang, {}).get(key.lower())
    return fill(found, *args) if found else None


__all__ = ["CACHE_TTL", "RETRY_AFTER_FAILURE", "cached_text", "fetch_texts", "fill", "get_texts", "text"]
