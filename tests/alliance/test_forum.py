"""Forum records and requests checked against the client forum parsers."""

import pytest

from empire_core.alliance import AllianceRank, ForumRankGroup
from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError
from tests.alliance.test_service import member_client
from tests.service_helpers import conn, xt_packet


def topic(topic_id=7, last=100):
    return {
        "TID": topic_id,
        "N": "Plans &quot;now&quot;",
        "CN": "Author",
        "CT": 12,
        "CR": 6,
        "RG": [0, 1, 99],
        "RC": 1,
        "LRN": "Poster",
        "LRT": last,
        "R": 0,
    }


def test_topic_overview_is_typed_sorted_and_decodes_text():
    client = member_client({"gat": xt_packet("gat", {"TC": 9, "T": [topic(), topic(8, 200)]})})
    result = client.alliance.get_forum_topics(timeout=1)
    assert result.topic_count == 9
    assert [t.topic_id for t in result.topics] == [8, 7]
    assert result.topics[0].name == 'Plans "now"'
    assert result.topics[0].author_rank is AllianceRank.GENERAL
    assert result.topics[0].visible_ranks[0] is ForumRankGroup.LEADER
    assert result.topics[0].visible_ranks[2] == 99
    assert not result.topics[0].was_read
    assert conn(client).request_payloads == [("gat", {})]


def test_empty_topics_and_unread_count():
    client = member_client({"gat": xt_packet("gat", {"TC": 0, "T": []}), "utc": xt_packet("utc", {"UTC": "3"})})
    assert client.alliance.get_forum_topics().topics == []
    assert client.alliance.get_unread_topic_count() == 3
    assert conn(client).request_payloads[-1] == ("utc", {})


def test_detail_posts_and_empty_replies():
    payload = {
        "TN": "A [plan]",
        "CN": "Author",
        "RG": [0, 3],
        "R": [{"RID": 2, "RT": "line<br />two", "PN": "Writer", "AR": 44, "T": 20}],
    }
    client = member_client(
        {"gtr": [xt_packet("gtr", payload), xt_packet("gtr", {"TN": "Empty", "CN": "Author", "RG": [0]})]}
    )
    result = client.alliance.get_topic(7)
    assert result.name == "A  plan "
    assert result.posts[0].reply_id == 2
    assert result.posts[0].text == "line\ntwo"
    assert result.posts[0].author_rank == 44
    assert client.alliance.get_topic(8).posts == []
    assert conn(client).request_payloads == [("gtr", {"TID": 7}), ("gtr", {"TID": 8})]


def test_malformed_rows_warn_and_keep_good_rows(caplog):
    client = member_client(
        {
            "gat": xt_packet("gat", {"TC": 2, "T": [None, [], topic()]}),
            "gtr": xt_packet(
                "gtr",
                {"TN": "Name", "CN": "A", "RG": [0], "R": [None, {"RID": 1, "RT": "ok", "PN": "B", "AR": 8, "T": 1}]},
            ),
        }
    )
    assert len(client.alliance.get_forum_topics().topics) == 1
    assert len(client.alliance.get_topic(7).posts) == 1
    assert caplog.records


@pytest.mark.parametrize(
    "command,method,args",
    [("gat", "get_forum_topics", ()), ("gtr", "get_topic", (7,)), ("utc", "get_unread_topic_count", ())],
)
def test_read_failures_propagate(command, method, args):
    for response, error in [
        (xt_packet(command, error_code=1), CommandError),
        (EmpireTimeoutError("timeout"), EmpireTimeoutError),
    ]:
        client = member_client({command: response})
        with pytest.raises(error):
            getattr(client.alliance, method)(*args, timeout=0.1)


def test_wrong_shaped_overview_is_not_successful_empty_result():
    client = member_client({"gat": xt_packet("gat", {"TC": 2, "T": {}})})
    with pytest.raises(PacketError):
        client.alliance.get_forum_topics()


@pytest.mark.parametrize(
    "method,args,command,payload",
    [
        (
            "create_topic",
            ("  100% \\ plan  ", "  A\t'\"\r\n\\%  ", [0, 1]),
            "atc",
            {"N": "100&percnt; &percnt;5C plan", "RG": [0, 1], "R": "A &145;&quot;<br /><br />&percnt;5C&percnt;"},
        ),
        ("reply", (7, "  Ready  "), "aat", {"TID": 7, "RT": "Ready"}),
        ("delete_topic", (7,), "atd", {"TID": 7}),
        ("delete_reply", (7, 3), "ada", {"TID": 7, "RID": 3}),
        ("set_topic_visibility", (7, [0, 1]), "acr", {"TID": 7, "RG": [0, 1]}),
    ],
)
def test_exact_write_payloads(method, args, command, payload):
    client = member_client()
    assert getattr(client.alliance, method)(*args, timeout=0.2) is None
    assert conn(client).request_payloads == [(command, payload)]


def test_visibility_returns_echoed_topic():
    client = member_client({"acr": xt_packet("acr", {"gtr": {"TN": "New", "CN": "A", "RG": [0], "R": []}})})
    result = client.alliance.set_topic_visibility(7, [ForumRankGroup.LEADER])
    assert result is not None and result.name == "New"


@pytest.mark.parametrize(
    "method,args,command",
    [
        ("create_topic", ("Name", "Text", [0]), "atc"),
        ("reply", (7, "Text"), "aat"),
        ("delete_topic", (7,), "atd"),
        ("delete_reply", (7, 3), "ada"),
        ("set_topic_visibility", (7, [0]), "acr"),
    ],
)
def test_write_failures_propagate(method, args, command):
    from empire_core.exceptions import ConnectionClosedError

    for response, error in [
        (xt_packet(command, error_code=1), CommandError),
        (EmpireTimeoutError("timeout"), EmpireTimeoutError),
        (ConnectionClosedError("closed"), ConnectionClosedError),
    ]:
        client = member_client({command: response})
        with pytest.raises(error):
            getattr(client.alliance, method)(*args, timeout=0.1)


@pytest.mark.parametrize(
    "name,text", [(" ", "Text"), ("A", "Text"), ("a" * 39, "Text"), ("Name", "A"), ("Name", "a" * 2001)]
)
def test_create_checks_client_encoded_lengths(name, text):
    client = member_client()
    with pytest.raises(ValueError):
        client.alliance.create_topic(name, text, [ForumRankGroup.LEADER])
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("bad", [{"bad": 1}, ["bad"], {}, [], 5, True])
def test_malformed_topic_text_drops_only_its_row_with_warning(bad, caplog):
    malformed = {**topic(), "N": bad}
    client = member_client({"gat": xt_packet("gat", {"TC": 2, "T": [malformed, topic(8)]})})
    assert [entry.topic_id for entry in client.alliance.get_forum_topics().topics] == [8]
    assert "unreadable forum topics" in caplog.text


@pytest.mark.parametrize("bad", [{"bad": 1}, ["bad"], {}, [], 5, True])
def test_malformed_post_text_drops_only_its_row_with_warning(bad, caplog):
    post = {"RID": 1, "RT": "valid", "PN": "Poster", "AR": 8, "T": 1}
    client = member_client(
        {
            "gtr": xt_packet(
                "gtr", {"TN": "Name", "CN": "Author", "RG": [0], "R": [{**post, "RT": bad}, {**post, "RID": 2}]}
            )
        }
    )
    assert [entry.reply_id for entry in client.alliance.get_topic(7).posts] == [2]
    assert "unreadable forum posts" in caplog.text


@pytest.mark.parametrize("bad", [{"bad": 1}, ["bad"], {}, [], 5, True])
def test_malformed_detail_title_is_a_typed_packet_failure(bad):
    client = member_client({"gtr": xt_packet("gtr", {"TN": bad, "CN": "Author", "RG": [0]})})
    with pytest.raises(PacketError):
        client.alliance.get_topic(7)


@pytest.mark.parametrize("empty", [None, False, 0, ""])
def test_falsy_forum_text_remains_empty(empty):
    client = member_client(
        {
            "gat": xt_packet("gat", {"TC": 1, "T": [{**topic(), "N": empty}]}),
            "gtr": xt_packet(
                "gtr",
                {"TN": empty, "CN": "Author", "RG": [0], "R": [{"RID": 1, "RT": empty, "PN": "A", "AR": 8, "T": 1}]},
            ),
        }
    )
    assert client.alliance.get_forum_topics().topics[0].name == ""
    detail = client.alliance.get_topic(7)
    assert detail.name == "" and detail.posts[0].text == ""
