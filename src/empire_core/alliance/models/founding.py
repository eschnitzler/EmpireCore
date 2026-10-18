"""Founding an alliance using the ordinary client resource-payment flow."""

from typing import Any, Literal

from pydantic import Field, field_serializer, model_validator

from empire_core.alliance.models.membership import JoinOpenAllianceResponse
from empire_core.alliance.models.settings import ALLIANCE_DESCRIPTION_MAX_LENGTH, alliance_description
from empire_core.protocol.base import BaseRequest
from empire_core.protocol.js import js_parse_int
from empire_core.protocol.text import encode_json_text

# Client: AllianceConst (dllsplit line 18805). Coins and rubies may receive cost modifiers.
ALLIANCE_FOUND_COINS = 50
ALLIANCE_FOUND_RUBIES = 375
ALLIANCE_FOUND_WOOD = 100
ALLIANCE_FOUND_STONE = 50


class FoundAllianceRequest(BaseRequest):
    """Client: C2SFoundAllianceVO (bundle 44153–44156), onCreateNewAlliance (44138–44141).

    The normal request always sends PO=-1/PWR=0, including when its base price
    includes rubies. The separate resource-shortage replay (35222–35224)
    enables ruby payment for missing resources; this request never uses it.
    """

    command = "afo"
    name: str = Field(validation_alias="N", description="Alliance name")
    description: str = Field(validation_alias="D", description="Alliance description")
    language: str = Field(validation_alias="ALL", description="Alliance language code")
    private_offer_id: Literal[-1] = Field(
        default=-1, validation_alias="PO", description="Always -1 for no private offer"
    )
    pay_with_rubies: Literal[0] = Field(
        default=0, validation_alias="PWR", description="Always 0: missing resources are never paid with rubies"
    )
    open_join: bool = Field(
        default=True, validation_alias="IA", description="Whether players may join without an invitation"
    )

    @field_serializer("name")
    def _name(self, value: str) -> str:
        return encode_json_text(value)

    @field_serializer("description")
    def _description(self, value: str) -> str:
        return encode_json_text(alliance_description(value))

    @field_serializer("open_join")
    def _open_join(self, value: bool) -> int:
        return int(value)

    def validate_description(self) -> None:
        """Client: CastleJSONTextFieldRestrictor and founding dialog (bundle 44123)."""
        length = len(alliance_description(self.description).encode("utf-16-le", errors="surrogatepass")) // 2
        if length > ALLIANCE_DESCRIPTION_MAX_LENGTH:
            raise ValueError(
                f"alliance description must encode to at most {ALLIANCE_DESCRIPTION_MAX_LENGTH} characters"
            )


class FoundAllianceResponse(JoinOpenAllianceResponse):
    """Client: AFOCommand.executeCommand (bundle 121465–121466), reads A and gal.

    It carries the same alliance and membership records as JOACommand. Both ids
    must agree and name a created alliance before either record is applied.
    """

    command = "afo"

    @model_validator(mode="before")
    @classmethod
    def _created_ids(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("A", "gal"):
                block = value.get(key)
                if isinstance(block, dict) and js_parse_int(block.get("AID")) is None:
                    raise ValueError("founding reply has no readable alliance id")
        return value

    @model_validator(mode="after")
    def _created_alliance(self) -> "FoundAllianceResponse":
        if self.alliance.alliance_id < 0:
            raise ValueError("founding reply names no created alliance")
        return self


__all__ = [
    "ALLIANCE_FOUND_COINS",
    "ALLIANCE_FOUND_RUBIES",
    "ALLIANCE_FOUND_WOOD",
    "ALLIANCE_FOUND_STONE",
    "FoundAllianceRequest",
    "FoundAllianceResponse",
]
