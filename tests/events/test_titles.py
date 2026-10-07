"""The in-game event titles, read from the game's texts (cache and backoff: tests/test_texts.py)."""

from typing import Any

import pytest
import requests

from empire_core import texts
from empire_core.events import get_event_titles


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", _forbidden)


class TestEventTitles:
    def test_the_titles_by_event_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        langs = []

        def fake_texts(lang: str = "en") -> dict[str, str]:
            langs.append(lang)
            return {"event_title_10": "Nomad Invasion", "Event_Title_x": "Broken", "dialog_ok": "OK"}

        monkeypatch.setattr(texts, "fetch_texts", fake_texts)

        assert get_event_titles("de") == {10: "Nomad Invasion"}
        assert langs == ["de"]

    def test_a_cdn_failure_gives_no_titles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Titles are cosmetic: a lang-server outage must not raise."""

        def down(lang: str = "en") -> dict[str, str]:
            raise requests.ConnectionError("lang down")

        monkeypatch.setattr(texts, "fetch_texts", down)

        assert get_event_titles() == {}
