"""Troop ids and troop counts, read from the one loaded game data."""

import logging
import threading
import time
from typing import Any

import pytest
import requests

from empire_core.exceptions import NetworkError
from empire_core.gamedata import cdn, troops

ITEMS_DATA: dict[str, Any] = {
    "units": [
        {"wodID": 1, "name": "spearman"},
        {"wodID": 2, "name": "bowman"},
        {"wodID": 300, "name": "ram", "slotTypes": "1"},
    ],
}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", _forbidden)


class Downloads:
    """Thread-safe count of stubbed items downloads."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def bump(self) -> None:
        with self._lock:
            self.count += 1


def stub_cdn(monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None, delay: float = 0.0) -> Downloads:
    downloads = Downloads()

    def fake_items(version: str) -> dict[str, Any]:
        downloads.bump()
        if delay:
            time.sleep(delay)
        if error is not None:
            raise error
        return ITEMS_DATA

    monkeypatch.setattr(cdn, "get_items_version", lambda: "1234")
    monkeypatch.setattr(cdn, "fetch_items_data", fake_items)
    return downloads


class TestGetTroopIds:
    def test_filters_equipment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert troops.get_troop_ids() == {1, 2}

    def test_raises_network_error_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with pytest.raises(NetworkError) as excinfo:
            troops.get_troop_ids()

        assert isinstance(excinfo.value.__cause__, requests.ConnectionError)

    def test_backoff_raises_without_refetching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        downloads = stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with pytest.raises(NetworkError):
            troops.get_troop_ids()
        with pytest.raises(NetworkError):
            troops.get_troop_ids()

        assert downloads.count == 1

    def test_force_refresh_skips_the_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        downloads = stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))
        with pytest.raises(NetworkError):
            troops.get_troop_ids()

        stub_cdn(monkeypatch)

        assert troops.get_troop_ids(force_refresh=True) == {1, 2}
        assert downloads.count == 1

    def test_loaded_data_is_used_without_the_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        downloads = stub_cdn(monkeypatch)
        troops.get_troop_ids()

        monkeypatch.setattr(cdn, "get_items_version", lambda: pytest.fail("asked the CDN again"))

        assert troops.get_troop_ids() == {1, 2}
        assert downloads.count == 1

    def test_concurrent_callers_fetch_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        downloads = stub_cdn(monkeypatch, delay=0.05)
        results: list[set[int]] = []

        def worker() -> None:
            results.append(troops.get_troop_ids())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert downloads.count == 1
        assert results == [{1, 2}] * 4

    def test_troop_data_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert troops.troop_data_available() is False
        troops.get_troop_ids()
        assert troops.troop_data_available() is True


class TestCountTroops:
    def test_excludes_equipment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_cdn(monkeypatch)

        assert troops.count_troops({1: 10, 2: 5, 300: 3}) == 15

    def test_explicit_empty_troop_ids_counts_nothing(self) -> None:
        """An explicitly empty set means 'genuinely no troop IDs', not 'unavailable'."""
        assert troops.count_troops({1: 10, 300: 3}, troop_ids=set()) == 0

    def test_counts_all_units_when_metadata_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Documented degraded fallback: inflated count, but it must be logged."""
        stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with caplog.at_level(logging.WARNING, logger=troops.__name__):
            assert troops.count_troops({1: 10, 300: 3}) == 13

        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_degraded_count_warning_is_throttled(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """troop_count is read per movement: the fallback must not spam warnings."""
        stub_cdn(monkeypatch, error=requests.ConnectionError("boom"))

        with caplog.at_level(logging.DEBUG, logger=troops.__name__):
            for _ in range(5):
                assert troops.count_troops({1: 10, 300: 3}) == 13

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == troops.__name__]
        assert len(warnings) == 1
