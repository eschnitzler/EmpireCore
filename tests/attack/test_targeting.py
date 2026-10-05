"""Tests for reading an attack's target from the server."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from empire_core.army.spy_army import SpyArmy
from empire_core.attack.filling import _target_defense
from empire_core.attack.targeting import _read_precalculation, _read_target
from empire_core.exceptions import EmpireTimeoutError
from tests.attack.fill_helpers import FillClient
from tests.service_helpers import conn, xt_packet


class TestTargetReading(FillClient):
    """Each read fills only what the target still lacks."""

    def test_the_precalculation_supplies_the_defenders_legend_skills(self):
        from empire_core.attack.targeting import _Target

        client = self.build([[601, 100_000]])
        army = SpyArmy.from_spy_data([[[601, 10]], [], [], [], [], [], []])

        def info(spy):
            return SimpleNamespace(
                target_row=lambda: None,
                spy_army=lambda: spy,
                defending_castellan=lambda: None,
                attacker_bonuses=lambda: [],
                owner_records=lambda: [],
                defender_legend_skill_ids=[434],
            )

        spied = _Target(x=5, y=6)
        client.attack.get_attack_info = lambda **_: info(army)
        _read_precalculation(client.attack, spied, timeout=1.0)
        assert spied.defender_legend_skill_ids == [434]

        unspied = _Target(x=5, y=6)
        client.attack.get_attack_info = lambda **_: info(None)
        _read_precalculation(client.attack, unspied, timeout=1.0)
        assert unspied.defender_legend_skill_ids is None

    def test_a_failed_tile_scan_still_tries_the_pre_calculation_once(self):
        from empire_core.attack.targeting import _Target

        client = self.build([[601, 100_000]])
        conn(client).script["gaa"] = EmpireTimeoutError("no gaa")
        target = _Target(x=700, y=710)

        _read_target(client.attack, target, castle_id=12345, timeout=1.0)

        sent = [command for command, _ in conn(client).request_payloads]
        assert sent.count("gaa") == 1
        assert "aci" in sent

    def test_a_pre_calculation_without_a_row_leaves_the_map_to_supply_it(self):
        from empire_core.attack.targeting import _Target

        client = self.build([[601, 100_000]])
        outpost_row = [4, 700, 710, 55, 4242, 1, 1, 1, 0, 0, "outpost"]
        conn(client).script["coi"] = xt_packet("coi", {"AB": 1, "MB": 2})
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [outpost_row], "OI": []})
        target = _Target(x=700, y=710, area_type=4, conquer=True)

        _read_target(client.attack, target, castle_id=12345, timeout=1.0)

        assert target.row == outpost_row

    def test_an_alien_camps_row_gives_its_protection_and_level(self):
        # A captured red alien camp row; AAlienInvasionMapobjectVO returns fields 6 to 8 as its bonuses
        from empire_core.attack.targeting import _Target
        from empire_core.enums import Flank

        client = self.build([[601, 100_000]])
        assert client.game_data is not None
        row = [34, 619, 242, 70, -1, 0, 120, 120, 45, 0, -1]
        target = _Target(x=619, y=242, row=row)

        defense = _target_defense(client.game_data, target)

        assert defense is not None
        left, middle = defense[Flank.LEFT], defense[Flank.MIDDLE]
        assert (left.wall_bonus, middle.gate_bonus, left.moat_bonus) == pytest.approx((1.2, 1.2, 0.45))

        conn(client).script["adi"] = xt_packet("adi", None, error_code=203)
        conn(client).script["gaa"] = xt_packet("gaa", {"KID": 0, "AI": [row], "OI": []})
        read = _Target(x=619, y=242)
        _read_target(client.attack, read, castle_id=12345, timeout=1.0)
        assert (read.row, read.level) == (row, 70)
        assert conn(client).requested.count("gaa") == 1
