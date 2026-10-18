"""Alliance upgrades and boost purchases paid from the alliance treasury."""

from pydantic import Field, field_validator

from empire_core.alliance.models.info import AllianceBuilding, AllianceStorage
from empire_core.enums import AllianceBuffType
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse


class AllianceUpgradeRequest(BaseRequest):
    """Client: C2SAllianceUpgradeVO (bundle lines 27432–27435)."""

    command = "aug"
    building_type: EnumOrInt[AllianceBuffType] = Field(validation_alias="BT", description="Alliance buff series")
    level: int = Field(validation_alias="L", default=1, description="Selected temporary boost level; otherwise 1")


class AllianceUpgradeResponse(BaseResponse):
    """Client: AUGCommand.executeCommand (bundle lines 121660–121661).

    Only treasury and buffs are returned; no personal currency is debited here.
    """

    command = "aug"
    storage: AllianceStorage = Field(validation_alias="STO", description="Alliance treasury after the purchase")
    buildings: list[AllianceBuilding] = Field(validation_alias="ABL", description="Authoritative alliance buff list")

    @field_validator("buildings", mode="before")
    @classmethod
    def _buffs(cls, value: object) -> object:
        # AllianceInfoVO.parseABL (bundle 25961) accepts the ABL wrapper too.
        if isinstance(value, dict):
            value = value.get("ABL")
        if not isinstance(value, list) or any(
            not isinstance(row, dict) or not {"BT", "L", "CD"} <= row.keys() for row in value
        ):
            raise ValueError("upgrade reply needs complete BT/L/CD buff rows")
        return value


__all__ = ["AllianceUpgradeRequest", "AllianceUpgradeResponse"]
