"""Public computations use loaded tables unless an offline dataset is supplied."""

import pytest

from empire_core.combat import EffectResolver, Inventory, construction_item_bonuses, legend_skill_value
from empire_core.commanders import SkillList
from empire_core.enums import TitleSystem
from empire_core.exceptions import GameDataNotLoadedError
from empire_core.gamedata import GameData, describe_effects, is_current
from empire_core.player import titles_in_order
from tests.service_helpers import conn, logged_in_state, make_client


def _data(cost: int = 6) -> GameData:
    return GameData.parse("test", {"legendskills": [{"skillID": "2", "totalCostSkillPoints": str(cost)}]})


def test_standalone_reads_use_the_loaded_data(stub_game_data_load):
    data = _data()
    loads = stub_game_data_load(data)
    skills = SkillList.model_validate({"SID": [2], "SP": 10})

    assert skills.spent_points() == 6
    assert skills.available_points() == 4
    assert Inventory({}).soldier_count() == 0
    assert is_current() is False
    assert EffectResolver().game_data is data
    assert construction_item_bonuses([]) == []
    assert legend_skill_value([], "spyAmountBonus") == 0
    assert titles_in_order(TitleSystem.GLORY) == []
    assert describe_effects([]) == []
    assert len(loads) == 1


def test_explicit_dataset_does_not_load_or_use_the_process_data(stub_game_data_load):
    loads = stub_game_data_load(_data(9))
    skills = SkillList.model_validate({"SID": [2], "SP": 10})

    assert skills.available_points(game_data=_data(3)) == 7
    assert EffectResolver(game_data=_data()).game_data.version == "test"
    assert loads == []


def test_missing_data_raises_the_typed_loading_error():
    with pytest.raises(GameDataNotLoadedError):
        SkillList.model_validate({"SID": [2], "SP": 10}).available_points()


def test_player_point_reads_use_the_clients_data_and_send_nothing(stub_game_data_load):
    loads = stub_game_data_load(_data(9))
    state = logged_in_state(skl={"SID": [2], "SP": 10})
    client = make_client(state=state)
    client.game_data = _data(3)

    assert client.player.spent_skill_points == 3
    assert client.player.available_skill_points == 7
    assert conn(client).request_payloads == []
    assert loads == []


def test_points_are_unknown_before_skills_arrive(stub_game_data_load):
    loads = stub_game_data_load(_data())
    client = make_client(state=logged_in_state())

    assert client.player.spent_skill_points is None
    assert client.player.available_skill_points is None
    assert loads == []


def test_player_titles_use_cached_sections_and_client_tables():
    state = logged_in_state()
    state.update_from_packet("ufa", {"CF": 100, "HF": 100})
    client = make_client(state=state)
    client.game_data = GameData.parse("test", {"titles": [{"titleID": "0", "type": "FAME", "threshold": "0"}]})

    assert client.player.title_ids == [0]
    assert conn(client).request_payloads == []


def test_reward_models_resolve_the_loaded_tables(stub_game_data_load):
    from empire_core.gamedata import TitleDef

    stub_game_data_load(GameData.parse("test", {}))
    assert TitleDef.model_validate({"titleID": "2", "type": "FAME"}).rewards() == ()


def test_nonempty_combat_calculations_use_one_loaded_dataset(stub_game_data_load):
    from empire_core.combat import pick_soldier_stack
    from tests.combat.combat_helpers import solver_data

    loads = stub_game_data_load(solver_data())
    inventory = Inventory({601: 10, 999999: 100})

    assert inventory.soldier_count() == 10
    assert pick_soldier_stack(4, inventory) == (601, 4)
    assert inventory.soldier_count() == 6
    assert len(loads) == 1


def test_campaign_rewards_use_the_loaded_dataset(stub_game_data_load):
    from empire_core.enums import CollectableKind

    state = logged_in_state()
    state.update_from_packet("sei", {"E": [{"EID": 95, "RS": 600, "RIDS": [3], "CQS": []}]})
    stub_game_data_load(GameData.parse("test", {"rewards": [{"rewardID": "3", "addC1": "100"}]}))

    assert [(reward.kind, reward.amount) for reward in state.get_event(95).rewards()] == [(CollectableKind.COINS, 100)]


def test_empty_explicit_dataset_is_not_replaced_by_loaded_data(stub_game_data_load):
    loads = stub_game_data_load(_data(9))
    skills = SkillList.model_validate({"SID": [2], "SP": 10})

    assert skills.available_points(game_data=GameData.parse("empty", {})) == 10
    assert loads == []
