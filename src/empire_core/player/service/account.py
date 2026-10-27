"""Your coat of arms, player name, email address and password."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import SecretStr

from empire_core.enums import QuestConditionType, VerificationLink
from empire_core.player.models.coat_of_arms import (
    ChangeCoatOfArmsRequest,
    ChangeCoatOfArmsResponse,
    CoatOfArmsResponse,
    CoatOfArmsSymbolsResponse,
    CreateAvatarRequest,
    UnlockSymbolRequest,
)
from empire_core.player.models.credentials import (
    PASSWORD_MIN_LENGTH,
    AccountDeletion,
    CancelEmailChangeRequest,
    ChangeEmailRequest,
    ChangePasswordRequest,
    ChangePlayerNameRequest,
    CredentialsStatus,
    PlayerNameChangeInfoRequest,
    PlayerNameChangeInfoResponse,
    ResendVerificationLinkRequest,
    SetCredentialsRequest,
    SetMigrationPasswordRequest,
)
from empire_core.protocol.text import SMARTFOX_INVALID_CHARS, is_smartfox_valid
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import CoatOfArmsSymbolId
    from empire_core.map.models.owners import OwnerCrest


def _require_valid_password(password: SecretStr) -> None:
    """
    Refuse a password the client would not send.

    Client: ``OptionsDialogChangePasswordItem.changePassword`` (bundle line 72828) checks the length and
    ``TextValide.isSmartFoxValide``
    """
    text = password.get_secret_value()
    if len(text) < PASSWORD_MIN_LENGTH or not is_smartfox_valid(text):
        raise ValueError(
            f"a password needs {PASSWORD_MIN_LENGTH} characters at least and none of {SMARTFOX_INVALID_CHARS}"
        )


class AccountMixin(ServiceMixin):
    # =========================================================================
    # Coat of arms
    # =========================================================================

    @property
    def coat_of_arms(self) -> CoatOfArmsResponse | None:
        """Your coat of arms, from the login data and the ``gem`` and :meth:`change_coat_of_arms` since; None before."""
        return self.client.state.get_coat_of_arms()

    @property
    def coat_of_arms_symbols(self) -> CoatOfArmsSymbolsResponse | None:
        """The premium symbols you have earned and unlocked, from the last ``gus``; None until one arrived."""
        return self.client.state.get_coat_of_arms_symbols()

    def change_coat_of_arms(self, coat_of_arms: OwnerCrest, *, timeout: float = 5.0) -> ChangeCoatOfArmsResponse:
        """
        Change your coat of arms to ``coat_of_arms``; the reply's is also kept in :attr:`coat_of_arms`.

        As in the client, no symbol is sent where the layout shows none. While an active quest asks you to create
        your coat of arms, it also goes out as your avatar (``lca``) first, which needs the game data.

        Args:
            coat_of_arms: The new coat of arms, e.g. :attr:`coat_of_arms` with fields changed
            timeout: Timeout in seconds

        Returns:
            Your coat of arms and your coins and rubies after the change

        Raises:
            GameDataNotLoadedError: A quest is active and the game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastlePremiumMarketPlaceDialogFlag.sendNewCrest`` (bundle line 77020),
        ``CastleQuestData.foundActiveQuestWithConditionType`` (bundle line 20339)
        """
        quest_ids = self.client.state.get_quests()
        if quest_ids:
            quests = self._require_game_data().quests
            if any(
                condition.condition_type == QuestConditionType.CREATE_EMBLEM
                for quest_id in quest_ids
                if (quest := quests.get(quest_id)) is not None
                for condition in quest.conditions
            ):
                self.send(CreateAvatarRequest(coat_of_arms=coat_of_arms))
        request = ChangeCoatOfArmsRequest(coat_of_arms=coat_of_arms)
        return self.request(request, ChangeCoatOfArmsResponse, timeout=timeout)

    def unlock_symbol(self, symbol_id: CoatOfArmsSymbolId, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Unlock for good a premium symbol an achievement has earned you, for its coin or ruby price.

        The game data's ``coat_of_arms_symbols`` lists the symbols. The new symbols arrive as a
        ``gus`` push into :attr:`coat_of_arms_symbols`, as the client expects them to.

        Args:
            symbol_id: The symbol, a premium ``coat_of_arms_symbols`` row
            spend_rubies: Allow the rubies a symbol priced in rubies costs
            timeout: Timeout in seconds

        Raises:
            ValueError: The game data has no such premium symbol, or it costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleBuyUnlockedCrestSymbolDialog.showLoaded`` and ``onClick`` (bundle lines 77181-77182),
        which show the coin price, else the ruby price; ``BUSCommand.executeCommand`` (bundle line 125032)
        """
        symbol = self._require_game_data().coat_of_arms_symbols.get(symbol_id)
        if symbol is None or not symbol.is_premium:
            raise ValueError(f"{symbol_id} is no premium symbol of the game data")
        self._require_spend_rubies(
            spend_rubies, f"symbol {symbol_id} costs {symbol.cost_rubies} rubies" if symbol.cost_rubies else None
        )
        self.execute(UnlockSymbolRequest(symbol_id=symbol_id), timeout=timeout)

    # =========================================================================
    # Player name, email address and password
    # =========================================================================

    @property
    def player_name_change_info(self) -> PlayerNameChangeInfoResponse | None:
        """Your player name changes and cooldown, from the last :meth:`get_player_name_change_info`; None before."""
        return self.client.state.get_player_name_change_info()

    def get_player_name_change_info(self, *, timeout: float = 5.0) -> PlayerNameChangeInfoResponse:
        """
        Request how often you have changed your name and when you may change it again; its
        ``cost_rubies(game_data)`` prices the next change.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SChangePlayerNameInfo`` (bundle line 46362), ``GNCICommand.executeCommand`` (bundle line 120604)
        """
        return self.request(PlayerNameChangeInfoRequest(), PlayerNameChangeInfoResponse, timeout=timeout)

    def change_player_name(self, name: str, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Change your player name to ``name``, the name other players see. This cannot be undone but by another
        paid change, and a cooldown follows it.

        The first change is free, each later one costs rubies (the game data's ``player_name_changes``), priced
        from a fresh :meth:`get_player_name_change_info`. Whether the name you log in with changes too is unverified;
        the client changes nothing about its login.

        Args:
            name: The new name
            spend_rubies: Allow the rubies the change costs
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: The cooldown runs, or the change costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError: The server refused: ``USAGE_OF_BADWORDS``, ``NAME_ALREADY_IN_USE``, ``INVALID_NAME``,
                ``NAME_HAS_ONLY_NUMBERS`` or ``COOLING_DOWN``
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleChangePlayerNameDialog.onClick`` and ``changeName`` (bundle lines 73164, 73185),
        ``CPNECommand.executeCommand`` (bundle line 120509)
        """
        info = self.get_player_name_change_info(timeout=timeout)
        if (seconds := info.remaining_cooldown_seconds()) > 0:
            raise ValueError(f"your name may change again in {seconds:.0f} seconds")
        rubies = info.cost_rubies(self._require_game_data())
        self._require_spend_rubies(spend_rubies, f"this player name change costs {rubies} rubies" if rubies else None)
        self.execute(ChangePlayerNameRequest(name=name), timeout=timeout)

    @property
    def credentials_status(self) -> CredentialsStatus | None:
        """Which of your player name, password and email address are temporary, from the last ``scd``; None before."""
        return self.client.state.get_credentials_status()

    def set_credentials(
        self,
        *,
        name: str = "",
        email: str | SecretStr = "",
        password: str | SecretStr = "",
        timeout: float = 5.0,
    ) -> CredentialsStatus:
        """
        Replace the temporary player name, email address or password the account started with; an empty one
        stays as it is. A new password replaces the one this client logs in again with.

        Args:
            name: Your new player name
            email: Your email address
            password: Your new password
            timeout: Timeout in seconds

        Returns:
            Which of them are still temporary, also kept in :attr:`credentials_status`

        Raises:
            ValueError: A password shorter than 4 characters or with a character the client refuses
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleSelectUserName.sendUsernameToServer`` (bundle line 143150), ``CastleSaveAccountDialog``
        (bundle lines 72996-72999), ``SCDCommand.executeCommand`` (bundle line 120922)
        """
        secret = password if isinstance(password, SecretStr) else SecretStr(password)
        if secret.get_secret_value():
            _require_valid_password(secret)
        status = self.request(
            SetCredentialsRequest(
                name=name, email=email if isinstance(email, SecretStr) else SecretStr(email), password=secret
            ),
            CredentialsStatus,
            timeout=timeout,
        )
        if secret.get_secret_value():
            self.client.password = secret
        return status

    def change_password(
        self, old_password: str | SecretStr, new_password: str | SecretStr, *, timeout: float = 5.0
    ) -> None:
        """
        Change your account's password from ``old_password`` to ``new_password``; on success this client logs
        in again with the new one.

        Raises:
            ValueError: A new password shorter than 4 characters or with a character the client refuses
            CommandError: The server refused, ``INVALID_PASSWORD`` for a wrong old password
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``OptionsDialogChangePasswordItem.changePassword`` (bundle line 72828), ``SCPCommand.executeCommand``
        (bundle line 120938)
        """
        old = old_password if isinstance(old_password, SecretStr) else SecretStr(old_password)
        new = new_password if isinstance(new_password, SecretStr) else SecretStr(new_password)
        _require_valid_password(new)
        self.execute(ChangePasswordRequest(old_password=old, new_password=new), timeout=timeout)
        self.client.password = new

    def set_migration_password(self, password: str | SecretStr, *, timeout: float = 5.0) -> None:
        """
        Give your account a password while its social login is migrated, as the client asks after an ``slms``
        push says it has none. This client's own login password is left as it is.

        Raises:
            ValueError: A password shorter than 4 characters or with a character the client refuses
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleChangePasswordForSocialMigrationDialog.changePassword`` (bundle line 56679),
        ``SPSLMSCommand.executeCommand`` (bundle line 121001)
        """
        secret = password if isinstance(password, SecretStr) else SecretStr(password)
        _require_valid_password(secret)
        self.execute(SetMigrationPasswordRequest(password=secret), timeout=timeout)

    def change_email(self, email: str | SecretStr, *, timeout: float = 5.0) -> None:
        """
        Change your account's email address to ``email``. The change stays in progress until its verification link
        is followed, and :meth:`cancel_email_change` cancels it.

        Raises:
            CommandError: The server refused: ``EMAIL_ALREADY_IN_USE``, ``INVALID_EMAIL`` or ``MAILDOMAIN_BLOCKED``
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleChangePlayerEmailDialog.changeEmail`` (bundle line 73243), ``RMCCommand.executeCommand``
        (bundle line 120886)
        """
        secret = email if isinstance(email, SecretStr) else SecretStr(email)
        self.execute(ChangeEmailRequest(email=secret), timeout=timeout)

    def cancel_email_change(self, *, timeout: float = 5.0) -> None:
        """
        Cancel the email change in progress; your email address stays as it is.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleChangePlayerEmailCancelDialog.onClick`` (bundle line 72770), ``CMCCommand.executeCommand``
        (bundle line 120496)
        """
        self.execute(CancelEmailChangeRequest(), timeout=timeout)

    def resend_verification_link(self, link: VerificationLink, *, timeout: float = 5.0) -> None:
        """
        Send another verification link: the account's, while its email address is unverified, or the email
        change's.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``OptionsDialogAccountDetails.onSendAgainEmail`` (bundle line 72747), ``RSMCommand.executeCommand``
        (bundle line 120908)
        """
        self.execute(ResendVerificationLinkRequest(link=link), timeout=timeout)

    @property
    def account_deletion(self) -> AccountDeletion | None:
        """When your account is deleted, from the last ``psd`` push; None until one arrived."""
        return self.client.state.get_account_deletion()
