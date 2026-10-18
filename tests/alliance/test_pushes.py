"""Alliance push updates, from AllianceInfoVO and AEECommand."""

from empire_core.state.manager import GameState
from empire_core.state.models import Player


def alliance_state():
    state = GameState()
    state.local_player = Player(PID=7, PN="Player")
    state.update_from_packet("gal", {"AID": 301, "R": 0})
    state.update_from_packet("ain", {"A": {"AID": 301, "N": "Guild", "CF": 1, "HF": 2}})
    return state


def test_fame_push_is_copy_on_write_and_survives_kept_context():
    state = alliance_state()
    previous = state.own_alliance
    state.update_from_packet("afa", {"CF": 10, "HF": 20})
    current = state.get_own_alliance()
    assert current is not None and current.fame_points == 10 and current.highest_fame_points == 20
    assert previous is not None and previous.fame_points == 1
    assert state._own_alliance_raw is not None and state._own_alliance_raw["CF"] == 10


def test_buff_push_replaces_list_including_valid_empty():
    state = alliance_state()
    for payload in [{"ABL": [{"BT": 999999, "L": 3, "CD": 12}]}, [{"BT": 999999, "L": 3, "CD": 12}]]:
        state.update_from_packet("abl", payload)  # type: ignore[arg-type]
        current = state.get_own_alliance()
        assert current is not None and current.buildings[0].building_type == 999999
    state.update_from_packet("abl", {"ABL": []})
    current = state.get_own_alliance()
    assert current is not None and current.buildings == []


def test_emblem_push_unwraps_nested_current_and_uses_top_fallback():
    state = alliance_state()
    state.update_from_packet(
        "aee", {"ACCA": {"ACCA": {"ACLI": 999999, "ACCS": [1, 2]}}, "ACFB": {"ACLI": 2, "ACCS": [3]}}
    )
    current = state.get_own_alliance()
    assert current is not None and current.crests is not None and current.crests.crest is not None
    assert current.crests.crest.layout_id == 999999
    assert current.crests.fallback_crest is not None and current.crests.fallback_crest.layout_id == 2
    state.update_from_packet("ain", {"A": {"AID": 301}})
    current = state.get_own_alliance()
    assert current is not None and current.crests is not None and current.crests.crest is not None
    assert current.crests.crest.layout_id == 999999


def test_failed_malformed_or_unscoped_push_keeps_state():
    state = alliance_state()
    before = state.get_own_alliance()
    for command, payload in [("afa", {"CF": 9, "HF": 9}), ("abl", {"ABL": []}), ("aee", {"ACCA": {}})]:
        state.update_from_packet(command, payload, 1)
    state.update_from_packet("afa", {"raw": "bad"})
    state.update_from_packet("abl", {"ABL": "bad"})
    state.update_from_packet("aee", {"ACCA": "bad"})
    assert state.get_own_alliance() == before
    state.update_from_packet("gal", {"AID": 401})
    state.update_from_packet("afa", {"CF": 9, "HF": 9})
    assert state.get_own_alliance() is None
