"""The game state that server pushes keep current, read through ``client.state``."""

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, ResourceCartType
from empire_core.state.manager import EventCallback, EventsCallback, GameState, MovementEventCallback
from empire_core.state.models import Alliance, Castle, JoinedArea, Player, Resources
from empire_core.utils.lazy import lazy_exports

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, Event, Horse, Tool, Unit

__all__ = [
    "GameState",
    "EventCallback",
    "EventsCallback",
    "MovementEventCallback",
    "Alliance",
    "Castle",
    "JoinedArea",
    "Player",
    "Resources",
    "Kingdom",
    "ResourceCartType",
    "Currency",
    "Event",
    "Horse",
    "Tool",
    "Unit",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Currency", "Event", "Horse", "Tool", "Unit"))
