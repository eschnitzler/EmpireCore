"""
The equipment and gem inventory, as the login data and its pushes send it.

Commands:
- nrf: whether new relics wait to be seen
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator

from empire_core.protocol.base import BaseResponse
from empire_core.protocol.js import js_loose_equals


class NewRelicsResponse(BaseResponse):
    """
    Whether new relic equipment waits to be seen.

    Command: nrf, as a login section of ``gbd`` and a push.

    Client: ``NRFCommand`` (bundle line 124002), ``CastleEquipmentData.parseNRF`` (bundle line 143756)
    """

    model_config = ConfigDict(frozen=True)

    command = "nrf"

    has_new_relics: bool = Field(alias="NR", default=False, description="Whether new relics wait to be seen")

    @field_validator("has_new_relics", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


__all__ = ["NewRelicsResponse"]
