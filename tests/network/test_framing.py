"""FrameBuffer: the server's message stream split into packets as the client splits it."""

import logging
import random
import re
import time

from empire_core.network.framing import FrameBuffer

GAM = '%xt%gam%1%0%{"M":[]}%'
DCL = '%xt%dcl%1%0%{"C":[]}%'
API_OK = "<msg t='sys'><body action='apiOK' r='0'></body></msg>"
JOIN_OK = "<msg t='sys'><body action='joinOK' r='1'><pid id='0'/></body></msg>"


def test_one_packet_per_message():
    assert FrameBuffer().feed(GAM + "\x00") == [GAM]


def test_two_packets_in_one_message():
    assert FrameBuffer().feed(GAM + "\x00" + DCL + "\x00") == [GAM, DCL]


def test_one_packet_split_across_two_messages():
    frames = FrameBuffer()
    assert frames.feed('%xt%gam%1%0%{"M"') == []
    assert frames.pending == '%xt%gam%1%0%{"M"'
    assert frames.feed(":[]}%\x00") == [GAM]
    assert frames.pending == ""


def test_a_complete_packet_followed_by_a_partial_one_waits_for_the_tail():
    frames = FrameBuffer()
    assert frames.feed(GAM + '%xt%dcl%1%0%{"C"') == []
    assert frames.feed(":[]}%") == [GAM, DCL]


def test_system_message_and_extension_packet_in_one_message():
    assert FrameBuffer().feed(API_OK + "\x00" + GAM + "\x00") == [API_OK, GAM]


def test_system_messages_come_out_before_extension_packets_wherever_they_sit():
    assert FrameBuffer().feed(GAM + API_OK) == [API_OK, GAM]


def test_two_system_messages_in_one_message_are_two_packets():
    assert FrameBuffer().feed(API_OK + JOIN_OK) == [API_OK, JOIN_OK]


def test_a_system_message_is_taken_even_while_an_extension_packet_is_incomplete():
    frames = FrameBuffer()
    assert frames.feed(API_OK + "%xt%gam%1%0%") == [API_OK, "%xt%gam%1%0%"]
    frames = FrameBuffer()
    assert frames.feed(API_OK + '%xt%gam%1%0%{"M"') == [API_OK]
    assert frames.pending == '%xt%gam%1%0%{"M"'


def test_null_bytes_and_noncharacters_are_stripped():
    assert FrameBuffer().feed("\x00%xt%gam%1%0%￾{}￿%\x00") == ["%xt%gam%1%0%{}%"]


def test_null_padding_yields_nothing():
    frames = FrameBuffer()
    assert frames.feed("\x00\x00") == []
    assert frames.pending == ""


def test_junk_before_a_packet_comes_out_as_its_own_piece():
    assert FrameBuffer().feed("junk" + GAM) == ["%xtjunk", GAM]


def test_a_buffer_that_never_completes_is_dropped_at_the_limit(caplog):
    frames = FrameBuffer(limit=10)
    with caplog.at_level(logging.WARNING, logger="empire_core.network.framing"):
        assert frames.feed("%xt%gam%1%0%{") == []
    assert frames.pending == ""
    assert "never completed a packet" in caplog.text
    assert frames.feed(GAM) == [GAM]


def test_a_closing_tag_split_across_messages_still_ends_the_system_message():
    frames = FrameBuffer()
    assert frames.feed(API_OK[:-3]) == []
    assert frames.feed(API_OK[-3:]) == [API_OK]


def test_a_large_packet_in_many_small_messages_comes_out_whole():
    payload = '{"M": [' + ",".join(["1"] * 5000) + "]}"
    packet = f"%xt%gam%1%0%{payload}%"
    frames = FrameBuffer()
    out: list[str] = []
    for i in range(0, len(packet), 7):
        out += frames.feed(packet[i : i + 7])
    assert out == [packet]
    assert frames.pending == ""


class _WholeBufferFrames:
    """The previous FrameBuffer, which read the whole pending buffer on every closing tag: the oracle."""

    def __init__(self):
        self.buffer = ""

    def feed(self, text: str) -> list[str]:
        tail = self.buffer[-5:]
        self.buffer += text
        if not text.endswith("%") and "</msg>" not in tail + text:
            return []
        packets = re.findall(r"<msg[\s\S]+?</msg>", self.buffer)
        if packets:
            self.buffer = re.sub(r"<msg[\s\S]+?</msg>", "", self.buffer)
        if self.buffer.endswith("%"):
            packets.extend("%xt" + piece for piece in self.buffer.split("%xt") if piece)
            self.buffer = ""
        return packets


def test_reading_from_the_first_opening_tag_takes_what_reading_everything_takes():
    rng = random.Random(7)
    tokens = ["<msg", "</msg>", "<msg t='sys'>", "%xt%", "%", "ab", "<", ">", "/", "m", "sg", "{}", "%xt%gam%1%0%"]
    for _ in range(3000):
        stream = "".join(rng.choice(tokens) for _ in range(rng.randint(1, 30)))
        cuts = sorted({rng.randint(1, len(stream)) for _ in range(rng.randint(0, 6))} | {len(stream)})
        pieces, start = [], 0
        for cut in cuts:
            if cut - start >= 5 or cut == len(stream):
                pieces.append(stream[start:cut])
                start = cut
        pieces = [piece for piece in pieces if piece]
        frames, oracle = FrameBuffer(), _WholeBufferFrames()
        for piece in pieces:
            assert frames.feed(piece) == oracle.feed(piece), (stream, pieces)
            assert frames.pending == oracle.buffer, (stream, pieces)


def test_system_messages_between_pieces_of_a_large_packet_cost_linear_time():
    packet = "%xt%gaa%1%0%{" + "x" * 2_000_000 + "}%"
    frames = FrameBuffer()
    out: list[str] = []
    started = time.perf_counter()
    for i in range(0, len(packet), 1024):
        out += frames.feed(packet[i : i + 1024])
        out += frames.feed(API_OK)
    elapsed = time.perf_counter() - started
    assert out.count(API_OK) == len(range(0, len(packet), 1024))
    assert out[-2:] == [packet, API_OK]
    assert elapsed < 1.0
