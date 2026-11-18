"""Buying a sceat skill (bss) and finishing its activation with rubies (ssa)."""

import pytest

from empire_core.commanders import (
    BuySceatSkillRequest,
    BuySceatSkillResponse,
    SkipSceatSkillActivationRequest,
    SkipSceatSkillActivationResponse,
)
from empire_core.enums import GGEError, SceatSkillTab
from empire_core.exceptions import CommandError
from empire_core.gamedata import GameData, SceatSkill
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, make_client, xt_packet

BUILDINGS_SKILL = next(skill for skill in SceatSkill if skill.skill_tree_id == 3)
UNITS_SKILL = next(skill for skill in SceatSkill if skill.skill_tree_id == 4)
UNLISTED_TREE_SKILL = next(skill for skill in SceatSkill if skill.skill_tree_id == 5)

# The sceatSkillTrees rows of items 790.02 for trees 3 and 4; tree 5's row is left out
ITEMS = {
    "sceatSkills": [
        {"skillID": str(int(skill)), "skillTreeID": str(skill.skill_tree_id)}
        for skill in (BUILDINGS_SKILL, UNITS_SKILL, UNLISTED_TREE_SKILL)
    ],
    "sceatSkillTrees": [{"skillTreeID": "3", "tabID": "1"}, {"skillTreeID": "4", "tabID": "2"}],
}


def client_with(script=None):
    client = make_client(script)
    client.game_data = GameData.parse("790.02", ITEMS)
    return client


def test_the_requests_follow_the_client():
    assert BuySceatSkillRequest(skill=BUILDINGS_SKILL).to_payload() == {"ID": int(BUILDINGS_SKILL)}
    assert SkipSceatSkillActivationRequest(tab=SceatSkillTab.UNITS).to_payload() == {"TID": 2}


def test_buy_sends_the_level_and_needs_no_consent():
    client = client_with()
    client.player.buy_sceat_skill(UNITS_SKILL)
    assert conn(client).request_payloads == [("bss", {"ID": int(UNITS_SKILL)})]


def test_a_refused_buy_raises():
    client = client_with({"bss": xt_packet("bss", error_code=GGEError.NOT_ENOUGH_SPECIAL_CURRENCY)})
    with pytest.raises(CommandError):
        client.player.buy_sceat_skill(UNITS_SKILL)


@pytest.mark.parametrize("skill, tab", [(BUILDINGS_SKILL, 1), (UNITS_SKILL, 2)])
def test_the_skip_sends_the_skill_s_tab(skill, tab):
    client = client_with()
    client.player.skip_sceat_skill_activation(skill, spend_rubies=True)
    assert conn(client).request_payloads == [("ssa", {"TID": tab})]


def test_the_skip_needs_consent():
    client = client_with()
    with pytest.raises(ValueError, match="spend_rubies"):
        client.player.skip_sceat_skill_activation(BUILDINGS_SKILL)
    assert conn(client).request_payloads == []


def test_a_skill_without_a_tab_sends_nothing():
    client = client_with()
    with pytest.raises(ValueError, match="no Hall of Legends tab"):
        client.player.skip_sceat_skill_activation(UNLISTED_TREE_SKILL, spend_rubies=True)
    with pytest.raises(ValueError, match="no Hall of Legends tab"):
        client.player.skip_sceat_skill_activation(999999, spend_rubies=True)  # type: ignore[arg-type]
    assert conn(client).request_payloads == []


def test_a_refused_skip_raises():
    client = client_with({"ssa": xt_packet("ssa", error_code=GGEError.NOTHING_TO_SKIP)})
    with pytest.raises(CommandError):
        client.player.skip_sceat_skill_activation(UNITS_SKILL, spend_rubies=True)


def test_the_replies_carry_nothing():
    assert isinstance(parse_response("bss", {}), BuySceatSkillResponse)
    assert isinstance(parse_response("ssa", {}), SkipSceatSkillActivationResponse)
