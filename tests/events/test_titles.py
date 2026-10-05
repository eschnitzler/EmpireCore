"""The in-game event titles from the language CDN: cache, TTL and failure backoff.

Every HTTP call is stubbed: ``requests.get`` is replaced so an un-stubbed code
path fails loudly instead of reaching the real GGS CDN.
"""

import threading
import time
from typing import Any

import pytest
import requests

from empire_core.events import titles as events
from empire_core.gamedata.cdn import RETRY_AFTER_FAILURE


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", _forbidden)


@pytest.fixture(autouse=True)
def reset_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "_cached_translations", {})
    monkeypatch.setattr(events, "_translations_fetched_at", {})
    monkeypatch.setattr(events, "_last_translations_failure_at", {})


class Counter:
    """Thread-safe call counter for stubbed fetches."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def bump(self) -> int:
        with self._lock:
            self.count += 1
            return self.count


def stub_events_cdn(
    monkeypatch: pytest.MonkeyPatch,
    *,
    error: Exception | None = None,
    delay: float = 0.0,
) -> Counter:
    """Stub the language CDN used by the event titles. Returns the fetch counter."""
    calls = Counter()

    def fake_translations(lang: str = "en") -> dict[str, str]:
        calls.bump()
        if delay:
            time.sleep(delay)
        if error is not None:
            raise error
        return {"event_title_10": "Nomad Invasion", "event_title_x": "Broken", "dialog_ok": "OK"}

    monkeypatch.setattr(events, "_fetch_translations", fake_translations)
    return calls


class TestEventTitles:
    def test_the_titles_by_event_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_events_cdn(monkeypatch)

        assert events.get_event_titles() == {10: "Nomad Invasion"}

    def test_a_cdn_failure_gives_no_titles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Titles are cosmetic: a lang-server outage must not raise."""
        stub_events_cdn(monkeypatch, error=requests.ConnectionError("lang down"))

        assert events.get_event_titles() == {}

    def test_the_titles_are_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = stub_events_cdn(monkeypatch)

        events.get_event_titles()
        events.get_event_titles()

        assert calls.count == 1

    def test_failure_backoff_does_not_refetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = stub_events_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        events.get_event_titles()
        events.get_event_titles()
        events._last_translations_failure_at = {"en": time.time() - (RETRY_AFTER_FAILURE + 1)}
        events.get_event_titles()

        assert calls.count == 2

    def test_the_cache_expires_and_a_failed_refresh_keeps_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_events_cdn(monkeypatch)
        events.get_event_titles()
        events._translations_fetched_at = {"en": time.time() - (events._CACHE_TTL + 1)}

        calls = stub_events_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        assert events.get_event_titles() == {10: "Nomad Invasion"}
        assert calls.count == 1

    def test_concurrent_callers_fetch_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = stub_events_cdn(monkeypatch, delay=0.05)

        threads = [threading.Thread(target=events.get_event_titles) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert calls.count == 1
