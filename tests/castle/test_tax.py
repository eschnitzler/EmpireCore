"""Tax collection: txi, txs and txc."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.castle.models.tax import (
    TAX_DURATIONS,
    TAX_RUBY_COSTS,
    CollectTaxRequest,
    CollectTaxResponse,
    GetTaxInfoRequest,
    StartTaxRequest,
    StartTaxResponse,
    TaxInfo,
    TaxInfoResponse,
)
from empire_core.enums import TaxStatus
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

TX: dict[str, Any] = {"TT": 2, "RT": 1200, "EM": 450, "PO": 75, "IB": 0, "VB": 10}
GCU: dict[str, Any] = {"C1": 12000, "C2": 300}


class TestRequests:
    def test_txi_sends_nothing(self):
        assert GetTaxInfoRequest().to_payload() == {}

    def test_txs_keys_follow_the_vo(self):
        # C2SStartCollectTaxVO: TT, then TX always 3
        payload = StartTaxRequest(TT=4).to_payload()
        assert list(payload.items()) == [("TT", 4), ("TX", 3)]

    def test_txc_sends_tr_29(self):
        assert CollectTaxRequest().to_payload() == {"TR": 29}


class TestTaxInfo:
    def test_fields(self):
        tax = TaxInfoResponse.model_validate({"TX": TX}).tax
        assert (tax.tax_type, tax.remaining_seconds, tax.expected_income, tax.population) == (2, 1200, 450, 75)
        assert (tax.is_boosted, tax.vip_bonus) == (False, 10)
        assert tax.duration_seconds == 5400
        assert tax.status is TaxStatus.COLLECTING

    @pytest.mark.parametrize(
        ("tt", "rt", "status"),
        [(-1, 0, TaxStatus.NONE), (3, 0, TaxStatus.COLLECTING), (3, -5, TaxStatus.WAIT_FOR_COLLECT)],
    )
    def test_status(self, tt: int, rt: int, status: TaxStatus):
        assert TaxInfo.model_validate({"TT": tt, "RT": rt}).status is status

    def test_no_tax_type_has_no_duration(self):
        assert TaxInfo.model_validate({"TT": -1}).duration_seconds is None

    @pytest.mark.parametrize(("ib", "boosted"), [(1, True), ("1", True), (0, False), (True, False), (None, False)])
    def test_boosted_reads_as_parse_int(self, ib: Any, boosted: bool):
        # Boolean(parseInt(IB)): parseInt(true) is NaN
        assert TaxInfo.model_validate({"IB": ib}).is_boosted is boosted

    def test_vip_bonus_truncates(self):
        assert TaxInfo.model_validate({"VB": "12.7"}).vip_bonus == 12

    @pytest.mark.parametrize("tx", [None, 5, [], "x"])
    def test_missing_block_reads_as_defaults(self, tx: Any):
        # parse_TXI makes a new TaxInfoVO even when fillFromParamObject skips the block
        tax = TaxInfoResponse.model_validate({"TX": tx}).tax
        assert (tax.tax_type, tax.remaining_seconds, tax.expected_income) == (0, 0, 0)

    def test_txi_is_registered(self):
        assert isinstance(parse_response("txi", {"TX": TX}), TaxInfoResponse)


class TestReplies:
    def test_txs(self):
        reply = StartTaxResponse.model_validate({"gcu": GCU, "txi": {"TX": TX}})
        assert reply.currencies is not None and reply.currencies.coins == 12000
        assert reply.tax_info is not None and reply.tax_info.tax.tax_type == 2

    def test_txc(self):
        reply = CollectTaxResponse.model_validate({"gcu": GCU, "txi": {"TX": {**TX, "TT": -1}}, "CT": "640"})
        assert reply.collected == 640
        assert reply.tax_info is not None and reply.tax_info.tax.status is TaxStatus.NONE

    @pytest.mark.parametrize("txi", [None, 0, ""])
    def test_falsy_txi_is_none(self, txi: Any):
        # parse_TXI skips a falsy block
        assert CollectTaxResponse.model_validate({"txi": txi}).tax_info is None


class TestCosts:
    def test_only_the_long_types_cost_rubies(self):
        assert len(TAX_DURATIONS) == len(TAX_RUBY_COSTS) == 7
        assert [t for t, cost in enumerate(TAX_RUBY_COSTS) if cost] == [5, 6]


class TestService:
    def test_get_tax_info(self):
        client = make_client({"txi": xt_packet("txi", {"TX": TX})})
        tax = client.castle.get_tax_info()
        assert tax.expected_income == 450
        assert conn(client).request_payloads == [("txi", {})]

    def test_start_tax(self):
        client = make_client({"txs": xt_packet("txs", {"gcu": GCU, "txi": {"TX": TX}})})
        reply = client.castle.start_tax(2)
        assert reply.tax_info is not None and reply.tax_info.tax.tax_type == 2
        assert conn(client).request_payloads == [("txs", {"TT": 2, "TX": 3})]

    @pytest.mark.parametrize("tax_type", [5, 6])
    def test_ruby_types_need_the_flag(self, tax_type: int):
        client = make_client({})
        with pytest.raises(ValueError, match="rubies"):
            client.castle.start_tax(tax_type)
        assert conn(client).request_payloads == []

    def test_ruby_type_with_the_flag(self):
        client = make_client({"txs": xt_packet("txs", {"gcu": GCU, "txi": {"TX": {**TX, "TT": 6}}})})
        client.castle.start_tax(6, spend_rubies=True)
        assert conn(client).request_payloads == [("txs", {"TT": 6, "TX": 3})]

    @pytest.mark.parametrize("tax_type", [-1, 7])
    def test_unknown_type(self, tax_type: int):
        with pytest.raises(ValueError, match="0 to 6"):
            make_client({}).castle.start_tax(tax_type, spend_rubies=True)

    def test_collect_tax(self):
        client = make_client({"txc": xt_packet("txc", {"gcu": GCU, "txi": {"TX": TX}, "CT": 640})})
        assert client.castle.collect_tax().collected == 640
        assert conn(client).request_payloads == [("txc", {"TR": 29})]


class TestTaxRepliesInState:
    @pytest.mark.parametrize("command", ["txs", "txc"])
    def test_the_reply_coins_reach_state(self, command: str):
        # TXSCommand and TXCCommand parse the reply's gcu before its txi
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet(command, {"gcu": {"C1": 40, "C2": 2}, "txi": {"TX": TX}})
        player = state.get_local_player()
        assert player is not None and (player.coins, player.rubies) == (40, 2)
        state.update_from_packet(command, {"gcu": {"C1": 1, "C2": 1}}, 3)
        player = state.get_local_player()
        assert player is not None and player.coins == 40
        state.shutdown()
