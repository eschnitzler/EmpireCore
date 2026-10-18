"""Upgrade wire/cost/state contracts from C2SAllianceUpgradeVO and AUGCommand."""

import pytest

from empire_core.enums import AllianceBuffType, CollectableKind
from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError, ReplyMismatchError
from empire_core.gamedata import GameData
from tests.alliance.test_pushes import alliance_state
from tests.service_helpers import conn, make_client, xt_packet


def upgrade_client(*, series=6, current=0, duration=-1, ruby_cost=0, reply=None, level=1):
    state = alliance_state()
    details = {"AID": 301, "ABL": [{"BT": series, "L": current, "CD": -1}], "STO": {"C2": 999}}
    state.update_from_packet("ain", {"A": details})
    data = GameData.parse(
        "synthetic",
        {
            "alliancebuffs": [
                {
                    "allianceBuffID": 100 + n,
                    "allianceBuffSeriesID": series,
                    "level": n,
                    "maxLevel": 3,
                    "duration": duration,
                    "costC2": ruby_cost if n == level else 0,
                }
                for n in range(4)
            ]
        },
    )
    payload = reply if reply is not None else {"STO": {"C2": 900}, "ABL": [{"BT": series, "L": level, "CD": -1}]}
    client = make_client(
        {
            "ain": xt_packet("ain", {"A": details}),
            "aug": payload if isinstance(payload, Exception) else xt_packet("aug", payload),
        },
        state=state,
    )
    client.game_data = data
    return client


def test_upgrade_returns_treasury_and_buffs_and_sends_default_level():
    client = upgrade_client()
    result = client.alliance.upgrade(AllianceBuffType.FORGE_UPGRADE)
    assert result.storage.rubies == 900
    assert result.buildings[0].building_type == AllianceBuffType.FORGE_UPGRADE
    assert result.buildings[0].level == 1
    assert conn(client).request_payloads == [("ain", {"AID": 301}), ("aug", {"BT": 6, "L": 1})]
    assert client.alliance.own_alliance is not None and client.alliance.own_alliance.storage == result.storage


def test_permanent_cost_uses_next_level_instead_of_wire_level():
    client = upgrade_client(current=1, ruby_cost=50, level=2)
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.upgrade(6)
    assert conn(client).requested == ["ain"]
    assert client.alliance.upgrade(6, spend_rubies=True).storage.rubies == 900


def test_custom_temporary_cost_uses_selected_level():
    client = upgrade_client(series=12, duration=60, ruby_cost=50, level=2)
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.upgrade(12, level=2)
    client.alliance.upgrade(12, level=2, spend_rubies=True)
    assert conn(client).request_payloads[-1] == ("aug", {"BT": 12, "L": 2})


@pytest.mark.parametrize("series,level", [(999999, 1), (6, 0), (6, 2), (11, 1)])
def test_unsupported_upgrade_sends_nothing(series, level):
    client = upgrade_client()
    with pytest.raises(ValueError):
        client.alliance.upgrade(series, level=level)
    assert conn(client).requested == []


@pytest.mark.parametrize(
    "reply", [{}, {"STO": {}}, {"STO": {}, "ABL": [{}]}, {"STO": [], "ABL": []}, {"STO": {}, "ABL": "bad"}]
)
def test_malformed_upgrade_reply_does_not_apply(reply):
    client = upgrade_client(reply=reply)
    with pytest.raises(PacketError):
        client.alliance.upgrade(6)
    assert client.alliance.own_alliance is not None
    assert client.alliance.own_alliance.buildings[0].level == 0


@pytest.mark.parametrize("failure", [CommandError("aug", 1, {}), EmpireTimeoutError("timeout")])
def test_upgrade_refusal_and_transport_errors_preserve_their_type(failure):
    client = upgrade_client(reply=failure)
    with pytest.raises(type(failure)):
        client.alliance.upgrade(6)


def test_upgrade_cannot_apply_after_membership_aba():
    client = upgrade_client()
    state = client.state

    def incoming(packet):
        if packet.command_id == "aug":
            state.update_from_packet("gal", {"AID": -1})
            state.update_from_packet("gal", {"AID": 301})
            state.update_from_packet("ain", {"A": {"AID": 301, "N": "New membership"}})
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)

    conn(client).on_packet = incoming
    with pytest.raises(ReplyMismatchError):
        client.alliance.upgrade(6)
    assert client.alliance.own_alliance is not None and client.alliance.own_alliance.name == "New membership"


def test_later_buff_push_and_member_timers_survive_upgrade_reply():
    client = upgrade_client()
    state = client.state
    state.update_from_packet(
        "ain", {"A": {"AID": 301, "M": [{"OID": 8, "RNP": 60}], "AMI": [[8, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0]]}}
    )

    def incoming(packet):
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if packet.command_id == "aug":
            state.update_from_packet("abl", {"ABL": [{"BT": 999999, "L": 9, "CD": 60}]})

    conn(client).on_packet = incoming
    client.alliance.upgrade(6)
    assert client.alliance.own_alliance is not None
    assert client.alliance.own_alliance.buildings[0].building_type == 999999


def test_reply_buff_series_are_typed_and_unknown_ids_survive():
    client = upgrade_client(reply={"STO": {}, "ABL": [{"BT": 6, "L": 1, "CD": -1}, {"BT": 999999, "L": 3, "CD": 5}]})
    result = client.alliance.upgrade(6)
    assert isinstance(result.buildings[0].building_type, AllianceBuffType)
    assert result.buildings[1].building_type == 999999


def test_unknown_or_malformed_cost_cannot_authorize_ruby_spending():
    client = upgrade_client()
    client.game_data = GameData.parse(
        "synthetic",
        {
            "alliancebuffs": [
                {"allianceBuffID": 100, "allianceBuffSeriesID": 6, "level": 0, "maxLevel": 1},
                {"allianceBuffID": 101, "allianceBuffSeriesID": 6, "level": 1, "maxLevel": 1, "costC2": "unknown"},
            ]
        },
    )
    with pytest.raises(ValueError):
        client.alliance.upgrade(6, spend_rubies=True)
    assert "aug" not in conn(client).requested


def test_permanent_upgrade_maximum_is_rejected():
    client = upgrade_client(current=3)
    with pytest.raises(ValueError, match="maximum"):
        client.alliance.upgrade(6)
    assert conn(client).requested == ["ain"]


def test_active_customizable_boost_cannot_change_level():
    client = upgrade_client(series=12, current=2, duration=60)
    conn(client).script["ain"] = xt_packet("ain", {"A": {"AID": 301, "ABL": [{"BT": 12, "L": 2, "CD": 60}]}})
    with pytest.raises(ValueError, match="prolonged"):
        client.alliance.upgrade(12, level=1)
    assert "aug" not in conn(client).requested


def test_preflight_other_alliance_cannot_authorize_upgrade():
    client = upgrade_client()
    conn(client).script["ain"] = xt_packet("ain", {"A": {"AID": 401, "ABL": [{"BT": 6, "L": 0, "CD": -1}]}})
    with pytest.raises((PacketError, EmpireTimeoutError)):
        client.alliance.upgrade(6)
    assert "aug" not in conn(client).requested


def test_temporary_prerequisite_must_be_known_and_held():
    client = upgrade_client(series=7, duration=60)
    assert client.game_data is not None
    client.game_data.alliance_buffs[101].required_buff_id = 999
    with pytest.raises(ValueError, match="prerequisite"):
        client.alliance.upgrade(7)
    assert "aug" not in conn(client).requested


def test_standard_temporary_boost_can_prolong_at_maximum():
    client = upgrade_client(series=7, current=3, duration=60, ruby_cost=25, level=3)
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.upgrade(7)
    client.alliance.upgrade(7, spend_rubies=True)
    assert conn(client).request_payloads[-1] == ("aug", {"BT": 7, "L": 1})


def test_valid_empty_upgrade_buff_list_clears_cached_buffs():
    client = upgrade_client(reply={"STO": {"C2": 0}, "ABL": []})
    assert client.alliance.upgrade(6).buildings == []
    assert client.alliance.own_alliance is not None and client.alliance.own_alliance.buildings == []


def test_upgrade_reply_preserves_later_alliance_details_and_fame_push():
    client = upgrade_client()
    state = client.state

    def incoming(packet):
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if packet.command_id == "aug":
            state.update_from_packet(
                "ain", {"A": {"AID": 301, "N": "Later", "STO": {"C2": 7}, "ABL": [{"BT": 6, "L": 3, "CD": -1}]}}
            )
            state.update_from_packet("afa", {"CF": 42, "HF": 50})

    conn(client).on_packet = incoming
    client.alliance.upgrade(6)
    alliance = client.alliance.own_alliance
    assert alliance is not None and alliance.name == "Later" and alliance.fame_points == 42
    assert alliance.storage is not None and alliance.storage.rubies == 7
    assert alliance.buildings[0].level == 3


def test_upgrade_partial_update_keeps_member_timer_and_linked_info():
    client = upgrade_client()
    conn(client).script["ain"] = xt_packet(
        "ain",
        {
            "A": {
                "AID": 301,
                "ABL": [{"BT": 6, "L": 0, "CD": -1}],
                "M": [{"OID": 8, "RNP": 60}],
                "AMI": [[8, 1, 2, 3, 0, 0, 0, 0, 0, 0, 0]],
            }
        },
    )
    members = []

    def incoming(packet):
        client.state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if packet.command_id == "ain":
            alliance = client.alliance.own_alliance
            assert alliance is not None
            members.append(alliance.members[0])

    conn(client).on_packet = incoming
    client.alliance.upgrade(6)
    alliance = client.alliance.own_alliance
    assert alliance is not None
    assert alliance.members[0].received_at == members[0].received_at
    assert alliance.members[0].member_info == members[0].member_info


def test_unknown_cost_kind_is_rejected_even_with_consent():
    client = upgrade_client()
    client.game_data = GameData.parse(
        "synthetic",
        {
            "alliancebuffs": [
                {"allianceBuffID": 100, "allianceBuffSeriesID": 6, "level": 0, "maxLevel": 1},
                {"allianceBuffID": 101, "allianceBuffSeriesID": 6, "level": 1, "maxLevel": 1, "costFutureCurrency": 25},
            ]
        },
    )
    with pytest.raises(ValueError, match="unknown.*cost"):
        client.alliance.upgrade(6, spend_rubies=True)
    assert "aug" not in conn(client).requested


def test_named_currency_treasury_cost_is_resolved_from_game_data():
    client = upgrade_client()
    client.game_data = GameData.parse(
        "synthetic",
        {
            "currencies": [{"currencyID": "100100", "Name": "FutureCoin", "JSONKey": "FC"}],
            "alliancebuffs": [
                {"allianceBuffID": 100, "allianceBuffSeriesID": 6, "level": 0, "maxLevel": 1},
                {"allianceBuffID": 101, "allianceBuffSeriesID": 6, "level": 1, "maxLevel": 1, "costFutureCoin": 25},
            ],
        },
    )
    client.alliance.upgrade(6)
    assert conn(client).request_payloads[-1] == ("aug", {"BT": 6, "L": 1})


@pytest.mark.parametrize("command", ["abl", "ain"])
@pytest.mark.parametrize("consent", [False, True])
def test_newer_buff_state_invalidates_free_to_paid_preflight(command, consent):
    client = upgrade_client(ruby_cost=50, level=2)

    def incoming(packet):
        client.state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if packet.command_id == "ain":
            buffs = {"ABL": [{"BT": 6, "L": 1, "CD": -1}]}
            payload = {"A": {"AID": 301, **buffs}} if command == "ain" else buffs
            client.state.update_from_packet(command, payload)

    conn(client).on_packet = incoming
    with pytest.raises(ValueError, match="changed"):
        client.alliance.upgrade(6, spend_rubies=consent)
    assert "aug" not in conn(client).requested


@pytest.mark.parametrize("command", ["abl", "ain"])
def test_newer_active_customizable_level_invalidates_preflight(command):
    client = upgrade_client(series=12, duration=60)

    def incoming(packet):
        client.state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if packet.command_id == "ain":
            buffs = {"ABL": [{"BT": 12, "L": 2, "CD": 60}]}
            client.state.update_from_packet(command, {"A": {"AID": 301, **buffs}} if command == "ain" else buffs)

    conn(client).on_packet = incoming
    with pytest.raises(ValueError, match="changed"):
        client.alliance.upgrade(12, level=1, spend_rubies=True)
    assert "aug" not in conn(client).requested


@pytest.mark.parametrize(
    "costs",
    [
        {"costC2": 50, "costs": []},
        {"costc2": "unknown"},
        {"costWood": "unknown"},
        {"costFutureCoin": "unknown"},
    ],
)
@pytest.mark.parametrize("consent", [False, True])
def test_raw_cost_columns_cannot_be_bypassed_or_malformed(costs, consent):
    client = upgrade_client()
    client.game_data = GameData.parse(
        "synthetic",
        {
            "currencies": [{"currencyID": "100100", "Name": "FutureCoin", "JSONKey": "FC"}],
            "alliancebuffs": [
                {"allianceBuffID": 100, "allianceBuffSeriesID": 6, "level": 0, "maxLevel": 1},
                {"allianceBuffID": 101, "allianceBuffSeriesID": 6, "level": 1, "maxLevel": 1, **costs},
            ],
        },
    )
    with pytest.raises(ValueError):
        client.alliance.upgrade(6, spend_rubies=consent)
    assert "aug" not in conn(client).requested


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -1, "unknown"])
def test_invalid_normalized_costs_never_authorize_send(amount):
    client = upgrade_client()
    client.game_data = GameData.parse(
        "synthetic",
        {
            "alliancebuffs": [
                {"allianceBuffID": 100, "allianceBuffSeriesID": 6, "level": 0, "maxLevel": 1},
                {
                    "allianceBuffID": 101,
                    "allianceBuffSeriesID": 6,
                    "level": 1,
                    "maxLevel": 1,
                    "costs": [{"kind": CollectableKind.RUBIES, "key": "C2", "amount": amount}],
                },
            ]
        },
    )
    with pytest.raises(ValueError):
        client.alliance.upgrade(6, spend_rubies=True)
    assert "aug" not in conn(client).requested


def test_plain_normalized_costs_remain_supported_and_require_consent():
    client = upgrade_client()
    client.game_data = GameData.parse(
        "synthetic",
        {
            "alliancebuffs": [
                {"allianceBuffID": 100, "allianceBuffSeriesID": 6, "level": 0, "maxLevel": 1},
                {
                    "allianceBuffID": 101,
                    "allianceBuffSeriesID": 6,
                    "level": 1,
                    "maxLevel": 1,
                    "costs": [{"kind": CollectableKind.RUBIES, "key": "c2", "amount": 50}],
                },
            ]
        },
    )
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.upgrade(6)
    client.alliance.upgrade(6, spend_rubies=True)
    assert conn(client).request_payloads[-1] == ("aug", {"BT": 6, "L": 1})


def test_push_received_during_cost_authorization_is_checked_before_send(monkeypatch):
    client = upgrade_client(ruby_cost=50, level=2)
    authorize = client.alliance._require_spend_rubies

    def received_push(spend_rubies, cost):
        authorize(spend_rubies, cost)
        client.state.update_from_packet("abl", {"ABL": [{"BT": 6, "L": 1, "CD": -1}]})

    monkeypatch.setattr(client.alliance, "_require_spend_rubies", received_push)
    with pytest.raises(ValueError, match="changed"):
        client.alliance.upgrade(6, spend_rubies=True)
    assert "aug" not in conn(client).requested
