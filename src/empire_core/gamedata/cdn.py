"""
The items payload on the GGE CDN, fetched without any caching.

:meth:`GameData.load <empire_core.gamedata.data.GameData.load>` is the one
place that calls these, caches the result and backs off after a failure;
everything else reads the game data through it.
"""

import re

import requests

ITEMS_BASE_URL = "https://empire-html5.goodgamestudios.com/default/items"

_VERSION = re.compile(r"\d+(\.\d+)*")

RETRY_AFTER_FAILURE = 300.0
"""Seconds a failed CDN fetch is not retried, for the items and the language file alike."""


def get_items_version() -> str:
    """
    The current items version, from ``ItemsVersion.properties``.

    Client: ``BasicFrameOne.loadItemVersionXML`` loads ``{baseURL}/ItemsVersion.properties``
    (ggs.dll lines 3928 and 32238) and ``onVersionPropertiesLoaded`` keeps the text after the
    first ``=``, trimmed (ggs.dll line 32240).

    Raises:
        ValueError: The text is not dotted digits (``786.03``), so it is never put in a URL or file name
    """
    response = requests.get(f"{ITEMS_BASE_URL}/ItemsVersion.properties", timeout=10)
    response.raise_for_status()
    text = response.text
    version = text[text.find("=") + 1 :].strip()
    if not _VERSION.fullmatch(version):
        raise ValueError(f"Unexpected items version {version[:40]!r}")
    return version


def fetch_items_data(version: str) -> dict:
    """The full ``items_v{version}.json`` payload."""
    response = requests.get(f"{ITEMS_BASE_URL}/items_v{version}.json", timeout=30)
    response.raise_for_status()
    return response.json()


__all__ = ["ITEMS_BASE_URL", "RETRY_AFTER_FAILURE", "fetch_items_data", "get_items_version"]
