"""
The in-game titles of the server's events, from the game's language file.

Usage:
    titles = get_event_titles("de")
    titles.get(83)  # the long-term point event's title

The titles are cosmetic: a CDN outage gives the titles last fetched, or none, and is
retried after a pause (see :func:`empire_core.texts.get_texts`).
"""

from empire_core.texts import get_texts

_TITLE_PREFIX = "event_title_"


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
    titles: dict[int, str] = {}
    for key, text in get_texts(lang=lang, force_refresh=force_refresh).items():
        if key.startswith(_TITLE_PREFIX) and key[len(_TITLE_PREFIX) :].isdigit():
            titles[int(key[len(_TITLE_PREFIX) :])] = text
    return titles


__all__ = ["get_event_titles"]
