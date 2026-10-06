"""Tests for the rewards service and its models."""

from __future__ import annotations

import threading

import pytest

from empire_core.client.client import EmpireClient
from empire_core.enums import CollectableKind
from empire_core.exceptions import (
    CommandError,
    LoginBonusUnavailableError,
    NotInAllianceError,
    PacketError,
    ReceiveThreadError,
)
from empire_core.gamedata import Collectable, Currency, Unit
from empire_core.rewards import (
    ActivityChestInfo,
    CollectLoginBonusRequest,
    GetLoginBonusResponse,
    GetLostAndFoundResponse,
    GetStartupBonusResponse,
    GetWeeklyHonorResponse,
    LoginBonusSpecial,
)
from empire_core.state.manager import GameState
from tests.service_helpers import StubPlayer, StubState, conn, make_client, xt_packet


def leveled_client(script=None, xp: int = 9_300_000, alliance_id: int = 0):
    """A client whose player has ``xp``, past the login bonus gate unless told otherwise."""
    return make_client(script, state=StubState(StubPlayer(xp=xp, alliance_id=alliance_id)))


# The keys a level-70 account's alb carried live, in the parseALB layout; the amounts are made up
LEVEL_70_ALB = {
    "D": 2,
    "R": [
        {"D1": [{"REW": [{"U": [[620, 40]], "MS2": [3], "C1": [25000]}]}, {"PICK": [{"C1": [25000]}]}, {}, {}]},
        {"D2": [{"REW": [{"HF": [2], "F": [5000], "S": [5000]}]}, {"PICK": [{"F": [5000]}]}, {}, {}]},
        {"D3": [{"REW": [{"C2": [50], "U": [[629, 20]], "C1": [30000]}]}, {"PICK": []}, {"ALLI": []}, {"VIP": []}]},
    ],
}


# Skaar's alb, as captured live (two of its days)
SKAAR_ALB = {
    "D": 1,
    "R": [
        {
            "D1": [
                {"REW": [{"U": [[664, 5]], "MS2": [1], "C1": [2000], "HF": [240]}]},
                {"PICK": [{"C1": [2000]}]},
                {"ALLI": [{"R": [["C2", 45]]}]},
                {},
            ]
        },
        {"D2": [{"REW": [{"U": [[614, 5]], "F": [5000], "MS3": [1]}]}, {}, {}, {}]},
    ],
}


# The alb layout CastleLoginBonusData.parseALB reads: R[d]["D"+(d+1)] = [{REW}, {PICK}, {ALLI}, {VIP}]
ALB = {
    "D": 8,
    "R": [
        {"D1": [{"REW": [{"C1": [500]}]}, {"PICK": [{"C1": [500]}]}, {"ALLI": []}, {"VIP": []}]},
        {"D2": [{"REW": [{"C1": [700], "U": [[620, 5]], "SO": "-1"}]}, {"PICK": []}, {"ALLI": []}, {"VIP": []}]},
    ],
}


class TestLoginBonusRewards:
    def test_skaars_login_bonus(self):
        bonus = GetLoginBonusResponse.model_validate(SKAAR_ALB)

        first, second = bonus.days
        assert [(item.kind, item.item, item.amount) for item in first.rewards] == [
            (CollectableKind.UNITS, Unit.KINGSCROSSBOWMAN, 5),
            (CollectableKind.CURRENCY, Currency.MS2, 1),
            (CollectableKind.COINS, None, 2000),
            (CollectableKind.OTHER, None, 1),
        ]
        assert first.picked == Collectable.from_entry("C1", 2000)
        # collectReward falls back to the first [key, value] pair under R
        assert first.alliance_reward == Collectable.from_entry("C2", 45)
        assert first.vip_reward is None and second.picked is None
        assert [item.send_key for item in second.rewards] == ["U", "F", "MS3"]

    def test_a_units_reward_is_sent_with_its_unit(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": SKAAR_ALB})})
        today = GetLoginBonusResponse.model_validate(SKAAR_ALB).today
        assert today is not None

        client.rewards.collect_login_bonus(today.rewards[0])
        assert conn(client).request_payloads == [("clb", {"ID": 614, "I": "U", "SP": None})]

    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            ("B", {"ID": 17, "D": 3600}, "PG"),
            ("B", {"ID": 18, "D": 3600}, "PG"),
            ("B", {"ID": 20, "D": 3600}, "KTB"),
            ("B", {"ID": 21, "D": 3600}, "XPB"),
            ("B", {"ID": 22, "D": 3600}, "STB"),
            ("B", {"ID": 23, "D": 3600}, "LTB"),
            ("B", {"ID": 24, "D": 3600}, "GPB"),
            ("B", {"ID": 26, "D": 3600}, "ACB"),
            ("B", {"ID": 27, "D": 3600}, "RPB"),
            ("B", {"ID": 28, "D": 3600}, "KMB"),
            ("B", {"ID": 29, "D": 3600}, "REPB"),
            # a prime sale booster, one with no type of its own, and a string id the strict switch misses
            ("B", {"ID": 6, "D": 3600}, "B"),
            ("B", {"ID": 25, "D": 3600}, "B"),
            ("B", {"ID": "17", "D": 3600}, "B"),
            ("GE", 11, "RE"),
            ("GE", 14, "RE"),
            ("GE", 10, "GE"),
            ("GE", 15, "GE"),
            ("GE", True, "GE"),
            ("C1", 100, "C1"),
            ("MS2", 3, "MS2"),
            ("MS", ["MS2", 3], "MS2"),
        ],
    )
    def test_the_send_key_is_the_one_the_client_sends(self, key, value, expected):
        # getTypeByServerKey (bundle lines 1603-1629), then getServerKeyByCollectable (bundle line 1646)
        assert Collectable.from_entry(key, value).send_key == expected


class TestLoginBonus:
    def test_today_is_the_day_index_modulo_seven(self):
        bonus = GetLoginBonusResponse.model_validate(ALB)

        today = bonus.today
        assert today is not None and today.day == 1
        assert [item.key for item in today.rewards] == ["C1", "U"]
        assert today.picked is None

    def test_picked_and_special_rewards(self):
        alb = {
            "D": 0,
            "R": [
                {
                    "D1": [
                        {"REW": [{"C1": [500]}]},
                        {"PICK": [{"C1": [500]}]},
                        {"ALLI": [{"R": [[1], ["W", 200]]}]},
                        {"VIP": []},
                    ]
                }
            ],
        }
        today = GetLoginBonusResponse.model_validate(alb).today

        assert today is not None
        assert today.picked == Collectable.from_entry("C1", 500)
        # collectReward falls back to the first [key, value] pair under R
        assert today.alliance_reward == Collectable.from_entry("W", 200)
        assert today.vip_reward is None

    @pytest.mark.parametrize(
        ("picked", "alli", "in_alliance", "expected"),
        [
            ([], [], False, True),
            ([{"C1": [5]}], [], False, False),
            ([{"C1": [5]}], [], True, True),
            ([{"C1": [5]}], [{"C1": [1]}], True, False),
        ],
    )
    def test_has_anything_to_collect(self, picked, alli, in_alliance, expected):
        alb = {"D": 0, "R": [{"D1": [{"REW": [{"C1": [5]}]}, {"PICK": picked}, {"ALLI": alli}, {"VIP": []}]}]}
        bonus = GetLoginBonusResponse.model_validate(alb)
        assert bonus.has_anything_to_collect(in_alliance=in_alliance) is expected

    def test_the_pick_sends_its_nulls_as_the_client_does(self):
        assert CollectLoginBonusRequest(reward_key="C1").to_payload() == {"ID": -1, "I": "C1", "SP": None}
        assert '"SP":null' in CollectLoginBonusRequest(reward_key="C1").to_packet()

    def test_get_login_bonus(self):
        client = leveled_client({"alb": xt_packet("alb", ALB)})

        bonus = client.rewards.get_login_bonus()

        assert bonus.day_index == 8
        assert conn(client).request_payloads == [("alb", {})]

    def test_collect_a_units_reward_sends_its_unit(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": ALB})})
        bonus = client.rewards.collect_login_bonus(Collectable.from_entry("U", [620, 5]))

        assert bonus.day_index == 8
        assert conn(client).request_payloads == [("clb", {"ID": 620, "I": "U", "SP": None})]

    def test_collect_a_special_bonus(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": ALB})})

        client.rewards.collect_login_bonus_special(LoginBonusSpecial.VIP)

        assert conn(client).request_payloads == [("clb", {"ID": -1, "I": None, "SP": "VIP"})]

    def test_collect_the_alliance_bonus_in_an_alliance(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": ALB})}, alliance_id=0)

        client.rewards.collect_login_bonus_special(LoginBonusSpecial.ALLIANCE)

        assert conn(client).request_payloads == [("clb", {"ID": -1, "I": None, "SP": "ALLI"})]

    def test_the_alliance_bonus_outside_an_alliance_sends_nothing(self):
        # the dialog enables the alliance bonus only with isInAlliance (bundle line 39230)
        client = leveled_client(alliance_id=-1)
        with pytest.raises(NotInAllianceError):
            client.rewards.collect_login_bonus_special(LoginBonusSpecial.ALLIANCE)
        assert conn(client).request_payloads == []

    def test_the_vip_bonus_outside_an_alliance_is_left_to_the_server(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": ALB})}, alliance_id=-1)
        client.rewards.collect_login_bonus_special(LoginBonusSpecial.VIP)
        assert conn(client).request_payloads == [("clb", {"ID": -1, "I": None, "SP": "VIP"})]

    def test_a_booster_pick_sends_its_own_type_key(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": ALB})})
        client.rewards.collect_login_bonus(Collectable.from_entry("B", {"ID": 21, "D": 3600}))
        assert conn(client).request_payloads == [("clb", {"ID": -1, "I": "XPB", "SP": None})]

    def test_a_minute_skip_under_ms_is_sent_as_its_currency(self):
        client = leveled_client({"clb": xt_packet("clb", {"alb": ALB})})
        client.rewards.collect_login_bonus(Collectable.from_entry("MS", ["MS2", 3]))
        assert conn(client).request_payloads == [("clb", {"ID": -1, "I": "MS2", "SP": None})]

    def test_a_reward_the_client_has_no_type_for_sends_nothing(self):
        client = leveled_client()
        with pytest.raises(ValueError, match="HF"):
            client.rewards.collect_login_bonus(Collectable.from_entry("HF", 240))
        assert conn(client).request_payloads == []

    def test_each_reward_of_a_level_70_login_bonus_is_sent_under_its_key(self):
        bonus = GetLoginBonusResponse.model_validate(LEVEL_70_ALB)
        today = bonus.today
        assert today is not None and today.picked is None
        assert {item.key for day in bonus.days for item in day.rewards} == {"U", "MS2", "C1", "HF", "F", "S", "C2"}
        rewards = [item for day in bonus.days for item in day.rewards]
        assert [item.key for item in rewards if item.kind is CollectableKind.OTHER] == ["HF"]
        assert all(item.send_key == item.key for item in rewards if item.kind is not CollectableKind.OTHER)

        client = leveled_client({"clb": xt_packet("clb", {"alb": LEVEL_70_ALB})})
        client.rewards.collect_login_bonus(today.rewards[1])
        assert conn(client).request_payloads == [("clb", {"ID": 629, "I": "U", "SP": None})]

    def test_xp_the_player_data_never_sent_is_unknown(self):
        # a player read from gpi alone has no XP yet; its 0 default is no reading
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})
        client = make_client({"alb": xt_packet("alb", ALB)}, state=state)  # type: ignore[arg-type]
        with pytest.raises(LoginBonusUnavailableError) as raised:
            client.rewards.get_login_bonus()
        assert raised.value.xp is None
        assert conn(client).request_payloads == []

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gxp": {"XP": 5000, "LVL": 20}})
        client.rewards.get_login_bonus()
        assert conn(client).request_payloads == [("alb", {})]
        state.shutdown()

    @pytest.mark.parametrize("player", [StubPlayer(xp=1199), None])
    def test_below_the_xp_gate_nothing_is_sent(self, player):
        # GBDCommand sends alb only with userXP >= REQUIRED_XP; the server stays silent below it
        client = make_client(state=StubState(player))
        with pytest.raises(LoginBonusUnavailableError) as raised:
            client.rewards.get_login_bonus()
        with pytest.raises(LoginBonusUnavailableError):
            client.rewards.collect_login_bonus(Collectable.from_entry("C1", 5))
        with pytest.raises(LoginBonusUnavailableError):
            client.rewards.collect_login_bonus_special(LoginBonusSpecial.ALLIANCE)
        assert raised.value.required_xp == 1200
        assert raised.value.xp == (None if player is None else 1199)
        assert conn(client).request_payloads == []
        assert conn(client).sent == []

    def test_at_the_gate_it_is_sent(self):
        client = leveled_client({"alb": xt_packet("alb", ALB)}, xp=1200)
        client.rewards.get_login_bonus()
        assert conn(client).request_payloads == [("alb", {})]

    def test_an_unknown_special_bonus_sends_nothing(self):
        client = leveled_client()
        with pytest.raises(ValueError, match="LoginBonusSpecial"):
            client.rewards.collect_login_bonus_special("GOLD")  # type: ignore[arg-type]
        assert conn(client).request_payloads == []

    def test_a_reply_without_the_login_bonus_raises(self):
        client = leveled_client({"clb": xt_packet("clb", {})})
        with pytest.raises(PacketError):
            client.rewards.collect_login_bonus(Collectable.from_entry("C1", 5))

    def test_a_refused_pick_raises(self):
        client = leveled_client({"clb": xt_packet("clb", {}, error_code=1)})
        with pytest.raises(CommandError):
            client.rewards.collect_login_bonus(Collectable.from_entry("C1", 5))


class TestStartupBonus:
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [({"NRR": 2, "CC": 1}, True), ({"NRR": 2, "CC": 0}, False), ({"NRR": -1, "CC": 1}, False)],
    )
    def test_collectable(self, payload, expected):
        assert GetStartupBonusResponse.model_validate(payload).collectable is expected

    def test_read_and_collect(self):
        client = make_client({"sli": xt_packet("sli", {"NRR": 3, "CC": 1}), "slc": xt_packet("slc", {})})

        assert client.rewards.get_startup_bonus().next_reward_id == 3
        assert client.rewards.collect_startup_bonus() is True
        assert conn(client).request_payloads == [("sli", {}), ("slc", {})]

    def test_a_refused_collect_is_false(self):
        client = make_client({"slc": xt_packet("slc", {}, error_code=1)})
        assert client.rewards.collect_startup_bonus() is False


class TestLostAndFound:
    ITEM = {"LFID": 12, "ROT": "UE", "ROV": 4711, "ET": 3600, "CT": 1700000000, "LFES": 0}

    def test_items_and_time_left(self):
        response = GetLostAndFoundResponse.model_validate({"lfe": [self.ITEM]})

        item = response.items[0]
        assert (item.item_id, item.reward.kind, item.reward.item, item.received_time) == (
            12,
            CollectableKind.EQUIPMENT_UNIQUE,
            4711,
            1700000000,
        )
        assert item.remaining_seconds(now=item.received_at + 600) == pytest.approx(3000)
        assert item.remaining_seconds(now=item.received_at + 4000) == 0

    def test_read_and_collect(self):
        client = make_client({"lfe": xt_packet("lfe", {"lfe": [self.ITEM]}), "clf": xt_packet("clf", {})})

        items = client.rewards.get_lost_and_found()
        assert client.rewards.collect_lost_and_found(items[0].item_id) is True
        assert conn(client).request_payloads == [("lfe", {}), ("clf", {"LFID": 12})]


class TestActivityChest:
    def test_ready_once_its_time_ran_out(self):
        chest = ActivityChestInfo.model_validate({"CID": 4, "TTU": 60})

        assert chest.is_active
        assert not chest.is_ready(now=chest.received_at + 30)
        assert chest.is_ready(now=chest.received_at + 61)

    def test_inactive_without_a_chest(self):
        chest = ActivityChestInfo.model_validate({"CID": -1, "TTU": 0})
        assert not chest.is_active and not chest.is_ready()

    def test_the_push_is_kept_and_announced(self):
        client = make_client()
        seen: list[ActivityChestInfo] = []
        client.rewards.on_activity_chest(seen.append)
        assert client.rewards.activity_chest is None

        client._on_packet(xt_packet("uac", {"CID": 2, "TTU": 0}))

        chest = client.rewards.activity_chest
        assert chest is not None and chest.next_reward_id == 2 and chest.is_ready()
        assert seen == [chest]
        client.rewards.on_activity_chest.remove(seen.append)

    @staticmethod
    def ready_client(script=None, chest=None):
        client = make_client(script)
        client._on_packet(xt_packet("uac", chest or {"CID": 2, "TTU": 0}))
        return client

    def test_open_sends_uoa_and_returns_the_next_chest(self):
        client = self.ready_client({"uac": xt_packet("uac", {"CID": 3, "TTU": 600})})

        chest = client.rewards.open_activity_chest()

        assert chest is not None and (chest.next_reward_id, chest.seconds) == (3, 600)
        # uoa goes out with no reply of its own owed; the wait is for the next uac
        assert [frame.split("%")[3] for frame in conn(client).request_frames] == ["uoa"]
        assert conn(client).requested == ["uac"]
        assert conn(client).sent == []

    @pytest.mark.parametrize("chest", [None, {"CID": 2, "TTU": 60}, {"CID": -1, "TTU": 0}])
    def test_a_chest_not_ready_sends_nothing(self, chest):
        # CastleActivityBonusDialog.onClick sends uoa only with no time left (bundle line 104934)
        client = make_client() if chest is None else self.ready_client(chest=chest)
        with pytest.raises(ValueError, match="not ready"):
            client.rewards.open_activity_chest()
        assert conn(client).request_frames == [] and conn(client).sent == []

    @pytest.mark.parametrize(
        ("pushed", "taken"),
        [({"CID": 2, "TTU": 0}, False), ({"CID": 3, "TTU": 0}, True), ({"CID": 2, "TTU": 120}, True), ([], True)],
    )
    def test_only_a_uac_past_the_opened_chest_is_its_answer(self, pushed, taken):
        # a non-object is taken too, so it raises PacketError rather than running out the timeout
        client = self.ready_client({"uac": xt_packet("uac", {"CID": 3, "TTU": 600})})
        client.rewards.open_activity_chest()
        accepts = conn(client).accepts[0]
        assert accepts(xt_packet("uac", pushed)) is taken

    def test_a_stale_uac_is_no_answer(self):
        client = self.ready_client({"uac": xt_packet("uac", {"CID": 2, "TTU": 0})})
        assert client.rewards.open_activity_chest() is None

    def test_an_error_uac_raises(self):
        client = self.ready_client({"uac": xt_packet("uac", {}, error_code=1)})
        with pytest.raises(CommandError):
            client.rewards.open_activity_chest()

    def test_a_uac_that_is_no_object_raises(self):
        client = self.ready_client({"uac": xt_packet("uac", [])})
        with pytest.raises(PacketError):
            client.rewards.open_activity_chest()

    def test_on_the_receive_thread_nothing_is_sent(self):
        class Socket:
            connected = True

            def __init__(self) -> None:
                self.sent: list[str] = []

            def send(self, data: str) -> None:
                self.sent.append(data)

            def close(self) -> None:
                self.connected = False

        client = EmpireClient(username="user", password="pass")
        try:
            socket = Socket()
            connection = client.connection
            connection.ws = socket  # type: ignore[assignment]
            connection._running = True
            client._on_packet(xt_packet("uac", {"CID": 2, "TTU": 0}))
            connection._recv_thread = threading.current_thread()
            with pytest.raises(ReceiveThreadError):
                client.rewards.open_activity_chest()
            assert socket.sent == []
        finally:
            client.close()


class TestWeeklyHonor:
    def test_ready_with_a_rank_last_week(self):
        honor = GetWeeklyHonorResponse.model_validate({"LWR": 3, "CWR": 5, "RT": 100, "LID": 2})

        assert honor.is_ready and (honor.current_rank, honor.league_id) == (5, 2)
        assert honor.remaining_seconds(now=honor.received_at + 40) == pytest.approx(60)
        assert not GetWeeklyHonorResponse.model_validate({"LWR": 0, "CWR": 5, "RT": 1, "LID": 2}).is_ready

    def test_read_and_redeem(self):
        client = make_client(
            {
                "gwh": xt_packet("gwh", {"LWR": 3, "CWR": 5, "RT": 100, "LID": 2}),
                "rwb": xt_packet("rwb", {"gcu": {"C1": 900, "C2": 4}}),
            }
        )

        assert client.rewards.get_weekly_honor().is_ready
        redeemed = client.rewards.redeem_weekly_honor()

        assert redeemed.currencies is not None and redeemed.currencies.coins == 900
        assert conn(client).request_payloads == [("gwh", {}), ("rwb", {})]

    def test_the_reward_coins_reach_state(self):
        # RWBCommand passes the reply to parseRWB, which reads its gcu
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet("rwb", {"gcu": {"C1": 900, "C2": 5}})
        player = state.get_local_player()
        assert player is not None and player.coins == 900
        state.update_from_packet("rwb", {"gcu": {"C1": 1, "C2": 1}}, 3)
        player = state.get_local_player()
        assert player is not None and player.coins == 900
        state.shutdown()
