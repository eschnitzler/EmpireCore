"""
Your player name, password and email address, and the account's deletion.

Passwords and email addresses are ``SecretStr``: they print masked and reach only the wire payload.

Commands:
- gnci: what your next name change costs, and its cooldown
- cpne: change your player name
- rmc: change your email address, pending its verification
- cmc: cancel the email change in progress
- rsm: send another verification link
- scp: change your password
- scd: set your player name, email address or password, and which of them are still temporary
- spslms: set a password while your social login is migrated
- slms: whether your account has a password, for the social login migration (push)
- psd: when your account is deleted (push)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, Field, SecretStr, field_serializer, field_validator

from empire_core.enums import VerificationLink
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import BaseRequest, BaseResponse, smartfox_text
from empire_core.protocol.js import ParseInt, js_number_or_none, js_truthy
from empire_core.protocol.text import encode_json_text

if TYPE_CHECKING:
    from empire_core.gamedata import GameData

_Flag = Annotated[bool, BeforeValidator(js_truthy)]
_NOT_SCHEDULED = -1

PASSWORD_MIN_LENGTH = 4
"""The shortest password the client sends.

Client: ``CredentialsValidationConstants.PASSWORD_MIN_LENGTH`` (dll line 32958)
"""


class PlayerNameChangeInfoRequest(BaseRequest):
    """
    Ask what your next name change costs, and how long its cooldown runs (``gnci``).

    Client: ``C2SChangePlayerNameInfo`` (bundle line 46362)
    """

    command = "gnci"


class PlayerNameChangeInfoResponse(BaseResponse):
    """
    How often you have changed your name, and when you may change it again.

    Client: ``GNCICommand.executeCommand`` (bundle line 120604), ``ChangePlayerNameData.parse_GNCI`` and
    ``resetNameChangeCooldownTimestamp`` (bundle lines 145460-145465), which count the cooldown to a Unix time
    in seconds
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gnci"

    name_changes: ParseInt = Field(validation_alias="PNCC", default=0, description="Name changes you have made")
    cooldown_ends_at: float = Field(
        validation_alias="PNCD", default=0, description="When you may change your name again, in Unix seconds"
    )

    @field_validator("cooldown_ends_at", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> float:
        seconds = js_number_or_none(value)
        return 0 if seconds is None else seconds

    def remaining_cooldown_seconds(self, now: float | None = None) -> float:
        """Seconds until you may change your name again, 0 when you may now."""
        return max(0.0, self.cooldown_ends_at - (time.time() if now is None else now))

    def cost_rubies(self, game_data: GameData) -> int:
        """
        The rubies your next name change costs: the price of change ``name_changes + 1``, the last price
        once you are past the last.

        Client: ``ChangePlayerNameData.parse_GNCI`` and ``getCurrentC2Cost`` (bundle lines 145460-145462)
        """
        prices = list(game_data.player_name_changes.values())
        if not prices:
            return 0
        number = min(self.name_changes + 1, prices[-1].name_change_id)
        return next((price.cost_rubies for price in prices if price.name_change_id == number), 0)


class ChangePlayerNameRequest(BaseRequest):
    """
    Change your player name (``cpne``).

    Client: ``C2SChangePlayerName`` (bundle line 73199), sent by ``CastleChangePlayerNameDialog.changeName``
    (bundle line 73185) with the name through ``TextValide.getValideSmartFoxText``
    """

    command = "cpne"

    name: str = Field(validation_alias="PN", description="The new name")

    @field_serializer("name")
    def _text(self, name: str) -> str:
        return smartfox_text(name)


class ChangePlayerNameResponse(BaseResponse):
    """
    The reply to ``cpne``, which carries nothing the client reads.

    Refusals: ``USAGE_OF_BADWORDS``, ``NAME_ALREADY_IN_USE``, ``INVALID_NAME``, ``NAME_HAS_ONLY_NUMBERS``,
    ``COOLING_DOWN``.

    Client: ``CPNECommand.executeCommand`` (bundle line 120509)
    """

    command = "cpne"


class ChangeEmailRequest(BaseRequest):
    """
    Change your email address (``rmc``); the change waits for its verification link.

    Client: ``C2SChangePlayerEmail`` (bundle line 73255), sent by ``CastleChangePlayerEmailDialog.changeEmail``
    (bundle line 73243) with the address through ``TextValide.getValideSmartFoxText``
    """

    command = "rmc"

    email: SecretStr = Field(validation_alias="PMA", repr=False, description="The new email address")

    @field_serializer("email")
    def _text(self, email: SecretStr) -> str:
        return smartfox_text(email.get_secret_value())


class ChangeEmailResponse(BaseResponse):
    """
    The email address the change waits on.

    Refusals: ``EMAIL_ALREADY_IN_USE``, ``INVALID_EMAIL``, ``MAILDOMAIN_BLOCKED``.

    Client: ``RMCCommand.executeCommand`` (bundle line 120886), which keeps it as ``PlayerEmailData.newEmail``
    """

    command = "rmc"

    new_email: SecretStr | None = Field(
        validation_alias="PMA", default=None, repr=False, description="The email address the change waits on"
    )


class CancelEmailChangeRequest(BaseRequest):
    """
    Cancel the email change in progress (``cmc``).

    Client: ``C2SCancelEmailChangeProgress`` (bundle line 72783)
    """

    command = "cmc"


class CancelEmailChangeResponse(BaseResponse):
    """
    The reply to ``cmc``, which carries nothing the client reads.

    Client: ``CMCCommand.executeCommand`` (bundle line 120496)
    """

    command = "cmc"


class ResendVerificationLinkRequest(BaseRequest):
    """
    Send another verification link (``rsm``).

    Client: ``C2SResendEmail`` (bundle line 72758), sent by ``OptionsDialogAccountDetails.onSendAgainEmail``
    (bundle line 72747)
    """

    command = "rsm"

    link: VerificationLink = Field(validation_alias="T", description="Which verification link to send")


class ResendVerificationLinkResponse(BaseResponse):
    """
    Which verification link was sent.

    Client: ``RSMCommand.executeCommand`` (bundle line 120908) reads ``CommKeys.RESEND_MAIL_ACTION_TYPE``
    (``T``, dll line 18946)
    """

    command = "rsm"

    link: VerificationLink | int | None = Field(
        validation_alias="T", default=None, description="The verification link sent"
    )

    @field_validator("link", mode="before")
    @classmethod
    def _link(cls, value: Any) -> VerificationLink | int | None:
        number = js_number_or_none(value)
        return None if number is None else known(VerificationLink, int(number))


class ChangePasswordRequest(BaseRequest):
    """
    Change your password (``scp``). The client sends both passwords as typed.

    Client: ``C2SChangePasswordVO`` (bundle line 72883), sent by ``OptionsDialogChangePasswordItem.changePassword``
    (bundle line 72828)
    """

    command = "scp"

    old_password: SecretStr = Field(validation_alias="OPW", repr=False, description="Your password now")
    new_password: SecretStr = Field(validation_alias="NPW", repr=False, description="The new password")

    @field_serializer("old_password", "new_password")
    def _plain(self, password: SecretStr) -> str:
        return password.get_secret_value()


class ChangePasswordResponse(BaseResponse):
    """
    The reply to ``scp``; ``INVALID_PASSWORD`` refuses a wrong password.

    Client: ``SCPCommand.executeCommand`` (bundle line 120938), which reads only whether ``NPW`` is set, and that
    only for a persistent login
    """

    command = "scp"

    confirmed: _Flag = Field(validation_alias="NPW", default=False, description="Whether the server confirmed it")


class SetCredentialsRequest(BaseRequest):
    """
    Set your player name, email address or password (``scd``), an empty one left as it is.

    Client: ``C2SSetCredentials`` (bundle line 28298), sent by ``CastleSelectUserName.sendUsernameToServer``
    (bundle line 143150) with the name through ``TextValide.getValideSmartFoxText``, and by
    ``CastleSaveAccountDialog.sendDataToServer`` (bundle line 72999) with the mail and password through
    ``getValideSmartFoxJSONTextMessage``
    """

    command = "scd"

    name: str = Field(validation_alias="PN", default="", description="The new name, empty to keep yours")
    email: SecretStr = Field(
        validation_alias="MAIL", default=SecretStr(""), repr=False, description="The email address, empty for none"
    )
    password: SecretStr = Field(
        validation_alias="PW", default=SecretStr(""), repr=False, description="The new password, empty for none"
    )

    @field_serializer("name")
    def _name(self, name: str) -> str:
        return smartfox_text(name)

    @field_serializer("email", "password")
    def _encoded(self, secret: SecretStr) -> str:
        return encode_json_text(secret.get_secret_value())


class CredentialsStatus(BaseResponse):
    """
    Which of your player name, password and email address are still the temporary ones the account started with.

    Command: scd, as a login section of ``gbd`` and the reply to setting them; ``INVALID_OBJECT_STATE`` refuses.

    Client: ``SCDCommand.executeCommand`` (bundle line 120922), ``CastleUserData.parse_SCD`` (bundle line 9922),
    ``CommKeys.IS_PLAYER_NAME_TEMPORARY``, ``IS_PASSWORD_TEMPORARY`` and ``IS_EMAIL_TEMPORARY`` (dll line 18945)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "scd"

    name_is_temporary: _Flag = Field(validation_alias="PNT", default=False, description="The name is temporary")
    password_is_temporary: _Flag = Field(validation_alias="PWT", default=False, description="The password is temporary")
    email_is_temporary: _Flag = Field(
        validation_alias="MLT", default=False, description="The email address is temporary"
    )


class SetMigrationPasswordRequest(BaseRequest):
    """
    Set a password for your account while its social login is migrated (``spslms``), sent as typed.

    Client: ``C2SSetPasswordForSocialLoginMigrationVO`` (bundle line 103408), sent by
    ``CastleChangePasswordForSocialMigrationDialog.changePassword`` (bundle line 56679)
    """

    command = "spslms"

    password: SecretStr = Field(validation_alias="NPW", repr=False, description="The new password")

    @field_serializer("password")
    def _plain(self, password: SecretStr) -> str:
        return password.get_secret_value()


class SetMigrationPasswordResponse(BaseResponse):
    """
    The reply to ``spslms``, which carries nothing the client reads.

    Client: ``SPSLMSCommand.executeCommand`` (bundle line 121001)
    """

    command = "spslms"


class SocialLoginMigrationStatus(BaseResponse):
    """
    Whether your account already has a password, as its social login is migrated; the client then asks for one or
    confirms it.

    Command: slms, a push.

    Client: ``SLMSCommand.executeCommand`` (bundle line 120956), which does nothing without ``hasPassword``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "slms"

    has_password: bool | None = Field(
        validation_alias="hasPassword", default=None, description="Whether it has a password; None when not said"
    )

    @field_validator("has_password", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool | None:
        return None if value is None else js_truthy(value)


class AccountDeletion(BaseResponse):
    """
    When your account is deleted, if its deletion was asked for.

    Command: psd, a push.

    Client: ``PSDCommand.executeCommand`` (bundle line 131797), ``DeleteAccountData.isAccountDeletionStarted`` and
    ``remainingTimeTillDeleteTimeStamp`` (bundle lines 145480-145483), which count to a Unix time in seconds
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "psd"

    deleted_at: float | None = Field(
        validation_alias="D", default=None, description="When the account is deleted, in Unix seconds; None for never"
    )

    @field_validator("deleted_at", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> float | None:
        seconds = js_number_or_none(value)
        return None if seconds is None or seconds == _NOT_SCHEDULED else seconds

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until the account is deleted, 0 when no deletion is scheduled."""
        if self.deleted_at is None:
            return 0.0
        return max(0.0, self.deleted_at - (time.time() if now is None else now))

    def is_scheduled(self, now: float | None = None) -> bool:
        """Whether a deletion is scheduled and still to come."""
        return self.remaining_seconds(now) > 0


__all__ = [
    "PASSWORD_MIN_LENGTH",
    "CancelEmailChangeRequest",
    "CancelEmailChangeResponse",
    "ChangePasswordRequest",
    "ChangePasswordResponse",
    "ChangePlayerNameRequest",
    "ChangePlayerNameResponse",
    "CredentialsStatus",
    "PlayerNameChangeInfoRequest",
    "PlayerNameChangeInfoResponse",
    "ChangeEmailRequest",
    "ChangeEmailResponse",
    "ResendVerificationLinkRequest",
    "ResendVerificationLinkResponse",
    "AccountDeletion",
    "SetCredentialsRequest",
    "SetMigrationPasswordRequest",
    "SetMigrationPasswordResponse",
    "SocialLoginMigrationStatus",
]
