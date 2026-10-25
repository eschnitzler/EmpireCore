"""Tests for the server-free parts of wave filling."""

from __future__ import annotations

import pytest

from empire_core.attack.filling import _target_defense
from empire_core.attack.targeting import _Target
from empire_core.enums import Flank
from empire_core.gamedata import GameData
from tests.attack.fill_helpers import FillClient
from tests.combat.combat_helpers import PAYLOAD


class TestTargetDefense(FillClient):
    """The defense estimated from a target's row."""

    def test_an_invasion_camps_protection_is_divided_by_a_hundred(self):
        # FightScreenHelper.getDefenceBonuses (bundle line 19148) takes baseWallBonus / 100,
        # as fortification_bonuses does for a castle's buildings
        from empire_core.attack.targeting import _Target
        from empire_core.enums import Flank

        client = self.build([[601, 100_000]])
        assert client.game_data is not None
        target = _Target(x=700, y=710, row=[27, 700, 710, -1, 4, 0, 0, 0, -1, 110, 120, 30])

        defense = _target_defense(client.game_data, target)

        assert defense is not None
        left, middle = defense[Flank.LEFT], defense[Flank.MIDDLE]
        assert (left.wall_bonus, left.gate_bonus, left.moat_bonus) == pytest.approx((1.1, 0.0, 0.3))
        assert middle.gate_bonus == pytest.approx(1.2)

    def test_the_wolf_king_and_alliance_camps_take_their_rows_protection(self):
        from empire_core.attack.targeting import _Target
        from empire_core.enums import Flank

        client = self.build([[601, 100_000]])
        assert client.game_data is not None
        for row in (
            [42, 1, 2, 60, 12, 0, 40, 50, 60],
            [35, 1, 2, 60, 8, 100, 500, 20, 6, 3, 40, 50, 60],
            [40, 1, 2, 60, 8, 100, 500, 20, 6, 3, 40, 50, 60],
        ):
            defense = _target_defense(client.game_data, _Target(x=1, y=2, row=row))
            assert defense is not None
            middle = defense[Flank.MIDDLE]
            assert (middle.wall_bonus, middle.gate_bonus, middle.moat_bonus) == pytest.approx((0.4, 0.5, 0.6)), row


def test_a_berimond_camp_takes_its_factions_protection_at_its_level():
    # FactionInvasionCampMapObjectVO: baseWallBonus / baseGateBonus from getFactionInvasion(dungeonLevel,
    # ownerInfo.factionID), baseMoatBonus 0
    game = GameData.parse(
        "test",
        dict(
            PAYLOAD,
            factioninvasioncamps=[
                {"countVictory": "24", "factionID": "0", "wallBonus": "10", "gateBonus": "20"},
                {"countVictory": "24", "factionID": "1", "wallBonus": "40", "gateBonus": "50"},
            ],
        ),
    )
    blue = _target_defense(game, _Target(x=1, y=2, row=[30, 1, 2, -1, 4, 0, 0, -410], level=24))
    red = _target_defense(game, _Target(x=1, y=2, row=[30, 1, 2, -1, 4, 0, 0, -411], level=24))
    unknown = _target_defense(game, _Target(x=1, y=2, row=[30, 1, 2, -1, 4, 0, 0, -411], level=25))

    assert blue is not None and red is not None and unknown is not None
    assert (blue[Flank.MIDDLE].wall_bonus, blue[Flank.MIDDLE].gate_bonus) == pytest.approx((0.1, 0.2))
    assert (red[Flank.MIDDLE].wall_bonus, red[Flank.MIDDLE].gate_bonus) == pytest.approx((0.4, 0.5))
    assert red[Flank.MIDDLE].moat_bonus == 0.0
    assert (unknown[Flank.MIDDLE].wall_bonus, unknown[Flank.MIDDLE].gate_bonus) == (0.0, 0.0)
