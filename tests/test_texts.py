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
from empire_core.exceptions import CommandError, LoginCooldownError, LoginError
from empire_core.texts import RETRY_AFTER_FAILURE, cached_text, fill, get_texts, text

LANG_FILE = {
    "@metadata": {"versionNo": "4372"},
    "errorCode_120": "This player's level is too low.",
    "errorCode_140": "You have to occupy this outpost for {0} before you can surrender it.",
    "travelSpeedBonusPerField": "+{0}% for every {1} fields",
    "currency_name_1MinSkip": "Skip 1 minute",
    "Dialog_OK": "OK",
    "dialog_ok": "Okay",
    "empty": "",
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
            ("no placeholders", (1,), "no placeholders"),
        ],
    )
    def test_like_the_client(self, template: str, args: tuple[object, ...], filled: str) -> None:
        assert fill(template, *args) == filled


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
        assert LoginCooldownError(30).game_message() is None
