"""Opening loot boxes: ole, gated and applied as the reward hub's mystery boxes do."""

import pytest

from empire_core.enums import CollectableKind
from empire_core.exceptions import CommandError
from empire_core.gamedata import Collectable, Currency, GameData, LootBox, LootBoxType, RewardId
from empire_core.player import MysteryBoxKey, OpenLootBoxRequest, OpenLootBoxResponse
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

ITEMS = {
    "lootBoxes": [
        {"lootBoxID": "5", "lootBoxTypeID": "1", "name": "MysteryBoxSilver", "rarity": "1", "lootBoxTombolaID": "21"},
    ],
    "lootBoxTypes": [{"lootBoxTypeID": "1", "lootBoxTheme": "MysteryBox", "lootBoxKeyPayoutThreshold": "10"}],
    "rewards": [{"rewardID": "77", "addC2": "15"}],
}
GLS = {"ALL": [{"ID": 5, "AMT": 3}], "KEY": [{"ID": 1, "AMT": 4}, {"ID": 2, "AMT": 1}]}
# The shape of a live ole reply: LTR lists one reward id per box, LTRR each box's collectable rows
OPENED = {
    "LID": 5,
    "UKI": 5000,
    "LTR": [77],
    "LTRR": [[["C2", 15], ["LM", 3]]],
    "KBS": 6,
    "TBF": 0,
    "KTR": [{"ID": 5001, "AMT": 1}],
}


def _client(script: dict | None = None, sce: list | None = None):
    state = logged_in_state(gls=GLS, sce=sce or [])
    client = make_client(script, state=state)  # type: ignore[arg-type]
    conn(client).on_packet = client._on_packet
    client.game_data = GameData.parse("test", ITEMS)
    return client


class TestWireShapes:
    def test_the_request(self):
        # C2SOpenLootBoxVO (bundle line 112368): ALL is 1 or 0
        request = OpenLootBoxRequest(loot_box_id=LootBox(5), key=MysteryBoxKey.RARE, open_all=True)
        assert request.to_payload() == {"LID": 5, "CID": 5001, "ALL": 1}
        assert OpenLootBoxRequest(loot_box_id=LootBox(5)).to_payload() == {"LID": 5, "CID": 5000, "ALL": 0}

    def test_the_reply(self):
        reply = OpenLootBoxResponse.model_validate(OPENED)

        assert reply.loot_box_id is LootBox(5)
        assert [(c.kind, c.amount) for c in reply.rewards] == [
            (CollectableKind.RUBIES, 15),
            (CollectableKind.CURRENCY, 3),
        ]
        assert reply.reward_ids == (RewardId(77),)
        assert (reply.key_progress, reply.key_bar_fills, reply.key_used) == (6, 0, MysteryBoxKey.COMMON)
        assert reply.keys_won == (Collectable.of_currency(5001, 1),)
        assert reply.raw_rewards == [77]

    def test_without_reward_rows_only_the_ids_are_read(self):
        reply = OpenLootBoxResponse.model_validate({key: value for key, value in OPENED.items() if key != "LTRR"})

        assert reply.reward_ids == (RewardId(77),)
        assert reply.rewards == ()


class TestGetLootBoxes:
    def test_the_status_is_requested_and_kept(self):
        # RewardHubMainDialogMysteryBoxes.show sends C2SGetLootBoxesStatus, with no fields
        client = _client({"gls": xt_packet("gls", {"ALL": [{"ID": 5, "AMT": 9}], "KEY": [{"ID": 1, "AMT": 2}]})})

        boxes = client.player.get_loot_boxes()

        assert conn(client).request_payloads == [("gls", {})]
        assert [(box.loot_box_id, box.amount) for box in boxes.loot_boxes] == [(LootBox(5), 9)]
        kept = client.player.loot_boxes
        assert kept is not None and kept.loot_boxes == boxes.loot_boxes
        # parse_GLS keeps the key progress of the types a gls leaves out
        assert [(int(keys.loot_box_type_id), keys.keys) for keys in kept.key_progress] == [(1, 2), (2, 1)]


class TestOpenLootBox:
    def test_a_common_key_opens_one_box_and_keeps_the_new_key_progress(self):
        client = _client({"ole": xt_packet("ole", OPENED)})

        opened = client.player.open_loot_box(LootBox(5))

        assert conn(client).request_payloads == [("ole", {"LID": 5, "CID": 5000, "ALL": 0})]
        assert opened.key_progress == 6
        boxes = client.player.loot_boxes
        assert boxes is not None
        assert boxes.keys(LootBoxType.MYSTERY_BOX) == 6 and boxes.keys(2) == 1
        # OLECommand does not lower the box count; the server's gls does
        assert boxes.amount(LootBox(5)) == 3

    def test_reward_ids_are_resolved_from_the_game_data(self):
        ids_only = {key: value for key, value in OPENED.items() if key != "LTRR"}
        client = _client({"ole": xt_packet("ole", ids_only)})

        opened = client.player.open_loot_box(LootBox(5))

        assert [(c.kind, c.amount) for c in opened.rewards] == [(CollectableKind.RUBIES, 15)]

    def test_all_boxes_open_with_the_common_key_only(self):
        client = _client({"ole": xt_packet("ole", OPENED)}, sce=[["RMBK", 3]])

        client.player.open_loot_box(LootBox(5), open_all=True)
        with pytest.raises(ValueError, match="common key"):
            client.player.open_loot_box(LootBox(5), MysteryBoxKey.RARE, open_all=True)

        assert conn(client).request_payloads == [("ole", {"LID": 5, "CID": 5000, "ALL": 1})]

    def test_a_rarer_key_must_be_held(self):
        client = _client({"ole": xt_packet("ole", OPENED)}, sce=[["RMBK", 1]])

        with pytest.raises(ValueError, match="EPIC"):
            client.player.open_loot_box(LootBox(5), MysteryBoxKey.EPIC)
        client.player.open_loot_box(LootBox(5), MysteryBoxKey.RARE)

        assert conn(client).request_payloads == [("ole", {"LID": 5, "CID": 5001, "ALL": 0})]

    def test_a_refusal_raises(self):
        client = _client({"ole": xt_packet("ole", {}, error_code=1)})

        with pytest.raises(CommandError):
            client.player.open_loot_box(LootBox(5))

        boxes = client.player.loot_boxes
        assert boxes is not None and boxes.keys(LootBoxType.MYSTERY_BOX) == 4


def test_the_key_currencies():
    # ClientConstCurrency.ID_MYSTERY_BOX_KEY_* (bundle line 1920)
    assert [key.value for key in MysteryBoxKey] == [5000, 5001, 5002, 5003]
    assert Currency.RARE_MYSTERY_KEY.currency_id == MysteryBoxKey.RARE
