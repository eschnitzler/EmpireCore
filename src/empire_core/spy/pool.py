"""
How many spies you have: the ``gms`` count plus research, legend skill and title boosts.

Client: ``CastleSpyData.getNumAllSpies`` and ``getNumAvailableSpies`` (bundle lines 139970-139978)
"""

from __future__ import annotations

from collections.abc import Iterable

from empire_core.combat.bonuses import EffectResolver, legend_skill_value, parse_effect_spec
from empire_core.gamedata import GameData
from empire_core.protocol.js import js_int, js_parse_int

# EffectTypeEnum (bundle line 1322): EFFECT_TYPE_SPY_COUNT_BOOST, EFFECT_TYPE_AMOUNT_SPIES_BOOST
_SPY_COUNT_BOOST = 73
_AMOUNT_SPIES_BOOST = 98
# CastleLegendSkillEffectsEnum.SPY_AMOUNT_BONUS (bundle line 7873)
_SPY_AMOUNT_BONUS = "spyAmountBonus"


def total_spies(max_spies: int, *, research_bonus: float = 0, legend_bonus: float = 0, title_percent: float = 0) -> int:
    """
    The client's count of all your spies, home or out.

    ``int((max_spies + int(research_bonus) + int(legend_bonus)) * (1 + title_percent / 100))``,
    each ``int`` truncating. The client adds ``legend_bonus`` only for a target
    whose owner is a legend; pass 0 otherwise.

    Args:
        max_spies: ``MaxSpiesResponse.max_spies``, from ``client.state.get_max_spies()``
        research_bonus: :func:`research_spy_bonus`
        legend_bonus: :func:`legend_spy_bonus`
        title_percent: :func:`title_spy_percent`

    Client: ``CastleSpyData.getNumAllSpies`` (bundle line 139976)
    """
    base = js_int(max_spies) + js_int(research_bonus) + js_int(legend_bonus)
    return js_int(base * (1 + title_percent / 100))


def research_spy_bonus(game_data: GameData, research_ids: Iterable[int]) -> float:
    """
    Extra spies from your finished research, uncapped as the client totals it.

    Args:
        game_data: Loaded tables
        research_ids: Your finished research ids, the ``BR`` of the ``rei`` section

    Client: ``CastleResearchData.getResearchEffectValue`` and ``getResearchEffectsByType``
    (bundle lines 139343-139357), ``CastleEffectsHelper.getTotalEffectValue`` with ``ignoreCap``
    (bundle line 4139)
    """
    resolver = EffectResolver(game_data)
    bonuses = [
        bonus
        for research_id in research_ids
        if (row := game_data.researches.get(research_id)) is not None
        for bonus in parse_effect_spec(row.get("effects"))
    ]
    return resolver.accumulate(bonuses, _AMOUNT_SPIES_BOOST, include_economy=True, ignore_cap=True)


def legend_spy_bonus(game_data: GameData, legend_skill_ids: Iterable[int]) -> float:
    """
    Extra spies from your legend skills.

    Args:
        game_data: Loaded tables
        legend_skill_ids: ``SkillList.legend_skill_ids``, from ``client.skills.get_skills()``

    Client: ``CastleLegendSkillData.getTotalValueOfLegendSkillEffect`` (bundle line 112086)
    """
    return legend_skill_value(game_data, legend_skill_ids, _SPY_AMOUNT_BONUS)


def island_title_chain(game_data: GameData, island_title_id: int) -> list[int]:
    """
    The island titles you hold with one: it and every title below it, lowest first.

    Args:
        game_data: Loaded tables
        island_title_id: Your current Storm Islands title, -1 or an unknown id for none

    Client: ``CastleTitleData.getUsersTitleVectorFromSystem`` for ``ISLAND_TITLE`` (bundle line 21119)
    """
    chain: list[int] = []
    title_id: int | None = island_title_id
    while title_id is not None and title_id in game_data.titles and title_id not in chain:
        chain.insert(0, title_id)
        title_id = js_parse_int(game_data.titles[title_id].get("previousTitleID"))
    return chain


def title_spy_percent(game_data: GameData, title_ids: Iterable[int]) -> float:
    """
    Your titles' spy boost in percent, uncapped as the client totals it.

    Each title counts its first spy boost only.

    Args:
        game_data: Loaded tables
        title_ids: Every title you hold; for a Storm Islands title, :func:`island_title_chain`

    Client: ``CastleTitleSystemHelper.returnTitleEffectValue`` and ``returnTitleEffectsByType``
    (bundle lines 4420-4428), ``EffectsHandlerVO.getBonusVOByEffectType`` (bundle line 25098)
    """
    resolver = EffectResolver(game_data)
    bonuses = []
    for title_id in title_ids:
        row = game_data.titles.get(title_id)
        if row is None:
            continue
        for bonus in parse_effect_spec(row.get("effects")):
            effect = resolver.effect_for(bonus)
            if effect is not None and effect.effect_type_id == _SPY_COUNT_BOOST:
                bonuses.append(bonus)
                break
    return resolver.accumulate(bonuses, _SPY_COUNT_BOOST, include_economy=True, ignore_cap=True)


__all__ = [
    "island_title_chain",
    "legend_spy_bonus",
    "research_spy_bonus",
    "title_spy_percent",
    "total_spies",
]
