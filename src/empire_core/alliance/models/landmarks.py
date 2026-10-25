"""Your alliance's landmarks, pushed when they change.

Commands:
- sll: The alliance's laboratories
- rca: The royal capital's alliance
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.map.models.items import MapAreaItem, parse_area_rows
from empire_core.protocol.base import BaseResponse

logger = logging.getLogger(__name__)


class AllianceLaboratoriesResponse(BaseResponse):
    """
    Your alliance's laboratories, listed whole.

    Command: sll
    Payload: {"ALA": [map_row, ...]}

    Client: ``SLLCommand.executeCommand`` (bundle line 122063), ``CastleAllianceData.parseSLL``
    (bundle line 11605) and ``AllianceLandmarksList.parseSLL`` / ``parseLaboratoryList`` (bundle lines
    42752, 42773), which replace your alliance's laboratories, with none for a missing ``ALA``
    """

    command = "sll"

    laboratories: list[MapAreaItem] = Field(
        validation_alias="ALA", default_factory=list, description="Map rows of the alliance's laboratories"
    )

    @field_validator("laboratories", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        items, skipped = parse_area_rows(value)
        if skipped:
            logger.warning(f"Skipped {skipped}/{len(value)} unparseable alliance laboratory rows")
        return items


class RoyalCapitalAllianceResponse(BaseResponse):
    """
    A push about the alliance holding the royal capital, which the client reads nothing from.

    Command: rca, pushed

    Client: ``RCACommand.executeCommand`` (bundle line 121991) parses the push and drops it
    """

    command = "rca"


__all__ = ["AllianceLaboratoriesResponse", "RoyalCapitalAllianceResponse"]
