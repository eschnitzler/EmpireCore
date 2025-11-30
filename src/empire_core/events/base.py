from pydantic import BaseModel, ConfigDict
from typing import Any, Dict

class Event(BaseModel):
    """Base class for all events."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

class PacketEvent(Event):
    """
    Raw event triggered when a packet is received.
    Useful for debugging or catching unhandled commands.
    """
    command_id: str
    payload: Any
    is_xml: bool

# We will add more specific events (e.g. AttackEvent) later
