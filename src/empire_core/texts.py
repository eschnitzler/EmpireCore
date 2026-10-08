"""
The game's texts: every string the client shows, from its language file on the GGS CDN.

Usage:
    from empire_core.texts import text

    text("errorCode_120")                 # "This player's level is too low."
    text("travelSpeedBonusPerField", 5, 10, lang="de")
    number(250000, compact=True)          # "250k"

The language file (about 30k keys in English) is fetched on the first call that asks
for a text in that language, cached for 24 hours, and after a failed fetch left alone
for five minutes; until then a text falls back to its key, as the client's does.
Nothing here touches the network unless a caller asks for a text.

Client: ``BasicFrameOne.initLocalizationModule`` (dll line 32213) loads the file into a
case-insensitive ``GlobalizeTextProcessor``, read through ``Localize.text`` (dll line 3278).
"""

import logging
import math
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

import requests

from empire_core.protocol.js import js_number_or_none, js_string

logger = logging.getLogger(__name__)

LANG_META_URL = "https://langserv.public.ggs-ep.com/12/fr/@metadata"
LANG_DATA_URL = "https://langserv.public.ggs-ep.com/12@{version}/{lang}/*"

CACHE_TTL = 86400.0
"""Seconds a fetched language file is used before it is fetched again."""

RETRY_AFTER_FAILURE = 300.0
"""Seconds a failed fetch is not retried, as for the items."""

# Reads take no lock; one lock per language serialises its downloads only
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
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
    logged, and the CDN is not asked again for five minutes. Fresh texts are returned
    without waiting. Concurrent callers on a cold cache share one download; while a stale
    copy is being refreshed, other callers get the stale copy. A download in one language
    never holds up another.

    Args:
        lang: Language code (default: "en")
        force_refresh: Fetch from the CDN even when the cached texts are fresh
    """
    if not force_refresh:
        settled = _settled(lang)
        if settled is not None:
            return settled
    with _locks_guard:
        lock = _locks.setdefault(lang, threading.Lock())
    stale = _texts.get(lang)
    if stale is not None and not force_refresh:
        if not lock.acquire(blocking=False):
            return stale
    else:
        lock.acquire()
    try:
        if not force_refresh:
            settled = _settled(lang)
            if settled is not None:
                return settled
        cached = _texts.get(lang)
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
    finally:
        lock.release()


def _settled(lang: str) -> Mapping[str, str] | None:
    """The texts to return without fetching: fresh ones, or what there is while a failure backs off."""
    cached = _texts.get(lang)
    if cached is not None and _is_recent(_fetched_at.get(lang, 0.0), CACHE_TTL):
        return cached
    if _is_recent(_failed_at.get(lang, 0.0), RETRY_AFTER_FAILURE):
        return cached if cached is not None else {}
    return None


def fill(template: str, *args: object) -> str:
    """
    ``template`` with ``{0}``, ``{1}``, ... replaced by ``args``, each as JavaScript's ``String()`` writes it.

    ``True`` goes in as ``true``, ``2.0`` as ``2`` and ``None`` as ``null``; a placeholder
    without an argument stays as it is.

    This is the client's plain mode, ``localizeReplacements`` off, as
    ``BasicEnvironmentGlobals`` (dll line 34326) leaves it; the castle client turns it on,
    which :func:`text` follows. ``fill(get_texts()[key.lower()], ...)`` fills a text plainly.

    Client: ``doReplacements`` (dll line 23045), called by ``GlobalizeTextProcessor.getText``
    (dll line 22948)
    """

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index >= len(args):
            return match.group(0)
        value = args[index]
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    return _PLACEHOLDER.sub(replace, template)


FRACTIONAL_DIGITS = 2
"""Most fraction digits a number is written with: ``CastleEnvironmentGlobals.fractionalDigits`` (bundle line 31469)."""

ABBREVIATION_THRESHOLD = 100_000
"""From this size a compact number is abbreviated: ``BasicEnvironmentGlobals.abbreviationThreshold``, dll line 34330."""

# The two locales whose CLDR data the client carries (dll lines 26326 and 29220, both grouping
# "#,##0.###"); any other it downloads (dll line 22983), which is not done here
_NUMBER_SYMBOLS = {"en": (".", ","), "de": (",", ".")}
_ABBREVIATIONS = ((1_000_000, "generic_mformillion"), (1_000, "generic_kforthousand"))


@dataclass(frozen=True)
class LocalizedNumber:
    """
    A number argument :func:`text` writes as set here, where a plain number would take the defaults.

    Client: ``LocalizedNumberVO`` (dll line 22822), composed by ``Localize.number``
    """

    value: float
    compact: bool = False
    """Abbreviate from :data:`ABBREVIATION_THRESHOLD` on, as ``250k``."""
    fractional_digits: int = 0
    """Most fraction digits; -1 for :data:`FRACTIONAL_DIGITS`."""
    right_to_left: bool = False
    """Put a space before the ``k`` or ``M``, as for a right-to-left language."""


def _right_to_left(lang: str) -> bool:
    """Client: ``LanguageVO.isLanguageWrittenRightToLeft`` (dll line 22789)."""
    return lang == "ar"


def _decimal_text(value: float, digits: int, grouping: bool, lang: str) -> str:
    """
    ``value`` rounded to at most ``digits`` fraction digits, trailing zeros dropped, grouped by thousands.

    Client: Globalize's ``numberFormatter`` (dll line 5615) with ``minimumFractionDigits`` 0, as
    ``CastleEnvironmentGlobals.trailingZeros`` (bundle line 31472) is off. It rounds the decimal
    digits with ``Math.round`` (dll line 5583), so a half goes up: 2.345 is 2.35, -2.345 is -2.34.
    """
    decimal_symbol, group_symbol = _NUMBER_SYMBOLS.get(re.sub(r"_\w+", "", lang), _NUMBER_SYMBOLS["en"])
    shifted = Decimal(js_string(value)).scaleb(digits) + Decimal("0.5")
    rounded = shifted.to_integral_value(rounding=ROUND_FLOOR).scaleb(-digits)
    whole, _, fraction = f"{abs(rounded):f}".partition(".")
    fraction = fraction.rstrip("0")
    if grouping:
        whole = re.sub(r"\B(?=(\d{3})+$)", group_symbol, whole)
    return ("-" if value < 0 else "") + whole + (decimal_symbol + fraction if fraction else "")


def _number(
    value: float,
    compact: bool,
    digits: int,
    right_to_left: bool,
    grouping: bool,
    lang: str,
    texts: Callable[[], Mapping[str, str]],
) -> str:
    """
    Client: ``GlobalizeTextProcessor.number`` (dll line 22959) and ``shortenLargeNumber`` (dll line 23000);
    ``texts`` is read for the ``k`` or ``M`` only when a number is abbreviated, and a missing one is left out.
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "-∞" if value < 0 else "∞"
    digits = digits if digits > -1 else FRACTIONAL_DIGITS
    if not compact or -ABBREVIATION_THRESHOLD < value < ABBREVIATION_THRESHOLD:
        return _decimal_text(value, digits, grouping, lang)
    for scale, key in _ABBREVIATIONS:
        if value <= -scale or value >= scale:
            space = " " if right_to_left else ""
            return _decimal_text(value / scale, digits, grouping, lang) + space + texts().get(key, "")
    return js_string(value)


def number(
    value: float,
    *,
    compact: bool = False,
    fractional_digits: int = -1,
    right_to_left: bool = False,
    grouping: bool = True,
    lang: str = "en",
) -> str:
    """
    ``value`` as the game writes a number: ``1,234.5``, or with ``compact`` from 100,000 on ``250k`` and ``1.5M``.

    At most two fraction digits (or ``fractional_digits``), a half rounded up, no trailing
    zeros; ``right_to_left`` puts a space before the ``k`` or ``M``. As in the client, both
    are the caller's to pass, not taken from ``lang``. Only the English and German symbols
    are known; any other language writes its numbers as English does. A compact number
    fetches the language file for its ``k`` or ``M`` on first use, as :func:`text` does.

    Client: ``Localize.number`` (dll line 3280) -> ``GlobalizeTextProcessor.number``
    (dll line 22959), with the castle client's settings (bundle lines 31469 and 31472)
    """
    return _number(value, compact, fractional_digits, right_to_left, grouping, lang, lambda: get_texts(lang))


def _localized(value: object, texts: Mapping[str, str], grouping: bool, lang: str) -> str:
    """
    One argument as the castle client fills it in: a number written for the language, a text id read as its text.

    Client: ``GlobalizeTextProcessor.text`` (dll line 22957) with ``localizeReplacements`` on
    (``CastleEnvironmentGlobals``, bundle line 31500, applied in ``BasicFrameOne.initLocalizationModule``,
    dll line 32214). What reads as a number is what ``Number()`` reads as one: ``"12"``, ``True``,
    and ``None`` (JavaScript's ``null``, which is 0).
    """
    if isinstance(value, LocalizedNumber):
        localized = value.value
        return _number(
            localized, value.compact, value.fractional_digits, value.right_to_left, True, lang, lambda: texts
        )
    if value == "":
        return ""
    as_number = 0 if value is None else js_number_or_none(value)
    if as_number is not None:
        right_to_left = _right_to_left(lang)
        return _number(as_number, not right_to_left, -1, right_to_left, grouping, lang, lambda: texts)
    if isinstance(value, str):
        return texts.get(value.lower()) or value
    return js_string(value)


def _filled(template: str, args: tuple[object, ...], texts: Mapping[str, str], grouping: bool, lang: str) -> str:
    return fill(template, *(_localized(arg, texts, grouping, lang) for arg in args))


def text(key: str, *args: object, lang: str = "en", grouping: bool = True) -> str:
    """
    The game's text for ``key`` in ``lang`` with its placeholders filled, or ``key`` itself when there is none.

    Fills the placeholders as the castle client does: a number argument is written for the
    language (``1,234.5``, from 100,000 on ``250k``; see :func:`number`), a string that is a
    text id goes in as that text, and a :class:`LocalizedNumber` as it says. Fetches the
    language file on first use (see :func:`get_texts`); a CDN outage gives the key.

    Args:
        key: The text id, any case (``"errorCode_120"``, ``"currency_name_1MinSkip"``)
        args: Values for the ``{0}``, ``{1}``, ... placeholders
        lang: Language code (default: "en")
        grouping: Group the digits of a number argument by thousands

    Client: ``Localize.text`` (dll line 3278) -> ``GlobalizeTextProcessor.text``
    (dll line 22952): a missing key reads as the key. Right-to-left reordering is not done.
    """
    texts = get_texts(lang)
    found = texts.get(key.lower())
    return _filled(found, args, texts, grouping, lang) if found else key


def has_text(key: str, lang: str = "en") -> bool:
    """
    Whether the language file has a non-empty text for ``key``; fetches it on first use, as :func:`text` does.

    Client: ``Localize.hasText`` (dll line 3279) -> ``GlobalizeTextProcessor.hasText`` (dll line 22945)
    """
    return bool(get_texts(lang).get(key.lower()))


def cached_text(key: str, *args: object, lang: str = "en", grouping: bool = True) -> str | None:
    """
    Like :func:`text`, but only from texts already loaded: never fetches and never waits.

    Returns:
        The filled text, or None when ``lang`` is not loaded or has no text for ``key``
    """
    texts = _texts.get(lang, {})
    found = texts.get(key.lower())
    return _filled(found, args, texts, grouping, lang) if found else None


__all__ = [
    "ABBREVIATION_THRESHOLD",
    "CACHE_TTL",
    "FRACTIONAL_DIGITS",
    "RETRY_AFTER_FAILURE",
    "LocalizedNumber",
    "cached_text",
    "fetch_texts",
    "fill",
    "get_texts",
    "has_text",
    "number",
    "text",
]
