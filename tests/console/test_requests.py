from empire_core.console.requests import parse_request, reply_command, request_models


def test_every_request_model_is_indexed_by_its_command():
    assert [model.__name__ for model in request_models("gcl")] == ["GetCastlesRequest"]
    assert {model.__name__ for model in request_models("dms")} == {"DeleteMessageRequest", "DeleteMessagesRequest"}
    assert request_models("zzz") == ()


def test_reply_command_follows_a_request_answered_under_another_command():
    assert reply_command("jca") == "jaa"
    assert reply_command("gcl") == "gcl"
    assert reply_command("zzz") == "zzz"


def test_a_payload_parses_into_the_model_whose_keys_it_carries():
    one = parse_request("dms", {"MID": 7})
    many = parse_request("dms", {"MIDS": [7, 8]})
    assert type(one).__name__ == "DeleteMessageRequest" and type(many).__name__ == "DeleteMessagesRequest"


def test_a_payload_no_model_takes_is_none():
    assert parse_request("dms", {"MID": "seven"}) is None
    assert parse_request("zzz", {"A": 1}) is None
