"""The Outer Realms and Beyond the Horizon: entering them and their charge camps.

Commands:
- tsc: Pick the castle you enter a special server with
- tse: Which kind of server this session is on (push)
- tcc: Your castles on the special servers (push)
- tpc: A player's collector points on the Outer Realms
- gce: A charge camp's effect and its reroll
- ccr: Reroll a charge camp's effect
- ace: Take the rerolled effect
- gpr: When the special servers last ran
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal

from pydantic import BeforeValidator, Field, field_serializer, field_validator, model_validator

from empire_core.enums import ServerType
from empire_core.gamedata import EnumOrInt, HorizonSettingId, OuterRealmsSettingId
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, TimedPayload
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_loose_equals, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import Effect, PrebuiltCastle


class SelectSpecialServerCastleRequest(BaseRequest):
    """
    Pick the pre-built castle you enter a special server with (``tsc``), sent on the main server.

    Client: ``C2STempServerSelectCastleVO`` (bundle line 45773), sent by
    ``CastleSpecialServerPreBuildCastleSelectionDialog.onConfirmed`` (bundle lines 27954-27955) with ``OC2`` set
    when the castle's costs hold rubies and ``PWR`` always false
    """

    command: ClassVar[str] = "tsc"

    castle_id: EnumOrInt["PrebuiltCastle"] = Field(validation_alias="ID", description="The pre-built castle")
    ruby_castle: bool = Field(
        validation_alias="OC2", default=False, description="The castle's selection costs hold rubies, even 0 of them"
    )
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
    def is_outer_realms(self) -> bool:
        """Whether this is the Outer Realms."""
        return self.server_type == ServerType.OUTER_REALMS

    @property
    def is_horizon(self) -> bool:
        """Whether this is the Beyond the Horizon server."""
        return self.server_type == ServerType.HORIZON


class SpecialServerCastles(BaseResponse):
    """
    Your castles on the special servers, pushed when they change.

    Client: ``TCCCommand.executeCommand`` (bundle line 127354), which marks each event's castle bought when
    its id is above 0
    """

    command: ClassVar[str] = "tcc"

    outer_realms_castle_id: ClientInt = Field(
        validation_alias="TSCI", default=0, description="Your castle on the Outer Realms; 0 for none"
    )
    horizon_castle_id: ClientInt = Field(
        validation_alias="BGCI", default=0, description="Your castle on Beyond the Horizon; 0 for none"
    )

    @property
    def outer_realms_castle_bought(self) -> bool:
        """Whether you have a castle on the Outer Realms."""
        return self.outer_realms_castle_id > 0

    @property
    def horizon_castle_bought(self) -> bool:
        """Whether you have a castle on Beyond the Horizon."""
        return self.horizon_castle_id > 0


class GetOuterRealmsCollectorPointsRequest(BaseRequest):
    """
    Ask for a player's collector points on the Outer Realms (``tpc``).

    Client: ``C2SGetPlayerTempServerCollectorCurrencyVO`` (bundle line 134044), sent by
    ``CastleCollectorEventData.getTempserverCollectorAmount`` (bundle line 134001)
    """

    command: ClassVar[str] = "tpc"

    player_id: int = Field(validation_alias="PID", description="The player asked about")


class OuterRealmsCollectorPoints(BaseResponse):
    """
    A player's collector points on the Outer Realms.

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


class GetPreviousSpecialServerRunsRequest(BaseRequest):
    """
    Ask when the Outer Realms and Beyond the Horizon last ran (``gpr``).

    Client: ``C2SGlobalServerPreviousRunInfoVO`` (bundle line 69969), sent by
    ``CastleHighscoreDialog.getGlobalServerInfo`` (bundle line 27707)
    """

    command: ClassVar[str] = "gpr"


class PreviousSpecialServerRun(TimedPayload):
    """
    A special server's last run: when it ended.

    Client: ``GlobalServerPreviousRunInfoVO.parseParams`` (bundle line 128906)
    """

    seconds_since_end: ClientNumber = Field(
        validation_alias="ET", default=0, description="Seconds since the run ended when the values were read"
    )

    def ended_seconds_ago(self, now: float | None = None) -> float:
        """Seconds since the run ended."""
        return self.seconds_since_end + self._elapsed(now)


class PreviousOuterRealmsRun(PreviousSpecialServerRun):
    """
    The Outer Realms' last run: when it ended and its settings.

    Client: ``GlobalServerPreviousRunInfoVO.parseParams`` (bundle line 128906) looks ``TSID`` up in
    ``tempServerData.getConfigVOByID``
    """

    setting_id: Annotated[OuterRealmsSettingId, BeforeValidator(js_int)] = Field(
        validation_alias="TSID",
        default=OuterRealmsSettingId(0),
        description="The run's settings, a GameData.outer_realms_settings row",
    )


class PreviousHorizonRun(PreviousSpecialServerRun):
    """
    Beyond the Horizon's last run: when it ended and its settings.

    Client: ``GlobalServerPreviousRunInfoVO.parseParams`` (bundle line 128906) looks ``TSID`` up in
    ``allianceBattlegroundData.getConfigVOByID``
    """

    setting_id: Annotated[HorizonSettingId, BeforeValidator(js_int)] = Field(
        validation_alias="TSID",
        default=HorizonSettingId(0),
        description="The run's settings, a GameData.horizon_settings row",
    )


class PreviousSpecialServerRuns(BaseResponse):
    """
    The Outer Realms' and Beyond the Horizon's last runs.

    Client: ``GPRCommand.executeCommand`` (bundle line 128892), ``GlobalServerPreviousRunInfoVO.parseParams``
    (bundle line 128906), which reads each run only when it is set
    """

    command: ClassVar[str] = "gpr"

    outer_realms: PreviousOuterRealmsRun | None = Field(
        validation_alias="TS", default=None, description="The Outer Realms' last run; None for none"
    )
    horizon: PreviousHorizonRun | None = Field(
        validation_alias="ABG", default=None, description="Beyond the Horizon's last run; None for none"
    )

    @field_validator("outer_realms", "horizon", mode="before")
    @classmethod
    def _run(cls, value: Any) -> Any:
        return value if js_truthy(value) else None


__all__ = [
    "ApplyChargeCampEffectRequest",
    "ApplyChargeCampEffectResponse",
    "ChargeCampEffect",
    "ChargeCampEffects",
    "CurrentServer",
    "GetChargeCampEffectsRequest",
    "GetPreviousSpecialServerRunsRequest",
    "GetOuterRealmsCollectorPointsRequest",
    "PreviousHorizonRun",
    "PreviousOuterRealmsRun",
    "PreviousSpecialServerRun",
    "PreviousSpecialServerRuns",
    "RerollChargeCampEffectRequest",
    "RerollChargeCampEffectResponse",
    "SelectSpecialServerCastleRequest",
    "SelectSpecialServerCastleResponse",
    "SpecialServerCastles",
    "OuterRealmsCollectorPoints",
]
