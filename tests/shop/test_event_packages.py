"""Buying an event package (sbp) and reading how often you bought each (gbc)."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from empire_core.enums import GGEError, Kingdom, PackageBuyType
from empire_core.exceptions import CommandError, EventNotRunningError, NotEnoughSpecialCurrencyError, PacketError
from empire_core.gamedata import GameData, PackageId
from empire_core.gamedata.ids.events import Event
from empire_core.shop import BuyEventPackageRequest, BuyEventPackageResponse
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

ITEMS = {
    "currencies": [{"currencyID": "28", "Name": "LegendaryToken", "JSONKey": "LT"}],
    "packages": [
        {"packageID": "60", "packageType": "resources", "packagePriceC1": "500", "amountWood": "1000"},
        {"packageID": "61", "packageType": "item", "packagePriceC2": "150", "equipmentAmount": "1"},
        {"packageID": "62", "packageType": "deco", "costLegendaryToken": "50", "buildingID": "381", "stock": "2"},
        {"packageID": "63", "packageType": "resources", "fillUpResourceStorage": "1", "amountWood": "10000000"},
        {"packageID": "64", "packageType": "unit", "costLegendaryToken": "10", "unitID": "1", "unitAmount": "5"},
    ],
    "events": [{"eventID": "42", "eventType": "Merchant", "packageIDs": "60+61+62+63"}],
}

CASTLE = 1001
FOREIGN_KINGDOM_CASTLE = 2002


def _castle(castle_id: int, kingdom: Kingdom) -> dict:
    return {"KID": int(kingdom), "AI": [{"AI": [1, 10, 20, castle_id, 1, 1, 1, 1, 0, 0, f"Castle {castle_id}"]}]}


def _client(replies: dict | None = None, *, entry: dict | None = None):
    state = GameState()
    gcl = {"C": [_castle(CASTLE, Kingdom.GREEN), _castle(FOREIGN_KINGDOM_CASTLE, Kingdom.FIRE)]}
    state.update_from_packet("gbd", {"gpi": {"PID": 1}, "gcl": gcl})
    state.update_from_packet("sei", {"E": [entry or {"EID": 42, "RS": 600, "PIDS": "64"}]})
    client = make_client(replies, state=state)
    client.game_data = GameData.parse("790.02", ITEMS)
    return client


def _bought(package_id: int, amount: int = 1, error_code: int = 0, payload: dict | None = None):
    body = payload if payload is not None else {"PID": package_id, "AMT": amount, "gcu": {"C1": 100, "C2": 7}}
    return {"sbp": xt_packet("sbp", body, error_code=error_code)}


def test_the_request_keys_follow_the_client_order():
    payload = BuyEventPackageRequest(
        package_id=PackageId(60), buy_type=PackageBuyType.EVENT, buy_type_id=42, amount=3, kingdom=Kingdom.GREEN
    ).to_payload()

    assert list(payload) == ["PID", "BT", "TID", "AMT", "KID", "AID", "PC2", "BA", "PWR", "_PO"]
    assert payload == {
        "PID": 60,
        "BT": 0,
        "TID": 42,
        "AMT": 3,
        "KID": 0,
        "AID": -1,
        "PC2": -1,
        "BA": 0,
        "PWR": 0,
        "_PO": -1,
    }


@pytest.mark.parametrize("buy_type", [PackageBuyType.PRIVATE_OFFER, PackageBuyType.GIFT])
def test_private_offers_and_gifts_are_refused(buy_type):
    with pytest.raises(ValidationError, match="not supported"):
        BuyEventPackageRequest(package_id=PackageId(60), buy_type=buy_type, amount=1, kingdom=Kingdom.GREEN)


def test_a_custom_price_is_refused():
    with pytest.raises(ValidationError, match="priced by your storages"):
        BuyEventPackageRequest(
            package_id=PackageId(63),
            buy_type=PackageBuyType.EVENT,
            amount=1,
            kingdom=Kingdom.GREEN,
            custom_price_rubies=5,
        )


def test_buying_sends_the_event_its_kingdom_and_no_castle_for_a_non_building():
    client = _client(_bought(60))

    reply = client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(60), FOREIGN_KINGDOM_CASTLE, 2)

    assert isinstance(reply, BuyEventPackageResponse) and reply.package_id == 60
    assert conn(client).request_payloads == [
        ("sbp", {"PID": 60, "BT": 0, "TID": 42, "AMT": 2, "KID": 3, "AID": -1, "PC2": -1, "BA": 0, "PWR": 0, "_PO": -1})
    ]


def test_a_building_goes_to_the_castle():
    client = _client(_bought(62))

    client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, client.game_data.packages[PackageId(62)], CASTLE)  # type: ignore[union-attr]

    assert conn(client).request_payloads[0][1]["AID"] == CASTLE


def test_a_package_the_server_added_can_be_bought():
    client = _client(_bought(64))

    client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(64), CASTLE)

    assert conn(client).request_payloads[0][1]["PID"] == 64


def test_a_ruby_price_needs_consent_and_then_pays_missing_costs_in_rubies():
    client = _client(_bought(61))

    with pytest.raises(ValueError, match="costs 150 rubies"):
        client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(61), CASTLE)
    assert conn(client).request_payloads == []

    client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(61), CASTLE, spend_rubies=True)
    assert conn(client).request_payloads[0][1]["PWR"] == 1


@pytest.mark.parametrize(
    ("package_id", "amount", "message"),
    [
        (63, 1, "priced by your storages"),
        (99, 1, "does not sell package 99"),
        (62, 3, "3 asked, 2 left"),
        (60, 0, "0 asked"),
        (62, 2, "bought one at a time"),
        (61, 2, "bought one at a time"),
    ],
)
def test_refusals_send_nothing(package_id, amount, message):
    client = _client(_bought(package_id))

    with pytest.raises(ValueError, match=message):
        client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(package_id), CASTLE, amount)
    assert conn(client).request_payloads == []


def test_an_event_that_does_not_run_or_sells_nothing_is_refused():
    client = _client(entry={"EID": 95, "RS": 600, "RIDS": [3], "CQS": []})

    with pytest.raises(EventNotRunningError):
        client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(60), CASTLE)
    with pytest.raises(ValueError, match="sells no packages"):
        client.shop.buy_event_package(Event(95), PackageId(60), CASTLE)
    assert conn(client).request_payloads == []


def test_the_stock_left_counts_the_packages_bought():
    client = _client(_bought(62))
    client.state.update_from_packet("gbc", {"PL": [{"PID": 62, "AMT": 2}]})

    with pytest.raises(ValueError, match="1 asked, 0 left"):
        client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(62), CASTLE)


def test_lacking_an_event_currency_names_the_package():
    client = _client(_bought(62, error_code=GGEError.NOT_ENOUGH_SPECIAL_CURRENCY, payload={"PID": 62}))

    with pytest.raises(NotEnoughSpecialCurrencyError) as raised:
        client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(62), CASTLE)
    assert raised.value.package_id == 62 and isinstance(raised.value, CommandError)


def test_another_refusal_raises_a_command_error():
    client = _client(_bought(60, error_code=GGEError.STORAGE_CAPACITY_REACHED, payload={}))

    with pytest.raises(CommandError) as raised:
        client.shop.buy_event_package(Event.TRAVELING_MERCHANT_EVENT, PackageId(60), CASTLE)
    assert raised.value.error is GGEError.STORAGE_CAPACITY_REACHED


def test_get_package_buy_counts_sends_the_castle_and_its_kingdom():
    client = _client({"gbc": xt_packet("gbc", {"PL": [{"PID": 62, "AMT": 1}]})})

    assert client.shop.get_package_buy_counts(FOREIGN_KINGDOM_CASTLE) == {62: 1}
    assert conn(client).request_payloads == [("gbc", {"CID": FOREIGN_KINGDOM_CASTLE, "KID": 3})]


def test_the_state_keeps_the_counts_of_gbc_and_sbp():
    state = GameState()
    state.update_from_packet("gbc", {"PL": [{"PID": 62, "AMT": 1}, {"PID": 70, "AMT": 4}]})
    state.update_from_packet("sbp", {"PID": 62, "AMT": 2, "gcu": {"C1": 1, "C2": 2}})
    assert state.get_package_buy_counts() == {62: 2, 70: 4}

    state.update_from_packet("sbp", {"PID": 70, "AMT": 9}, error_code=GGEError.NOT_ENOUGH_SPECIAL_CURRENCY)
    state.update_from_packet("gbc", {})
    assert state.get_package_buy_counts() == {62: 2, 70: 4}

    state.update_from_packet("gbc", {"PL": []})
    assert state.get_package_buy_counts() == {}


def test_bought_count_is_kept_only_for_a_package_with_a_stock():
    client = _client()
    client.state.update_from_packet("gbc", {"PL": [{"PID": 60, "AMT": 3}, {"PID": 62, "AMT": 1}]})
    packages = client.game_data.packages  # type: ignore[union-attr]

    assert client.shop.bought_count(packages[PackageId(60)]) == 0
    assert client.shop.bought_count(packages[PackageId(62)]) == 1


def test_a_buy_count_list_of_the_wrong_shape_raises_and_the_state_warns(caplog):
    client = _client({"gbc": xt_packet("gbc", {"PL": "62:1"})})

    with pytest.raises(PacketError):
        client.shop.get_package_buy_counts(CASTLE)

    state = GameState()
    with caplog.at_level(logging.WARNING):
        state.update_from_packet("gbc", {"PL": "62:1"})
    assert state.get_package_buy_counts() is None
    assert "package buy counts" in caplog.text


def test_the_reply_reads_its_sections():
    reply = BuyEventPackageResponse.model_validate(
        {
            "PID": 62,
            "AMT": 1,
            "gcu": {"C1": 10, "C2": 20},
            "cpi": {"APM": 1, "TPM": 2},
            "vip": {"VP": 5, "VRL": 1, "VRS": 60, "UPG": 0},
            "sin": [],
            "gui": {"I": []},
        }
    )

    assert (reply.package_id, reply.bought_count) == (62, 1)
    assert reply.plague_doctors is not None and reply.plague_doctors.total_plague_doctors == 2
    assert reply.vip is not None and reply.vip.vip_points == 5
    assert reply.currencies is not None and reply.resources is None
