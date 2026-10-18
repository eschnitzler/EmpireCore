"""Generals progression: unlocking, star upgrades, the flags, and the generals hub's spins."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.enums import CollectableKind
from empire_core.exceptions import CommandError
from empire_core.gamedata import (
    Currency,
    CurrencyId,
    GameData,
    General,
    GeneralDef,
    GeneralRarity,
    GeneralRarityDef,
    GeneralsHubCharacter,
    GeneralsHubCharacterDef,
)
from empire_core.protocol.models import (
    GetGeneralsHubResponse,
    OwnedGeneral,
    SpinGeneralsHubRequest,
    SpinGeneralsHubResponse,
)
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# Rows as items v787.03 has them, the xp requirements cut to the first 21 levels.
RARITY_LEGENDARY = {
    "generalRarityID": "4",
    "maxStarLevel": "10",
    "unlockCosts": "150",
    "upgradeCosts": "225,300,450,600,750,1200,2500,4000,6000,9000",
    "xpRequirements": "0,1500,3750,6750,10500,15000,20250,26250,33000,40500,48750,57750,67500,78000,89250,101250,"
    "114000,127500,141750,156750,172500",
    "universalShardsPerHundred": "10",
    "name": "legendary",
}
TORIL = {
    "generalID": "101",
    "generalName": "Toril",
    "generalRarityID": "4",
    "maxLevel": "100",
    "maxStarLevel": "10",
    "unlockCurrencyID": "10001",
    "upgradeCurrencyIDs": "10000,10001",
    "isPreview": "0",
    "isNPCGeneral": "0",
}
FAT_KING = {
    "characterID": "1",
    "name": "fatKing",
    "spinRarities": "1,1,1,2",
    "tombolas": "6001+10001#6006+10006#6007+10007",
    "coolDownInSeconds": "259200",
    "maxFreeOpenings": "2",
    "freeOpeningTombolaID": "10001",
    "badLuckProtectionDrawAmount": "30",
    "packageIDs": "10515",
    "badLuckSpinRarities": "1,1,2,3",
}
PAYLOAD: dict[str, Any] = {
    "generals": [TORIL, {**TORIL, "generalID": "120", "generalName": "Preview", "isPreview": "1"}],
    "generalRarities": [RARITY_LEGENDARY],
    "characters": [FAT_KING],
    "rewards": [{"rewardID": "7", "addC1": "500"}],
    "currencies": [
        {"currencyID": "10000", "Name": "ShardUniversal", "JSONKey": "SUN"},
        {"currencyID": "10001", "Name": "ShardToril", "JSONKey": "STL"},
        {"currencyID": "6001", "Name": "FatKingToken", "JSONKey": "FKT"},
        {"currencyID": "6002", "Name": "KnightToken", "JSONKey": "KTK"},
    ],
}


def generals_client(script: dict[str, Any] | None = None, **held: int):
    """A client with the generals game data, holding ``held`` (``Currency`` name -> amount)."""
    sce = [[Currency[name].value, amount] for name, amount in held.items()]
    client = make_client(script, state=logged_in_state(sce=sce))
    client.game_data = GameData.parse("787.03", PAYLOAD)
    return client


class TestGameData:
    """``GeneralXmlVO``, ``GeneralRarityXmlVO`` and ``GeneralsHubQuestVO``, as ``GeneralsData`` reads them."""

    def test_a_general_names_its_shards(self):
        general = GeneralDef.model_validate(TORIL)

        assert general.unlock_currency_id is CurrencyId.TORILS_GENERAL_SHARD
        assert general.upgrade_currency_ids == (CurrencyId.UNIVERSAL_GENERAL_SHARD, CurrencyId.TORILS_GENERAL_SHARD)
        assert general.rarity_id is GeneralRarity.LEGENDARY
        assert general.is_implemented

    def test_a_preview_general_is_not_implemented(self):
        assert not GeneralDef.model_validate({**TORIL, "isPreview": "1"}).is_implemented

    def test_a_general_without_columns_reads_as_the_client_defaults_them(self):
        general = GeneralDef.model_validate({"generalID": "999"})

        assert general.rarity_id == GeneralRarity.RARE
        assert (general.unlock_currency_id, general.upgrade_currency_ids, general.is_implemented) == (0, (), True)

    def test_a_rarity_prices_unlocking_and_each_star(self):
        rarity = GeneralRarityDef.model_validate(RARITY_LEGENDARY)

        assert (rarity.rarity_id, rarity.unlock_cost, rarity.max_star_level) == (GeneralRarity.LEGENDARY, 150, 10)
        assert rarity.upgrade_costs[:3] == (225, 300, 450)
        assert [rarity.star_upgrade_cost(star) for star in (0, 9, 10)] == [225, 9000, 0]

    @pytest.mark.parametrize(
        ("xp", "level"),
        [(0, 1), (1499, 1), (1500, 2), (40500, 10), (172499, 20), (172500, 21), (10**9, 21)],
    )
    def test_the_level_follows_the_xp_as_the_client_counts_it(self, xp, level):
        assert GeneralRarityDef.model_validate(RARITY_LEGENDARY).level_for_xp(xp) == level

    def test_a_rarity_without_requirements_is_level_one(self):
        assert GeneralRarityDef.model_validate({"generalRarityID": "1"}).level_for_xp(500) == 1

    def test_a_hub_character_names_its_offerings(self):
        character = GeneralsHubCharacterDef.model_validate(FAT_KING)

        assert character.character_id is GeneralsHubCharacter.FAT_KING
        assert character.offering_currency_ids[0] is CurrencyId.OFFERING_TO_LUDWIG
        assert character.offering_currency_ids[1:] == (6006, 6007)
        assert (character.cooldown_seconds, character.max_free_openings) == (259200, 2)

    def test_the_tables_are_keyed_by_their_enums(self):
        data = GameData.parse("787.03", PAYLOAD)

        assert data.general_rarities[GeneralRarity.LEGENDARY].unlock_cost == 150
        assert data.generals_hub_characters[GeneralsHubCharacter.FAT_KING].name == "fatKing"


class TestHubModels:
    """``parse_GCS`` and ``parse_SCT`` (bundle lines 113080, 113073)."""

    def test_the_hub_lists_each_character(self):
        response = GetGeneralsHubResponse.model_validate(
            {"CHR": [{"CID": 1, "FOA": 2, "LFO": 1000}, {"CID": 2, "FOA": 0, "LFO": 1200}]}
        )

        assert [(c.character_id, c.free_spins, c.last_free_spin) for c in response.characters] == [
            (GeneralsHubCharacter.FAT_KING, 2, 1000),
            (GeneralsHubCharacter.DRUNK_KNIGHT, 0, 1200),
        ]
        assert response.characters[0].cooldown_ends_at is None

    def test_a_spin_sends_the_character_offering_and_flag(self):
        request = SpinGeneralsHubRequest(
            character_id=GeneralsHubCharacter.FAT_KING, offering_id=CurrencyId.OFFERING_TO_LUDWIG, free=True, amount=1
        )

        assert request.to_payload() == {"CID": 1, "OID": 6001, "IF": 1, "AMT": 1}

    def test_a_spin_reads_reward_rows_and_reward_ids(self):
        response = SpinGeneralsHubResponse.model_validate(
            {
                "CH": {"CID": 1, "FOA": 1, "LFO": 1000},
                "LTR": [{"R": 2, "RR": [["STL", 20]], "A": 3}, {"R": 1, "RW": [7, 8]}],
            }
        )

        assert response.character.free_spins == 1
        first, second = response.rewards
        assert (first.rarity, first.count, [(c.key, c.amount) for c in first.rewards]) == (2, 3, [("STL", 20)])
        assert (second.rarity, second.count, second.reward_ids, second.rewards) == (1, 1, (7, 8), ())


class TestUnlockGeneral:
    """``GeneralsOverviewDialog`` sends ``gue`` while ``GeneralVO.canBeUnlocked`` (bundle lines 15851, 26751)."""

    def test_unlock_sends_the_general(self):
        client = generals_client(TORILS_GENERAL_SHARD=150)

        client.commanders.unlock_general(General.TORIL)

        assert conn(client).request_payloads == [("gue", {"GID": 101})]

    def test_too_few_shards_send_nothing(self):
        client = generals_client(TORILS_GENERAL_SHARD=149)

        with pytest.raises(ValueError, match="150"):
            client.commanders.unlock_general(General.TORIL)

        assert conn(client).request_payloads == []

    def test_a_preview_general_cannot_be_unlocked(self):
        client = generals_client(TORILS_GENERAL_SHARD=500)

        with pytest.raises(ValueError, match="preview"):
            client.commanders.unlock_general(120)

        assert conn(client).request_payloads == []

    def test_a_refusal_raises(self):
        client = generals_client({"gue": xt_packet("gue", error_code=114)}, TORILS_GENERAL_SHARD=150)

        with pytest.raises(CommandError):
            client.commanders.unlock_general(General.TORIL)


def toril(**fields: Any) -> OwnedGeneral:
    return OwnedGeneral.model_validate({"GID": 101, **fields})


class TestUpgradeGeneralStars:
    """``GeneralsLevelUpDialogListItem`` sends ``gsue`` while ``isStarLevelUpgradeable`` (bundle lines 74481, 26777)."""

    def test_upgrade_sends_the_general_and_shard(self):
        client = generals_client(UNIVERSAL_GENERAL_SHARD=1)

        client.commanders.upgrade_general_stars(toril(XP=40500, ST=0), Currency.UNIVERSAL_GENERAL_SHARD)

        assert conn(client).request_payloads == [("gsue", {"GID": 101, "CID": 10000})]

    def test_a_fixed_level_counts_over_the_xp(self):
        client = generals_client(TORILS_GENERAL_SHARD=5)

        client.commanders.upgrade_general_stars(toril(XP=0, L=20, ST=1), Currency.TORILS_GENERAL_SHARD)

        assert conn(client).request_payloads == [("gsue", {"GID": 101, "CID": 10001})]

    @pytest.mark.parametrize(
        "general",
        [toril(XP=40499, ST=0), toril(XP=40500, ST=1), toril(L=100, ST=10), toril(XP=0)],
        ids=["not a tenth level", "star already earned", "max stars", "level one"],
    )
    def test_a_general_that_cannot_rise_sends_nothing(self, general):
        client = generals_client(UNIVERSAL_GENERAL_SHARD=10)

        with pytest.raises(ValueError, match="star"):
            client.commanders.upgrade_general_stars(general, Currency.UNIVERSAL_GENERAL_SHARD)

        assert conn(client).request_payloads == []

    def test_a_shard_of_another_general_sends_nothing(self):
        client = generals_client(OFFERING_TO_LUDWIG=10)

        with pytest.raises(ValueError, match="upgrade"):
            client.commanders.upgrade_general_stars(toril(XP=40500), Currency.OFFERING_TO_LUDWIG)

    def test_a_shard_not_held_sends_nothing(self):
        client = generals_client()

        with pytest.raises(ValueError, match="hold"):
            client.commanders.upgrade_general_stars(toril(XP=40500), Currency.TORILS_GENERAL_SHARD)


class TestClearGeneralFlags:
    def test_clear_flags_sends_the_general(self):
        client = generals_client()

        client.commanders.clear_general_flags(General.TORIL)

        assert conn(client).request_payloads == [("grf", {"GID": 101})]


class TestGeneralsHub:
    def test_the_hub_status_carries_each_cooldown_end(self):
        client = generals_client(
            {"gcs": xt_packet("gcs", {"CHR": [{"CID": 1, "FOA": 0, "LFO": 1000}, {"CID": 9, "FOA": 1, "LFO": 5}]})}
        )

        hub = client.commanders.get_generals_hub()

        assert conn(client).request_payloads == [("gcs", {})]
        assert [(c.character_id, c.cooldown_ends_at) for c in hub] == [
            (GeneralsHubCharacter.FAT_KING, 260200),
            (9, None),
        ]

    def test_a_free_spin_sends_one(self):
        reply = {"CH": {"CID": 1, "FOA": 1, "LFO": 2000}, "LTR": [{"R": 1, "RW": [7]}]}
        client = generals_client({"sct": xt_packet("sct", reply)})

        spin = client.commanders.spin_generals_hub(
            GeneralsHubCharacter.FAT_KING, Currency.OFFERING_TO_LUDWIG, free=True
        )

        assert conn(client).request_payloads == [("sct", {"CID": 1, "OID": 6001, "IF": 1, "AMT": 1})]
        assert spin.character.cooldown_ends_at == 261200
        assert [(c.kind, c.amount) for c in spin.rewards[0].rewards] == [(CollectableKind.COINS, 500)]

    def test_a_paid_spin_spends_held_offerings(self):
        client = generals_client({"sct": xt_packet("sct", {"CH": {"CID": 1}, "LTR": []})}, OFFERING_TO_LUDWIG=3)

        client.commanders.spin_generals_hub(GeneralsHubCharacter.FAT_KING, Currency.OFFERING_TO_LUDWIG, amount=3)

        assert conn(client).request_payloads == [("sct", {"CID": 1, "OID": 6001, "IF": 0, "AMT": 3})]

    def test_more_offerings_than_held_send_nothing(self):
        client = generals_client(OFFERING_TO_LUDWIG=2)

        with pytest.raises(ValueError, match="hold"):
            client.commanders.spin_generals_hub(GeneralsHubCharacter.FAT_KING, Currency.OFFERING_TO_LUDWIG, amount=3)

        assert conn(client).request_payloads == []

    def test_a_free_spin_is_one_spin(self):
        client = generals_client()

        with pytest.raises(ValueError, match="one"):
            client.commanders.spin_generals_hub(
                GeneralsHubCharacter.FAT_KING, Currency.OFFERING_TO_LUDWIG, free=True, amount=2
            )

    def test_another_characters_offering_sends_nothing(self):
        client = generals_client(OFFERING_TO_ULRICH=5)

        with pytest.raises(ValueError, match="offering"):
            client.commanders.spin_generals_hub(GeneralsHubCharacter.FAT_KING, Currency.OFFERING_TO_ULRICH)

        assert conn(client).request_payloads == []
