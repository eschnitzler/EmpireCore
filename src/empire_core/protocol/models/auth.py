"""
Authentication protocol models.

Commands:
- lli: Login
- lre: Register new account
- vpn: Check username availability
- vln: Check if username exists (for login)
- lpp: Password recovery
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse

# =============================================================================
# LLI - Login
# =============================================================================


class LoginRequest(BaseRequest):
    """
    Login request.

    Command: lli
    Payload: {"NM": "username", "PW": "password", "L": "en", "AID": "..."}

    Note: The actual login is typically handled by the client's login() method
    which manages the full authentication flow including handshake.
    """

    command = "lli"

    username: str = Field(alias="NM")
    password: str = Field(alias="PW")
    language: str = Field(alias="L", default="en")
    app_id: str | None = Field(alias="AID", default=None)


class PlayerData(BaseRequest):
    """Player data returned after login."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_id: int = Field(alias="PID")
    player_name: str = Field(alias="PN")
    alliance_id: int | None = Field(alias="AID", default=None)
    alliance_name: str | None = Field(alias="AN", default=None)
    level: int = Field(alias="L", default=1)
    experience: int = Field(alias="XP", default=0)
    rubies: int = Field(alias="R", default=0)
    coins: int = Field(alias="C", default=0)


class LoginResponse(BaseResponse):
    """
    Login response.

    Command: lli
    Contains player data on successful login.
    """

    command = "lli"

    player: PlayerData | None = Field(alias="P", default=None)
    session_id: str | None = Field(alias="SID", default=None)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# LRE - Register
# =============================================================================


class RegisterRequest(BaseRequest):
    """
    Register new account request.

    Command: lre
    Payload: {"NM": "username", "PW": "password", "EM": "email", "L": "en"}
    """

    command = "lre"

    username: str = Field(alias="NM")
    password: str = Field(alias="PW")
    email: str = Field(alias="EM")
    language: str = Field(alias="L", default="en")


class RegisterResponse(BaseResponse):
    """
    Register response.

    Command: lre
    """

    command = "lre"

    success: bool = Field(alias="S", default=False)
    error_code: int = Field(alias="E", default=0)
    error_message: str | None = Field(alias="EM", default=None)


# =============================================================================
# VPN - Check Username Availability
# =============================================================================


class CheckUsernameAvailableRequest(BaseRequest):
    """
    Check if a username is available for registration.

    Command: vpn
    Payload: {"NM": "username"}
    """

    command = "vpn"

    username: str = Field(alias="NM")


class CheckUsernameAvailableResponse(BaseResponse):
    """
    Response for username availability check.

    Command: vpn
    """

    command = "vpn"

    available: bool = Field(alias="A", default=False)


# =============================================================================
# VLN - Check Username Exists (for login)
# =============================================================================


class CheckUsernameExistsRequest(BaseRequest):
    """
    Check if a username exists (for login validation).

    Command: vln
    Payload: {"NM": "username"}
    """

    command = "vln"

    username: str = Field(alias="NM")


class CheckUsernameExistsResponse(BaseResponse):
    """
    Response for username existence check.

    Command: vln
    """

    command = "vln"

    exists: bool = Field(alias="E", default=False)


# =============================================================================
# LPP - Password Recovery
# =============================================================================


class PasswordRecoveryRequest(BaseRequest):
    """
    Request password recovery email.

    Command: lpp
    Payload: {"EM": "email"} or {"NM": "username"}
    """

    command = "lpp"

    email: str | None = Field(alias="EM", default=None)
    username: str | None = Field(alias="NM", default=None)


class PasswordRecoveryResponse(BaseResponse):
    """
    Response for password recovery request.

    Command: lpp
    """

    command = "lpp"

    success: bool = Field(alias="S", default=False)
    error_code: int = Field(alias="E", default=0)


__all__ = [
    # LLI - Login
    "LoginRequest",
    "LoginResponse",
    "PlayerData",
    # LRE - Register
    "RegisterRequest",
    "RegisterResponse",
    # VPN - Username Available
    "CheckUsernameAvailableRequest",
    "CheckUsernameAvailableResponse",
    # VLN - Username Exists
    "CheckUsernameExistsRequest",
    "CheckUsernameExistsResponse",
    # LPP - Password Recovery
    "PasswordRecoveryRequest",
    "PasswordRecoveryResponse",
]
