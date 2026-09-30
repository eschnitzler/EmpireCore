"""Alliance help: the help list, its pushes, and helping or asking for help.

Commands:
- ahl: The alliance help list
- ahh: One help request added or changed (push)
- ahd: One help request removed (push)
- ahf: Someone helped one of your requests (push)
- ahc: Help one request
- aha: Help every request
- ahr: Ask the alliance for help
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.enums import HelpType
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none, read_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_number_or_none, js_truthy

logger = logging.getLogger(__name__)

REPAIR_HELP_COOLDOWN_SECONDS = 10800
"""Seconds between two repair help requests. Client: ``AllianceConst.ALLIANCE_HELP_REPAIR_COOLDOWN`` (dll line 18772)"""


# =============================================================================
# Help request entries
# =============================================================================


class RecruitHelpParams(BasePayload):
    """
    The recruitment a recruit help request is for: its ``OP``.

    Client: ``AllianceHelpRequestRecruitParamsVO.parseParams`` (bundle line 51138)
    """

    recruit_id: ClientInt = Field(alias="RID", default=0, description="The recruitment's id")
    area_id: ClientInt = Field(alias="AID", default=0, description="The castle recruiting")
    space_id: ClientInt = Field(alias="SID", default=0, description="The recruiting building's space")
    recruitment_list_id: ClientInt = Field(alias="RLID", default=0, description="The recruitment list")


class HealHelpParams(BasePayload):
    """
    The wounded units a heal help request is for: its ``OP``.

    Client: ``AllianceHelpRequestHealParamsVO.parseParams`` (bundle line 50800)
    """

    hospital_entry_id: ClientInt = Field(alias="RID", default=0, description="The hospital entry")
    hospital_list_id: ClientInt = Field(alias="T", default=0, description="The hospital list the entry is on")
    area_id: ClientInt = Field(alias="AID", default=0, description="The castle with the hospital")
    space_id: ClientInt = Field(alias="SID", default=0, description="The hospital's space")


class BuildingHelpParams(BasePayload):
    """
    The building a repair or build help request is for: its ``OP``.

    Client: ``AllianceHelpRequestRepairParamsVO.parseParams`` (bundle line 50054),
    ``AllianceHelpRequestConstructionParamsVO.parseParams`` (bundle line 31702)
    """

    kingdom_id: ClientInt = Field(alias="KID", default=0, description="The castle's kingdom")
    area_id: ClientInt = Field(alias="AID", default=0, description="The castle")
    object_id: ClientInt = Field(alias="OID", default=0, description="The building's object id")


HelpParams = RecruitHelpParams | HealHelpParams | BuildingHelpParams

_PARAMS_BY_TYPE: dict[int, type[BasePayload]] = {
    HelpType.RECRUITMENT: RecruitHelpParams,
    HelpType.LOOP_RECRUIT: RecruitHelpParams,
    HelpType.RECRUITMENT_LIST: RecruitHelpParams,
    HelpType.HEAL_UNIT: HealHelpParams,
    HelpType.REPAIR: BuildingHelpParams,
    HelpType.BUILD: BuildingHelpParams,
}


_RECRUIT_TYPES = frozenset({HelpType.RECRUITMENT, HelpType.LOOP_RECRUIT, HelpType.RECRUITMENT_LIST})


class AllianceHelpRequest(BasePayload):
    """
    One request on the alliance help list.

    Deliberately more lenient than the client: ``AllianceHelpRequestParamsFactory.parseParams``
    (bundle line 133451) switches on the raw ``TID`` and throws for any other type
    or a missing ``OP``, losing the whole list; here such an entry is skipped
    alone, and ``TID`` is read with ``int()``, so ``"3"`` counts as 3.

    Client: ``AllianceHelpRequestData.parseHelpRequestEntry`` (bundle line 133416)
    """

    already_confirmed: bool = Field(alias="AC", default=False, description="You already helped this request")
    list_id: ClientInt = Field(alias="LID", default=0, description="The request's id on the help list")
    player_name: str | None = Field(alias="PN", default=None, description="The asking player's name")
    progress: ClientInt = Field(alias="P", default=0, description="Helps received so far")
    player_id: ClientInt = Field(alias="PID", default=0, description="The asking player's id")
    help_type: ClientInt = Field(alias="TID", default=0, description="What help is asked for, a HelpType value")
    params: HelpParams = Field(alias="OP", description="What the request is for; its shape follows help_type")
    remaining_seconds: int | float = Field(
        alias="RT", default=-1, description="Seconds until the request expires; -1 when it does not"
    )

    @model_validator(mode="before")
    @classmethod
    def _params_by_type(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        model = _PARAMS_BY_TYPE.get(js_int(data.get("TID")))
        if model is None:
            raise ValueError(f"no help params for help type {data.get('TID')!r}")
        op = data.get("OP")
        if not isinstance(op, dict):
            raise ValueError("help params must be an object")
        return {**data, "OP": model.model_validate(op)}

    @field_validator("player_name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        # Stored as sent; a value that is not text reads as no name instead of losing the entry
        return value if isinstance(value, str) else None

    @field_validator("already_confirmed", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator("remaining_seconds", mode="before")
    @classmethod
    def _expiry(cls, value: Any) -> int | float:
        # RT > -1 ? RT : -1, compared as a number
        number = js_number_or_none(value)
        return number if number is not None and number > -1 else -1

    @property
    def help_type_enum(self) -> HelpType | None:
        """``help_type`` as a :class:`HelpType`."""
        return enum_or_none(HelpType, self.help_type)


def _help_requests(value: Any) -> list[AllianceHelpRequest]:
    return readable_list(AllianceHelpRequest, value, warn=logger, what="alliance help requests")


# =============================================================================
# AHL - Alliance help list
# =============================================================================


class AllianceHelpListRequest(BaseRequest):
    """
    Ask for the alliance help list.

    Command: ahl
    Payload: {}

    The client never sends ahl: it has only the ``C2S_ALLIANCE_HELP_LIST``
    constant (bundle line 71), no VO and no call site. It reads the ahl the
    server sends, so this payload is not taken from the client.
    """

    command = "ahl"


class AllianceHelpListResponse(BaseResponse):
    """
    The alliance help list.

    Command: ahl

    Client: ``AHLCommand.executeCommand`` (bundle line 121904),
    ``AllianceHelpRequestData.parse_AHL`` (bundle line 133386)
    """

    command = "ahl"

    requests: list[AllianceHelpRequest] = Field(alias="AHL", default_factory=list, description="The help requests")
    seconds_since_repair_help: ClientInt = Field(
        alias="TSL", default=-1, description="Seconds since you last asked for repair help; -1 when never"
    )

    @field_validator("requests", mode="before")
    @classmethod
    def _requests(cls, value: Any) -> Any:
        return _help_requests(value)

    @property
    def repair_help_cooldown_seconds(self) -> int:
        """Seconds until you may ask for repair help again, 0 when you may now."""
        if self.seconds_since_repair_help == -1:
            return 0
        return max(0, REPAIR_HELP_COOLDOWN_SECONDS - self.seconds_since_repair_help)


# =============================================================================
# Help list pushes
# =============================================================================


class AllianceHelpRequestChanged(BaseResponse):
    """
    One help request added to the list or changed on it, pushed by the server.

    Command: ahh
    Payload: the request's own keys, plus ``TSL``

    Client: ``AHHCommand.executeCommand`` (bundle line 121889),
    ``AllianceHelpRequestData.parse_AHH`` (bundle line 133394) replaces the
    entry with the same ``LID`` or adds it
    """

    command = "ahh"

    request: AllianceHelpRequest | None = Field(default=None, description="The request; None when unreadable")
    seconds_since_repair_help: ClientInt | None = Field(
        alias="TSL", default=None, description="Seconds since you last asked for repair help; -1 when never"
    )

    @model_validator(mode="before")
    @classmethod
    def _request_is_the_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "request" in data:
            return data
        return {**data, "request": read_or_none(AllianceHelpRequest.model_validate, data, warn=logger, what="ahh")}


class AllianceHelpRequestRemoved(BaseResponse):
    """
    One help request taken off the list, pushed by the server.

    Command: ahd

    Client: ``AHDCommand.executeCommand`` (bundle line 121859),
    ``AllianceHelpRequestData.parse_AHD`` (bundle line 133396)
    """

    command = "ahd"

    list_id: ClientInt = Field(alias="LID", default=0, description="The removed request's id")


class AllianceHelpReceived(BaseResponse):
    """
    Someone helped one of your requests, pushed by the server.

    Command: ahf

    Client: ``AHFCommand.executeCommand`` (bundle line 121874),
    ``AllianceHelpRequestData.parse_AHF`` (bundle line 133384); the feedback
    component reads ``WID`` as a building's wod id (bundle line 133498)
    """

    command = "ahf"

    helper_name: str | None = Field(alias="PN", default=None, description="The helping player's name")
    list_id: ClientInt = Field(alias="LID", default=0, description="Your request's id")
    building_wod_id: ClientInt = Field(alias="WID", default=0, description="The helped building's wod id; 0 for none")


# =============================================================================
# AHC - Help one request
# =============================================================================


class HelpMemberRequest(BaseRequest):
    """
    Help one request on the alliance help list.

    Command: ahc
    Payload: {"LID": list_id, "KID": 1}

    The client always sends ``KID`` 1, ``WorldDessert.KINGDOM_ID`` (dll line 20019).

    Client: ``C2SAllianceHelpConfirmedVO`` (bundle line 105302), sent by
    ``AllianceHelpRequestScrollItem.onMouseClick`` (bundle line 105288)
    """

    command = "ahc"

    list_id: int = Field(alias="LID", description="The request's AllianceHelpRequest.list_id")
    kingdom_id: int = Field(alias="KID", default=1, description="Always 1, as the client sends it")

    @classmethod
    def for_request(cls, request: AllianceHelpRequest) -> HelpMemberRequest:
        """Help ``request``."""
        return cls(LID=request.list_id)


# =============================================================================
# AHA - Help every request
# =============================================================================


class HelpAllRequest(BaseRequest):
    """
    Help every request on the alliance help list.

    Command: aha
    Payload: {"KID": 15}

    Client: ``C2SAllianceHelpAllRequestVO`` (bundle line 105268) defaults ``KID``
    to 15 and ``CastleAllianceActionOverviewDialogHelpRequest.onClick`` (bundle
    line 105247) sends it with that default
    """

    command = "aha"

    kingdom_id: int = Field(alias="KID", default=15, description="Always 15, as the client sends it")


# =============================================================================
# AHR - Ask for help
# =============================================================================


class AskHelpRequest(BaseRequest):
    """
    Ask the alliance for help.

    Command: ahr
    Payload: {"ID": target_id, "T": type}

    For heal help the client puts the hospital list id in ``T``, not a help type.

    Client: ``C2SAllianceHelpRequestVO`` (bundle line 36196), sent by
    ``RingMenuButtonConstructionHelpRequest.onClick`` (bundle line 49994),
    ``RingMenuButtonRepairHelpRequest.onClick`` (bundle line 81402) and
    ``CastleAllianceHelpRequestButtonComponent.onClick`` (bundle line 50836)
    """

    command = "ahr"

    target_id: int = Field(alias="ID", description="The building, recruitment or hospital entry to help")
    type_id: int = Field(alias="T", description="The HelpType, or for heal help the hospital list id")

    @classmethod
    def build(cls, building_id: int) -> AskHelpRequest:
        """Ask for help building ``building_id``, the building's object id."""
        return cls(ID=building_id, T=HelpType.BUILD)

    @classmethod
    def repair(cls, building_id: int) -> AskHelpRequest:
        """Ask for help repairing ``building_id``, the building's object id."""
        return cls(ID=building_id, T=HelpType.REPAIR)

    @classmethod
    def recruit(cls, recruit_id: int, help_type: HelpType) -> AskHelpRequest:
        """Ask for help with the recruitment ``recruit_id``; ``help_type`` is one of the three recruit types."""
        if help_type not in _RECRUIT_TYPES:
            raise ValueError(f"{help_type!r} is not a recruit help type")
        return cls(ID=recruit_id, T=help_type)

    @classmethod
    def heal(cls, hospital_entry_id: int, hospital_list_id: int) -> AskHelpRequest:
        """Ask for help healing the hospital entry ``hospital_entry_id`` on list ``hospital_list_id``."""
        return cls(ID=hospital_entry_id, T=hospital_list_id)


class AskHelpResponse(BaseResponse):
    """
    The answer to asking for help; it carries nothing the client reads.

    Command: ahr

    Client: ``AHRCommand.executeCommand`` (bundle line 121919)
    """

    command = "ahr"


__all__ = [
    "REPAIR_HELP_COOLDOWN_SECONDS",
    "RecruitHelpParams",
    "HealHelpParams",
    "BuildingHelpParams",
    "HelpParams",
    "AllianceHelpRequest",
    "AllianceHelpListRequest",
    "AllianceHelpListResponse",
    "AllianceHelpRequestChanged",
    "AllianceHelpRequestRemoved",
    "AllianceHelpReceived",
    "HelpMemberRequest",
    "HelpAllRequest",
    "AskHelpRequest",
    "AskHelpResponse",
]
