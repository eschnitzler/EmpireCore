"""A monument's or laboratory's level from a gmp or glp reply: GMPCommand and GLPCommand (split.js lines 654067,
654016) through UpgradableLandmarkData.updateLandmark and UpgradableLandmarkMapobjectVO.updateProgress."""

import logging
import threading

import pytest

from empire_core.enums import Kingdom
from empire_core.gamedata import GameData
from empire_core.gamedata import data as data_module
from empire_core.state.manager import GameState

# MonumentMapobjectVO.parseAreaInfo and LaboratoryMapobjectVO.parseAreaInfo rows
MONUMENT_ROW = [26, 110, 210, 601, 7, 1, 1, 0, -1, "Monument"]
OTHER_MONUMENT_ROW = [26, 120, 220, 602, 7, 0, 2, 0, -1, "Other"]
ICE_LABORATORY_ROW = [28, 10, 20, 901, 7, 1, 2, 0, "Ice lab"]
GREEN_LABORATORY_ROW = [28, 30, 40, 902, 7, 1, 0, 0, "Green lab"]

MONUMENT_LEVELS = [
    {"level": "1", "fameBoost": "2", "requiredPoints": "0"},
    {"level": "2", "fameBoost": "3", "requiredPoints": "100"},
    {"level": "3", "fameBoost": "4", "requiredPoints": "250"},
]
LABORATORY_LEVELS = [
    {"level": "1", "requiredPoints": "0", "ironAllianceBoost": "10", "kID": "0"},
    {"level": "2", "requiredPoints": "30", "ironAllianceBoost": "20", "kID": "0"},
    {"level": "1", "charcoalAllianceBoost": "10", "kID": "2"},
    {"level": "2", "requiredPoints": "12", "charcoalAllianceBoost": "20", "kID": "2"},
]


@pytest.fixture
def game_data(monkeypatch: pytest.MonkeyPatch) -> GameData:
    data = GameData.parse("790.02", {"monuments": MONUMENT_LEVELS, "laboratories": LABORATORY_LEVELS})
    monkeypatch.setattr(data_module, "_loaded", data)
    return data


@pytest.fixture
def landmarks(state: GameState) -> GameState:
    state.update_from_packet("gml", {"AI": [[MONUMENT_ROW], [OTHER_MONUMENT_ROW]]})
    state.update_from_packet("gll", {"AI": [[ICE_LABORATORY_ROW], [GREEN_LABORATORY_ROW]]})
    return state


def monument_levels(state: GameState) -> list[int | None]:
    listed = state.get_monuments()
    assert listed is not None
    return [own.location.landmark_level for own in listed.monuments]


def laboratory_levels(state: GameState) -> list[int | None]:
    listed = state.get_laboratories()
    assert listed is not None
    return [own.location.landmark_level for own in listed.laboratories]


@pytest.mark.usefixtures("game_data")
def test_gmp_sets_your_monuments_level_from_its_points(landmarks: GameState):
    before = landmarks.get_monuments()

    landmarks.update_from_packet("gmp", {"OID": 601, "CP": 250})

    assert monument_levels(landmarks) == [3, 2]
    assert before is not None and [own.location.landmark_level for own in before.monuments] == [1, 2]
    assert landmarks.get_last_packet_time("gmp") is not None


@pytest.mark.usefixtures("game_data")
def test_glp_counts_the_levels_of_the_laboratorys_kingdom(landmarks: GameState):
    landmarks.update_from_packet("glp", {"OID": 901, "CP": 12})
    landmarks.update_from_packet("glp", {"OID": 902, "CP": 12})

    assert laboratory_levels(landmarks) == [2, 1]
    labs = landmarks.get_laboratories()
    assert labs is not None and labs.laboratories[0].location.kingdom == Kingdom.ICE


@pytest.mark.usefixtures("game_data")
def test_a_landmark_not_yours_or_a_refused_reply_changes_nothing(landmarks: GameState):
    monuments, labs = landmarks.get_monuments(), landmarks.get_laboratories()

    landmarks.update_from_packet("gmp", {"OID": 999, "CP": 250})
    landmarks.update_from_packet("glp", {"OID": 602, "CP": 30})
    landmarks.update_from_packet("glp", {"OID": 902, "CP": 30}, 1)

    assert landmarks.get_monuments() is monuments and landmarks.get_laboratories() is labs
    assert landmarks.get_last_packet_time("glp") is not None


def test_a_refused_reply_is_not_stamped(state: GameState):
    state.update_from_packet("gmp", {"OID": 601, "CP": 250}, 1)

    assert state.get_last_packet_time("gmp") is None


@pytest.mark.usefixtures("game_data")
def test_a_reply_without_points_keeps_the_level(landmarks: GameState):
    landmarks.update_from_packet("gmp", {"OID": 601})

    assert monument_levels(landmarks) == [1, 2]


def test_without_game_data_the_level_is_kept_with_a_warning(landmarks: GameState, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        landmarks.update_from_packet("gmp", {"OID": 601, "CP": 250})

    assert monument_levels(landmarks) == [1, 2]
    assert "no game data loaded" in caplog.text


@pytest.mark.usefixtures("game_data")
def test_points_that_reach_no_level_keep_it_with_a_warning(landmarks: GameState, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        landmarks.update_from_packet("gmp", {"OID": 601, "CP": -1})

    assert monument_levels(landmarks) == [1, 2]
    assert "reach no level" in caplog.text


@pytest.mark.usefixtures("game_data")
def test_an_unreadable_reply_is_skipped_with_a_warning(landmarks: GameState, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        landmarks.update_from_packet("glp", {"OID": "x", "CP": 30})
        landmarks.update_from_packet("glp", ["not", "a", "reply"])  # type: ignore[arg-type]

    assert laboratory_levels(landmarks) == [1, 1]
    assert "a glp reply" in caplog.text


@pytest.mark.usefixtures("game_data")
def test_progress_before_any_list_is_ignored(state: GameState):
    state.update_from_packet("gmp", {"OID": 601, "CP": 250})
    state.update_from_packet("glp", {"OID": 901, "CP": 12})

    assert state.get_monuments() is None and state.get_laboratories() is None


@pytest.mark.usefixtures("game_data")
def test_a_reader_sees_whole_lists_while_replies_arrive(landmarks: GameState):
    seen: set[tuple[int | None, ...]] = set()
    done = threading.Event()

    def read() -> None:
        while not done.is_set():
            listed = landmarks.monuments
            seen.add(tuple(own.location.landmark_level for own in listed.monuments) if listed else ())

    reader = threading.Thread(target=read)
    reader.start()
    for points in (0, 100, 250) * 200:
        landmarks.update_from_packet("gmp", {"OID": 601, "CP": points})
    done.set()
    reader.join()

    assert seen <= {(1, 2), (2, 2), (3, 2)}
