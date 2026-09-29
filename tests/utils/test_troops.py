"""Tests for the CDN-backed metadata helpers and the experimental write queue.

Every HTTP call is stubbed: the ``no_real_network`` fixture below replaces
``requests.get`` so an un-stubbed code path fails loudly instead of reaching
the real GGS/GGE CDN.
"""

import asyncio
import contextlib
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
    events._cached_events_index = None
    events._cached_translations = {}
    events._events_index_fetched_at = 0.0
    events._translations_fetched_at = {}
    events._last_index_failure_at = 0.0
    events._last_translations_failure_at = {}


def _reset_troops_cache() -> None:
    troops._troop_ids = None
    troops._last_failure_at = 0.0
    troops._last_degraded_warning_at = 0.0


ITEMS_DATA: dict[str, Any] = {
    "events": [
        {"eventID": "10", "eventType": "Nomad", "comment1": "Nomad invasion"},
        {"eventID": "11", "eventType": "AllianceBattleGround", "comment2": "ABG"},
        {"eventID": "not-an-int", "eventType": "Broken"},
    ],
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
    items_error: Exception | None = None,
    translations_error: Exception | None = None,
    delay: float = 0.0,
) -> tuple[Counter, Counter]:
    """Stub the CDN seams used by utils.events. Returns (items, translations) counters."""
    items_calls = Counter()
    translation_calls = Counter()

    def fake_version() -> str:
        return "1234"

    def fake_items(version: str) -> dict[str, Any]:
        items_calls.bump()
        if delay:
            time.sleep(delay)
        if items_error is not None:
            raise items_error
        return ITEMS_DATA

    def fake_translations(lang: str = "en") -> dict[str, str]:
        translation_calls.bump()
        if translations_error is not None:
            raise translations_error
        return {"event_title_10": "Nomad Invasion"}

    monkeypatch.setattr(events, "get_items_version", fake_version)
    monkeypatch.setattr(events, "fetch_items_data", fake_items)
    monkeypatch.setattr(events, "_fetch_translations", fake_translations)
    return items_calls, translation_calls


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


class TestGetActiveEvents:
    def test_resolves_names_from_cdn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_events_cdn(monkeypatch)

        result = events.get_active_events([10, 11, 999])

        assert [e.id for e in result] == [10, 11]
        assert result[0].internal_name == "Nomad"
        assert result[0].display_name == "Nomad Invasion"
        assert result[0].description == "Nomad invasion"
        # No translation key for 11 -> falls back to the internal name
        assert result[1].display_name == "AllianceBattleGround"

    def test_empty_input_makes_no_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        items_calls, translation_calls = stub_events_cdn(monkeypatch)

        assert events.get_active_events([]) == []
        assert items_calls.count == 0
        assert translation_calls.count == 0

    def test_raises_network_error_on_cdn_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A CDN outage must be distinguishable from 'no events are active'."""
        stub_events_cdn(monkeypatch, items_error=requests.ConnectionError("dns down"))

        with pytest.raises(NetworkError) as excinfo:
            events.get_active_events([10])

        assert isinstance(excinfo.value.__cause__, requests.ConnectionError)

    def test_translation_failure_degrades_to_internal_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Display names are cosmetic: a lang-server outage must not raise."""
        stub_events_cdn(monkeypatch, translations_error=requests.ConnectionError("lang down"))

        result = events.get_active_events([10])

        assert [e.display_name for e in result] == ["Nomad"]

    def test_index_is_cached_across_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        items_calls, translation_calls = stub_events_cdn(monkeypatch)

        events.get_active_events([10])
        events.get_active_events([10])

        assert items_calls.count == 1
        assert translation_calls.count == 1

    def test_failure_backoff_does_not_refetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mirror troops.py: a CDN outage must not re-issue HTTP on every call."""
        items_calls, _ = stub_events_cdn(monkeypatch, items_error=requests.ConnectionError("boom"))

        with pytest.raises(NetworkError):
            events.get_active_events([10])
        with pytest.raises(NetworkError):
            events.get_active_events([10])

        assert items_calls.count == 1

    def test_failure_backoff_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        items_calls, _ = stub_events_cdn(monkeypatch, items_error=requests.ConnectionError("boom"))

        with pytest.raises(NetworkError):
            events.get_active_events([10])
        events._last_index_failure_at = time.time() - (events._FAILURE_RETRY_INTERVAL + 1)
        with pytest.raises(NetworkError):
            events.get_active_events([10])

        assert items_calls.count == 2

    def test_cached_index_expires_after_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A long-running bot must eventually see events added to the CDN data."""
        items_calls, _ = stub_events_cdn(monkeypatch)

        events.get_active_events([10])
        events._events_index_fetched_at = time.time() - (events._CACHE_TTL + 1)
        events._translations_fetched_at = {"en": time.time() - (events._CACHE_TTL + 1)}
        events.get_active_events([10])

        assert items_calls.count == 2

    def test_stale_index_served_when_refresh_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub_events_cdn(monkeypatch)
        events.get_active_events([10])

        stub_events_cdn(monkeypatch, items_error=requests.ConnectionError("boom"))
        result = events.get_active_events([10], force_refresh=True)

        assert [e.id for e in result] == [10]

    def test_concurrent_callers_fetch_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        items_calls, _ = stub_events_cdn(monkeypatch, delay=0.05)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                events.get_active_events([10])
            except BaseException as e:  # pragma: no cover - reported below
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        assert items_calls.count == 1


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


# ---------------------------------------------------------------------------
# storage/database.py (experimental, optional extra)
# ---------------------------------------------------------------------------

database = pytest.importorskip("empire_core.storage.database", reason="requires the 'storage' extra")


@contextlib.asynccontextmanager
async def open_db(path: Any, **kwargs: Any) -> Any:
    """Yield a GameDatabase and always tear it down.

    A leaked engine keeps a live aiosqlite connection thread, which hangs the
    interpreter at exit, so teardown must run even when the test body fails.
    """
    db = database.GameDatabase(db_path=str(path), **kwargs)
    try:
        yield db
    finally:
        db._running = False
        task = db._writer_task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            db._writer_task = None
        await db.engine.dispose()


class TestWriteQueue:
    """The storage module is async; these drive their own loop via asyncio.run."""

    def test_queue_is_bounded(self, tmp_path: Any) -> None:
        async def body() -> None:
            async with open_db(tmp_path / "bounded.db") as db:
                assert db._write_queue.maxsize > 0

        asyncio.run(body())

    def test_save_before_initialize_raises(self, tmp_path: Any) -> None:
        async def body() -> None:
            async with open_db(tmp_path / "early.db") as db:
                with pytest.raises(RuntimeError):
                    await db.mark_chunk_scanned(1, 0, 0)
                assert db._write_queue.qsize() == 0

        asyncio.run(body())

    def test_save_after_close_raises(self, tmp_path: Any) -> None:
        async def body() -> None:
            async with open_db(tmp_path / "closed.db") as db:
                await db.initialize()
                await db.close()

                with pytest.raises(RuntimeError):
                    await db.mark_chunk_scanned(1, 0, 0)
                assert db._write_queue.qsize() == 0

        asyncio.run(body())

    def test_writes_are_persisted(self, tmp_path: Any) -> None:
        async def body() -> None:
            async with open_db(tmp_path / "roundtrip.db") as db:
                await db.initialize()
                await db.mark_chunk_scanned(7, 1, 2)
                await asyncio.wait_for(db._write_queue.join(), timeout=10)

                assert await db.get_scanned_chunks(7) == {(1, 2)}
                await db.close()

        asyncio.run(body())

    def test_failed_commit_retries_then_records_dropped_writes(
        self, tmp_path: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        commit_calls = Counter()

        async def body() -> None:
            async with open_db(tmp_path / "failing.db") as db:
                await db.initialize()

                async def always_fails(batch: list[Any]) -> None:
                    commit_calls.bump()
                    raise RuntimeError("database is locked")

                monkeypatch.setattr(db, "_commit_batch", always_fails)
                monkeypatch.setattr(database, "_COMMIT_RETRY_DELAY", 0.0)

                await db.mark_chunk_scanned(7, 1, 2)
                await asyncio.wait_for(db._write_queue.join(), timeout=10)

                assert commit_calls.count >= 2, "the failed batch should be retried at least once"
                assert db.failed_write_count == 1
                assert isinstance(db.last_write_error, RuntimeError)
                await db.close()

        with caplog.at_level(logging.ERROR, logger="empire_core.storage.database"):
            asyncio.run(body())

        assert any(r.levelno >= logging.ERROR for r in caplog.records)
