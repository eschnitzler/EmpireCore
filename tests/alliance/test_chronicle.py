"""The chronicle entries' values typed by action, and their lines as the overview writes them."""

from typing import Any

import pytest
import requests

from empire_core import texts
from empire_core.alliance import (
    AllianceBuffType,
    AllianceChronicleAction,
    AllianceChronicleEntry,
    ChronicleAmount,
    ChronicleBuff,
    ChronicleDaimyoContract,
    ChronicleDiplomacy,
    ChronicleLevel,
    ChronicleMember,
    ChroniclePlace,
    ChronicleText,
    ChronicleTournamentPrize,
    DiplomacyStatus,
)
from empire_core.gamedata import GameData, ids

Action = AllianceChronicleAction

# From the English language file
LANG_FILE = {
    "dialog_alliance_chronic0": "A new member has joined the alliance",
    "dialog_alliance_chronic2": "{1} has been thrown out of the alliance",
    "dialog_alliance_chronic6": "{0} coins have been donated to the alliance funds",
    "dialog_alliance_chronic6_singleDigit": "A coin has been donated to the alliance funds",
    "dialog_alliance_chronic9": "The alliance name has been changed to: {0}",
    "dialog_alliance_chronic12_0": "The alliance's membership limit has been increased",
    "dialog_alliance_chronic12_1": "{0} has been increased",
    "dialog_alliance_chronic12_6": "The alliance smithy has been upgraded to level {0}",
    "dialog_alliance_chronic13": "Diplomacy with {0} changed to: {1}",
    "dialog_alliance_chronic17": "The alliance has reached level {0}",
    "dialog_alliance_chronic23": "{0} has captured a capital",
    "dialog_alliance_chronic26": "Alliance tournament prize: {0} coins and {1} rubies",
    "dialog_alliance_chronic44_7": "Combat strength for attacks has been temporarily increased",
    "dialog_alliance_chronic62_Maya": "Statuette penalty increased by {0}%",
    "dialog_alliance_chronic65": "Completed daimyo castle contract rank {0} level ({1}/{2})",
    "dialog_alliance_chronic66": "Completed township contract rank {0} level ({1}/{2})",
    "dialog_alliance_marketBoost": "Market barrows - travel speed",
    "dialog_allianceDiplomacy_status0": "War",
    "dialog_allianceDiplomacy_status3": "Pact",
    "generic_kforthousand": "k",
}

CONTRACTS = [
    {"id": "1", "rank": "1", "enableOnStart": "1", "nextContract": "2", "shogunPoints": "1000"},
    {"id": "2", "rank": "1", "nextContract": "3", "shogunPoints": "1700", "warEffortPoints": "1"},
    {"id": "3", "rank": "1", "shogunPoints": "2900"},
    {"id": "11", "rank": "2", "enableOnStart": "0"},
    {"id": "12", "rank": "2"},
]


@pytest.fixture(autouse=True)
def stub_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(texts, "fetch_texts", lambda lang="en": LANG_FILE)


@pytest.fixture
def game_data() -> GameData:
    return GameData.parse(
        ids.ITEMS_VERSION,
        {"daimyoCastleAllianceContracts": CONTRACTS, "daimyoTownshipAllianceContracts": CONTRACTS[:2]},
    )


def entry(action: int, *values: Any, player_id: int = 7, player_name: str = "Sir Bob") -> AllianceChronicleEntry:
    return AllianceChronicleEntry.model_validate({"PID": player_id, "PN": player_name, "A": action, "AV": list(values)})


class TestDetails:
    @pytest.mark.parametrize(
        ("action", "values", "details"),
        [
            (Action.CHANGE_DIPLOMACY, [55, "Rivals", 0], ChronicleDiplomacy("Rivals", DiplomacyStatus.IN_WAR)),
            (Action.REFUSE_DIPLOMACY, [55, "Rivals", "3"], ChronicleDiplomacy("Rivals", DiplomacyStatus.REAL_ALLIED)),
            (Action.UPGRADE, [6, 4], ChronicleBuff(AllianceBuffType.FORGE_UPGRADE, 4)),
            (Action.UPGRADE, [0, 2], ChronicleBuff(AllianceBuffType.MEMBERS)),
            (Action.UPGRADE, [2], ChronicleBuff(AllianceBuffType.MARKET_SPEED_BOOST)),
            (Action.ACTIVATE_TEMP_BUFF, [7], ChronicleBuff(AllianceBuffType.TEMP_ATTACK_POWER_BOOST)),
            (Action.EXTEND_TEMP_BUFF, [99], ChronicleBuff(99)),
            (Action.MEMBER_DONATE_COINS, [1500], ChronicleAmount(1500)),
            (Action.TRIBUTE_GET_RUBIES, ["40"], ChronicleAmount(40)),
            (Action.LEVEL_UP, [12], ChronicleLevel(12)),
            (Action.TOURNAMENT_RANK, [3], ChroniclePlace(3)),
            (Action.TOURNAMENT_REWARD, [1000, 20, "Us"], ChronicleTournamentPrize(1000, 20)),
            (Action.CHANGE_NAME, ["New name"], ChronicleText("New name")),
            (Action.ALLIANCE_BATTLE_GROUND_MALUS_INCREASED, [5], ChronicleText("5")),
            (Action.MEMBER_KICKED, [42, "Kicked"], ChronicleMember("Kicked")),
            (Action.DAIMYO_ALLIANCE_TOWNSHIP_CONTRACT_COMPLETED, ["12"], ChronicleDaimyoContract(12)),
        ],
    )
    def test_the_values_are_read_by_action(self, action: int, values: list[Any], details: object) -> None:
        assert entry(action, *values).details == details

    def test_a_missing_value_is_none(self) -> None:
        assert entry(Action.CHANGE_DIPLOMACY).details == ChronicleDiplomacy(None, None)

    @pytest.mark.parametrize("action", [Action.MEMBER_JOIN, Action.CONQUERED_CAPITAL, Action.STORM_ISLAND_ENDED, 99])
    def test_an_entry_whose_values_nothing_reads_has_none(self, action: int) -> None:
        assert entry(action, 1, 2).details is None

    def test_a_deleted_player(self) -> None:
        assert entry(0, player_name="!!!_Gone").is_deleted_player
        assert not entry(0).is_deleted_player
        assert not AllianceChronicleEntry.model_validate({"A": 0}).is_deleted_player

    def test_the_alliance_the_overview_names_for_an_entry_no_player_made(self) -> None:
        diplomacy = entry(Action.GET_REQUEST_DIPLOMACY, 55, "Rivals", 2, player_id=-1)
        prize = entry(Action.TOURNAMENT_REWARD, 1000, 20, "Us", player_id=-1)
        place = entry(Action.TOURNAMENT_RANK, 3, player_id=-1)
        by_player = entry(Action.GET_REQUEST_DIPLOMACY, 55, "Rivals", 2)

        assert (diplomacy.named_alliance_id, diplomacy.named_alliance_name) == (55, "Rivals")
        assert (prize.named_alliance_id, prize.named_alliance_name) == (None, "Us")
        assert (place.named_alliance_id, place.named_alliance_name) == (None, None)
        assert (by_player.named_alliance_id, by_player.named_alliance_name) == (None, None)


class TestDescribe:
    @pytest.mark.parametrize(
        ("action", "values", "line"),
        [
            (Action.MEMBER_JOIN, [], "A new member has joined the alliance"),
            (Action.MEMBER_KICKED, [42, "Kicked"], "Kicked has been thrown out of the alliance"),
            (Action.CHANGE_DIPLOMACY, [55, "Rivals", 3], "Diplomacy with Rivals changed to: Pact"),
            (Action.CHANGE_DIPLOMACY, [55, "12345", 0], "Diplomacy with 12345 changed to: War"),
            (Action.UPGRADE, [0, 30], "The alliance's membership limit has been increased"),
            (Action.UPGRADE, ["6", 4], "The alliance smithy has been upgraded to level 4"),
            (Action.UPGRADE, [2, 3], "Market barrows - travel speed has been increased"),
            (Action.UPGRADE, [12], " has been increased"),
            (Action.ACTIVATE_TEMP_BUFF, [7], "Combat strength for attacks has been temporarily increased"),
            (Action.MEMBER_DONATE_COINS, [1], "A coin has been donated to the alliance funds"),
            (Action.MEMBER_DONATE_COINS, [150000], "150k coins have been donated to the alliance funds"),
            (Action.CHANGE_NAME, ["2000"], "The alliance name has been changed to: 2000"),
            (Action.LEVEL_UP, [12], "The alliance has reached level 12"),
            (Action.CONQUERED_CAPITAL, [], "Sir Bob has captured a capital"),
            (Action.TOURNAMENT_REWARD, [1000, 20, "Us"], "Alliance tournament prize: 1,000 coins and 20 rubies"),
            (99, [], "dialog_alliance_chronic99"),
        ],
    )
    def test_the_line_is_written_as_the_overview_writes_it(self, action: int, values: list[Any], line: str) -> None:
        assert entry(action, *values).describe() == line

    def test_a_skin_text_is_preferred_where_there_is_one(self) -> None:
        malus = entry(Action.ALLIANCE_BATTLE_GROUND_MALUS_INCREASED, 5)

        assert malus.describe(skin="Maya") == "Statuette penalty increased by 5%"
        assert malus.describe() == "dialog_alliance_chronic62"
        assert entry(Action.LEVEL_UP, 3).describe(skin="Maya") == "The alliance has reached level 3"

    def test_a_daimyo_contract_names_its_rank_and_level(self, game_data: GameData) -> None:
        assert (
            entry(Action.DAIMYO_ALLIANCE_CASTLE_CONTRACT_COMPLETED, 2).describe(game_data)
            == "Completed daimyo castle contract rank 1 level (2/3)"
        )
        # the client reads a township contract from the castle contracts too
        assert (
            entry(Action.DAIMYO_ALLIANCE_TOWNSHIP_CONTRACT_COMPLETED, 3).describe(game_data)
            == "Completed township contract rank 1 level (3/3)"
        )

    def test_a_daimyo_contract_needs_the_game_data_that_has_it(self, game_data: GameData) -> None:
        with pytest.raises(ValueError, match="game data"):
            entry(Action.DAIMYO_ALLIANCE_CASTLE_CONTRACT_COMPLETED, 2).describe()
        with pytest.raises(KeyError):
            entry(Action.DAIMYO_ALLIANCE_CASTLE_CONTRACT_COMPLETED, 404).describe(game_data)

    def test_series_position(self, game_data: GameData) -> None:
        contract, level, levels = ChronicleDaimyoContract(11).series_position(game_data)

        assert (contract.contract_id, contract.rank, level, levels) == (11, 2, 1, 2)


class TestDaimyoContracts:
    def test_rows_are_read_as_the_client_reads_them(self, game_data: GameData) -> None:
        first = game_data.daimyo_castle_contracts[1]
        last = game_data.daimyo_castle_contracts[12]

        assert (first.rank, first.enable_on_start, first.next_contract_id, first.shogun_points) == (1, True, 2, 1000)
        assert (first.war_effort_points, last.enable_on_start, last.next_contract_id) == (-1, False, -1)
        assert list(game_data.daimyo_castle_contracts) == [1, 2, 3, 11, 12]
        assert list(game_data.daimyo_township_contracts) == [1, 2]


class TestBuffTypes:
    def test_text_ids(self) -> None:
        assert AllianceBuffType.MARKET_SPEED_BOOST.text_id == "dialog_alliance_marketBoost"
        assert AllianceBuffType.FORGE_UPGRADE.text_id is None
        assert DiplomacyStatus.SOFT_ALLIED.text_id == "dialog_allianceDiplomacy_status2"

    def test_an_alliance_buff_names_its_type(self) -> None:
        data = GameData.parse(
            ids.ITEMS_VERSION,
            {"alliancebuffs": [{"allianceBuffID": "5", "allianceBuffSeriesID": "7", "level": "1"}]},
        )

        assert data.alliance_buffs[5].series_id is AllianceBuffType.TEMP_ATTACK_POWER_BOOST
