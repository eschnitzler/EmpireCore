"""
Troop metadata fetcher - gets valid troop IDs from GGE CDN.

Units with slotTypes are equipment, not troops.
This filters to get only actual combat units.

A CDN outage makes :func:`get_troop_ids` raise
:class:`~empire_core.exceptions.NetworkError` rather than return an empty set,
so callers can tell "metadata unavailable" apart from "no troop IDs".
:func:`count_troops` still degrades to counting every unit in that case, which
inflates the count; see its docstring.
"""

import logging
import threading
import time

import requests

from empire_core.exceptions import NetworkError

logger = logging.getLogger(__name__)

# Cached troop IDs. Guarded by _fetch_lock so concurrent callers on a cold
# cache do not both run the blocking CDN download.
_troop_ids: set[int] | None = None
_fetch_lock = threading.Lock()
# After a failed fetch, don't retry the CDN for this many seconds. Without
# this, every Movement.troop_count access re-issues blocking HTTP requests.
_FAILURE_RETRY_INTERVAL = 300.0
_last_failure_at: float = 0.0
# count_troops() runs per movement, so its degraded-count warning is throttled
# to the retry interval instead of firing on every access during an outage.
_last_degraded_warning_at: float = 0.0


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


def troop_data_available() -> bool:
    """
    Whether troop metadata is cached, i.e. whether troop counts are exact.

    Returns:
        True if a CDN fetch has succeeded in this process, so
        :func:`count_troops` filters equipment out. False means the metadata has
        not been fetched (or every attempt failed), and ``count_troops`` falls
        back to counting every unit. This does not touch the network.
    """
    # Deliberately lock-free: reading the reference is atomic, and taking
    # _fetch_lock here would block for the duration of an in-flight fetch.
    return _troop_ids is not None


def get_troop_ids(force_refresh: bool = False) -> set[int]:
    """
    Get the set of valid troop unit IDs.

    Troops are units without slotTypes (equipment has slotTypes). The result is
    cached for the lifetime of the process.

    Args:
        force_refresh: Force re-fetch from CDN

    Returns:
        Set of wodID values for valid troops. An empty set means the CDN data
        genuinely listed no troops - a fetch failure raises instead.

    Raises:
        NetworkError: The CDN fetch failed and no troop IDs are cached. While
            the post-failure backoff window (``_FAILURE_RETRY_INTERVAL``) is
            open this is raised without issuing another request, so repeated
            callers don't hammer the CDN.
    """
    global _troop_ids, _last_failure_at

    with _fetch_lock:
        if _troop_ids is not None and not force_refresh:
            return _troop_ids

        # Back off after a failure so repeated callers don't hammer the CDN
        if not force_refresh and _last_failure_at > 0.0 and time.time() - _last_failure_at < _FAILURE_RETRY_INTERVAL:
            raise NetworkError(
                "GGE CDN troop metadata is unavailable: the last fetch failed less than "
                f"{_FAILURE_RETRY_INTERVAL:.0f}s ago and is not retried yet"
            )

        try:
            version = get_items_version()
            items_data = fetch_items_data(version)
        except Exception as e:
            _last_failure_at = time.time()
            raise NetworkError(f"Failed to fetch troop metadata from GGE CDN: {e}") from e

        units = items_data.get("units", [])
        # Filter units without slotTypes (those are actual troops)
        troop_ids = set()
        for unit in units:
            if not unit.get("slotTypes"):
                wod_id = unit.get("wodID")
                if wod_id:
                    troop_ids.add(wod_id)

        _troop_ids = troop_ids
        _last_failure_at = 0.0
        logger.info(f"Loaded {len(troop_ids)} troop IDs from GGE CDN (v{version})")
        return troop_ids


def count_troops(units: dict[int, int], troop_ids: set[int] | None = None) -> int:
    """
    Count only actual troops in a unit dict, excluding equipment.

    Args:
        units: Dict of {unit_id: count}
        troop_ids: Explicit set of valid troop IDs. Fetched from the CDN when
            omitted. An explicitly empty set counts nothing, since it means
            "no unit ID is a troop".

    Returns:
        Total count of actual troops.

        Degraded fallback: when ``troop_ids`` is omitted and the CDN metadata
        cannot be fetched, every unit is counted - including equipment - so the
        result can be inflated. The fallback warns (throttled to once per
        retry interval); callers that need to know whether a count is exact
        should check
        :func:`troop_data_available`, or call :func:`get_troop_ids` themselves
        and handle ``NetworkError``.
    """
    global _last_degraded_warning_at

    if troop_ids is None:
        try:
            troop_ids = get_troop_ids()
        except NetworkError as e:
            message = f"Troop metadata unavailable, counting all units including equipment (inflated): {e}"
            now = time.time()
            if now - _last_degraded_warning_at >= _FAILURE_RETRY_INTERVAL:
                _last_degraded_warning_at = now
                logger.warning(message)
            else:
                logger.debug(message)
            return sum(units.values())

    return sum(count for uid, count in units.items() if uid in troop_ids)
