"""
Trade reports: the goods a market carriage brought, read from its message in the mailbox.

Commands:
- mmn: read a market carriage's report
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.gamedata import CollectableRows
from empire_core.map.models import MapObject
from empire_core.map.models.areas import MapArea
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseRequest, BaseResponse, readable_list

logger = logging.getLogger(__name__)


class GetTradeReportRequest(BaseRequest):
    """
    Read a market carriage's report.

    Command: mmn
    Payload: {"MID": message_id}

    Client: ``C2SMarketCarriageNotifyVO`` (bundle line 136661), sent by
    ``CastleTradeMessageDialog.requestTradeData`` (bundle line 136636)
    """

    command = "mmn"

    message_id: int = Field(validation_alias="MID", description="The trade message's MessageInfo.message_id")


class TradeReportResponse(BaseResponse):
    """
    A market carriage's report: its two areas and the goods.

    Command: mmn
    Payload: {"O": [owner, ...], "gaa": {"AI": [owner_row, target_row]}, "R": [[key, entry, amount?], ...]}

    Client: ``MMNCommand.executeCommand`` (bundle line 125460) reads ``O`` with ``parseOwnerInfoArray``;
    ``CastleTradeMessageDialog.onGetTradeData`` (bundle line 136637) reads ``gaa.AI[0]`` and ``gaa.AI[1]``
    and the goods ``R``
    """

    command = "mmn"

    owners: list[MapObject] = Field(
        validation_alias="O", default_factory=list, description="Owner records for the two areas"
    )
    area: MapArea = Field(validation_alias="gaa", default_factory=MapArea, description="The two areas' map rows")
    goods: CollectableRows = Field(validation_alias="R", default=(), description="The goods sent")

    @field_validator("owners", mode="before")
    @classmethod
    def _owners(cls, value: Any) -> list[MapObject]:
        return readable_list(MapObject, value, warn=logger, what="owner records")

    @field_validator("area", mode="before")
    @classmethod
    def _area(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, MapArea)) else {}

    @property
    def owner_area(self) -> MapAreaItem | None:
        """The first row, the client's owner area; None when the reply has none."""
        return self.area.items[0] if self.area.items else None

    @property
    def target_area(self) -> MapAreaItem | None:
        """The second row, the client's target area; None when the reply has none."""
        return self.area.items[1] if len(self.area.items) > 1 else None


__all__ = ["GetTradeReportRequest", "TradeReportResponse"]
