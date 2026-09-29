"""Tests for the map service."""

from __future__ import annotations

from typing import get_type_hints

from empire_core.map.scanner import ScanResult
from empire_core.map.service import MapService


class TestPublicSurfaceIsTyped:
    """The README advertises a fully typed client."""

    def test_scan_methods_return_scan_result(self):
        assert get_type_hints(MapService.scan_kingdom)["return"] is ScanResult
        assert get_type_hints(MapService.scan_chunks)["return"] is ScanResult
