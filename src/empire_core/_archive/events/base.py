from typing import Any, Dict, List

from empire_core.state.world_models import MapObject
from pydantic import BaseModel, ConfigDict


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


# ============================================================
# Map Events
# ============================================================


class MapChunkParsedEvent(Event):
    """Triggered when a map chunk is parsed."""

    kingdom_id: int
    map_objects: List[MapObject]


# ============================================================
# Movement Events
# ============================================================


class MovementEvent(Event):
    """Base class for all movement-related events."""

    movement_id: int
    movement_type: int
    movement_type_name: str
    source_area_id: int
    target_area_id: int
    is_incoming: bool
    is_outgoing: bool


class MovementStartedEvent(MovementEvent):
    """
    Triggered when a new movement is detected.
    This includes both our outgoing movements and incoming attacks from others.
    """

    total_time: int  # Total travel time in seconds
    unit_count: int  # Total units in movement


class MovementUpdatedEvent(MovementEvent):
    """
    Triggered when a movement's progress is updated.
    """

    progress_time: int  # Time elapsed
    total_time: int  # Total travel time
    time_remaining: int  # Time left
    progress_percent: float


class MovementArrivedEvent(MovementEvent):
    """
    Triggered when a movement arrives at its destination.
    """

    was_incoming: bool  # True if it was incoming to us
    was_outgoing: bool  # True if it was our movement


class MovementCancelledEvent(MovementEvent):
    """
    Triggered when a movement is cancelled/recalled.
    """

    pass


class IncomingAttackEvent(Event):
    """
    Triggered specifically when an incoming attack is detected.
    This is a high-priority alert event.
    """

    movement_id: int
    attacker_id: int
    attacker_name: str
    target_area_id: int
    target_name: str
    time_remaining: int
    unit_count: int
    source_x: int
    source_y: int


class ReturnArrivalEvent(Event):
    """
    Triggered when returning troops arrive back.
    Useful for tracking loot from attacks.
    """

    movement_id: int
    castle_id: int
    units: Dict[int, int]  # UnitID -> Count
    resources_wood: int
    resources_stone: int
    resources_food: int
    total_loot: int


# ============================================================
# Attack/Battle Events
# ============================================================


class AttackSentEvent(Event):
    """Triggered when we send an attack."""

    movement_id: int
    origin_castle_id: int
    target_area_id: int
    units: Dict[int, int]


class ScoutSentEvent(Event):
    """Triggered when we send scouts."""

    movement_id: int
    origin_castle_id: int
    target_area_id: int


class TransportSentEvent(Event):
    """Triggered when we send a transport."""

    movement_id: int
    origin_castle_id: int
    target_castle_id: int
    resources_wood: int
    resources_stone: int
    resources_food: int
