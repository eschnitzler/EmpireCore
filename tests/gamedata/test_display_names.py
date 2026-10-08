"""Display names: the text id each enum names its members by, read through the language file (stubbed)."""

from typing import Any

import pytest
import requests

from empire_core import texts
from empire_core.enums import AllianceRank, Kingdom
from empire_core.gamedata import CurrencyDef, GameData, ToolStats, UnitStats
from empire_core.gamedata.ids import (
    Achievement,
    AllianceCrestLayout,
    Currency,
    CurrencyId,
    Event,
    Gem,
    General,
    LegendSkill,
    MainQuest,
    Research,
    SceatSkill,
    Title,
    Tool,
    Unit,
)
from empire_core.texts import cached_text, get_texts, text

LANG_FILE = {
    "meadranger_name": "Mead ranger",
    "currency_name_5MinSkip": "Skip 5 minutes",
    "research_1_title": "Maneuver",
    "event_title_5": "Nomad invasion",
    "gem_unique_1": "Core of the city",
    "gem_effect_name_gemDefenseSupportUnitsWeak": "Gem of the reserves: {0}",
    "kingdomName_Dessert": "The Burning Sands",
    "dialog_alliance_rank4": "Deputy",
    "dialog_alliance_rank9": "Novice",
}


@pytest.fixture(autouse=True)
def stub_texts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"test attempted a real HTTP request: {args!r}")

    langs: list[str] = []

    def fetch(lang: str = "en") -> dict[str, str]:
        langs.append(lang)
        return {key: value if lang == "en" else f"{value} ({lang})" for key, value in LANG_FILE.items()}

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(texts, "fetch_texts", fetch)
    return langs


class TestGeneratedEnums:
    @pytest.mark.parametrize(
        ("member", "text_id"),
        [
            (Unit.MEAD_RANGER_L6, "meadranger_name"),
            (Tool.PREMIUMSTAKES, "premiumstakes_name"),
            (Currency.SKIP_5_MINUTES, "currency_name_5MinSkip"),
            (CurrencyId.SKIP_5_MINUTES, "currency_name_5MinSkip"),
            (Research.MANEUVER_L1, "research_1_title"),
            (Event.NOMAD_INVASION, "event_title_5"),
            (Gem.CORE_OF_THE_CITY, "gem_unique_1"),
            (Gem.GEM_OF_THE_RESERVES_L6, "gem_effect_name_gemDefenseSupportUnitsWeak"),
            (General.TORIL, "generals_characters_101_name"),
            (LegendSkill.GATE_REDUCTION_T0_G1_L1, "dialog_legendTemple_1_name"),
            (SceatSkill.NEW_HEIGHTS_L1, "dialog_legendTemple_sceat_1_name"),
            (Achievement.ACHIEVEMENT_POINTS_L4, "achievementName_0"),
            (Title.CHEVALIER, "playerTitle_1"),
            (AllianceCrestLayout.FREE_1, "allianceCoat_Layout_name_1"),
            (MainQuest.BRAVERY_AND_LUCK_IN_BATTLE, "mainquest_1_title"),
        ],
    )
    def test_each_member_names_its_text_id(self, member: Any, text_id: str) -> None:
        assert member.text_id == text_id

    def test_display_names_read_the_language_file(self, stub_texts: list[str]) -> None:
        assert Unit.MEAD_RANGER_L6.display_name() == "Mead ranger"
        assert Currency.SKIP_5_MINUTES.display_name() == "Skip 5 minutes"
        assert Research.MANEUVER_L1.display_name() == "Maneuver"
        assert Event.NOMAD_INVASION.display_name("de") == "Nomad invasion (de)"
        assert stub_texts == ["en", "de"]

    def test_a_gem_fills_in_its_level(self) -> None:
        assert Gem.GEM_OF_THE_RESERVES_L6.display_name() == "Gem of the reserves: 6"
        assert Gem.CORE_OF_THE_CITY.display_name() == "Core of the city"

    def test_a_missing_text_reads_as_its_id(self) -> None:
        assert Title.CHEVALIER.display_name() == "playerTitle_1"

    def test_events_and_generals_without_a_text_have_none(self) -> None:
        assert Event.NOMAD_INVASION.display_name() == "Nomad invasion"
        assert Event.THORNKING.display_name() is None
        assert General.TORIL.display_name() is None

    def test_a_blueprint_research_is_named_by_its_blueprint(self) -> None:
        assert Research.BEEFSTORAGE_G193_L1.text_id == "ci_blueprint_BeefCapacityIncrease_premium"
        assert Research.RECRUTING_COST_REDUCTION_G61_L1.text_id == "ci_blueprint_barracksCost"

    def test_a_crafting_recipe_research_has_none(self) -> None:
        assert Research.DRAGON_CHARM_G175_L1.text_id == ""
        assert Research.DRAGON_CHARM_G175_L1.display_name() is None

    def test_cached_text_never_fetches(self, stub_texts: list[str]) -> None:
        assert cached_text(Unit.MEAD_RANGER_L6.text_id) is None
        get_texts("en")
        assert cached_text(Unit.MEAD_RANGER_L6.text_id) == "Mead ranger"
        assert stub_texts == ["en"]


class TestHandWrittenEnums:
    def test_kingdoms(self) -> None:
        assert [k.text_id for k in Kingdom] == [
            "kingdomName_Classic",
            "kingdomName_Dessert",
            "kingdomName_Icecream",
            "kingdomName_Volcano",
            "kingdomName_Eiland",
            "kingdomName_Faction",
        ]
        assert text(Kingdom.SANDS.text_id) == "The Burning Sands"

    def test_alliance_ranks_have_a_numbering_of_their_own(self) -> None:
        assert [r.text_id[-1] for r in AllianceRank] == ["0", "4", "5", "6", "7", "8", "1", "2", "3", "9"]
        assert text(AllianceRank.COLEADER.text_id) == "Deputy"
        assert text(AllianceRank.APPLICANT.text_id) == "Novice"


class TestGameDataRows:
    def test_units_tools_and_currencies_name_their_text_id(self) -> None:
        data = GameData.parse(
            "786.03",
            {
                "units": [
                    {"wodID": "211", "type": "MeadRanger", "level": "6"},
                    {"wodID": "646", "type": "PremiumStakes", "slotTypes": "1"},
                ],
                "currencies": [
                    {"currencyID": "1", "Name": "5MinSkip", "JSONKey": "MS2"},
                    {"currencyID": "2", "Name": "Other", "assetName": "Asset", "JSONKey": "X"},
                ],
            },
        )
        assert isinstance(data.units[211], UnitStats) and data.units[211].name_text_id == "meadranger_name"
        assert isinstance(data.tools[646], ToolStats) and data.tools[646].name_text_id == "premiumstakes_name"
        currencies: list[CurrencyDef] = [data.currencies[1], data.currencies[2]]
        assert [c.name_text_id for c in currencies] == ["currency_name_5MinSkip", "currency_name_Asset"]
