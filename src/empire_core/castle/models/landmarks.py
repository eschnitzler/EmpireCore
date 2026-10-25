"""Kings towers, monuments and laboratories: upgrade progress, the ones you hold and their resets.

Commands:
- glp: A laboratory's progress
- gmp: A monument's progress
- gkl: Your kings towers, a login section of ``gbd`` and a push
- gml: Your monuments, a login section of ``gbd`` and a push
- gll: Your laboratories, a login section of ``gbd`` and a push
- mre: When monuments reset, a login section of ``gbd`` and a push
- lrr: When laboratories reset, a login section of ``gbd`` and a push
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from empire_core.gamedata import WodAmounts
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, TimedResponse, readable_list
from empire_core.protocol.js import ClientNumber

logger = logging.getLogger(__name__)


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


class OwnArea(BasePayload):
    """
    A map object of yours with the units stationed in it: ``[map_row, [[wod_id, amount], ...]]``.

    Client: ``parseAreaInfo`` reads the map row and ``fillFromWodAmountArray`` the units, in
    ``KingstowerMapobjectVO.parseGKL``, ``MonumentMapobjectVO.parseGML``, ``LaboratoryMapobjectVO.parseGLL``
    and ``CastleKingdomVillageInfoVO.parseParamObject`` (bundle lines 19066, 21663, 25952, 73469)
    """

    location: MapAreaItem = Field(description="The object's map row")
    units: WodAmounts = Field(default_factory=dict, description="Units stationed in it")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list) or not data:
            return data
        return {"location": MapAreaItem.from_list(data[0]), "units": data[1] if len(data) > 1 else []}


class OwnKingsTower(OwnArea):
    """One of your kings towers. Client: ``KingstowerMapobjectVO.parseGKL`` (bundle line 19066)"""


class OwnMonument(OwnArea):
    """One of your monuments. Client: ``MonumentMapobjectVO.parseGML`` (bundle line 21663)"""


class OwnLaboratory(OwnArea):
    """One of your laboratories. Client: ``LaboratoryMapobjectVO.parseGLL`` (bundle line 25952)"""


class KingsTowerListResponse(BaseResponse):
    """
    Your kings towers, listed whole.

    Command: gkl, as a login section of ``gbd``, a push and inside an ``mir``
    Payload: {"AI": [row, ...]}

    Client: ``GKLCommand.executeCommand`` (bundle line 129589), ``CastleKingstowerList.parseGKL``
    (bundle line 73493), which replaces the list; ``CastleUserData.parse_MIR`` (bundle line 9884)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gkl"

    kings_towers: list[OwnKingsTower] = Field(
        validation_alias="AI", default_factory=list, description="Your kings towers"
    )

    @field_validator("kings_towers", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        return readable_list(
            OwnKingsTower, value, accept=lambda row: isinstance(row, list), warn=logger, what="kings towers"
        )


class MonumentListResponse(BaseResponse):
    """
    Your monuments, listed whole.

    Command: gml, as a login section of ``gbd``, a push and inside an ``mir``
    Payload: {"AI": [row, ...]}

    Client: ``GMLCommand.executeCommand`` (bundle line 129638), ``CastleMonumentList.parseGML``
    (bundle line 73545), which replaces the list; ``CastleUserData.parse_MIR`` (bundle line 9884)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gml"

    monuments: list[OwnMonument] = Field(validation_alias="AI", default_factory=list, description="Your monuments")

    @field_validator("monuments", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        return readable_list(
            OwnMonument, value, accept=lambda row: isinstance(row, list), warn=logger, what="monuments"
        )


class LaboratoryListResponse(BaseResponse):
    """
    Your laboratories, listed whole.

    Command: gll, as a login section of ``gbd``, a push and inside an ``mir``
    Payload: {"AI": [row, ...]}

    Client: ``GLLCommand.executeCommand`` (bundle line 129604), ``CastleLaboratoryList.parseGLL``
    (bundle line 73521), which replaces the list; ``CastleUserData.parse_MIR`` (bundle line 9884)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gll"

    laboratories: list[OwnLaboratory] = Field(
        validation_alias="AI", default_factory=list, description="Your laboratories"
    )

    @field_validator("laboratories", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        return readable_list(
            OwnLaboratory, value, accept=lambda row: isinstance(row, list), warn=logger, what="laboratories"
        )


class LaboratoryResetResponse(TimedResponse):
    """
    When the laboratories reset next; a negative time means they reset now.

    Command: lrr, as a login section of ``gbd`` and a push
    Payload: {"LRS": seconds}

    Client: ``LRRCommand.executeCommand`` (bundle line 131638), ``CastleLaboratoryData.parseLRR``
    (bundle line 134899), which ignores an ``LRS`` of 0, resets the shown laboratories for a negative
    one and otherwise counts down to the next reset
    """

    command = "lrr"

    seconds: ClientNumber = Field(
        validation_alias="LRS", default=0, description="Seconds until the next reset when read; negative: resetting now"
    )

    def remaining_seconds(self, now: float | None = None) -> int:
        """Whole seconds until the next reset, 0 at least."""
        return int(max(0.0, self.seconds - self._elapsed(now)))


class MonumentResetResponse(TimedResponse):
    """
    When the monuments reset next; a negative time means they reset now.

    Command: mre, as a login section of ``gbd`` and a push
    Payload: {"MRS": seconds}

    Client: ``MRECommand.executeCommand`` (bundle line 131653), ``CastleMonumentData.parseMRE``
    (bundle line 46192), which ignores an ``MRS`` of 0, resets the shown monuments for a negative
    one and otherwise counts down to the next reset; ``GBDCommand.exec`` (bundle line 129430)
    """

    command = "mre"

    seconds: ClientNumber = Field(
        validation_alias="MRS", default=0, description="Seconds until the next reset when read; negative: resetting now"
    )

    def remaining_seconds(self, now: float | None = None) -> int:
        """Whole seconds until the next reset, 0 at least."""
        return int(max(0.0, self.seconds - self._elapsed(now)))


__all__ = [
    "KingsTowerListResponse",
    "MonumentListResponse",
    "MonumentResetResponse",
    "OwnArea",
    "OwnKingsTower",
    "OwnMonument",
    "LaboratoryListResponse",
    "LaboratoryResetResponse",
    "OwnLaboratory",
    "GetLaboratoryProgressRequest",
    "GetMonumentProgressRequest",
    "LaboratoryProgressResponse",
    "LandmarkProgress",
    "MonumentProgressResponse",
]
