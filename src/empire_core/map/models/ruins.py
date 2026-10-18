"""Ruins: how long until one frees for relocating onto, and the reminder for when it does."""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt


class RuinInfoRequest(BaseRequest):
    """
    Ask how long a ruin stays a ruin.

    Command: rui
    Payload: {"PX": x, "PY": y}

    Client: ``C2SRuinInfoVO`` (bundle line 109346), sent when a ruin is clicked while relocating
    (bundle line 39595)
    """

    command = "rui"

    x: int = Field(validation_alias="PX", description="The ruin's map x")
    y: int = Field(validation_alias="PY", description="The ruin's map y")


class RuinInfoResponse(BaseResponse):
    """
    How long a ruin stays a ruin.

    Command: rui

    Client: ``RUICommand.executeCommand`` (bundle line 126835); ``CastleRelocateRuinDialog`` shows
    ``ART`` as a time in seconds, and a waiting text once it is 0 or less (bundle lines 60529-60530)
    """

    command = "rui"

    remaining_seconds: ClientInt = Field(
        validation_alias="ART", default=0, description="Seconds until the ruin frees; 0 or less once it has"
    )
    x: ClientInt = Field(validation_alias="PX", default=0, description="The ruin's map x")
    y: ClientInt = Field(validation_alias="PY", default=0, description="The ruin's map y")


class RememberRuinRequest(BaseRequest):
    """
    Ask to be reminded when a ruin frees.

    Command: rmb
    Payload: {"PX": x, "PY": y}

    The client has no handler for an answer.

    Client: ``C2SRememberRuinVO`` (bundle line 126848), sent by the reminder button of
    ``CastleRelocateRuinDialog.onClick`` (bundle line 60533)
    """

    command = "rmb"

    x: int = Field(validation_alias="PX", description="The ruin's map x")
    y: int = Field(validation_alias="PY", description="The ruin's map y")


__all__ = ["RememberRuinRequest", "RuinInfoRequest", "RuinInfoResponse"]
