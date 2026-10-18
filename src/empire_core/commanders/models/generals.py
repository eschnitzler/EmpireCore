"""
Generals progression: unlocking a general, raising its stars, and the generals hub's spins.

Commands:
- gue: unlock a general with its shards
- gsue: raise a general's star level with shards
- grf: clear a general's new and level-up flags
- gcs: the generals hub's characters, their free spins and cooldowns
- sct: spin a hub character's tombola with an offering
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.gamedata import Collectable, EnumOrInt, RewardId
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber

if TYPE_CHECKING:
    from empire_core.gamedata import CurrencyId, General, GeneralsHubCharacter


class UnlockGeneralRequest(BaseRequest):
    """
    Unlock a general with its shards.

    Command: gue
    Payload: {"GID": general_id}

    The server replies with no body.

    Client: ``C2SGeneralUnlockVO`` (bundle line 41682), ``GUECommand`` (bundle line 124266)
    """

    command = "gue"

    general_id: EnumOrInt["General"] = Field(validation_alias="GID", description="The general to unlock")


class UpgradeGeneralStarsRequest(BaseRequest):
    """
    Raise a general's star level with one of its shards.

    Command: gsue
    Payload: {"GID": general_id, "CID": currency_id}

    The server replies with no body.

    Client: ``C2SGeneralStarUpgradeVO`` (bundle line 74516), ``GSUECommand`` (bundle line 124253)
    """

    command = "gsue"

    general_id: EnumOrInt["General"] = Field(validation_alias="GID", description="The general to raise")
    currency_id: EnumOrInt["CurrencyId"] = Field(validation_alias="CID", description="The shard to spend")


class ClearGeneralFlagsRequest(BaseRequest):
    """
    Clear a general's new and level-up flags.

    Command: grf
    Payload: {"GID": general_id}

    The server replies with no body.

    Client: ``C2SGeneralResetFlagsVO`` (bundle line 67451), ``GRFCommand`` (bundle line 124229)
    """

    command = "grf"

    general_id: EnumOrInt["General"] = Field(validation_alias="GID", description="The general")


class GetGeneralsHubRequest(BaseRequest):
    """
    Request the generals hub's characters.

    Command: gcs
    Payload: {}

    Client: ``C2SGeneralsHUBStatusVO`` (bundle line 113160, no fields)
    """

    command = "gcs"


class GeneralsHubCharacterStatus(BasePayload):
    """
    One character of the generals hub: its free spins and when the last was taken.

    Client: ``GeneralsHubQuestVO.parseServerObject`` (bundle line 47009)
    """

    character_id: EnumOrInt["GeneralsHubCharacter"] = Field(validation_alias="CID", description="The character")
    free_spins: ClientInt = Field(validation_alias="FOA", default=0, description="Free spins waiting")
    last_free_spin: ClientNumber = Field(
        validation_alias="LFO", default=0, description="When the last free spin was taken, in epoch seconds"
    )
    cooldown_ends_at: int | float | None = Field(
        default=None,
        description=(
            "When the next free spin comes, in epoch seconds: last_free_spin plus the character's "
            "cooldown_seconds; set by client.commanders, None when the game data lacks the character"
        ),
    )


class GetGeneralsHubResponse(BaseResponse):
    """
    The generals hub's characters.

    Command: gcs
    Payload: {"CHR": [{"CID": character, "FOA": free spins, "LFO": last free spin}, ..]}

    Client: ``GCSCommand`` (bundle line 124187), ``GeneralsData.parse_GCS`` (bundle line 113080)
    """

    command = "gcs"

    characters: list[GeneralsHubCharacterStatus] = Field(
        validation_alias="CHR", default_factory=list, description="Each character's spins"
    )

    @field_validator("characters", mode="before")
    @classmethod
    def _readable(cls, value: Any) -> Any:
        return readable_list(GeneralsHubCharacterStatus, value)


class SpinGeneralsHubRequest(BaseRequest):
    """
    Spin a hub character's tombola with an offering.

    Command: sct
    Payload: {"CID": character, "OID": offering, "IF": 1 or 0, "AMT": amount}

    A free spin is one, sent with ``IF`` 1; a paid one spends ``AMT`` of the offering.

    Client: ``C2SSpinCharacterTombolaVO`` (bundle line 46994), ``GeneralsHubQuestComponent.onFreeQuest`` and
    ``onPaidQuest`` (bundle lines 75148-75149), ``GeneralsHubRewardsComponent.onClick`` (bundle line 74904)
    """

    command = "sct"

    character_id: EnumOrInt["GeneralsHubCharacter"] = Field(validation_alias="CID", description="The character")
    offering_id: EnumOrInt["CurrencyId"] = Field(
        validation_alias="OID", description="The offering, one of the character's offering_currency_ids"
    )
    free: bool = Field(validation_alias="IF", default=False, description="A free spin; sent as 1 or 0")
    amount: int = Field(validation_alias="AMT", default=1, description="Offerings to spend; 1 for a free spin")

    @field_serializer("free")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


def _reward_ids(value: Any) -> tuple[RewardId, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(RewardId(entry) for entry in value if isinstance(entry, int) and not isinstance(entry, bool))


class GeneralsHubReward(BasePayload):
    """
    One draw of a spin: rows of collectables (``RR``) or reward ids (``RW``), given ``count`` times.

    ``client.commanders.spin_generals_hub`` resolves reward ids into ``rewards`` through the game data.

    Client: ``GeneralsHubRewardsComponent.onRewardsGained`` (bundle line 74934) reads ``RR`` over ``RW`` and
    adds the list ``A`` times, once when ``A`` is unset
    """

    rarity: ClientInt = Field(validation_alias="R", default=0, description="The draw's rarity")
    rewards: tuple[Collectable, ...] = Field(validation_alias="RR", default=(), description="What one draw gave")
    reward_ids: tuple[RewardId, ...] = Field(validation_alias="RW", default=(), description="The rewards drawn")
    count: int = Field(validation_alias="A", default=1, description="How many times the draw was given")

    @field_validator("rewards", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> tuple[Collectable, ...]:
        return Collectable.from_rows(value)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _ids(cls, value: Any) -> tuple[RewardId, ...]:
        return _reward_ids(value)

    @field_validator("count", mode="before")
    @classmethod
    def _count(cls, value: Any) -> Any:
        return value or 1

    @model_validator(mode="before")
    @classmethod
    def _rows_over_ids(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("RR"):
            return {key: value for key, value in data.items() if key != "RW"}
        return data


class SpinGeneralsHubResponse(BaseResponse):
    """
    What a spin gave, and the character's spins after it.

    Command: sct
    Payload: {"CH": {"CID": .., "FOA": .., "LFO": ..}, "LTR": [{"R": rarity, "RR": rows | "RW": ids, "A": count}, ..]}

    Client: ``SCTCommand`` (bundle line 124303), ``GeneralsData.parse_SCT`` (bundle line 113073)
    """

    command = "sct"

    character: GeneralsHubCharacterStatus = Field(validation_alias="CH", description="The character after the spin")
    rewards: list[GeneralsHubReward] = Field(validation_alias="LTR", default_factory=list, description="The draws")

    @field_validator("rewards", mode="before")
    @classmethod
    def _readable(cls, value: Any) -> Any:
        return readable_list(GeneralsHubReward, value)


__all__ = [
    "UnlockGeneralRequest",
    "UpgradeGeneralStarsRequest",
    "ClearGeneralFlagsRequest",
    "GetGeneralsHubRequest",
    "GetGeneralsHubResponse",
    "GeneralsHubCharacterStatus",
    "SpinGeneralsHubRequest",
    "SpinGeneralsHubResponse",
    "GeneralsHubReward",
]
