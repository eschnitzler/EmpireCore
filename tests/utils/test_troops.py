"""Tests for the CDN-backed metadata helpers.

Every HTTP call is stubbed: the ``no_real_network`` fixture below replaces
``requests.get`` so an un-stubbed code path fails loudly instead of reaching
the real GGS/GGE CDN.
"""

import logging
import threading
import time
from typing import Any

import pytest
import requests

from empire_core.exceptions import NetworkError
from empire_core.utils import events, troops

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test reaches the network."""

    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", _forbidden)


@pytest.fixture(autouse=True)
def reset_caches() -> Any:
    """Clear the module-level CDN caches before and after every test."""
    _reset_events_cache()
    _reset_troops_cache()
    yield
    _reset_events_cache()
    _reset_troops_cache()


def _reset_events_cache() -> None:
    events._cached_translations = {}
    events._translations_fetched_at = {}
    events._last_translations_failure_at = {}


def _reset_troops_cache() -> None:
    troops._troop_ids = None
    troops._last_failure_at = 0.0
    troops._last_degraded_warning_at = 0.0


ITEMS_DATA: dict[str, Any] = {
    "units": [
        {"wodID": 1, "name": "spearman"},
        {"wodID": 2, "name": "bowman"},
        {"wodID": 300, "name": "ram", "slotTypes": ["tool"]},
    ],
}


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
    """Stub the language CDN used by utils.events. Returns the fetch counter."""
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


def stub_troops_cdn(
    monkeypatch: pytest.MonkeyPatch,
    *,
    error: Exception | None = None,
    delay: float = 0.0,
) -> Counter:
    """Stub the CDN seams used by utils.troops. Returns the fetch counter."""
    calls = Counter()

    def fake_version() -> str:
        return "1234"

    def fake_items(version: str) -> dict[str, Any]:
        calls.bump()
        if delay:
            time.sleep(delay)
        if error is not None:
            raise error
        return ITEMS_DATA

    monkeypatch.setattr(troops, "get_items_version", fake_version)
    monkeypatch.setattr(troops, "fetch_items_data", fake_items)
    return calls


# ---------------------------------------------------------------------------
# utils/events.py
# ---------------------------------------------------------------------------


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
        events._last_translations_failure_at = {"en": time.time() - (events._FAILURE_RETRY_INTERVAL + 1)}
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


# ---------------------------------------------------------------------------
# utils/troops.py
# ---------------------------------------------------------------------------


class TestGetTroopIds:
    def test_filters_equipment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_troops_cdn(monkeypatch)

        assert troops.get_troop_ids() == {1, 2}

    def test_raises_network_error_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_troops_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with pytest.raises(NetworkError) as excinfo:
            troops.get_troop_ids()

        assert isinstance(excinfo.value.__cause__, requests.ConnectionError)

    def test_backoff_raises_without_refetching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = stub_troops_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with pytest.raises(NetworkError):
            troops.get_troop_ids()
        with pytest.raises(NetworkError):
            troops.get_troop_ids()

        assert calls.count == 1

    def test_concurrent_callers_fetch_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = stub_troops_cdn(monkeypatch, delay=0.05)
        results: list[set[int]] = []

        def worker() -> None:
            results.append(troops.get_troop_ids())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert calls.count == 1
        assert results == [{1, 2}] * 4

    def test_troop_data_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_troops_cdn(monkeypatch)

        assert troops.troop_data_available() is False
        troops.get_troop_ids()
        assert troops.troop_data_available() is True


class TestCountTroops:
    def test_excludes_equipment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_troops_cdn(monkeypatch)

        assert troops.count_troops({1: 10, 2: 5, 300: 3}) == 15

    def test_explicit_empty_troop_ids_counts_nothing(self) -> None:
        """An explicitly empty set means 'genuinely no troop IDs', not 'unavailable'."""
        assert troops.count_troops({1: 10, 300: 3}, troop_ids=set()) == 0

    def test_counts_all_units_when_metadata_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Documented degraded fallback: inflated count, but it must be logged."""
        stub_troops_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with caplog.at_level(logging.WARNING, logger="empire_core.utils.troops"):
            assert troops.count_troops({1: 10, 300: 3}) == 13

        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_degraded_count_warning_is_throttled(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """troop_count is read per movement: the fallback must not spam warnings."""
        stub_troops_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with caplog.at_level(logging.DEBUG, logger="empire_core.utils.troops"):
            for _ in range(5):
                assert troops.count_troops({1: 10, 300: 3}) == 13

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == troops.__name__]
        assert len(warnings) == 1
