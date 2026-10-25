"""
Districts: buildings that hold other buildings, such as a decoration district.

Commands:
- mde: move a building of the joined castle into a district
- rde: move a building out of its district onto the castle grounds
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BaseRequest

from .buildings import MoveBuildingResponse


class MoveToDistrictRequest(BaseRequest):
    """
    Move a building of the joined castle into a district.

    Command: mde
    Payload: {"OID": object_id, "DOID": district_object_id}

    Client: ``C2SMoveToDistrictVO`` (bundle line 41105), sent by ``IsoViewMouse.dropDraggedTarget`` (bundle
    line 64023) when a building is dropped on a district and by ``RingMenuButtonBuildingDistrictAdd.onClick``
    (bundle line 81798)
    """

    command = "mde"

    object_id: int = Field(validation_alias="OID", description="The building's object id")
    district_object_id: int = Field(validation_alias="DOID", description="The district's object id")


class MoveToDistrictResponse(MoveBuildingResponse):
    """
    The moved building.

    Command: mde
    Payload: {"MO": row}

    Client: ``MDECommand.executeCommand`` (bundle line 123166), which also reads the reply to a
    failed move, ``AreaDataUpdater.parseEMO`` (bundle line 131567)
    """

    command = "mde"


class RemoveFromDistrictRequest(BaseRequest):
    """
    Move a building out of its district onto the joined castle's grounds.

    Command: rde
    Payload: {"OID": object_id, "X": x, "Y": y, "R": rotation}

    Client: ``C2SRemoveFromDistrictVO`` (bundle line 63853), sent by ``IsoServerCommands.moveObject``
    (bundle line 63799) for a building in a district
    """

    command = "rde"

    object_id: int = Field(validation_alias="OID", description="The building's object id")
    x: int = Field(validation_alias="X", description="Castle grid x")
    y: int = Field(validation_alias="Y", description="Castle grid y")
    rotation: int = Field(validation_alias="R", default=0, description="Rotation")


class RemoveFromDistrictResponse(MoveBuildingResponse):
    """
    The moved building.

    Command: rde
    Payload: {"MO": row}

    Client: ``RDECommand.executeCommand`` (bundle line 123249), which also reads the reply to a
    failed move, ``AreaDataUpdater.parseEMO`` (bundle line 131567)
    """

    command = "rde"


__all__ = ["MoveToDistrictRequest", "MoveToDistrictResponse", "RemoveFromDistrictRequest", "RemoveFromDistrictResponse"]
