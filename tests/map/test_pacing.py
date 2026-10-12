"""MapAreaPacer: map area reads spaced by their tile count."""

import math
import threading

import pytest

from empire_core.map import pacing
from empire_core.map.models.areas import GetMapAreaRequest
from empire_core.map.pacing import MapAreaPacer


class Clock:
    """A monotonic clock that moves only when the pacer sleeps."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float, cancel: threading.Event | None) -> bool:
        self.sleeps.append(seconds)
        self.now += seconds
        return cancel is not None and cancel.is_set()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(pacing.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pacing, "sleep_unless_cancelled", clock.sleep)
    return clock


def test_the_first_read_goes_at_once_and_the_next_waits_its_tiles(clock):
    pacer = MapAreaPacer(lambda: 8100.0)
    assert pacer.wait(8100) is False
    assert pacer.wait(8100) is False
    assert pacer.wait(900) is False
    assert clock.sleeps == [1.0, 1.0]


def test_time_already_passed_counts(clock):
    pacer = MapAreaPacer(lambda: 8100.0)
    pacer.wait(8100)
    clock.now += 0.75
    pacer.wait(8100)
    assert clock.sleeps == [pytest.approx(0.25)]


def test_the_rate_is_read_at_each_wait(clock):
    rate = [8100.0]
    pacer = MapAreaPacer(lambda: rate[0])
    pacer.wait(8100)
    rate[0] = 4050.0
    pacer.wait(8100)
    pacer.wait(8100)
    assert clock.sleeps == [1.0, 2.0]


def test_an_unlimited_rate_never_waits(clock):
    pacer = MapAreaPacer(lambda: math.inf)
    for _ in range(3):
        pacer.wait(8100)
    assert clock.sleeps == []


def test_a_cancel_during_the_wait_is_reported(clock):
    pacer = MapAreaPacer(lambda: 8100.0)
    cancel = threading.Event()
    pacer.wait(8100, cancel)
    cancel.set()
    assert pacer.wait(8100, cancel) is True


def test_a_request_counts_its_corners():
    assert GetMapAreaRequest(x1=0, y1=0, x2=89, y2=89).tiles == 8100
    assert GetMapAreaRequest(x1=10, y1=10, x2=10, y2=10).tiles == 1
    assert GetMapAreaRequest(x1=89, y1=89, x2=0, y2=0).tiles == 8100


def test_the_default_rate_stays_under_the_ban():
    from empire_core.config import EmpireConfig

    rate = EmpireConfig().map_tiles_per_second
    # About 810,000 tiles inside a window of at most 31 seconds bans the account.
    assert rate * 31 < 810_000
