"""The wire protocol: request and response bases, packets, error codes, text codecs and the login models."""

from empire_core.enums import GGEError
from empire_core.protocol.auth import (
    CheckUsernameAvailableRequest,
    CheckUsernameAvailableResponse,
    CheckUsernameExistsRequest,
    CheckUsernameExistsResponse,
    LoginRequest,
    LoginResponse,
    LoginTokenResponse,
    PasswordRecoveryRequest,
    PasswordRecoveryResponse,
    RegisterRequest,
    RegisterResponse,
)
from empire_core.protocol.base import (
    DEFAULT_ZONE,
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyTotals,
    GGECommand,
    PlayerInfo,
    Position,
    TimedPayload,
    TimedResponse,
    get_response_model,
    parse_response,
)
from empire_core.protocol.packet import Packet
from empire_core.protocol.text import decode_json_text, encode_json_text

__all__ = [
    "BasePayload",
    "BaseRequest",
    "BaseResponse",
    "CheckUsernameAvailableRequest",
    "CheckUsernameAvailableResponse",
    "CheckUsernameExistsRequest",
    "CheckUsernameExistsResponse",
    "CurrencyTotals",
    "DEFAULT_ZONE",
    "GGECommand",
    "GGEError",
    "LoginRequest",
    "LoginResponse",
    "LoginTokenResponse",
    "Packet",
    "PasswordRecoveryRequest",
    "PasswordRecoveryResponse",
    "PlayerInfo",
    "Position",
    "RegisterRequest",
    "RegisterResponse",
    "TimedPayload",
    "TimedResponse",
    "decode_json_text",
    "encode_json_text",
    "get_response_model",
    "parse_response",
]
