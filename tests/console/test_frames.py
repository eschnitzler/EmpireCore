import json
import time

from empire_core.console.frames import HEADER, FrameLog, detail_title, frame_detail
from empire_core.network.connection import Frame, FrameDirection


def frame(command="gam", text='%xt%gam%1%0%{"M":[]}%', error_code=0, direction=FrameDirection.RECEIVED, at=0.0):
    return Frame(direction, command, error_code, text, at)


def commands(log):
    return [row.frame.command for row in log.visible()]


def only_row(f):
    log = FrameLog()
    log.add(f)
    return log.visible()[0]


def test_filter_shows_only_named_commands():
    log = FrameLog()
    log.add(frame("gam"))
    log.add(frame("gbd"))
    log.set_filter(["gbd"])
    assert commands(log) == ["gbd"]
    log.set_filter([])
    assert len(log.visible()) == 2


def test_search_shows_frames_containing_the_text():
    log = FrameLog()
    log.add(frame("gam", '%xt%gam%1%0%{"OID":4242}%'))
    log.add(frame("gbd", '%xt%gbd%1%0%{"OID":7}%'))
    log.set_search("4242")
    assert commands(log) == ["gam"]
    log.add(frame("gaa", '%xt%gaa%1%0%{"X":4242}%'))
    assert commands(log) == ["gam", "gaa"]
    log.set_search("")
    assert len(log.visible()) == 3


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


def test_capacity_drops_the_oldest_from_a_filtered_view():
    log = FrameLog(capacity=2)
    log.set_filter(["a", "c"])
    for command in ("a", "b", "c"):
        log.add(frame(command))
    assert commands(log) == ["c"]


def test_clear_and_change_callback():
    calls = []
    log = FrameLog()
    log.on_change = lambda: calls.append(1)
    log.add(frame())
    log.clear()
    assert log.visible() == [] and len(calls) == 2


def test_reply_carries_the_time_since_its_request():
    log = FrameLog()
    log.add(frame("gcl", "%xt%EmpireEx_21%gcl%1%{}%", direction=FrameDirection.SENT, at=10.0))
    log.add(frame("gcl", "%xt%gcl%1%0%{}%", at=10.048))
    log.add(frame("gcl", "%xt%gcl%1%0%{}%", at=11.0))
    request, reply, push = log.visible()
    assert request.latency is None and push.latency is None
    assert reply.latency is not None and abs(reply.latency - 0.048) < 1e-9
    assert "48 ms" in reply.text


def test_size_is_in_bytes():
    assert only_row(frame(text="%xt%gam%1%0%" + json.dumps({"N": "é" * 600}, ensure_ascii=False) + "%")).size > 1200


def test_row_shows_direction_command_and_error_badge():
    sent = only_row(frame("gcl", "%xt%EmpireEx_21%gcl%1%{}%", direction=FrameDirection.SENT))
    assert "↑" in sent.text and "gcl" in sent.text
    failed = only_row(frame(error_code=114))
    assert "✗ 114" in failed.text
    assert any("error" in style for style, *_ in failed.cells)


def test_header_lines_up_with_rows():
    row = only_row(frame("gbd"))
    assert HEADER.index("command") == row.text.index("gbd")


def test_row_is_bounded_for_huge_frames():
    huge = only_row(frame("gbd", "%xt%gbd%1%0%" + json.dumps({"x": "y" * 50_000}) + "%"))
    assert "\n" not in huge.text and len(huge.text) < 140 and "KB" in huge.text


MIGHT = '%xt%gmu%1%0%{"MP":1252,"TSBM":953,"HMP":4976}%'


def test_detail_parses_into_the_response_model():
    detail = frame_detail(frame("gmu", MIGHT))
    assert detail.model == "MightPointsResponse"
    assert detail.text.startswith("MightPointsResponse(") and "might_points=1252" in detail.text


def test_raw_detail_pretty_prints_json_payload():
    detail = frame_detail(frame("gmu", MIGHT), parsed=False)
    assert detail.model is None and detail.text == json.dumps({"MP": 1252, "TSBM": 953, "HMP": 4976}, indent=2)


def test_unmodelled_and_sent_frames_show_raw():
    assert frame_detail(frame("zzz", '%xt%zzz%1%0%{"A":1}%')).model is None
    sent = frame("gmu", "%xt%EmpireEx_21%gmu%1%{}%", direction=FrameDirection.SENT)
    assert frame_detail(sent).model is None


def test_a_payload_that_does_not_parse_shows_raw_with_a_note():
    detail = frame_detail(frame("gam", '%xt%gam%1%0%{"M":"lots"}%'))
    assert detail.model is None and "GetMovementsResponse" in detail.text.splitlines()[0]
    assert '"M": "lots"' in detail.text


def test_detail_falls_back_to_raw_text():
    xml = frame("rndK", "<msg t='sys'><body action='rndK'><k>abc</k></body></msg>")
    assert frame_detail(xml).text == xml.text


def test_detail_title_names_the_response_model():
    title = detail_title(only_row(frame("gcl", "%xt%gcl%1%0%{}%", error_code=114)))
    assert "↓ gcl" in title and "Response" in title and "err 114" in title


def test_many_large_frames_stay_fast():
    big = "%xt%gbd%1%0%" + json.dumps({"x": "y" * 50_000}) + "%"
    start = time.perf_counter()
    log = FrameLog()
    log.set_search("zzz")
    for _ in range(5000):
        log.add(frame("gbd", big))
        log.visible()
    log.set_search("")
    log.set_filter(["gbd"])
    assert len(log.visible()) == 5000
    assert log.visible() is log.visible()
    assert time.perf_counter() - start < 2.0


def test_parsed_detail_fits_the_width_it_is_given():
    narrow = frame_detail(frame("gmu", MIGHT), width=40).text
    wide = frame_detail(frame("gmu", MIGHT), width=400).text
    assert all(len(line) <= 40 for line in narrow.splitlines()) and len(wide.splitlines()) == 1


def test_a_request_and_its_reply_share_a_pair():
    log = FrameLog()
    log.add(frame("gcl", "%xt%EmpireEx_21%gcl%1%{}%", direction=FrameDirection.SENT, at=1.0))
    log.add(frame("gam", at=1.01))
    log.add(frame("gcl", "%xt%gcl%1%0%{}%", at=1.05))
    request, push, reply = log.visible()
    assert request.pair is not None and reply.pair == request.pair and push.pair is None


def test_a_reply_under_another_command_still_pairs():
    log = FrameLog()
    log.add(frame("jca", '%xt%EmpireEx_21%jca%1%{"CID":1}%', direction=FrameDirection.SENT, at=1.0))
    log.add(frame("jaa", "%xt%jaa%1%0%{}%", at=1.2))
    request, reply = log.visible()
    assert reply.pair == request.pair and abs((reply.latency or 0) - 0.2) < 1e-9


def test_sent_frames_parse_into_their_request_model():
    detail = frame_detail(frame("gcl", '%xt%EmpireEx_21%gcl%1%{"PID":5}%', direction=FrameDirection.SENT))
    assert detail.model == "GetCastlesRequest" and "GetCastlesRequest(" in detail.text
