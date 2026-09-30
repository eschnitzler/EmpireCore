"""
Authentication protocol models.

Commands:
- lli: Login
- slt: Login token push after a persistent login
- vck: Version check before the login
- lre: Register new account
- vpn: Check a new player name
- vln: Check a login name
- lpp: Password recovery
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from .base import BaseRequest, BaseResponse, build_command, list_or_empty
from .js import js_number_or_none, js_string, js_truthy
from .text import encode_json_text

_Number = Annotated[int | float | None, BeforeValidator(js_number_or_none)]
_Names = Annotated[list[str], BeforeValidator(lambda value: [n for n in list_or_empty(value) if isinstance(n, str)])]

# =============================================================================
# LLI - Login
# =============================================================================


class LoginRequest(BaseRequest):
    """
    Log in (``lli``), with a password or with the token an earlier persistent login got.

    :meth:`create` encodes the name and password as the login screen does.
    With a non-empty password the token goes out as null; without one, the
    token logs in and no password is sent.

    Client: ``C2SLoginVO`` (bundle line 131792), built by ``CastleLoginCommand`` (bundle line 131772)
    """

    command = "lli"

    connection_time: int = Field(
        alias="CONM", default=0, description="Milliseconds from opening the socket to the server's apiOK"
    )
    round_trip_time: int = Field(
        alias="RTM", default=0, description="Milliseconds from sending roundTrip to its answer; 0 before one came back"
    )
    login_id: int = Field(alias="ID", default=0, description="Always 0")
    persistent_login: bool = Field(
        alias="PL", default=False, description="Stay logged in; the server then pushes a login token (slt)"
    )
    username: str = Field(alias="NOM", description="The login name, encoded")
    password: str | None = Field(
        alias="PW", default=None, repr=False, description="The password, encoded; None to log in by token"
    )
    login_token: str | None = Field(alias="LT", default=None, repr=False, description="A persistent login's token")
    language: str = Field(alias="LANG", default="en", description="Language code of the chosen country")
    distributor_id: str = Field(alias="DID", default="0", description="Distributor id of the install")
    account_id: str = Field(alias="AID", description="Account (install) id")
    identity_management_id: str = Field(
        alias="KID", default="", description="Identity management id, empty outside Korea"
    )
    referrer: str = Field(alias="REF", default="", description="The page the game was opened from")
    gci: str = Field(alias="GCI", default="", description="The page's gci URL parameter")
    store_id: int = Field(alias="SID", default=9, description="Store id: 9 for the web")
    platform_id: int = Field(alias="PLFID", default=1, description="Platform id: 1 for the web")
    recaptcha_token: str | None = Field(
        alias="RCT", default=None, repr=False, description="A reCAPTCHA v3 token for the action 'login'"
    )

    @classmethod
    def create(cls, username: str, password: str | None = None, **fields: Any) -> LoginRequest:
        """A login request with the name and password encoded as the login screen encodes them."""
        return cls(
            NOM=encode_json_text(username),
            PW=None if password is None else encode_json_text(password),
            **fields,
        )

    def to_payload(self) -> dict[str, Any]:
        """The payload in ``C2SLoginVO``'s key order: a password nulls the token, a missing key is left out."""
        payload: dict[str, Any] = {
            "CONM": self.connection_time,
            "RTM": self.round_trip_time,
            "ID": self.login_id,
            "PL": 1 if self.persistent_login else 0,
            "NOM": self.username,
        }
        if self.password is not None:
            payload["PW"] = self.password
        if self.password:
            payload["LT"] = None
        elif self.login_token is not None:
            payload["LT"] = self.login_token
        payload.update(
            {
                "LANG": self.language,
                "DID": self.distributor_id,
                "AID": self.account_id,
                "KID": self.identity_management_id,
                "REF": self.referrer,
                "GCI": self.gci,
                "SID": self.store_id,
                "PLFID": self.platform_id,
            }
        )
        if self.recaptcha_token is not None:
            payload["RCT"] = self.recaptcha_token
        return payload


class LoginResponse(BaseResponse):
    """
    The reply to ``lli``.

    A successful login carries nothing; a refused one explains itself in
    these keys, depending on its status: ``IS_BANNED`` (27),
    ``EXISTING_MAPPING_WRONG_SERVER`` (368), ``LOGIN_COOLDOWN_ACTIVE`` (453)
    and ``NO_KOREA_USER_DATA_AVAILABLE`` (10003).

    Client: ``LLICommand.executeCommand`` (bundle line 120651)
    """

    command = "lli"

    account_deleted: Annotated[bool, BeforeValidator(js_truthy)] = Field(
        alias="GDPR", default=False, description="The banned account was deleted"
    )
    remaining_ban_seconds: _Number = Field(alias="RS", default=None, description="Seconds until the ban ends")
    instance_id: _Number = Field(alias="IID", default=None, description="Instance id of the server the account is on")
    remaining_cooldown_seconds: _Number = Field(
        alias="CD", default=None, description="Seconds until the next login attempt is allowed"
    )
    player_id: _Number = Field(alias="PID", default=None, description="The player's id")


# =============================================================================
# SLT - Login token
# =============================================================================


class LoginTokenResponse(BaseResponse):
    """
    The login token the server pushes after a persistent login (``PL`` 1).

    The client saves it and logs in with it later, as ``LoginRequest``'s
    token with no password.

    Client: ``SLTCommand.executeCommand`` (bundle line 120936)
    """

    command = "slt"

    login_token: Annotated[str | None, BeforeValidator(lambda value: None if value is None else js_string(value))] = (
        Field(alias="LT", default=None, repr=False, description="The token")
    )


# =============================================================================
# VCK - Version check
# =============================================================================

VERSION_CHECK_PLATFORM = "web-html5"


def build_version_check(zone: str, build_number: str, session_id: str, room_id: int) -> str:
    """
    The ``vck`` frame the client sends once it has joined the lobby.

    The server answers under ``vck``: status 0 lets the login go ahead,
    1 says the client's version is too low and 2 too high. The reply's first
    field is the server's build number.

    Client: ``BasicJoinedRoomCommand.execute`` (dll line 33011), reply read by
    ``CastleVCKCommand.executeCommand`` (bundle line 120444)
    """
    return build_command(zone, "vck", [build_number, VERSION_CHECK_PLATFORM, "", session_id], room_id)


# =============================================================================
# LRE - Register
# =============================================================================


class RegisterRequest(BaseRequest):
    """
    Register a new account (``lre``).

    Only the keys ``initialize`` sets and the reCAPTCHA token ``RCT`` are
    modelled. The client's object also
    carries the helper properties it was filled from (``username``,
    ``password``, ``campaignVars`` and so on) and, when it has them, an
    inviter code ``IC`` and a Steam ticket ``STK``; whether the server needs
    any of those is unverified.

    Client: ``C2SRegisterWithNameVO.initialize`` (bundle line 52392), filled by
    ``BasicRegisterUserCommand.composeRegisterUserVO`` (dll line 33134) and
    sent, with ``RCT`` last, by ``CastleRegisterUserCommand.sendRegisterUserCommandWithRecaptcha``
    (bundle line 110800)
    """

    command = "lre"

    distributor_id: int = Field(alias="DID", default=0, description="Distributor id of the install")
    connection_time: int = Field(
        alias="CONM", default=0, description="Milliseconds from opening the socket to the server's apiOK"
    )
    round_trip_time: int = Field(
        alias="RTM", default=0, description="Milliseconds from sending roundTrip to its answer"
    )
    campaign_partner_id: int = Field(alias="campainPId", default=0, description="Campaign partner id")
    campaign_creative: int = Field(alias="campainCr", default=0, description="Campaign creative")
    campaign_landing_page: int = Field(alias="campainLP", default=0, description="Campaign landing page")
    ad_id: int = Field(alias="adID", default=0, description="Campaign ad id")
    time_zone: int = Field(alias="timeZone", default=0, description="UTC offset in hours plus 13")
    username: str = Field(alias="PN", description="The new player's name")
    password: str | None = Field(alias="PW", default=None, repr=False, description="The new account's password")
    referrer: str = Field(alias="REF", default="", description="The page the game was opened from")
    language: str = Field(alias="LANG", default="en", description="Language code of the chosen country")
    account_id: str = Field(alias="AID", description="Account (install) id")
    gci: str = Field(alias="GCI", default="", description="The page's gci URL parameter")
    store_id: int = Field(alias="SID", default=9, description="Store id: 9 for the web")
    platform_id: int = Field(alias="PLFID", default=1, description="Platform id: 1 for the web")
    network_id: int = Field(alias="NID", description="Network id of the install")
    recaptcha_token: str | None = Field(
        alias="RCT", default=None, repr=False, description="A reCAPTCHA v3 token for the action 'submit'"
    )


class RegisterResponse(BaseResponse):
    """
    The reply to ``lre``: the new player's id, or name suggestions when the name was refused.

    Client: ``LRECommand.executeCommand`` (bundle line 120729)
    """

    command = "lre"

    player_id: _Number = Field(alias="PID", default=None, description="The new player's id")
    suggested_names: _Names = Field(alias="NS", default_factory=list, description="Free names like the refused one")


# =============================================================================
# VPN - Check a new player name
# =============================================================================


class CheckUsernameAvailableRequest(BaseRequest):
    """
    Check whether a name is free for a new player (``vpn``).

    Status 0 means it is; ``INVALID_NAME``, ``NAME_ALREADY_IN_USE``,
    ``NAME_HAS_ONLY_NUMBERS`` and ``USAGE_OF_BADWORDS`` say why not, and
    ``client.send`` raises them as a ``CommandError`` whose payload reads as
    :class:`CheckUsernameAvailableResponse`.

    Client: ``C2SValidateNewPlayerNameVO`` (bundle line 108936)
    """

    command = "vpn"

    username: str = Field(alias="PN", description="The name to check")


class CheckUsernameAvailableResponse(BaseResponse):
    """
    The reply to ``vpn``; a refusal carries free names like the refused one.

    Client: ``VPNCommand.executeCommand`` (bundle line 121103)
    """

    command = "vpn"

    suggested_names: _Names = Field(alias="NS", default_factory=list, description="Free names like the refused one")


# =============================================================================
# VLN - Check a login name
# =============================================================================


class CheckUsernameExistsRequest(BaseRequest):
    """
    Check a login name (``vln``).

    Status 0 means the name is valid; any other status is raised by
    ``client.send`` as a ``CommandError``.

    Client: ``C2SValidateLoginNameVO`` (bundle line 108927), reply read by
    ``VLNCommand.executeCommand`` (bundle line 121093)
    """

    command = "vln"

    username: str = Field(alias="NOM", description="The name to check")


class CheckUsernameExistsResponse(BaseResponse):
    """
    The reply to ``vln``, which carries nothing the client reads.

    Client: ``VLNCommand.executeCommand`` (bundle line 121093)
    """

    command = "vln"


# =============================================================================
# LPP - Password Recovery
# =============================================================================


class PasswordRecoveryRequest(BaseRequest):
    """
    Ask for a password recovery email (``lpp``).

    Client: ``BasicLostPasswordCommand.sendMessage`` (dll line 33056), sent from
    ``CastleLostPasswordDialog`` (bundle line 34746)
    """

    command = "lpp"

    email: str = Field(alias="MAIL", description="Email address of the account")


class PasswordRecoveryResponse(BaseResponse):
    """
    The reply to ``lpp``.

    Its status has its own codes, not ``GGEError``'s: 0 means sent, 1 a
    general error and 2 that no such player exists.

    Client: ``CastleLostPasswordCommand.execute`` (bundle line 131805)
    """

    command = "lpp"


__all__ = [
    # LLI - Login
    "LoginRequest",
    "LoginResponse",
    # SLT - Login token
    "LoginTokenResponse",
    # VCK - Version check
    "VERSION_CHECK_PLATFORM",
    "build_version_check",
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
