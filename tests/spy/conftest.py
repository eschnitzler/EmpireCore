"""Fixtures for the spy tests."""

from __future__ import annotations

import pytest

from empire_core.spy import service as spy_module

# =============================================================================
# SpyService
# =============================================================================


@pytest.fixture
def no_sleep(monkeypatch):
    """The spy poll sleeps 2s between attempts; tests must not."""
    monkeypatch.setattr(spy_module, "sleep_unless_cancelled", lambda seconds, cancel: cancel.is_set())
