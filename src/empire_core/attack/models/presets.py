"""Attack presets.

Commands:
- gas: Get attack presets
- sas: Save an attack preset
- upan: Rename an attack preset
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from empire_core.army.models.units import AttackWave, WaveFlank
from empire_core.gamedata import SupportToolSlots, WodAmount, WodAmountSlots
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse

# =============================================================================
# GAS / SAS - Attack presets
# =============================================================================


class GetPresetsRequest(BaseRequest):
    """
    Get the player's saved attack presets.

    Command: gas
    Payload: {}
    Client: ``C2SGetPreDefinedAttackSetupVO`` (bundle line 141803), sent by
    ``FightPresetData.loadDataFromServer``
    """

    command = "gas"


def _pairs(flat: list[int]) -> list[list[int]]:
    """``[wod, count, wod, count, ...]`` as ``[[wod, count], ...]``, a missing count read as 0."""
    return [[flat[i], flat[i + 1] if i + 1 < len(flat) else 0] for i in range(0, len(flat), 2)]


def _filled(slots: tuple[WodAmount, ...]) -> tuple[WodAmount, ...]:
    """The slots holding something; the client skips a slot whose wod id is -1."""
    return tuple(slot for slot in slots if slot.item is not None)


def _flat(slots: tuple[WodAmount, ...]) -> list[int]:
    return [value for item, amount in slots if item is not None for value in (item, amount)]


class PresetArmy(BaseModel):
    """
    A preset's army, decoded from its ``A`` string.

    ``A`` is a JSON list of flat ``[wod_id, count, wod_id, count, ...]`` arrays,
    one per container of a wave in ``CastleAttackWaveVO.flanks`` order: middle,
    left and right tools, then middle, left and right units. A seventh array,
    read only when the list has exactly seven entries, holds the support-tool
    wod ids.

    Client: ``FightPresetVO.getUnitWodId`` / ``getUnitCount`` /
    ``getSupportTools`` (bundle lines 141845-141848), ``CastleAttackWaveVO``
    constructor and ``flanks`` getter (bundle lines 99925, 99983)
    """

    middle_tools: WodAmountSlots = Field(default=(), description="Middle tool slots")
    left_tools: WodAmountSlots = Field(default=(), description="Left tool slots")
    right_tools: WodAmountSlots = Field(default=(), description="Right tool slots")
    middle_units: WodAmountSlots = Field(default=(), description="Middle unit slots")
    left_units: WodAmountSlots = Field(default=(), description="Left unit slots")
    right_units: WodAmountSlots = Field(default=(), description="Right unit slots")
    support_tools: SupportToolSlots = Field(
        default=(None, None, None),
        description="Support tools, one per slot; None for an empty slot, as a preset without any has",
    )

    @classmethod
    def from_arrays(cls, arrays: list[list[int]]) -> PresetArmy:
        """Decode the list ``A`` parses to."""

        def part(index: int) -> list[list[int]]:
            return _pairs(arrays[index]) if index < len(arrays) and isinstance(arrays[index], list) else []

        return cls.model_validate(
            {
                "middle_tools": part(0),
                "left_tools": part(1),
                "right_tools": part(2),
                "middle_units": part(3),
                "left_units": part(4),
                "right_units": part(5),
                "support_tools": arrays[6] if len(arrays) == 7 else (None, None, None),
            }
        )

    @classmethod
    def from_wave(cls, wave: AttackWave) -> PresetArmy:
        """
        The preset the client saves from a wave.

        Empty slots are dropped. The client saves no support tools: its
        ``setContentFromWave`` ignores the support tools it is handed and
        writes six arrays.

        Client: ``FightPresetVO.setContentFromWave`` (bundle line 141850),
        called by ``AttackDialogPresets.fillPresetFromWave`` (bundle line 101668)
        """
        return cls(
            middle_tools=_filled(wave.middle.tools),
            left_tools=_filled(wave.left.tools),
            right_tools=_filled(wave.right.tools),
            middle_units=_filled(wave.middle.units),
            left_units=_filled(wave.left.units),
            right_units=_filled(wave.right.units),
        )

    def to_arrays(self) -> list[list[int]]:
        """The six flat arrays the client saves, empty slots dropped."""
        return [
            _flat(self.middle_tools),
            _flat(self.left_tools),
            _flat(self.right_tools),
            _flat(self.middle_units),
            _flat(self.left_units),
            _flat(self.right_units),
        ]

    def to_wave(self) -> AttackWave:
        """The army as a wave, without the support tools."""
        return AttackWave(
            left=WaveFlank(tools=self.left_tools, units=self.left_units),
            middle=WaveFlank(tools=self.middle_tools, units=self.middle_units),
            right=WaveFlank(tools=self.right_tools, units=self.right_units),
        )


class AttackPreset(BasePayload):
    """
    One unlocked preset slot from the ``gas`` reply.

    Client: ``FightPresetData.parsePresets`` (bundle line 141770),
    ``FightPresetVO.update`` / ``deserialize`` (bundle lines 141830, 141836)
    """

    index: int = Field(alias="S", description="Preset slot index")
    name: str | None = Field(
        alias="SN",
        default=None,
        description="Preset name; None or empty means the game's default name",
    )
    raw_army: str | None = Field(alias="A", default=None, description="The army as a JSON string, see PresetArmy")

    def army(self) -> PresetArmy | None:
        """The decoded army, or None when the slot is empty or ``A`` does not parse."""
        if not self.raw_army:
            return None
        try:
            arrays = json.loads(self.raw_army)
        except ValueError:
            return None
        if not isinstance(arrays, list):
            return None
        try:
            return PresetArmy.from_arrays(arrays)
        except (TypeError, ValidationError):
            return None


class GetPresetsResponse(BaseResponse):
    """
    The unlocked preset slots.

    Command: gas
    Payload: {"S": [{"S": index, "SN": name, "A": "<JSON string>"}, ...]}
    Client: ``GASCommand.executeCommand`` (bundle line 122070) into
    ``FightPresetData.parsePresets`` (bundle line 141770), which counts every
    entry present as an unlocked slot
    """

    command = "gas"

    presets: list[AttackPreset] = Field(alias="S", default_factory=list, description="Unlocked preset slots")

    @field_validator("presets", mode="before")
    @classmethod
    def _skip_missing_entries(cls, value: Any) -> Any:
        return [entry for entry in value if entry is not None] if isinstance(value, list) else value


class SavePresetRequest(BaseRequest):
    """
    Save an army into a preset slot.

    Command: sas
    Payload: {"S": index, "A": "<JSON string of PresetArmy.to_arrays()>"}
    Client: ``C2SUpdatePreDefinedAttackSetupVO`` (bundle line 141820), with
    ``A`` from ``FightPresetVO.unitsAsString``, a ``JSON.stringify`` (bundle
    line 141843); sent by ``FightPresetData.savePresetArmy``
    """

    command = "sas"

    index: int = Field(alias="S", description="Preset slot index")
    raw_army: str = Field(alias="A", description="The army as a compact JSON string")

    @classmethod
    def create(cls, index: int, army: PresetArmy) -> SavePresetRequest:
        """Build the request for an army, serialised the way ``JSON.stringify`` does."""
        return cls(index=index, raw_army=json.dumps(army.to_arrays(), separators=(",", ":")))


class SavePresetResponse(BaseResponse):
    """
    Acknowledgement of a saved preset; the client reads nothing from it.

    Command: sas
    Client: ``SASCommand.executeCommand`` (bundle line 122086)
    """

    command = "sas"


PRESET_NAME_MAX_LENGTH = 15
"""The longest preset name the client's rename dialog takes.

Client: ``RenameFightPresetDialog.PRESET_MAX_CHARS`` (bundle line 45597)
"""


class RenamePresetRequest(BaseRequest):
    """
    Rename a preset slot.

    Command: upan
    Payload: {"S": index, "SN": name}

    The client sends the name as typed, unencoded, once its rename dialog has
    checked it: at most ``PRESET_NAME_MAX_LENGTH`` characters, passing
    ``TextValide.isSmartFoxValide``.

    Client: ``C2SUpdatePresetNameVO`` (bundle line 141794), sent by
    ``FightPresetData.savePresetName`` from ``RenameFightPresetDialog.sendCommand``
    (bundle line 45609)
    """

    command = "upan"

    index: int = Field(alias="S", description="Preset slot index")
    name: str = Field(alias="SN", description="The new name")


class RenamePresetResponse(BaseResponse):
    """
    Acknowledgement of a renamed preset; the client reads nothing from it.

    Command: upan
    Client: ``UPANCommand.executeCommand`` (bundle line 122114)
    """

    command = "upan"


__all__ = [
    "GetPresetsRequest",
    "GetPresetsResponse",
    "AttackPreset",
    "PresetArmy",
    "SavePresetRequest",
    "SavePresetResponse",
    "PRESET_NAME_MAX_LENGTH",
    "RenamePresetRequest",
    "RenamePresetResponse",
]
