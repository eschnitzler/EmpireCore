"""Fields that name a game-data row read as its enum member, keep an unknown id, and keep their sentinels."""

import logging
from typing import Any

import pytest
from pydantic import BaseModel

from empire_core.alliance.models.help import AllianceHelpReceived
from empire_core.army.models.hospital import HealUnitsRequest
from empire_core.army.models.production import AddedUnit, HospitalSlot, ProduceUnitsRequest, ProductionSlot
from empire_core.army.models.units import DismissUnitsRequest, StoreSoldiersRequest
from empire_core.castle.models.buildings import BuildRequest
from empire_core.castle.models.objects import BuildingRow
from empire_core.castle.models.research import ResearchInfoResponse
from empire_core.commanders.models.roster import Commander, CommanderEffect
from empire_core.commanders.models.skills import AddGeneralXpRequest, AssignGeneralRequest, OwnedGeneral
from empire_core.enums import Kingdom, ProductionListId
from empire_core.gamedata import (
    Achievement,
    Building,
    CurrencyId,
    Effect,
    Event,
    General,
    Research,
    Title,
    Tool,
    Unit,
)
from empire_core.map.models.areas import MapObject
from empire_core.messages.models.battle_logs import BattleLogUnit
from empire_core.player.models.info import PlayerOwnerInfo
from empire_core.player.models.progress import AchievementProgress
from empire_core.ranking.models import GetRankingListRequest
from empire_core.rewards.models import CollectLoginBonusRequest

RESEARCH = next(iter(Research))
EFFECT = next(iter(Effect))
TOOL = next(iter(Tool))


def _field(model: type[BaseModel], data: Any, field: str) -> Any:
    return getattr(model.model_validate(data), field)


KNOWN = [
    (DismissUnitsRequest, {"WID": 211, "A": 1}, "wod_id", Unit.MEAD_RANGER_L6),
    (DismissUnitsRequest, {"WID": int(TOOL), "A": 1}, "wod_id", TOOL),
    (StoreSoldiersRequest, {"WID": 211, "A": 1}, "wod_id", Unit.MEAD_RANGER_L6),
    (HealUnitsRequest, {"U": 211, "A": 1}, "wod_id", Unit.MEAD_RANGER_L6),
    (ProductionSlot, {"ICT": 60, "WID": 211, "TUA": 5}, "wod_id", Unit.MEAD_RANGER_L6),
    (HospitalSlot, {"wod_id": 211}, "wod_id", Unit.MEAD_RANGER_L6),
    (AddedUnit, {"W": int(TOOL), "AMT": 3}, "wod_id", TOOL),
    (BattleLogUnit, ["211", 5, 0], "wod_id", Unit.MEAD_RANGER_L6),
    (CollectLoginBonusRequest, {"ID": 211}, "unit_id", Unit.MEAD_RANGER_L6),
    (BuildRequest, {"WID": 6, "X": 1, "Y": 2}, "wod_id", Building.DECO_VICTORYCOLUMN_ELECTRUM_L1),
    (AllianceHelpReceived, {"WID": "6"}, "building_wod_id", Building.DECO_VICTORYCOLUMN_ELECTRUM_L1),
    (ResearchInfoResponse, {"ARID": int(RESEARCH)}, "current_research_id", RESEARCH),
    (OwnedGeneral, {"GID": 101}, "general_id", General.TORIL),
    (AssignGeneralRequest, {"LID": 7, "GID": 101}, "general_id", General.TORIL),
    (AddGeneralXpRequest, {"GID": 101, "CID": 7001, "AMT": 1}, "currency_id", CurrencyId.GENERALS_XP_250),
    (Commander, {"ID": 7, "GID": 101}, "general_id", General.TORIL),
    (CommanderEffect, [int(EFFECT), [10]], "effect_id", EFFECT),
    (
        GetRankingListRequest,
        {"LT": 84, "LID": 4, "M": 10, "EID": int(Event.GRAND_TOURNAMENT)},
        "event_id",
        Event.GRAND_TOURNAMENT,
    ),
    (MapObject, {"OID": 5, "PRE": 3}, "prefix_title", Title.BARON),
    (PlayerOwnerInfo, {"OID": 5, "SUF": "4"}, "title_suffix", Title.VISCOUNT),
    (AchievementProgress, {"AID": 1}, "achievement_id", Achievement.ACHIEVEMENT_POINTS_L1),
]


@pytest.mark.parametrize(("model", "data", "field", "member"), KNOWN, ids=lambda v: getattr(v, "__name__", None))
def test_a_known_id_reads_as_its_member(model, data, field, member):
    assert _field(model, data, field) is member


SENTINELS = [
    (ProductionSlot, {}, "wod_id", 0),
    (HospitalSlot, {"wod_id": -1}, "wod_id", -1),
    (HospitalSlot, {"wod_id": -2}, "wod_id", -2),
    (AddedUnit, {"AMT": 3}, "wod_id", 0),
    (CollectLoginBonusRequest, {}, "unit_id", -1),
    (BuildingRow, None, "upgrade_target_wod_id", -1),
    (AllianceHelpReceived, {}, "building_wod_id", 0),
    (ResearchInfoResponse, {"ARID": -1}, "current_research_id", -1),
    (OwnedGeneral, {}, "general_id", -1),
    (AssignGeneralRequest, {"LID": 7}, "general_id", -1),
    (Commander, {"ID": 7, "GID": -1}, "general_id", -1),
    (MapObject, {"OID": 5, "PRE": -1}, "prefix_title", None),
    (PlayerOwnerInfo, {"OID": 5, "SUF": -1}, "title_suffix", None),
    (AchievementProgress, {}, "achievement_id", 0),
]


@pytest.mark.parametrize(("model", "data", "field", "value"), SENTINELS, ids=lambda v: getattr(v, "__name__", None))
def test_a_sentinel_stays_as_sent_without_a_warning(model, data, field, value, caplog, monkeypatch):
    monkeypatch.setattr("empire_core.gamedata.lenient._warned", set())
    with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.lenient"):
        read = BuildingRow.from_list([6]) if model is BuildingRow else model.model_validate(data)
    assert getattr(read, field) == value and type(getattr(read, field)) is type(value)
    assert not caplog.records


def test_an_unknown_id_stays_an_int_and_is_logged(caplog, monkeypatch):
    monkeypatch.setattr("empire_core.gamedata.lenient._warned", set())
    with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.lenient"):
        request = ProduceUnitsRequest(
            list_id=ProductionListId.SOLDIERS, wod_id=987654, amount=1, kingdom_id=Kingdom.GREEN, castle_id=1
        )
        row = BuildingRow.from_list([987653])
    assert request.wod_id == 987654 and type(request.wod_id) is int
    assert row.wod_id == 987653 and type(row.wod_id) is int
    assert "Unit/Tool has no member 987654" in caplog.text
    assert "Building has no member 987653" in caplog.text


def test_a_building_row_reads_its_type_and_upgrade_target():
    row = BuildingRow.from_list([6, 1, 0, 0, 0, 0, 0, 100, 0, 100, 0, 0, 0, 0, 0, 0, 6])
    assert row.wod_id is Building.DECO_VICTORYCOLUMN_ELECTRUM_L1
    assert row.upgrade_target_wod_id is Building.DECO_VICTORYCOLUMN_ELECTRUM_L1
