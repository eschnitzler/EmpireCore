"""The temporary server (Outer Realms) and the alliance battleground: entering them and their charge camps.

Commands:
- tsc: Pick the castle you enter a special server with
- tse: Which kind of server this session is on (push)
- tcc: Your castles on the special servers (push)
- tpc: A player's collector points on the temporary server
- gce: A charge camp's effect and its reroll
- ccr: Reroll a charge camp's effect
- ace: Take the rerolled effect
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.enums import ServerType
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals

if TYPE_CHECKING:
    from empire_core.gamedata import Effect


class SelectSpecialServerCastleRequest(BaseRequest):
    """
    Pick the pre-built castle you enter a special server with (``tsc``), sent on the main server.

    Client: ``C2STempServerSelectCastleVO`` (bundle line 45773), sent by
    ``CastleSpecialServerPreBuildCastleSelectionDialog.onConfirmed`` (bundle lines 27954-27955) with ``OC2`` set
    when the castle's costs hold rubies and ``PWR`` always false
    """

    command: ClassVar[str] = "tsc"

    castle_id: int = Field(validation_alias="ID", description="The pre-built castle's id")
    ruby_castle: bool = Field(validation_alias="OC2", default=False, description="The castle is priced in rubies")
    pay_with_rubies: Literal[0] = Field(
        validation_alias="PWR", default=0, description="Always 0: missing resources are never paid with rubies"
    )
    server_type: ServerType = Field(validation_alias="GST", description="The special server the castle is for")

    @field_serializer("ruby_castle")
    def _flag(self, value: bool) -> int:
        return int(value)


class SelectSpecialServerCastleResponse(BaseResponse):
    """
    The reply to ``tsc``, which carries nothing the client reads; on success the client connects to the server.

    Client: ``TSCCommand.executeCommand`` (bundle line 128531)
    """

    command: ClassVar[str] = "tsc"


class CurrentServer(BaseResponse):
    """
    The kind of server this session is on, pushed after the login.

    Client: ``TSECommand.executeCommand`` (bundle line 128917)
    """

    command: ClassVar[str] = "tse"

    server_type: EnumOrInt[ServerType] = Field(validation_alias="GST", description="The kind of server")
    is_cross_play: bool = Field(
        validation_alias="ICS", default=False, description="Whether the server is a cross-play one"
    )

    @field_validator("is_cross_play", mode="before")
    @classmethod
    def _cross_play(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @property
    def is_temporary_server(self) -> bool:
        """Whether this is the temporary server (Outer Realms)."""
        return self.server_type == ServerType.TEMPORARY

    @property
    def is_alliance_battleground(self) -> bool:
        """Whether this is the alliance battleground server."""
        return self.server_type == ServerType.ALLIANCE_BATTLEGROUND


class SpecialServerCastles(BaseResponse):
    """
    Your castles on the special servers, pushed when they change.

    Client: ``TCCCommand.executeCommand`` (bundle line 127354), which marks each event's castle bought when
    its id is above 0
    """

    command: ClassVar[str] = "tcc"

    temporary_server_castle_id: ClientInt = Field(
        validation_alias="TSCI", default=0, description="Your castle on the temporary server; 0 for none"
    )
    battleground_castle_id: ClientInt = Field(
        validation_alias="BGCI", default=0, description="Your castle on the alliance battleground; 0 for none"
    )

    @property
    def temporary_server_castle_bought(self) -> bool:
        """Whether you have a castle on the temporary server."""
        return self.temporary_server_castle_id > 0

    @property
    def battleground_castle_bought(self) -> bool:
        """Whether you have a castle on the alliance battleground."""
        return self.battleground_castle_id > 0


class GetTemporaryServerCollectorPointsRequest(BaseRequest):
    """
    Ask for a player's collector points on the temporary server (``tpc``).

    Client: ``C2SGetPlayerTempServerCollectorCurrencyVO`` (bundle line 134044), sent by
    ``CastleCollectorEventData.getTempserverCollectorAmount`` (bundle line 134001)
    """

    command: ClassVar[str] = "tpc"

    player_id: int = Field(validation_alias="PID", description="The player asked about")


class TemporaryServerCollectorPoints(BaseResponse):
    """
    A player's collector points on the temporary server.

    Client: ``TPCCommand.executeCommand`` (bundle line 128516), ``CastleCollectorEventData.parse_PCC``
    (bundle line 134004)
    """

    command: ClassVar[str] = "tpc"

    player_id: ClientInt = Field(validation_alias="PID", description="The player")
    amount: ClientInt = Field(validation_alias="CCA", description="The player's collector points")


class _ChargeCampRequest(BaseRequest):
    """A charge camp, named by its map position."""

    x: int = Field(validation_alias="XPOS", description="The charge camp's map x")
    y: int = Field(validation_alias="YPOS", description="The charge camp's map y")


class GetChargeCampEffectsRequest(_ChargeCampRequest):
    """
    Ask for a charge camp's effect and its rerolled one (``gce``).

    Client: ``C2STempServerGetChargeCampEffectsEventVO`` (bundle line 140318), sent when
    ``CastleTempServerEffectRerollDialog`` opens (bundle line 140279)
    """

    command: ClassVar[str] = "gce"


class ChargeCampEffect(BasePayload):
    """
    One charge camp effect: ``[effect_id, [value, ...]]``.

    Client: ``CastleTempServerData.parse_RerollChargeEffects`` (bundle line 140268) looks the effect up by id
    and reads the values with ``BonusVO.parseFromValueArray``
    """

    effect: EnumOrInt["Effect"] = Field(description="The effect")
    values: tuple[int | float, ...] = Field(default=(), description="The effect's values, in the effect's order")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            values = data[1] if len(data) > 1 else []
            return {"effect": data[0] if data else None, "values": values if isinstance(values, list) else [values]}
        return data


class ChargeCampEffects(BaseResponse):
    """
    A charge camp's effect, and the one a reroll offered in its place.

    Client: ``GCECommand.executeCommand`` (bundle line 128501), ``CastleTempServerData.parse_RerollChargeEffects``
    (bundle line 140268): the first ``CCOE`` entry is the effect, the first ``CCNE`` entry the rerolled one
    when its id is above 0
    """

    command: ClassVar[str] = "gce"

    current: ChargeCampEffect = Field(validation_alias="CCOE", description="The camp's effect")
    rerolled: ChargeCampEffect | None = Field(
        validation_alias="CCNE", default=None, description="The effect a reroll offered; None when none was rolled"
    )

    @field_validator("current", mode="before")
    @classmethod
    def _first(cls, value: Any) -> Any:
        return value[0] if isinstance(value, list) and value else value

    @field_validator("rerolled", mode="before")
    @classmethod
    def _first_rolled(cls, value: Any) -> Any:
        first = value[0] if isinstance(value, list) and value else None
        return first if isinstance(first, list) and first and js_int(first[0]) > 0 else None


class RerollChargeCampEffectRequest(_ChargeCampRequest):
    """
    Reroll a charge camp's effect for rubies (``ccr``).

    Client: ``C2STempServerChargeCampRerollEventVO`` (bundle line 140309), sent by
    ``CastleTempServerEffectRerollDialog.onClick`` (bundle line 140282); the dialog shows the reroll's
    ``c2Cost`` (bundle line 140279)
    """

    command: ClassVar[str] = "ccr"


class RerollChargeCampEffectResponse(BaseResponse):
    """
    The reply to ``ccr``, which carries nothing the client reads.

    Client: ``CCRCommand.executeCommand`` (bundle line 128488)
    """

    command: ClassVar[str] = "ccr"


class ApplyChargeCampEffectRequest(_ChargeCampRequest):
    """
    Take the rerolled effect in place of a charge camp's effect (``ace``).

    Client: ``C2STempServerApplyChargeCampEffectsEventVO`` (bundle line 140300), sent by
    ``CastleTempServerEffectRerollDialog.onClick`` (bundle line 140284) when the rerolled effect is picked
    """

    command: ClassVar[str] = "ace"


class ApplyChargeCampEffectResponse(BaseResponse):
    """
    The reply to ``ace``, which carries nothing the client reads.

    Client: ``ACECommand.executeCommand`` (bundle line 128475)
    """

    command: ClassVar[str] = "ace"


__all__ = [
    "ApplyChargeCampEffectRequest",
    "ApplyChargeCampEffectResponse",
    "ChargeCampEffect",
    "ChargeCampEffects",
    "CurrentServer",
    "GetChargeCampEffectsRequest",
    "GetTemporaryServerCollectorPointsRequest",
    "RerollChargeCampEffectRequest",
    "RerollChargeCampEffectResponse",
    "SelectSpecialServerCastleRequest",
    "SelectSpecialServerCastleResponse",
    "SpecialServerCastles",
    "TemporaryServerCollectorPoints",
]
