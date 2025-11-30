from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict
from empire_core.utils.enums import MapObjectType, MovementType

class MapObject(BaseModel):
    """Represents an object on the world map (Castle, Resource, NPC)."""
    model_config = ConfigDict(extra='ignore')
    
    area_id: int = Field(default=-1, alias="AID")
    owner_id: int = Field(default=-1, alias="OID")
    type: MapObjectType = Field(default=MapObjectType.UNKNOWN, alias="T") 
    level: int = Field(default=0, alias="L")
    
    # Location - sometimes embedded or passed separately
    x: int = Field(default=0, alias="X")
    y: int = Field(default=0, alias="Y")
    kingdom_id: int = Field(default=0, alias="KID")

class Army(BaseModel):
    """Represents troops in a movement or castle."""
    model_config = ConfigDict(extra='ignore')
    units: Dict[int, int] = Field(default_factory=dict) # UnitID -> Count

class Movement(BaseModel):
    """Represents a movement (Attack, Support, Transport, etc.)."""
    model_config = ConfigDict(extra='ignore', populate_by_name=True)
    
    MID: int = Field(default=-1)     # Movement ID
    T: int = Field(default=0)        # Type (11=return, etc.)
    PT: int = Field(default=0)       # Progress Time
    TT: int = Field(default=0)       # Total Time
    D: int = Field(default=0)        # Direction
    TID: int = Field(default=-1)     # Target/Owner ID
    KID: int = Field(default=0)      # Kingdom ID
    SID: int = Field(default=-1)     # Source ID
    OID: int = Field(default=-1)     # Owner ID
    HBW: int = Field(default=-1)     # ?
    
    # TA = Target Area (array with area details)
    # SA = Source Area (array with area details)
    target_area: Optional[List[Any]] = Field(default=None, alias="TA")
    source_area: Optional[List[Any]] = Field(default=None, alias="SA")
    
    # Extracted fields
    target_area_id: int = Field(default=-1)
    source_area_id: int = Field(default=-1)
    target_x: int = Field(default=-1)
    target_y: int = Field(default=-1)
    source_x: int = Field(default=-1)
    source_y: int = Field(default=-1)
    
    @property
    def movement_id(self) -> int:
        return self.MID
    
    @property
    def movement_type(self) -> int:
        return self.T
    
    @property
    def movement_type_name(self) -> str:
        """Get the name of the movement type."""
        try:
            return MovementType(self.T).name
        except ValueError:
            return f"UNKNOWN_{self.T}"
    
    @property
    def progress_time(self) -> int:
        return self.PT
    
    @property
    def total_time(self) -> int:
        return self.TT
    
    @property
    def time_remaining(self) -> int:
        return max(0, self.TT - self.PT)
    
    @property
    def progress_percent(self) -> float:
        if self.TT > 0:
            return (self.PT / self.TT) * 100
        return 0.0
    
    @property
    def is_incoming(self) -> bool:
        """Check if this movement is incoming to player."""
        # Type 11 is typically return movement
        return self.T != 11 and self.D == 0
    
    @property
    def is_outgoing(self) -> bool:
        """Check if this movement is outgoing from player."""
        return self.T != 11 and self.D == 1
