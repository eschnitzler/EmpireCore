"""Event minigames: requests as the client builds them, replies and pushes as the client reads them."""

import pytest

from empire_core.enums import CollectableKind, GachaRarity, Kingdom, LuckyWheelType, WorldCupVote
from empire_core.exceptions import CommandError, EventNotRunningError
from empire_core.gamedata import Event, GameData
from empire_core.protocol.base import get_response_model
from empire_core.protocol.models import (
    ColossusCoinDepositResponse,
    GachaInfoResponse,
    GachaSpinResponse,
    LuckyWheelSpinResponse,
)
from empire_core.state.manager import GameState
from tests.service_helpers import conn, gcl_castles, make_client, xt_packet

WHEEL = {"HVPM": 1, "HFS": 0, "PMA": 1, "CWC": 3, "WCP": 2, "JSID": 7, "JHID": 8}


def events_client(entries, script=None, castles=None):
    client = make_client(script or {}, state=GameState())
    client.state.castles = {castle.id: castle for castle in gcl_castles(*(castles or []))}
    client._on_packet(xt_packet("sei", {"E": [{"RS": 600, **entry} for entry in entries]}))
    conn(client).on_packet = client._on_packet
    return client


class TestLuckyWheel:
    def test_spin_sends_the_wheel_and_updates_it(self):
        reply = {**WHEEL, "WC": 4, "R": [["C1", 500]], "OR": [12], "OP": [40]}
        client = events_client([{"EID": 15}], {"lws": xt_packet("lws", reply)})
        result = client.events.spin_lucky_wheel()
        assert conn(client).request_payloads == [("lws", {"LWET": 0})]
        assert result.winning_category == 4
        assert result.rewards[0].kind is CollectableKind.COINS and result.rewards[0].amount == 500
        wheel = client.state.get_event(Event.LUCKY_WHEEL)
        assert wheel is not None
        assert (wheel.pro_mode, wheel.win_class, wheel.win_class_progress, wheel.jackpot_set_id) == (True, 3, 2, 7)
        assert (wheel.own_rank, wheel.own_points) == (12, 40)

    def test_sale_days_spin_updates_the_sale_days_wheel(self):
        reply = {**WHEEL, "LWET": 1, "WC": 1, "R": []}
        client = events_client([{"EID": 15}, {"EID": 89}], {"lws": xt_packet("lws", reply)})
        client.events.spin_lucky_wheel(LuckyWheelType.SALE_DAYS)
        assert conn(client).request_payloads == [("lws", {"LWET": 1})]
        assert client.state.get_event(Event.SALE_DAYS_LUCKY_WHEEL).win_class == 3
        assert client.state.get_event(Event.LUCKY_WHEEL).win_class == 0

    def test_mode_change_flips_the_mode(self):
        client = events_client([{"EID": 15, "PMA": 0}], {"lwm": xt_packet("lwm", {"JSID": 2, "JHID": 5})})
        client.events.change_lucky_wheel_mode()
        wheel = client.state.get_event(Event.LUCKY_WHEEL)
        assert conn(client).request_payloads == [("lwm", {})]
        assert (wheel.pro_mode, wheel.jackpot_set_id, wheel.jackpot_spin_set_id) == (True, 2, 5)

    @pytest.mark.parametrize(
        "method,command", [("buy_lucky_wheel_jackpot", "lwj"), ("increase_lucky_wheel_win_class", "lwc")]
    )
    def test_ruby_actions_need_consent_and_update_the_wheel(self, method, command):
        client = events_client([{"EID": 15}], {command: xt_packet(command, {**WHEEL, "R": []})})
        with pytest.raises(ValueError, match="spend_rubies=True"):
            getattr(client.events, method)()
        assert conn(client).request_payloads == []
        getattr(client.events, method)(spend_rubies=True)
        assert conn(client).request_payloads == [(command, {})]
        assert client.state.get_event(Event.LUCKY_WHEEL).win_class == 3

    def test_refused_spin_raises_and_keeps_the_wheel(self):
        client = events_client([{"EID": 15}], {"lws": xt_packet("lws", error_code=1)})
        before = client.state.get_event(Event.LUCKY_WHEEL)
        with pytest.raises(CommandError):
            client.events.spin_lucky_wheel()
        assert client.state.get_event(Event.LUCKY_WHEEL) is before

    def test_not_running_sends_nothing(self):
        client = events_client([])
        with pytest.raises(EventNotRunningError):
            client.events.spin_lucky_wheel()
        assert conn(client).request_payloads == []

    def test_jackpot_reply_parses_as_a_spin(self):
        model = get_response_model("lwj")
        assert model is not None and issubclass(model, LuckyWheelSpinResponse)


class TestGacha:
    def test_pull_sends_the_pulls_and_updates_the_event(self):
        reply = {"ID": 31, "OP": 9, "OR": 4, "FCRT": 60, "LTR": [{"RR": [["C2", 5]], "R": 3}, {"RR": [], "R": 9}]}
        client = events_client([{"EID": 127}], {"dge": xt_packet("dge", reply)})
        result = client.events.pull_gacha(Event.CHRISTMAS_GACHA, 2, spend_rubies=True)
        assert conn(client).request_payloads == [("dge", {"EID": 127, "AMT": 2, "OB": 0})]
        assert isinstance(result, GachaSpinResponse) and result.gacha_id == 31
        assert result.pulls[0].rarity is GachaRarity.EPIC and result.pulls[0].rewards[0].amount == 5
        assert result.pulls[1].rarity == 9
        gacha = client.state.get_event(Event.CHRISTMAS_GACHA)
        assert (gacha.own_points, gacha.own_rank) == (9, 4)
        assert gacha.free_chest_reset_time > 0

    def test_pull_needs_consent(self):
        client = events_client([{"EID": 127}])
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.events.pull_gacha(Event.CHRISTMAS_GACHA)
        assert conn(client).request_payloads == []

    def test_free_chest_push_updates_the_event_it_names(self):
        client = events_client([{"EID": 127, "OP": 3}])
        client._on_packet(xt_packet("cfc", {"EID": 127, "OP": 0, "OR": 2, "FCRT": 0}))
        gacha = client.state.get_event(Event.CHRISTMAS_GACHA)
        assert (gacha.own_points, gacha.own_rank) == (3, 2)

    def test_gacha_info_is_parsed_without_fields(self):
        assert get_response_model("gde") is GachaInfoResponse


class TestColossus:
    CHE = {"OP": 250, "LR": 40, "HS": [{"CR": 1, "PN": "Top", "CP": 900, "PID": 3}]}

    def test_resource_donation(self):
        client = events_client(
            [{"EID": 44}], {"cde": xt_packet("cde", {"che": self.CHE})}, castles=[(321, Kingdom.ICE)]
        )
        result = client.events.donate_to_colossus(321, wood=100, stone=50)
        assert conn(client).request_payloads == [("cde", {"SCID": 321, "SKID": 2, "DS": 50, "DW": 100})]
        assert result.highscore is not None and result.highscore.rows[0].player_name == "Top"

    def test_coin_donation_reads_the_coins(self):
        reply = {"che": self.CHE, "gcu": {"C1": 10, "C2": 3}}
        client = events_client([{"EID": 69}], {"ccd": xt_packet("ccd", reply)})
        result = client.events.donate_to_coin_colossus(500)
        assert conn(client).request_payloads == [("ccd", {"DC": 500})]
        assert isinstance(result, ColossusCoinDepositResponse)
        assert result.currency is not None and result.currency.coins == 10
        assert result.highscore is not None and result.highscore.own_donation_points == 250

    def test_empty_donation_is_not_sent(self):
        client = events_client([{"EID": 44}], castles=[(321, Kingdom.ICE)])
        with pytest.raises(ValueError):
            client.events.donate_to_colossus(321)
        assert conn(client).request_payloads == []


class TestDonation:
    def test_progress_is_kept_on_the_event(self):
        reply = {"DIS": [{"DII": 5, "DIP": 120}]}
        client = events_client([{"EID": 123}], {"gdti": xt_packet("gdti", reply)})
        assert client.events.donated_points is None
        points = client.events.get_donation_progress()
        assert conn(client).request_payloads == [("gdti", {})]
        assert [(row.donation_item_id, row.points) for row in points] == [(5, 120)]
        assert client.events.donated_points == points

    def test_donation_sends_the_items_given(self):
        reply = {"DIS": [{"DII": 5, "DIP": 130}]}
        client = events_client([{"EID": 123}], {"ddi": xt_packet("ddi", reply)})
        points = client.events.donate_items({5: 10, 6: 0})
        assert conn(client).request_payloads == [("ddi", {"DIV": [{"DII": 5, "DIA": 10}]})]
        assert points[0].points == 130 and client.events.donated_points == points


def test_marauder_packages_then_points():
    script = {"bkp": xt_packet("bkp", {}), "pep": xt_packet("pep", {"EID": 62, "OR": [3], "OP": [70]})}
    client = events_client([{"EID": 62}], script, castles=[(321, Kingdom.GREEN)])
    points = client.events.give_marauder_packages(321, wood_packages=2, food_packages=1)
    assert conn(client).request_payloads == [
        ("bkp", {"SCID": 321, "SKID": 0, "WP": 2, "SP": 0, "FP": 1}),
        ("pep", {"EID": 62}),
    ]
    assert points is not None and client.state.get_event(Event.BEGGING_KNIGHTS).own_points == 70


class TestArtifact:
    def test_buying_pieces_sends_the_event_kingdom(self):
        reply = {"EID": 23, "PF": 4, "gcu": {"C1": 1, "C2": 2}}
        client = events_client([{"EID": 23, "PF": 1}], {"sap": xt_packet("sap", reply)})
        client.game_data = GameData.parse("test", {"events": [{"eventID": "23", "kIDs": "2,1"}]})
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.events.buy_artifact_pieces(23, 3)
        result = client.events.buy_artifact_pieces(23, 3, spend_rubies=True)
        assert conn(client).request_payloads == [("sap", {"A": 3, "EID": 23, "KID": 2})]
        assert result.parts_found == 4 and result.currency is not None and result.currency.rubies == 2
        assert client.state.get_event(23).parts_found == 4

    def test_found_push_updates_a_running_event_only(self):
        client = events_client([{"EID": 23, "PF": 1}])
        client._on_packet(xt_packet("saf", {"EID": 23, "PF": 2}))
        client._on_packet(xt_packet("saf", {"EID": 19, "PF": 2}))
        assert client.state.get_event(23).parts_found == 2
        assert client.state.get_event(19) is None


class TestBountyHunter:
    def test_validate_sends_nothing_else(self):
        client = events_client([{"EID": 25}], {"brt": xt_packet("brt", {})})
        client.events.validate_bounty_target()
        assert conn(client).request_payloads == [("brt", {})]

    def test_skip_needs_consent_and_reads_the_rubies(self):
        client = events_client([{"EID": 25}], {"bst": xt_packet("bst", {"gcu": {"C1": 5, "C2": 9}, "sei": {"E": []}})})
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.events.skip_bounty_target()
        result = client.events.skip_bounty_target(spend_rubies=True)
        assert conn(client).request_payloads == [("bst", {})]
        assert result.currency is not None and result.currency.rubies == 9


def test_fortune_teller_reading_resolves_its_reward():
    client = events_client([{"EID": 117}], {"ftl": xt_packet("ftl", {"RIDS": [3]})})
    client.game_data = GameData.parse("test", {"rewards": [{"rewardID": "3", "addC1": "100"}]})
    with pytest.raises(ValueError, match="spend_rubies=True"):
        client.events.buy_fortune_teller_reading()
    reading = client.events.buy_fortune_teller_reading(spend_rubies=True)
    assert conn(client).request_payloads == [("ftl", {})]
    assert reading.reward_ids == (3,) and reading.rewards[0].amount == 100


class TestWorldCup:
    def test_the_event_is_read(self):
        client = events_client([{"EID": 63, "TA": 4, "TB": 9, "PC2": 1000, "BC2": 50, "V": -1, "CC2": 1200}])
        cup = client.state.get_event(Event.WORLD_CUP)
        assert (cup.team_a, cup.team_b, cup.vote, cup.rubies_spent, cup.bonus_rubies) == (4, 9, -1, 1200, 500)

    def test_vote_updates_the_event(self):
        client = events_client(
            [{"EID": 63, "V": -1, "PC2": 10, "CC2": 10}], {"vwc": xt_packet("vwc", {"V": 2, "CC2": 10})}
        )
        result = client.events.vote_world_cup(WorldCupVote.TEAM_B)
        assert conn(client).request_payloads == [("vwc", {"V": 2})]
        assert result.vote is WorldCupVote.TEAM_B
        assert client.state.get_event(Event.WORLD_CUP).vote is WorldCupVote.TEAM_B
        with pytest.raises(ValueError):
            client.events.vote_world_cup(WorldCupVote.DRAW)


def test_collector_currency():
    client = make_client({"pcc": xt_packet("pcc", {"PID": 77, "CCA": 1234})}, state=GameState())
    assert client.events.get_collector_currency(77) == 1234
    assert conn(client).request_payloads == [("pcc", {"PID": 77})]
