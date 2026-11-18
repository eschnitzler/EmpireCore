"""Buying a time-limited campaign's quest and end reward with rubies: bcq and bcr."""

import pytest

from empire_core.exceptions import CommandError, EventNotRunningError
from empire_core.gamedata import Event
from empire_core.protocol.base import parse_response
from empire_core.quests import (
    BuyCampaignQuestRequest,
    BuyCampaignQuestResponse,
    BuyCampaignRewardRequest,
    BuyCampaignRewardResponse,
    Quest,
)
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

CAMPAIGN = {
    "EID": 95,
    "RS": 600,
    "RIDS": [3],
    "COL": 0,
    "ERV": 12,
    "CQS": [
        {"QID": 50, "CQID": 2, "QCS": "N"},
        {"QID": 51, "CQID": 3, "ST": 10, "QCS": "C"},
        {"QID": 52, "CQID": 1, "ST": 10, "P": [4], "QCS": "F"},
        {"QID": 53, "CQID": 4, "ST": 10, "P": [1]},
    ],
}


def campaign_client(script=None, **entry):
    state = logged_in_state()
    state.update_from_packet("sei", {"E": [{**CAMPAIGN, **entry}]})
    return make_client(script, state=state)


def campaign_quest(client, campaign_quest_id: int) -> Quest:
    campaign = client.state.get_event(Event.TIME_LIMITED_CAMPAIGN_EVENT)
    return next(quest for quest in campaign.quests if quest.campaign_quest_id == campaign_quest_id)


def test_the_models():
    assert BuyCampaignQuestRequest(campaign_quest_id=4).to_payload() == {"CQID": 4}
    assert BuyCampaignRewardRequest().to_payload() == {}
    assert isinstance(parse_response("bcq", {}), BuyCampaignQuestResponse)
    reply = parse_response("bcr", {"gcu": {"C1": 7, "C2": 30}})
    assert isinstance(reply, BuyCampaignRewardResponse)
    assert reply.currencies is not None and reply.currencies.rubies == 30


def test_a_quest_purchase_sends_its_place_in_the_campaign():
    client = campaign_client()
    client.events.buy_campaign_quest(campaign_quest(client, 1), spend_rubies=True)
    assert conn(client).request_payloads == [("bcq", {"CQID": 1})]


@pytest.mark.parametrize("campaign_quest_id", [2, 3])
def test_a_locked_or_done_quest_is_not_bought(campaign_quest_id):
    client = campaign_client()
    with pytest.raises(ValueError, match="done or not open"):
        client.events.buy_campaign_quest(campaign_quest(client, campaign_quest_id), spend_rubies=True)
    assert conn(client).request_payloads == []


def test_a_running_quest_is_not_bought():
    client = campaign_client()
    with pytest.raises(ValueError, match="has not failed"):
        client.events.buy_campaign_quest(campaign_quest(client, 4), spend_rubies=True)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("entry", [{"QID": 7, "P": [0]}, {"QID": 7, "CQID": 1, "QCS": "F"}])
def test_a_quest_outside_the_campaign_is_not_bought(entry):
    client = campaign_client()
    with pytest.raises(ValueError, match="not one of"):
        client.events.buy_campaign_quest(Quest.from_entry(entry), spend_rubies=True)
    assert conn(client).request_payloads == []


def test_nothing_is_bought_without_a_campaign():
    client = make_client(state=logged_in_state())
    with pytest.raises(EventNotRunningError):
        client.events.buy_campaign_reward(spend_rubies=True)
    assert conn(client).request_payloads == []


def test_the_reward_purchase_sends_bcr():
    client = campaign_client({"bcr": xt_packet("bcr", {"gcu": {"C1": 7, "C2": 30}})})
    reply = client.events.buy_campaign_reward(spend_rubies=True)
    assert conn(client).request_payloads == [("bcr", {})]
    assert reply.currencies is not None and reply.currencies.coins == 7


def test_a_collected_reward_is_not_bought_again():
    client = campaign_client(COL=1)
    with pytest.raises(ValueError, match="collected"):
        client.events.buy_campaign_reward(spend_rubies=True)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize(
    "buy",
    [
        lambda client: client.events.buy_campaign_quest(campaign_quest(client, 1)),
        lambda client: client.events.buy_campaign_reward(),
    ],
)
def test_both_need_consent(buy):
    client = campaign_client()
    with pytest.raises(ValueError, match="spend_rubies"):
        buy(client)
    assert conn(client).request_payloads == []


def test_a_refusal_raises():
    client = campaign_client({"bcq": xt_packet("bcq", error_code=1)})
    with pytest.raises(CommandError):
        client.events.buy_campaign_quest(campaign_quest(client, 1), spend_rubies=True)


def test_the_reward_reply_reaches_the_currencies():
    state = logged_in_state()
    state.update_from_packet("bcr", {"gcu": {"C1": 7, "C2": 30}})
    assert state.get_local_player().rubies == 30
