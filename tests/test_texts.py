"""The game's texts from the language CDN: lookup, placeholders, cache, TTL, backoff, and the error messages.

Every HTTP call is stubbed: ``requests.get`` is replaced so an un-stubbed code
path fails loudly instead of reaching the real GGS CDN.
"""

import threading
import time
from typing import Any

import pytest
import requests

from empire_core import texts
from empire_core.exceptions import AccountBannedError, CommandError, LoginCooldownError, LoginError, WrongServerError
from empire_core.protocol.errors import GGEError
from empire_core.texts import (
    RETRY_AFTER_FAILURE,
    LocalizedNumber,
    PlainText,
    cached_text,
    fill,
    get_texts,
    has_text,
    number,
    text,
)

LANG_FILE = {
    "@metadata": {"versionNo": "4372"},
    "errorCode_120": "This player's level is too low.",
    "errorCode_140": "You have to occupy this outpost for {0} before you can surrender it.",
    "travelSpeedBonusPerField": "+{0}% for every {1} fields",
    "currency_name_1MinSkip": "Skip 1 minute",
    "Dialog_OK": "OK",
    "dialog_ok": "Okay",
    "empty": "",
    "generic_kForThousand": "k",
    "generic_mForMillion": "M",
    "kingdomName_Dessert": "The Burning Sands",
    "ci_effect_recruitCostReduction": "-{0}% recruitment costs",
}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", _forbidden)


class FakeCdn:
    """Stands in for :func:`empire_core.texts.fetch_texts`, counting calls."""

    def __init__(self, error: Exception | None = None, delay: float = 0.0) -> None:
        self.error = error
        self.delay = delay
        self.langs: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, lang: str = "en") -> dict[str, Any]:
        with self._lock:
            self.langs.append(lang)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return {
            key: f"{value} ({lang})" if lang != "en" and isinstance(value, str) else value
            for key, value in LANG_FILE.items()
        }


def stub_cdn(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> FakeCdn:
    cdn = FakeCdn(**kwargs)
    monkeypatch.setattr(texts, "fetch_texts", cdn)
    return cdn


class TestText:
    def test_a_key_in_any_case(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("errorCode_120") == "This player's level is too low."
        assert text("ERRORCODE_120") == "This player's level is too low."
        assert text("currency_name_1minskip") == "Skip 1 minute"

    def test_of_keys_differing_in_case_the_later_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("Dialog_OK") == "Okay"

    def test_placeholders_are_filled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("travelSpeedBonusPerField", 5, 10) == "+5% for every 10 fields"

    def test_a_missing_or_empty_text_reads_as_its_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("no_such_key", 1) == "no_such_key"
        assert text("empty") == "empty"

    def test_the_metadata_is_not_a_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert "@metadata" not in get_texts()

    def test_a_language_is_fetched_once_and_apart_from_others(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch)

        assert text("dialog_ok", lang="de") == "Okay (de)"
        text("errorCode_120", lang="de")
        text("errorCode_120")

        assert cdn.langs == ["de", "en"]

    def test_a_cdn_failure_gives_the_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch, error=requests.ConnectionError("lang down"))

        assert text("errorCode_120") == "errorCode_120"


class TestFill:
    @pytest.mark.parametrize(
        ("template", "args", "filled"),
        [
            ("+{0}% for every {1} fields", (5, 10), "+5% for every 10 fields"),
            ("{0} and {0}", ("a",), "a and a"),
            ("{1} before {0}", ("a", "b"), "b before a"),
            ("only {0} of {1}", (3,), "only 3 of {1}"),
            ("{0}", (2.0,), "2"),
            ("{0}", (2.5,), "2.5"),
            ("{0} or {1}", (True, False), "true or false"),
            ("{0}", (None,), "null"),
            ("no placeholders", (1,), "no placeholders"),
        ],
    )
    def test_like_the_client(self, template: str, args: tuple[object, ...], filled: str) -> None:
        assert fill(template, *args) == filled

    def test_is_plain(self) -> None:
        assert fill("{0} {1}", 1234567, "dialog_ok") == "1234567 dialog_ok"


class TestLocalizedArguments:
    @pytest.mark.parametrize(
        ("args", "filled"),
        [
            ((5, 10), "+5% for every 10 fields"),
            ((1234, 2.5), "+1,234% for every 2.5 fields"),
            ((12.345, 0.004), "+12.35% for every 0 fields"),
            ((99999, 100000), "+99,999% for every 100k fields"),
            ((123456, 1500000), "+123.46k% for every 1.5M fields"),
            ((-250000, "12"), "+-250k% for every 12 fields"),
            ((True, None), "+1% for every 0 fields"),
            (("dialog_OK", "not a key"), "+Okay% for every not a key fields"),
            (("", "currency_name_1MinSkip"), "+% for every Skip 1 minute fields"),
            (
                (LocalizedNumber(3.14159, fractional_digits=1), LocalizedNumber(250000)),
                "+3.1% for every 250,000 fields",
            ),
            ((LocalizedNumber(250000, compact=True), 0), "+250k% for every 0 fields"),
            ((PlainText("150000"), PlainText("dialog_OK")), "+150000% for every dialog_OK fields"),
        ],
    )
    def test_like_the_castle_client(
        self, monkeypatch: pytest.MonkeyPatch, args: tuple[object, ...], filled: str
    ) -> None:
        stub_cdn(monkeypatch)

        assert text("travelSpeedBonusPerField", *args) == filled

    def test_without_grouping(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("travelSpeedBonusPerField", 1234, 99999, grouping=False) == "+1234% for every 99999 fields"

    def test_german_numbers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("travelSpeedBonusPerField", 1234.5, 2500000, lang="de") == (
            "+1.234,5% for every 2,5M (de) fields (de)"
        )

    def test_cached_text_localizes_from_the_loaded_texts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts("en")

        assert cached_text("errorCode_140", 150000) == (
            "You have to occupy this outpost for 150k before you can surrender it."
        )


class TestNumber:
    @pytest.mark.parametrize(
        ("value", "written"),
        [(0, "0"), (2.5, "2.5"), (2.345, "2.35"), (-2.345, "-2.34"), (1234567.891, "1,234,567.89"), (0.1 + 0.2, "0.3")],
    )
    def test_plain(self, value: float, written: str) -> None:
        assert number(value) == written

    def test_compact_needs_no_texts_below_the_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch)

        assert number(99999.5, compact=True) == "99,999.5"
        assert cdn.langs == []
        assert number(100000, compact=True) == "100k"
        assert number(-1000000, compact=True) == "-1M"
        assert cdn.langs == ["en"]

    def test_a_missing_abbreviation_text_is_left_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(texts, "fetch_texts", lambda lang="en": {})

        assert number(250000, compact=True) == "250"

    def test_digits_and_grouping(self) -> None:
        assert number(1234.5678, fractional_digits=0) == "1,235"
        assert number(1234.5678, fractional_digits=3, grouping=False) == "1234.568"
        assert number(1234.5, lang="de") == "1.234,5"
        assert number(1234.5, lang="fr") == "1,234.5"

    def test_right_to_left_is_the_callers_to_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert number(250000, compact=True, right_to_left=True) == "250 k"
        assert number(250000, compact=True, lang="ar") == "250k (ar)"

    def test_a_localized_number_has_no_fraction_digits_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert text("travelSpeedBonusPerField", LocalizedNumber(2.5), 1.25) == "+3% for every 1.25 fields"
        assert text("travelSpeedBonusPerField", LocalizedNumber(250000, compact=True, right_to_left=True), 0) == (
            "+250 k% for every 0 fields"
        )


class TestHasText:
    def test_a_non_empty_text_in_any_case(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert has_text("ERRORCODE_120")
        assert not has_text("empty")
        assert not has_text("no_such_key")


class TestCachedText:
    def test_never_fetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch)

        assert cached_text("errorCode_120") is None
        assert cdn.langs == []

    def test_reads_loaded_texts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts("en")

        assert cached_text("errorCode_140", "2 hours") == (
            "You have to occupy this outpost for 2 hours before you can surrender it."
        )
        assert cached_text("no_such_key") is None
        assert cached_text("errorCode_120", lang="de") is None

    def test_does_not_wait_on_a_download(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts("en")
        texts._fetched_at["en"] = 0.0
        stub_cdn(monkeypatch, delay=0.5)
        refresh = threading.Thread(target=get_texts)
        refresh.start()
        time.sleep(0.05)

        started = time.monotonic()
        assert cached_text("errorCode_120") == "This player's level is too low."
        assert time.monotonic() - started < 0.25
        refresh.join(timeout=10)


class TestCache:
    def test_the_texts_are_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch)

        get_texts()
        get_texts()

        assert len(cdn.langs) == 1

    def test_force_refresh_fetches_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch)

        get_texts()
        get_texts(force_refresh=True)

        assert len(cdn.langs) == 2

    def test_failure_backoff_does_not_refetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        assert get_texts() == {}
        get_texts()
        texts._failed_at["en"] = time.time() - (RETRY_AFTER_FAILURE + 1)
        get_texts()

        assert len(cdn.langs) == 2

    def test_the_cache_expires_and_a_failed_refresh_keeps_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts()
        texts._fetched_at["en"] = time.time() - (texts.CACHE_TTL + 1)
        cdn = stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        assert get_texts()["errorcode_120"] == "This player's level is too low."
        assert len(cdn.langs) == 1

    def test_concurrent_callers_fetch_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cdn = stub_cdn(monkeypatch, delay=0.05)

        threads = [threading.Thread(target=get_texts) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(cdn.langs) == 1

    def test_a_download_does_not_hold_up_fresh_texts_or_another_language(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts("en")
        stub_cdn(monkeypatch, delay=0.5)
        download = threading.Thread(target=get_texts, args=("de",))
        download.start()
        time.sleep(0.05)

        started = time.monotonic()
        assert get_texts("en")["errorcode_120"] == "This player's level is too low."
        assert time.monotonic() - started < 0.25
        download.join(timeout=10)

    def test_a_refresh_gives_other_callers_the_stale_copy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        stale = get_texts("en")
        texts._fetched_at["en"] = time.time() - (texts.CACHE_TTL + 1)
        cdn = stub_cdn(monkeypatch, delay=0.5)
        refresh = threading.Thread(target=get_texts)
        refresh.start()
        time.sleep(0.05)

        started = time.monotonic()
        assert get_texts() is stale
        assert time.monotonic() - started < 0.25
        refresh.join(timeout=10)
        assert len(cdn.langs) == 1
        assert get_texts() is not stale


class TestErrorMessages:
    def test_a_command_error_without_texts_is_unchanged_and_fetches_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cdn = stub_cdn(monkeypatch)

        err = CommandError("gaa", 120)

        assert str(err) == "Server error OTHER_LEVEL_TOO_LOW (120) for command 'gaa'"
        assert err.game_message() is None
        assert cdn.langs == []

    def test_a_command_error_carries_the_loaded_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts("en")
        get_texts("de")

        err = CommandError("gaa", 120)

        assert str(err).endswith("for command 'gaa': This player's level is too low.")
        assert err.game_message() == "This player's level is too low."
        assert err.game_message("de") == "This player's level is too low. (de)"
        assert err.game_message("fr") is None
        assert CommandError("gaa", 99999).game_message() is None

    def test_a_login_error_carries_the_loaded_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)
        get_texts("en")

        assert LoginError("Login failed", 120).game_message() == "This player's level is too low."
        assert str(LoginError("Login failed", 120)).endswith(": This player's level is too low.")
        assert LoginError("Login failed").game_message() is None

    def test_the_login_refusals_carry_their_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def lang_file(lang: str = "en") -> dict[str, str]:
            return {
                "errorCode_453": "Too many logins.",
                "errorCode_27": "This account\nis banned.",
                "errorCode_368": "Wrong server.",
            }

        monkeypatch.setattr(texts, "fetch_texts", lang_file)
        get_texts("en")

        cooldown, banned, wrong = LoginCooldownError(30), AccountBannedError(None), WrongServerError(None)

        assert (cooldown.code, cooldown.error) == (453, GGEError.LOGIN_COOLDOWN_ACTIVE)
        assert str(cooldown).endswith(": Too many logins.") and "Retry in 30s" in str(cooldown)
        assert (banned.code, banned.error) == (27, GGEError.IS_BANNED)
        assert str(banned).endswith(": This account is banned.")
        assert banned.game_message() == "This account\nis banned."
        assert (wrong.code, wrong.error) == (368, GGEError.EXISTING_MAPPING_WRONG_SERVER)
        assert str(wrong).endswith(": Wrong server.")

    def test_a_command_error_message_is_on_one_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(texts, "fetch_texts", lambda lang="en": {"errorCode_197": "Relocating.\nWait  {0}."})
        get_texts("en")

        err = CommandError("cra", 197)

        assert str(err).endswith(": Relocating. Wait {0}.")
        assert err.game_message() == "Relocating.\nWait  {0}."
