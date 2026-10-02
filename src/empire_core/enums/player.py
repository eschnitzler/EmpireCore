"""Player progress constants."""

from enum import Enum


class TitleSystem(str, Enum):
    """
    A title system: the ``type`` of a title in the items data, and a ``uar``'s ``PFX`` and ``SFX``.

    Client: ``ClientConstTitle.GLORY_TITLE``, ``BRAVERY_TITLE`` and ``ISLAND_TITLE`` (bundle line 6767)
    """

    GLORY = "FAME"
    FACTION = "FACTION"
    ISLAND = "ISLE"
