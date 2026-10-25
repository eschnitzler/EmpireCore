"""Account and profile: the coat of arms (gem, cem, lca, gus, bus), player name, email address and password
(gnci, cpne, rmc, cmc, rsm, scp, scd, spslms, slms), the account's deletion (psd), gift packages (gpg), the
Goodgames gift (rgg), vouchers (rve) and message counts (mcd)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from empire_core.enums import CoatOfArmsBackground, GGEError, MessageType, SymbolLayout, VerificationLink
from empire_core.exceptions import CommandError
from empire_core.gamedata import CoatOfArmsSymbolId as Symbol
from empire_core.gamedata import CollectableKind, GameData, PackageId
from empire_core.map import OwnerCrest
from empire_core.messages import MessagesSentToday
from empire_core.network.connection import redact_frame
from empire_core.player import (
    AccountDeletion,
    ChangeCoatOfArmsRequest,
    ChangeEmailRequest,
    ChangeEmailResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    CoatOfArmsResponse,
    CoatOfArmsSymbolsResponse,
    CredentialsStatus,
    PlayerNameChangeInfoResponse,
    SetCredentialsRequest,
    SocialLoginMigrationStatus,
)
from empire_core.protocol.base import parse_response
from empire_core.protocol.packet import _redacted_prefix
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, request_payload, xt_packet

# Shaped as CrestVO.loadFromParamObject and CastleUserData.parse_GEM read a gem
GEM = {"IS": 1, "BGT": 1, "BGC1": 30512, "BGC2": 39783, "SPT": 2, "S1": 3, "SC1": 1644825, "S2": 4, "SC2": 0, "MCE": 1}

ITEMS = {
    "crestsymbols": [
        {"crestSymbolID": "3", "comment1": "basic"},
        {"crestSymbolID": "39", "requiredAchievementID": "1", "costC1": "120", "effects": "51&4"},
        {"crestSymbolID": "60", "requiredAchievementID": "20", "costC2": "500"},
    ],
    "playerNameChanges": [
        {"nameChangeID": "1", "costC2": "0"},
        {"nameChangeID": "2", "costC2": "10000"},
        {"nameChangeID": "3", "costC2": "12500"},
    ],
    "quests": [{"questID": "1200", "conditions": "createEmblem+1+"}],
}


def _client(script=None, state=None):
    client = make_client(script, state=state or GameState())
    client.game_data = GameData.parse("test", ITEMS)
    return client


def _feed_state(client):
    conn(client).on_packet = lambda packet: client.state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )


class TestCoatOfArms:
    def test_the_crest_and_may_change_are_read(self):
        crest = parse_response("gem", GEM)

        assert isinstance(crest, CoatOfArmsResponse) and isinstance(crest, OwnerCrest)
        assert crest.symbol_type is SymbolLayout.TWO_HORIZONTAL
        assert crest.background_type is CoatOfArmsBackground.TWO_HORIZONTAL
        assert (crest.symbol1, crest.symbol2, crest.may_change) == (3, 4, True)

    def test_an_unknown_layout_stays_an_int(self):
        crest = parse_response("gem", {**GEM, "SPT": 9, "BGT": 7})

        assert isinstance(crest, CoatOfArmsResponse)
        assert (crest.symbol_type, crest.background_type) == (9, 7)
        assert not isinstance(crest.symbol_type, SymbolLayout)

    def test_the_request_sends_the_design_without_hidden_symbols(self):
        crest = OwnerCrest(
            symbol_type=SymbolLayout.ONE_CENTERED, symbol1=Symbol(3), symbol2=Symbol(4), background_color1=5
        )

        assert ChangeCoatOfArmsRequest(coat_of_arms=crest).to_payload() == {
            "CAE": {"BGT": 0, "BGC1": 5, "BGC2": 5, "SPT": 1, "S1": 3, "SC1": 0, "S2": -1, "SC2": 0}
        }
        no_symbols = crest.model_copy(update={"symbol_type": SymbolLayout.NONE})
        sent = ChangeCoatOfArmsRequest(coat_of_arms=no_symbols).to_payload()["CAE"]
        assert (sent["SPT"], sent["S1"], sent["S2"]) == (0, -1, -1)

    def test_change_crest_keeps_the_new_crest_and_currencies(self):
        reply = {"gem": GEM, "gcu": {"C1": 100, "C2": 7}}
        client = _client({"cem": xt_packet("cem", reply)})
        _feed_state(client)

        response = client.player.change_coat_of_arms(OwnerCrest.model_validate(GEM))

        assert conn(client).requested == ["cem"]
        assert response.coat_of_arms is not None and response.coat_of_arms.symbol1 == 3
        assert client.player.coat_of_arms == response.coat_of_arms

    def test_an_active_create_emblem_quest_sends_the_avatar_first(self):
        client = _client()
        client.state.update_from_packet("qli", {"QL": [{"QID": 1200, "P": [0]}]})
        assert client.state.get_quests()

        client.player.change_coat_of_arms(OwnerCrest.model_validate(GEM))

        assert [request_payload(frame) for frame in conn(client).sent] == [
            {"CAE": {"BGT": 1, "BGC1": 30512, "BGC2": 39783, "SPT": 2, "S1": 3, "SC1": 1644825, "S2": 4, "SC2": 0}}
        ]
        assert "%lca%" in conn(client).sent[0] and conn(client).requested == ["cem"]

    def test_the_login_data_and_a_push_keep_the_crest(self):
        state = GameState()
        state.update_from_packet("gbd", {"gem": GEM})
        assert state.get_coat_of_arms() == parse_response("gem", GEM)

        state.update_from_packet("gem", {**GEM, "S1": 9})
        crest = state.get_coat_of_arms()
        assert crest is not None and crest.symbol1 == 9

    def test_a_refused_change_keeps_the_crest(self):
        state = GameState()
        state.update_from_packet("gem", GEM)
        state.update_from_packet("cem", {"gem": {**GEM, "S1": 9}}, error_code=1)
        crest = state.get_coat_of_arms()
        assert crest is not None and crest.symbol1 == 3


class TestCoatOfArmsSymbols:
    def test_the_symbols_are_read_and_kept(self):
        symbols = parse_response("gus", {"U": [39, "60"], "P": [60]})
        assert isinstance(symbols, CoatOfArmsSymbolsResponse)
        assert (
            symbols.earned_symbol_ids == (39, 60)
            and symbols.is_unlocked(Symbol(60))
            and not symbols.is_unlocked(Symbol(39))
        )

        state = GameState()
        state.update_from_packet("gus", {"U": None, "P": [39]})
        kept = state.get_coat_of_arms_symbols()
        assert kept is not None and kept.is_earned(Symbol(39)) and kept.earned_symbol_ids == ()

    def test_a_coin_symbol_needs_no_consent(self):
        client = _client()
        client.player.unlock_symbol(Symbol(39))
        assert conn(client).request_payloads == [("bus", {"CSI": 39})]

    def test_a_ruby_symbol_needs_consent(self):
        client = _client()
        with pytest.raises(ValueError, match="500 rubies"):
            client.player.unlock_symbol(Symbol(60))
        assert conn(client).request_payloads == []

        client.player.unlock_symbol(Symbol(60), spend_rubies=True)
        assert conn(client).request_payloads == [("bus", {"CSI": 60})]

    @pytest.mark.parametrize("symbol_id", [3, 999])
    def test_only_a_premium_symbol_is_bought(self, symbol_id):
        client = _client()
        with pytest.raises(ValueError, match="no premium symbol"):
            client.player.unlock_symbol(Symbol(symbol_id))


class TestName:
    def test_the_info_prices_the_next_change(self):
        game_data = GameData.parse("test", ITEMS)
        info = parse_response("gnci", {"PNCC": "1", "PNCD": 1.7e9})

        assert isinstance(info, PlayerNameChangeInfoResponse)
        assert (info.name_changes, info.cost_rubies(game_data)) == (1, 10000)
        assert info.remaining_cooldown_seconds(now=1.7e9 - 60) == 60
        assert PlayerNameChangeInfoResponse(name_changes=0).cost_rubies(game_data) == 0
        assert PlayerNameChangeInfoResponse(name_changes=20).cost_rubies(game_data) == 12500

    def test_the_first_change_is_free(self):
        client = _client({"gnci": xt_packet("gnci", {"PNCC": 0, "PNCD": 0})})

        client.player.change_player_name("New 100%")

        assert conn(client).request_payloads == [("gnci", {}), ("cpne", {"PN": "New 100&percnt;"})]

    def test_a_paid_change_needs_consent(self):
        client = _client({"gnci": [xt_packet("gnci", {"PNCC": 1, "PNCD": 0})] * 2})
        with pytest.raises(ValueError, match="10000 rubies"):
            client.player.change_player_name("New")
        assert [command for command, _ in conn(client).request_payloads] == ["gnci"]

        client.player.change_player_name("New", spend_rubies=True)
        assert conn(client).request_payloads[-1] == ("cpne", {"PN": "New"})

    def test_the_cooldown_refuses(self):
        client = _client({"gnci": xt_packet("gnci", {"PNCC": 0, "PNCD": 4e9})})
        with pytest.raises(ValueError, match="may change again"):
            client.player.change_player_name("New")

    def test_a_refused_name_raises(self):
        refusal = xt_packet("cpne", None, error_code=GGEError.NAME_ALREADY_IN_USE)
        client = _client({"gnci": xt_packet("gnci", {"PNCC": 0}), "cpne": refusal})
        with pytest.raises(CommandError):
            client.player.change_player_name("Taken")

    def test_the_state_keeps_the_info(self):
        client = _client({"gnci": xt_packet("gnci", {"PNCC": 3, "PNCD": 5})})
        _feed_state(client)
        client.player.get_player_name_change_info()
        assert client.player.player_name_change_info == PlayerNameChangeInfoResponse(name_changes=3, cooldown_ends_at=5)


class TestEmail:
    def test_the_email_address_is_a_secret_sent_as_the_client_escapes_it(self):
        request = ChangeEmailRequest(email=SecretStr("o'neil@example.com"))

        assert request.to_payload() == {"PMA": "oneil@example.com"}
        assert "example" not in repr(request)
        reply = parse_response("rmc", {"PMA": "oneil@example.com"})
        assert isinstance(reply, ChangeEmailResponse) and "example" not in repr(reply)
        assert "example" not in reply.model_dump_json() and "example" not in str(reply.model_dump())

    def test_the_email_requests(self):
        client = _client()

        client.player.change_email("me@example.com")
        client.player.cancel_email_change()
        client.player.resend_verification_link(VerificationLink.ACCOUNT_VERIFICATION)

        assert conn(client).request_payloads == [("rmc", {"PMA": "me@example.com"}), ("cmc", {}), ("rsm", {"T": 0})]

    def test_a_refused_email_raises(self):
        client = _client({"rmc": xt_packet("rmc", None, error_code=GGEError.INVALID_EMAIL)})
        with pytest.raises(CommandError):
            client.player.change_email("nope")

    def test_the_resent_link_is_read(self):
        assert parse_response("rsm", {"T": 1}).link is VerificationLink.EMAIL_CHANGE  # type: ignore[union-attr]


class TestPassword:
    def test_the_passwords_go_out_as_typed_and_never_print(self):
        request = ChangePasswordRequest(old_password=SecretStr("old pass"), new_password=SecretStr("new pass"))

        assert request.to_payload() == {"OPW": "old pass", "NPW": "new pass"}
        assert "pass" not in repr(request) and "pass" not in str(request)

    def test_a_change_logs_in_again_with_the_new_password(self):
        client = _client()

        client.player.change_password("secret", "better1")

        assert conn(client).request_payloads == [("scp", {"OPW": "secret", "NPW": "better1"})]
        assert client.password is not None and client.password.get_secret_value() == "better1"

    def test_a_wrong_password_raises_and_keeps_the_login_password(self):
        client = _client({"scp": xt_packet("scp", None, error_code=GGEError.INVALID_PASSWORD)})
        with pytest.raises(CommandError):
            client.player.change_password("wrong", "better1")
        assert client.password is not None and client.password.get_secret_value() == "secret"

    @pytest.mark.parametrize("password", ["abc", "with%sign", "   "])
    def test_a_password_the_client_refuses_is_not_sent(self, password):
        client = _client()
        with pytest.raises(ValueError, match="password"):
            client.player.change_password("secret", password)
        assert conn(client).request_payloads == []

    def test_the_reply_reads_the_confirmation(self):
        reply = parse_response("scp", {"NPW": "x"})
        assert isinstance(reply, ChangePasswordResponse) and reply.confirmed

    def test_the_migration_password(self):
        client = _client()
        client.player.set_migration_password("better1")
        assert conn(client).request_payloads == [("spslms", {"NPW": "better1"})]
        assert client.password is not None and client.password.get_secret_value() == "secret"

    def test_the_migration_status_is_read(self):
        status = parse_response("slms", {"hasPassword": 0})
        assert isinstance(status, SocialLoginMigrationStatus) and status.has_password is False
        assert parse_response("slms", {}).has_password is None  # type: ignore[union-attr]


class TestCredentials:
    def test_the_request_escapes_each_value_as_its_sender_does(self):
        request = SetCredentialsRequest(name="Ann's", email=SecretStr('a"b@example.com'), password=SecretStr("pa'ss"))

        assert request.to_payload() == {"PN": "Anns", "MAIL": "a&quot;b@example.com", "PW": "pa&145;ss"}
        assert "example" not in repr(request) and "ss" not in repr(request)

    def test_set_credentials_keeps_the_status_and_the_new_password(self):
        client = _client({"scd": xt_packet("scd", {"PNT": 0, "PWT": 0, "MLT": 1})})
        _feed_state(client)

        status = client.player.set_credentials(password="better1")

        assert conn(client).request_payloads == [("scd", {"PN": "", "MAIL": "", "PW": "better1"})]
        assert status == CredentialsStatus(email_is_temporary=True)
        assert client.player.credentials_status == status
        assert client.password is not None and client.password.get_secret_value() == "better1"

    def test_the_login_data_keeps_the_status(self):
        state = GameState()
        state.update_from_packet("gbd", {"scd": {"PNT": 1, "PWT": 1, "MLT": 0}})
        assert state.get_credentials_status() == CredentialsStatus(name_is_temporary=True, password_is_temporary=True)


class TestDeletion:
    def test_the_deletion_is_read(self):
        deletion = parse_response("psd", {"D": 1.8e9})
        assert isinstance(deletion, AccountDeletion)
        assert deletion.remaining_seconds(now=1.8e9 - 10) == 10 and deletion.is_scheduled(now=1.8e9 - 10)
        assert not deletion.is_scheduled(now=1.8e9 + 1)

    def test_minus_one_is_none_scheduled(self):
        deletion = parse_response("psd", {"D": -1})
        assert isinstance(deletion, AccountDeletion) and deletion.deleted_at is None and not deletion.is_scheduled()

    def test_the_push_is_kept(self):
        client = _client()
        client.state.update_from_packet("psd", {"D": 1.8e9})
        assert client.player.account_deletion == AccountDeletion(deleted_at=1.8e9)


class TestGifts:
    def test_send_gift_names_the_receiver_and_the_package(self):
        client = _client()
        client.player.send_gift_packages(1234, PackageId(56), 2)
        assert conn(client).request_payloads == [("gpg", {"RID": 1234, "PID": 56, "A": 2})]

    def test_the_game_data_describes_the_package(self):
        game_data = GameData.parse(
            "test", {"packages": [{"packageID": "401", "packageType": "tool", "isGiftPackage": "1", "unitID": "25"}]}
        )
        package = game_data.packages[PackageId(401)]
        assert (package.package_type, package.is_gift_package) == ("tool", True)

    def test_past_the_daily_limit_raises(self):
        client = _client({"gpg": xt_packet("gpg", None, error_code=GGEError.TOO_MANY_PACKAGES_SENT_TODAY)})
        with pytest.raises(CommandError):
            client.player.send_gift_packages(1234, PackageId(56))

    def test_no_amount_is_refused(self):
        with pytest.raises(ValueError):
            _client().player.send_gift_packages(1234, PackageId(56), 0)

    def test_the_goodgames_gift_is_listed_then_collected(self):
        reply = xt_packet("rgg", {"R": [["C1", 500], ["C2", 20]]})
        client = _client({"rgg": [reply, reply]})

        rewards = client.rewards.get_goodgames_gift()
        client.rewards.collect_goodgames_gift()

        assert conn(client).request_payloads == [("rgg", {"CR": 0}), ("rgg", {"CR": 1})]
        assert [(reward.kind, reward.amount) for reward in rewards] == [
            (CollectableKind.COINS, 500),
            (CollectableKind.RUBIES, 20),
        ]

    def test_a_voucher_is_sent_as_typed_and_a_refusal_raises(self):
        client = _client({"rve": [xt_packet("rve"), xt_packet("rve", None, error_code=1)]})
        client.rewards.redeem_voucher("ABC-123")
        assert conn(client).request_payloads == [("rve", {"VC": "ABC-123"})]
        with pytest.raises(CommandError):
            client.rewards.redeem_voucher("used")


class TestMessagesSentToday:
    def test_the_counts_are_read(self):
        counts = parse_response("mcd", {"MTC": [[2, 5], ["22", "3"], [36]]})
        assert isinstance(counts, MessagesSentToday)
        assert counts.sent == {MessageType.USER_OUT: 5, MessageType.ALLIANCE_NEWSLETTER: 3}

    def test_the_login_data_and_a_push_keep_them(self):
        client = _client()
        client.state.update_from_packet("gbd", {"mcd": {"MTC": [[2, 5]]}})
        assert client.messages.sent_today == MessagesSentToday(sent={MessageType.USER_OUT: 5})

        client.state.update_from_packet("mcd", {"MTC": [[2, 6]]})
        assert client.messages.sent_today == MessagesSentToday(sent={MessageType.USER_OUT: 6})

    def test_the_login_data_without_an_mcd_is_read_itself(self):
        state = GameState()
        state.update_from_packet("gbd", {"MTC": [[2, 1]]})
        assert state.get_messages_sent_today() == MessagesSentToday(sent={MessageType.USER_OUT: 1})


class TestRedaction:
    @pytest.mark.parametrize("command", ["scp", "scd", "spslms", "rmc"])
    def test_credential_frames_are_never_logged(self, command):
        frame = f'%xt%EmpireEx_21%{command}%1%{{"NPW":"hunter22","MAIL":"me@example.com"}}%'
        redacted = redact_frame(frame, command)
        assert "hunter22" not in redacted and "example" not in redacted

    def test_password_and_mail_keys_are_masked_elsewhere(self):
        frame = '%xt%EmpireEx_21%xyz%1%{"OPW":"a1","NPW":"b2","MAIL":"c@d.e","PMA":"f@g.h"}%'
        redacted = redact_frame(frame, "xyz")
        assert not any(secret in redacted for secret in ("a1", "b2", "c@d.e", "f@g.h"))


@pytest.mark.parametrize("key", ["OPW", "NPW", "MAIL", "PMA", "ABT"])
def test_a_degraded_frame_logs_no_credential(key: str):
    frame = f'%xt%rmc%1%0%{{"{key}":"secret@example.com"'
    assert "secret" not in _redacted_prefix(frame)
