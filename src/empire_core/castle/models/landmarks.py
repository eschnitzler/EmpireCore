"""A monument's or laboratory's upgrade progress.

Commands:
- glp: A laboratory's progress
- gmp: A monument's progress
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BaseRequest, BaseResponse


class GetLaboratoryProgressRequest(BaseRequest):
    """
    Ask for a laboratory's upgrade progress.

    Command: glp
    Payload: {"ID": object_id}

    Client: ``C2SGetLaboratoryProgressVO`` (bundle line 86480), sent by the upgrade dialog with the map object's
    ``objectId`` (``CastleUpgradeLaboratoryDialogProperties.progressCommandVO``, bundle line 51665)
    """

    command = "glp"

    object_id: int = Field(validation_alias="ID", description="The laboratory's MapAreaItem.location_id")


class GetMonumentProgressRequest(BaseRequest):
    """
    Ask for a monument's upgrade progress.

    Command: gmp
    Payload: {"ID": object_id}

    Client: ``C2SGetMonumentProgress`` (bundle line 86526), sent by the upgrade dialog with the map object's
    ``objectId`` (``CastleUpgradeLandmarkDialogProperties.progressCommandVO``, bundle line 51709)
    """

    command = "gmp"

    object_id: int = Field(validation_alias="ID", description="The monument's MapAreaItem.location_id")


class LandmarkProgress(BaseResponse):
    """
    A monument's or laboratory's upgrade points.

    The client turns the points into a level through the ``monuments`` and ``laboratories`` level tables
    (``UpgradableLandmarkMapobjectVO.updateProgress``, bundle line 42666), which the game data does not load.
    """

    object_id: int = Field(validation_alias="OID", description="The landmark's MapAreaItem.location_id")
    points: int = Field(validation_alias="CP", default=0, description="The upgrade points gathered")


class LaboratoryProgressResponse(LandmarkProgress):
    """
    A laboratory's upgrade points.

    Command: glp

    Client: ``GLPCommand.executeCommand`` (bundle line 130135)
    """

    command = "glp"


class MonumentProgressResponse(LandmarkProgress):
    """
    A monument's upgrade points.

    Command: gmp

    Client: ``GMPCommand.executeCommand`` (bundle line 130150)
    """

    command = "gmp"


__all__ = [
    "GetLaboratoryProgressRequest",
    "GetMonumentProgressRequest",
    "LaboratoryProgressResponse",
    "LandmarkProgress",
    "MonumentProgressResponse",
]
