import json
import time

from empire_core.console.frames import FrameLog, frame_detail, frame_line
from empire_core.network.connection import Frame, FrameDirection


def frame(command="gam", text='%xt%gam%1%0%{"M":[]}%', error_code=0, direction=FrameDirection.RECEIVED):
    return Frame(direction, command, error_code, text, 0.0)


def commands(log):
    return [row.frame.command for row in log.visible()]


def test_filter_shows_only_named_commands():
    log = FrameLog()
    log.add(frame("gam"))
    log.add(frame("gbd"))
    log.set_filter(["gbd"])
    assert commands(log) == ["gbd"]
    log.set_filter([])
    assert len(log.visible()) == 2


def test_pause_freezes_the_view_but_keeps_recording():
    log = FrameLog()
    log.add(frame("gam"))
    assert log.toggle_pause() is True
    log.add(frame("gbd"))
    assert commands(log) == ["gam"]
    log.toggle_pause()
    assert commands(log) == ["gam", "gbd"]


def test_capacity_drops_the_oldest():
    log = FrameLog(capacity=2)
    for command in ("a", "b", "c"):
        log.add(frame(command))
    assert commands(log) == ["b", "c"]


def test_clear_and_change_callback():
    calls = []
    log = FrameLog()
    log.on_change = lambda: calls.append(1)
    log.add(frame())
    log.clear()
    assert log.visible() == [] and len(calls) == 2


def test_line_shows_direction_command_and_error():
    sent = frame("gcl", "%xt%EmpireEx_21%gcl%1%{}%", direction=FrameDirection.SENT)
    assert "↑" in frame_line(sent) and "gcl" in frame_line(sent)
    assert "err 114" in frame_line(frame(error_code=114))


def test_line_is_bounded_for_huge_frames():
    huge = frame("gbd", "%xt%gbd%1%0%" + json.dumps({"x": "y" * 50_000}) + "%")
    line = frame_line(huge)
    assert "\n" not in line and len(line) < 140 and "KB" in line


def test_detail_pretty_prints_json_payload():
    assert frame_detail(frame()) == json.dumps({"M": []}, indent=2)


def test_detail_falls_back_to_raw_text():
    xml = frame("rndK", "<msg t='sys'><body action='rndK'><k>abc</k></body></msg>")
    assert frame_detail(xml) == xml.text


def test_many_large_frames_stay_fast():
    big = "%xt%gbd%1%0%" + json.dumps({"x": "y" * 50_000}) + "%"
    start = time.perf_counter()
    log = FrameLog()
    for _ in range(5000):
        log.add(frame("gbd", big))
    log.set_filter(["gbd"])
    assert len(log.visible()) == 5000
    assert log.visible() is log.visible()
    assert time.perf_counter() - start < 1.0
