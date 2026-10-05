"""
Telling troops from equipment in a unit dict, by the loaded game data.

Troops are the ``units`` rows without ``slotTypes``, which :class:`GameData` keeps
as its ``units``; the rows with them are tools. The ids come from
:meth:`GameData.load`, so they share its one download, cache and failure backoff.

With no game data loaded, a CDN outage makes :func:`get_troop_ids` raise
:class:`~empire_core.exceptions.NetworkError` rather than return an empty set,
so callers can tell "metadata unavailable" apart from "no troop IDs".
:func:`count_troops` still degrades to counting every unit in that case, which
inflates the count; see its docstring.
"""

import logging
import time

from empire_core.exceptions import NetworkError

from .cdn import RETRY_AFTER_FAILURE
from .data import GameData

logger = logging.getLogger(__name__)

# count_troops() runs per movement, so its degraded-count warning is throttled.
_last_degraded_warning_at: float = 0.0


def troop_data_available() -> bool:
    """
    Whether game data is loaded in this process, i.e. whether troop counts are exact.

    Returns:
        True once a :meth:`GameData.load` has succeeded here, so
        :func:`count_troops` filters equipment out. False means
        ``count_troops`` would load the game data first, or fall back to counting
        every unit. This does not touch the network.
    """
    return GameData.loaded() is not None


def get_troop_ids(force_refresh: bool = False) -> set[int]:
    """
    The ``wodID`` of every troop: the ids of the loaded game data's ``units``.

    Uses the game data already loaded in the process, and loads it through
    :meth:`GameData.load` when there is none.

    Args:
        force_refresh: Load the game data again, past its cache and failure backoff

    Returns:
        Set of wodID values for valid troops. An empty set means the CDN data
        genuinely listed no troops - a fetch failure raises instead.

    Raises:
        NetworkError: The game data is not loaded and could not be. Within five
            minutes of a failed fetch this is raised without another request.
    """
    data = None if force_refresh else GameData.loaded()
    if data is None:
        data = GameData.load(refresh=force_refresh)
    return set(data.units)


def count_troops(units: dict[int, int], troop_ids: set[int] | None = None) -> int:
    """
    Count only actual troops in a unit dict, excluding equipment.

    Args:
        units: Dict of {unit_id: count}
        troop_ids: Explicit set of valid troop IDs. Taken from the game data
            (loading it if needed) when omitted. An explicitly empty set counts
            nothing, since it means "no unit ID is a troop".

    Returns:
        Total count of actual troops.

        Degraded fallback: when ``troop_ids`` is omitted and the game data
        cannot be loaded, every unit is counted - including equipment - so the
        result can be inflated. The fallback warns (throttled to once per
        retry interval); callers that need to know whether a count is exact
        should check :func:`troop_data_available`, or call
        :func:`get_troop_ids` themselves and handle ``NetworkError``.
    """
    global _last_degraded_warning_at

    if troop_ids is None:
        try:
            troop_ids = get_troop_ids()
        except NetworkError as e:
            message = f"Troop metadata unavailable, counting all units including equipment (inflated): {e}"
            now = time.monotonic()
            if not _last_degraded_warning_at or now - _last_degraded_warning_at >= RETRY_AFTER_FAILURE:
                _last_degraded_warning_at = now
                logger.warning(message)
            else:
                logger.debug(message)
            return sum(units.values())

    return sum(count for uid, count in units.items() if uid in troop_ids)


__all__ = ["count_troops", "get_troop_ids", "troop_data_available"]
