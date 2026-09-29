"""Each model reads a flag with the conversion its client line uses."""

import pytest

from empire_core.army.spy_army import SpyArmy, UnitStack
from empire_core.gamedata.models import EquipmentEffectDef
from empire_core.movements.models import MovementOwner
from empire_core.protocol.models import AllianceInfo, General, MessageInfo
from empire_core.state.models import Alliance


class TestLooseOneFlags:
    """``1 == e.X``: ``"1"``, ``"1.0"`` and ``true`` are 1; ``1.5`` is not."""

    @pytest.mark.parametrize(("value", "expected"), [(1, True), ("1", True), ("1.0", True), (True, True), (1.5, False)])
    def test_alliance_king_flag(self, value, expected):
        # AllianceInfoVO.fillFromParamObject (bundle line 25932): 1 == e.KA
        assert AllianceInfo.model_validate({"KA": value}).is_king_alliance is expected

    @pytest.mark.parametrize(("value", "expected"), [("1", True), ("1.0", True), (1.5, False), (2, False)])
    def test_general_new_flag(self, value, expected):
        # GeneralVO.parseData (bundle line 26666): 1 == e.IN
        assert General.model_validate({"GID": 1, "IN": value}).is_new is expected

    @pytest.mark.parametrize(("value", "expected"), [("1.0", True), (1.5, False), ([1], True)])
    def test_message_read_flag(self, value, expected):
        # AMessageVO.loadFromParamArray (bundle line 3808): 1 == e[6]
        row = [7, 12, "x", "", 0, 0, value, 0, 0]
        assert MessageInfo.model_validate(row).is_read is expected

    def test_owner_dummy_flag(self):
        # WorldMapOwnerInfoVO.fillFromParamObject (bundle line 10794): 1 == e.DUM
        assert MovementOwner.model_validate({"OID": 5, "DUM": "1"}).is_dummy is True
        assert MovementOwner.model_validate({"OID": 5, "DUM": 1.5}).is_dummy is False


class TestIntOneFlag:
    @pytest.mark.parametrize(("value", "expected"), [(1.5, True), ("1.9", True), ("1abc", False)])
    def test_message_forwarded_flag(self, value, expected):
        # AMessageVO.loadFromParamArray (bundle line 3808): 1 == int(e[8])
        row = [7, 12, "x", "", 0, 0, 0, 0, value]
        assert MessageInfo.model_validate(row).is_forwarded is expected


class TestParseIntOneFlags:
    @pytest.mark.parametrize(("value", "expected"), [("1abc", True), ("1.9", True), (True, False), ("0x1", True)])
    def test_owner_ruin_flag(self, value, expected):
        # WorldMapOwnerInfoVO.fillFromParamObject (bundle line 10794): 1 == parseInt(e.R)
        assert MovementOwner.model_validate({"OID": 5, "R": value}).is_ruin is expected

    @pytest.mark.parametrize(
        ("value", "expected"), [("1.9", True), ("1abc", True), ("0x1", True), (True, False), (0, False)]
    )
    def test_owner_refer_a_friend_flag(self, value, expected):
        # WorldMapOwnerInfoVO.fillFromParamObject (bundle line 10794): !!parseInt(e.IRF)
        assert MovementOwner.model_validate({"OID": 5, "IRF": value}).via_refer_a_friend is expected

    @pytest.mark.parametrize(("value", "expected"), [("1abc", True), (True, False), (1, True)])
    def test_alliance_searching_flag(self, value, expected):
        # CastleUserData.parse_GAL (bundle line 9869): 1 == parseInt(e.SA)
        assert Alliance.model_validate({"AID": 1, "SA": value}).is_searching is expected


class TestTruthyFlags:
    @pytest.mark.parametrize(("value", "expected"), [([], True), ({}, True), (float("nan"), False), ("0", True)])
    def test_owner_searching_alliance(self, value, expected):
        # WorldMapOwnerInfoVO.fillFromParamObject (bundle line 10794): !!e.SA
        assert MovementOwner.model_validate({"OID": 5, "SA": value}).is_searching_alliance is expected

    @pytest.mark.parametrize(("value", "expected"), [([], True), (float("nan"), False)])
    def test_alliance_accepting_members(self, value, expected):
        # AllianceInfoVO.fillFromParamObject (bundle line 25928): !!e.IA
        assert AllianceInfo.model_validate({"IA": value}).is_accepting_members is expected


def test_spy_army_reads_pairs_through_int_and_drops_empty_stacks():
    # AUnitInventory.fillFromWodAmountArray (bundle line 42572) into a UnitInventoryList (bundle line 21826)
    army = SpyArmy.from_spy_data([[["652", "100"], [746, 0], [602, -3], [601, 2.9]]])
    assert army is not None
    assert army.left == [UnitStack(652, 100), UnitStack(601, 2)]


@pytest.mark.parametrize(("value", "expected"), [("12abc", 12), ("1e3", 1), ("", 0), ("abc", 0)])
def test_equipment_effect_bonus_reads_through_parse_int(value, expected):
    # XmlEquipmentEffectVO.parseXml (bundle line 144158): int(CastleXMLUtils.getIntAttribute("bonus", e))
    row = EquipmentEffectDef.model_validate({"equipmentEffectID": "1", "bonus": value})
    assert row.bonus == expected
