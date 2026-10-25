"""The decoration fusion forge: ffi, ffl, fsr, fcc, gtd and dff."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.castle import (
    DECORATION_FORGE_ID,
    CatalystConversion,
    FuseDecorationResponse,
    FusionDecoration,
    FusionTargetArea,
)
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError
from empire_core.gamedata import CurrencyId
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# FusionForgeVO.parseServerObject reads FL, FE, FRS, FUM and FUPS (bundle line 142197)
FORGE: dict[str, Any] = {"FID": 1, "FL": 3, "FE": 450, "FRS": 120, "FUM": 0, "FUPS": 2}

# DecoStorageTempDecoVO.parseServerObject: AID, KID and A, each read by ADecoBuildingVO.parseServerInfoShort
TARGETS: list[dict[str, Any]] = [
    {"AID": 5001, "KID": 0, "A": [{"WID": 512, "OID": 31, "FXP": 900, "UID": 7}, {"WID": 600, "OID": 32, "DP": 40}]},
]


def targets() -> FusionTargetArea:
    return FusionTargetArea.model_validate(TARGETS[0])


class TestForges:
    def test_get_fusion_forges_asks_for_the_decoration_forge_and_keeps_it(self):
        client = make_client({"ffi": xt_packet("ffi", {"FI": [FORGE]})}, state=logged_in_state())
        conn(client).on_packet = lambda packet: client.state.update_from_packet(
            packet.command_id, packet.payload, packet.error_code
        )

        (forge,) = client.castle.get_fusion_forges()

        assert conn(client).request_payloads == [("ffi", {"FIDS": [DECORATION_FORGE_ID]})]
        assert (forge.level, forge.energy, forge.recharge_progress_seconds, forge.used_ruby_refills) == (3, 450, 120, 2)
        assert client.castle.fusion_forges == {1: forge}

    def test_a_later_ffi_updates_only_the_forges_it_lists(self):
        state = logged_in_state()
        state.update_from_packet("ffi", {"FI": [FORGE, {**FORGE, "FID": 2}]})
        state.update_from_packet("ffi", {"FI": [{**FORGE, "FE": 10}]})
        forges = state.get_fusion_forges() or {}
        assert forges[1].energy == 10 and forges[2].energy == 450

    def test_level_up_returns_the_new_level(self):
        client = make_client({"ffl": xt_packet("ffl", {"FID": 1, "FL": 4})})
        assert client.castle.level_up_fusion_forge() == 4
        assert conn(client).request_payloads == [("ffl", {"FID": 1})]

    def test_refill_needs_consent_and_returns_the_energy_added(self):
        client = make_client({"fsr": xt_packet("fsr", {"FID": 1, "FE": 300})})
        with pytest.raises(ValueError, match="spend_rubies"):
            client.castle.refill_fusion_forge()
        assert client.castle.refill_fusion_forge(spend_rubies=True) == 300
        assert conn(client).request_payloads == [("fsr", {"FID": 1, "FSRP": 1})]

    def test_catalysts_convert_either_way(self):
        reply = {"FID": 1, "FCCD": 1, "FCID": 100000, "FCCA": 5}
        client = make_client({"fcc": xt_packet("fcc", reply)})
        converted = client.castle.convert_catalysts(CurrencyId.DECORATION_DUST, 5, CatalystConversion.DISASSEMBLE)
        assert conn(client).request_payloads == [("fcc", {"FID": 1, "FCCD": 1, "FCID": 100000, "FCCA": 5})]
        assert converted.direction is CatalystConversion.DISASSEMBLE and converted.amount == 5


class TestFusion:
    def test_gtd_reads_each_area_s_decorations(self):
        client = make_client({"gtd": xt_packet("gtd", TARGETS)})
        (area,) = client.castle.get_fusion_targets()
        assert conn(client).request_payloads == [("gtd", {})]
        assert area.kingdom is Kingdom.GREEN and area.castle_id == 5001
        first, custom = area.decorations
        assert (first.wod_id, first.fusion_xp, first.unique_id, first.decoration_points) == (512, 900, 7, None)
        assert custom.unique_id == -1 and custom.decoration_points == 40

    def test_dff_sends_source_target_and_catalyst(self):
        reply = {"WID": 512, "OID": 31, "FXP": 1500, "UID": 7, "SID": 0, "AID": 5001, "BFXP": 100}
        client = make_client({"dff": xt_packet("dff", reply)})
        area = targets()

        fused = client.castle.fuse_decoration(600, 88, area, area.decorations[0], 100001)

        assert conn(client).request_payloads == [
            (
                "dff",
                {
                    "FCID": 100001,
                    "FFFP": 0,
                    "FSUID": 88,
                    "FSWID": 600,
                    "FTOID": 31,
                    "FTSID": 0,
                    "FTAID": 5001,
                    "FTUID": 7,
                    "FTWID": 512,
                },
            )
        ]
        assert isinstance(fused, FuseDecorationResponse)
        assert fused.decoration.fusion_xp == 1500 and fused.bonus_xp == 100 and fused.castle_id == 5001
        assert not fused.decoration.model_extra

    def test_the_premium_fusion_needs_consent(self):
        client = make_client()
        area = targets()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.castle.fuse_decoration(600, 88, area, area.decorations[0], 100001, pay_with_rubies=True)
        assert conn(client).request_payloads == []

    def test_a_target_outside_the_area_sends_nothing(self):
        client = make_client()
        stranger = FusionDecoration.model_validate({"WID": 512, "OID": 99, "UID": 3})
        with pytest.raises(ValueError, match="not in area"):
            client.castle.fuse_decoration(600, 88, targets(), stranger, 100001)

    def test_a_refused_fusion_raises(self):
        client = make_client({"dff": xt_packet("dff", error_code=1)})
        area = targets()
        with pytest.raises(CommandError):
            client.castle.fuse_decoration(600, 88, area, area.decorations[0], 100001)

    def test_dff_reply_parses_alone(self):
        reply = parse_response("dff", {"WID": 512, "OID": 31, "FXP": 10, "UID": 7, "SID": 3, "AID": 9})
        assert isinstance(reply, FuseDecorationResponse)
        assert reply.kingdom is Kingdom.FIRE and reply.bonus_xp == 0
