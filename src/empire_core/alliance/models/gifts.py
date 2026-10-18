"""Alliance gifts received as pushes and their collection rewards."""

from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.enums import CollectableKind
from empire_core.gamedata import Collectable, CollectableRows
from empire_core.protocol.base import BaseRequest, BaseResponse, TimedPayload
from empire_core.protocol.js import ClientInt, ClientNumber, js_same_number


class AllianceGift(TimedPayload):
    """Client: AllianceGiftVO.parseArray/remainingTimeInSeconds (bundle 131974–131981)."""

    gift_id: ClientInt = Field(validation_alias="ID", description="Gift id used for collection")
    seconds_left: ClientNumber = Field(validation_alias="T", description="Seconds before this gift expires")
    reward: Collectable = Field(description="The gift to unpack on collection")

    @model_validator(mode="before")
    @classmethod
    def _row(cls, value: Any) -> Any:
        if isinstance(value, list):
            if len(value) < 4 or value[0] != CollectableKind.ALLIANCE_GIFT.server_key:
                raise ValueError("alliance gift must be an AG row with expiry and id")
            rewards = Collectable.from_rows([value])
            if len(rewards) != 1:
                raise ValueError("alliance gift contains no reward")
            return {"ID": value[3], "T": value[2], "reward": rewards[0]}
        return value

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until expiration, zero once it has expired."""
        return max(0.0, self.seconds_left - self._elapsed(now))


class AllianceGiftReceived(BaseResponse):
    """Client: AGRCommand/parse_AGR (bundle lines 121867–121868, 131949–131951)."""

    command = "agr"
    gift: AllianceGift = Field(validation_alias="G", description="New alliance gift")


class CollectAllianceGiftRequest(BaseRequest):
    """Client: C2SAllianceGiftCollect (bundle lines 105252–105254)."""

    command = "agc"
    gift_id: int = Field(validation_alias="ID", description="Gift to collect")

    def accepts_reply(self, payload: Any) -> bool:
        return not isinstance(payload, dict) or "ID" not in payload or js_same_number(payload["ID"], self.gift_id)


class CollectAllianceGiftResponse(BaseResponse):
    """Client: CastleAllianceGiftData.parse_AGC (bundle lines 131937–131939).

    Rewards use CollectableParserS2CParamList.createList (bundle 40567–40580).
    """

    command = "agc"
    gift_id: ClientInt = Field(validation_alias="ID", description="Collected gift id")
    rewards: CollectableRows = Field(validation_alias="R", description="Rewards unpacked from the gift")

    @field_validator("rewards", mode="before")
    @classmethod
    def _rewards(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("gift rewards must be an array")
        if value and not Collectable.from_rows(value):
            raise ValueError("gift rewards contain no readable entries")
        return value


__all__ = ["AllianceGift", "AllianceGiftReceived", "CollectAllianceGiftRequest", "CollectAllianceGiftResponse"]
