"""Donating for a quest: the condition in the quest's game data row picks the command and the field."""

from __future__ import annotations

import pytest

from empire_core.gamedata import GameData
from empire_core.quests import (
    CurrencyId,
    FinishQuestConditionRequest,
    QuestConditionType,
    QuestDonateCurrencyRequest,
    QuestDonateResourcesRequest,
    QuestStarterClickRequest,
)
from tests.service_helpers import conn, make_client, request_payload

QUEST_ID = 3047
NO_RESOURCES = {"F": 0, "W": 0, "S": 0, "C1": 0, "O": 0, "C": 0, "I": 0, "G": 0}


def _client(conditions: str):
    client = make_client()
    client.game_data = GameData.parse("test", {"quests": [{"questID": str(QUEST_ID), "conditions": conditions}]})
    return client


def test_the_resource_request_sends_the_free_path():
    request = QuestDonateResourcesRequest(quest_id=QUEST_ID, food=500)

    assert request.to_payload() == {"QID": QUEST_ID, **NO_RESOURCES, "F": 500, "PWR": 0, "PO": -1}


def test_the_currency_request_sends_the_currency_id():
    request = QuestDonateCurrencyRequest(quest_id=QUEST_ID, currency_id=CurrencyId.KHAN_MEDALS, amount=40)

    assert request.to_payload() == {"QID": QUEST_ID, "CID": 10, "A": 40}


@pytest.mark.parametrize(
    ("condition", "field"),
    [
        ("donateFood", "F"),
        ("donateWood", "W"),
        ("donateStone", "S"),
        ("donateCurrency1", "C1"),
        ("donateCoal", "C"),
        ("donateOil", "O"),
        ("donateGlass", "G"),
        ("donateIron", "I"),
    ],
)
def test_a_resource_condition_sends_its_amount_in_its_field(condition, field):
    client = _client(f"{condition}+500+")

    client.quests.donate(QUEST_ID)

    assert conn(client).request_payloads == [("qdr", {"QID": QUEST_ID, **NO_RESOURCES, field: 500, "PWR": 0, "PO": -1})]


@pytest.mark.parametrize(("condition", "currency_id"), [("donateKhanMedals", 10), ("donateSamuraiTokens", 7)])
def test_a_currency_condition_sends_qdc(condition, currency_id):
    client = _client(f"buyRubies+1#{condition}+40+")

    client.quests.donate(QUEST_ID)

    assert conn(client).request_payloads == [("qdc", {"QID": QUEST_ID, "CID": currency_id, "A": 40})]


@pytest.mark.parametrize("quest_id", [QUEST_ID, 9999])
def test_a_quest_without_a_donate_condition_is_refused(quest_id):
    client = _client("buyRubies+1")

    with pytest.raises(ValueError):
        client.quests.donate(quest_id)

    assert conn(client).requested == []


@pytest.mark.parametrize(
    ("request_", "payload"),
    [
        (
            FinishQuestConditionRequest(condition_type=QuestConditionType.VISIT_GENERALS_OVERVIEW),
            {"QC": "visitGeneralsOverview", "QTID": -1},
        ),
        (
            FinishQuestConditionRequest(condition_type=QuestConditionType.VISIT_GENERALS_INN, target_id=2),
            {"QC": "visitGeneralsInn", "QTID": 2},
        ),
    ],
)
def test_the_finish_condition_request(request_, payload):
    assert request_.to_payload() == payload


@pytest.mark.parametrize(
    ("args", "payload"),
    [
        ((QuestConditionType.VISIT_GENERALS_OVERVIEW,), {"QC": "visitGeneralsOverview", "QTID": -1}),
        ((QuestConditionType.VISIT_GENERALS_INN, 2), {"QC": "visitGeneralsInn", "QTID": 2}),
    ],
)
def test_finish_condition_sends_without_waiting(args, payload):
    client = make_client()

    client.quests.finish_condition(*args)

    assert [request_payload(p) for p in conn(client).sent] == [payload]
    assert conn(client).requested == []


def test_the_quest_starter_request():
    assert QuestStarterClickRequest(quest_id=QUEST_ID).to_payload() == {"QID": QUEST_ID}


def test_finish_starter_sends_without_waiting():
    client = make_client()

    client.quests.finish_starter(QUEST_ID)

    assert [request_payload(p) for p in conn(client).sent] == [{"QID": QUEST_ID}]
    assert conn(client).requested == []
