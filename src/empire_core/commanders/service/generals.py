"""Generals: assigning them, their abilities, skills and stars, and the generals hub."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from empire_core.commanders.models.generals import (
    ClearGeneralFlagsRequest,
    GeneralsHubCharacterStatus,
    GetGeneralsHubRequest,
    GetGeneralsHubResponse,
    SpinGeneralsHubRequest,
    SpinGeneralsHubResponse,
    UnlockGeneralRequest,
    UpgradeGeneralStarsRequest,
)
from empire_core.commanders.models.roster import CommanderRoster, SelectedAbility
from empire_core.commanders.models.skills import (
    AddGeneralXpRequest,
    AssignGeneralRequest,
    AssignGeneralResponse,
    GetGeneralsRequest,
    GetGeneralsResponse,
    OwnedGeneral,
    ResetGeneralSkillsRequest,
    SetGeneralAbilitiesRequest,
    UnlockGeneralSkillRequest,
)
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, CurrencyId, General, GeneralAbility, GeneralsHubCharacter, GeneralSkill
    from empire_core.gamedata.models import GeneralDef

    AnyGeneral = General | GeneralDef | OwnedGeneral


def _general_id(general: AnyGeneral) -> int:
    """The general's ``generalID``, from the enum, its game data row or an owned general."""
    return general if isinstance(general, int) else general.general_id


class GeneralsMixin(ServiceMixin):
    def get_generals(self, *, timeout: float = 5.0) -> list[OwnedGeneral]:
        """
        Every general the player owns, with the skills each has unlocked.

        Args:
            timeout: Timeout in seconds

        Returns:
            Your generals, from the ``gie`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetGeneralsRequest(), GetGeneralsResponse, timeout=timeout).generals

    def assign_general(self, commander_id: int, general: AnyGeneral | None, *, timeout: float = 5.0) -> CommanderRoster:
        """
        Assign a general to a commander; ``general=None`` takes its general away (the client sends -1,
        ``CastleLordData.assignGeneral``, bundle line 38679).

        Args:
            commander_id: A ``Commander.commander_id`` from
                ``client.commanders.get_commanders()``
            general: The general: one of :meth:`get_generals`, its row from
                ``GameData.require().general(name)``, or a ``General``
            timeout: Timeout in seconds

        Returns:
            Your commanders and castellans after the change, from the ``gla`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        request = AssignGeneralRequest(
            commander_id=commander_id, general_id=-1 if general is None else _general_id(general)
        )
        return self.request(request, AssignGeneralResponse, timeout=timeout).commander_roster

    def set_general_abilities(
        self, general: AnyGeneral, abilities: Iterable[tuple[int, GeneralAbility | None]], *, timeout: float = 5.0
    ) -> None:
        """
        Choose a general's abilities.

        Args:
            general: The general: one of :meth:`get_generals`, its row from
                ``GameData.require().general(name)``, or a ``General``
            abilities: ``(slot_id, ability)`` pairs, ``None`` to clear a slot.
                The client sends every slot it shows. An ability id comes from
                ``GameData.require().general_ability(name, level)``
            timeout: Timeout in seconds
        """
        slots = [SelectedAbility(slot_id=slot_id, ability_id=ability_id) for slot_id, ability_id in abilities]
        self.execute(SetGeneralAbilitiesRequest(general_id=_general_id(general), abilities=slots), timeout=timeout)

    def unlock_general_skill(self, skill_id: GeneralSkill, *, timeout: float = 5.0) -> None:
        """
        Unlock a general skill; the skill id names the general.

        The general's new skills arrive with the next ``gie``.

        Args:
            skill_id: The skill level's ``skillID``, from
                ``GameData.require().general_skill(general_id, name, level)``
                (``GeneralVO.unlockSkill``, bundle line 26773)
            timeout: Timeout in seconds
        """
        self.execute(UnlockGeneralSkillRequest(skill_id=skill_id), timeout=timeout)

    def reset_general_skills(self, general: AnyGeneral, *, timeout: float = 5.0) -> None:
        """
        Reset a general's skill tree.

        Args:
            general: The general: one of :meth:`get_generals`, its row from
                ``GameData.require().general(name)``, or a ``General``
            timeout: Timeout in seconds
        """
        self.execute(ResetGeneralSkillsRequest(general_id=_general_id(general)), timeout=timeout)

    def add_general_xp(
        self, general: AnyGeneral, currency_id: CurrencyId, amount: int, *, timeout: float = 5.0
    ) -> None:
        """
        Feed a general xp items.

        Args:
            general: The general: one of :meth:`get_generals`, its row from
                ``GameData.require().general(name)``, or a ``General``
            currency_id: The xp item's ``currencyID``, e.g.
                ``GameData.require().currency("GXP1").currency_id``
                (``GeneralsLevelUpDialogListItem.sendXPSelected``, bundle line 74485)
            amount: How many of the item to use
            timeout: Timeout in seconds
        """
        self.execute(
            AddGeneralXpRequest(general_id=_general_id(general), currency_id=currency_id, amount=amount),
            timeout=timeout,
        )

    def unlock_general(self, general: General, *, timeout: float = 5.0) -> None:
        """
        Unlock a general with its shards.

        The general must be out (not a preview) and you must hold the ``unlock_cost`` of its rarity in its
        ``unlock_currency_id`` shards (:attr:`PlayerService.currencies`). Whether it is already unlocked is
        not checked here, as only a ``gie`` lists the unlocked generals; the server refuses that.

        Client: ``GeneralsOverviewDialog.updateUnlockButton`` (bundle line 15833) shows the button, which sends
        ``gue`` (bundle line 15851), while ``GeneralVO.canBeUnlocked`` (bundle line 26751)

        Args:
            general: The general, from ``GameData.require().generals``
            timeout: Timeout in seconds

        Raises:
            ValueError: The game data lacks the general or its rarity, it is a preview, or too few shards are held
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        game_data = self._require_game_data()
        general_def = game_data.generals.get(general)
        if general_def is None:
            raise ValueError(f"general {general} is not in the game data")
        if not general_def.is_implemented:
            raise ValueError(f"general {general} is a preview and cannot be unlocked")
        rarity = game_data.general_rarities.get(general_def.rarity_id)
        if rarity is None:
            raise ValueError(f"general rarity {general_def.rarity_id} is not in the game data")
        held = self._held(general_def.unlock_currency_id)
        if held < rarity.unlock_cost:
            raise ValueError(f"unlocking general {general} takes {rarity.unlock_cost} shards; {held} are held")
        self.execute(UnlockGeneralRequest(general_id=general), timeout=timeout)

    def upgrade_general_stars(self, general: OwnedGeneral, currency: Currency, *, timeout: float = 5.0) -> None:
        """
        Raise a general's star level with one of its shards.

        A star comes at every tenth level: the general's level must be a multiple of 10, above 0, with
        fewer stars than its tenths and fewer than its ``max_star_level``. The level is the general's
        ``fixed_level`` when it has one, else the level its rarity gives its xp. ``currency`` must be one of
        its ``upgrade_currency_ids``, held (:attr:`PlayerService.currencies`). The client lists any held shard
        and does not compare the amount with the cost, ``GeneralRarityDef.star_upgrade_cost(star_level)``;
        neither does this.

        Client: ``GeneralsLevelUpDialogListItem.onClick`` (bundle line 74481) sends ``gsue`` for an unlocked
        general; ``GeneralVO.isStarLevelUpgradeable`` (bundle line 26777), whose trailing ``|| !isUnlocked``
        only switches the dialog to unlocking, and ``GeneralsLevelUPDialog.updateItems`` (bundle line 46889)
        lists the held ``upgradeCurrencyIDs``

        Args:
            general: The general, an ``OwnedGeneral`` from :meth:`get_generals`
            currency: The shard to spend
            timeout: Timeout in seconds

        Raises:
            ValueError: The game data lacks the general or its rarity, it has no star to earn, the shard is not
                one of its own, or none is held
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        game_data = self._require_game_data()
        general_def = game_data.generals.get(general.general_id)
        rarity = game_data.general_rarities.get(general_def.rarity_id) if general_def is not None else None
        if general_def is None or rarity is None:
            raise ValueError(f"general {general.general_id} or its rarity is not in the game data")
        level = general.fixed_level if general.fixed_level > -1 else rarity.level_for_xp(general.experience)
        star = general.star_level
        if not (level > 0 and level % 10 == 0 and level // 10 > star and star < general_def.max_star_level):
            raise ValueError(f"general {general.general_id} at level {level} has no star to earn at star {star}")
        if currency.currency_id not in general_def.upgrade_currency_ids:
            raise ValueError(f"{currency.name} does not upgrade general {general.general_id}")
        if self._held(currency.currency_id) <= 0:
            raise ValueError(f"you hold no {currency.name}")
        request = UpgradeGeneralStarsRequest(general_id=general.general_id, currency_id=currency.currency_id)
        self.execute(request, timeout=timeout)

    def clear_general_flags(self, general: General, *, timeout: float = 5.0) -> None:
        """
        Clear a general's new and level-up flags; the next ``gie`` lists it without them.

        Client: ``GeneralVO.resetFlags`` (bundle line 26789), which also clears them on its own copy

        Args:
            general: The general, an ``OwnedGeneral.general_id`` from :meth:`get_generals`
            timeout: Timeout in seconds
        """
        self.execute(ClearGeneralFlagsRequest(general_id=general), timeout=timeout)

    def get_generals_hub(self, *, timeout: float = 5.0) -> list[GeneralsHubCharacterStatus]:
        """
        The generals hub's characters: their free spins, and when the next free spin comes.

        Args:
            timeout: Timeout in seconds

        Returns:
            Each character, from the ``gcs`` reply

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        response = self.request(GetGeneralsHubRequest(), GetGeneralsHubResponse, timeout=timeout)
        return [self._with_cooldown(character) for character in response.characters]

    def spin_generals_hub(
        self,
        character: GeneralsHubCharacter,
        offering: Currency,
        *,
        free: bool = False,
        amount: int = 1,
        timeout: float = 5.0,
    ) -> SpinGeneralsHubResponse:
        """
        Spin a hub character's tombola with an offering, free or paid.

        ``offering`` must be one the character takes (``GeneralsHubCharacterDef.offering_currency_ids``).
        A free spin is one spin; a paid one spends ``amount`` offerings, which must be held
        (:attr:`PlayerService.currencies`). Whether a free spin waits is not checked here
        (:meth:`get_generals_hub` says); the server refuses one that does not. Reward ids in the reply are
        resolved through the game data.

        Client: ``GeneralsHubQuestComponent.onFreeQuest`` and ``onPaidQuest`` (bundle lines 75148-75149),
        ``GeneralsHubRewardsComponent.onClick`` (bundle line 74904) and ``onCurrenciesUpdated`` (bundle line
        74903), which caps the amount at the offerings held

        Args:
            character: The character
            offering: The offering to spin with
            free: Take a free spin
            amount: Offerings to spend on a paid spin
            timeout: Timeout in seconds

        Returns:
            The draws, and the character's spins after it

        Raises:
            ValueError: The game data lacks the character, it takes no such offering, a free spin is asked for
                more than one, or fewer offerings are held than spent
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        game_data = self._require_game_data()
        character_def = game_data.generals_hub_characters.get(character)
        if character_def is None:
            raise ValueError(f"generals hub character {character} is not in the game data")
        if offering.currency_id not in character_def.offering_currency_ids:
            raise ValueError(f"{offering.name} is no offering to character {character}")
        if free and amount != 1:
            raise ValueError("a free spin is one spin")
        if not free and not 0 < amount <= self._held(offering.currency_id):
            raise ValueError(f"spending {amount} {offering.name}; you hold {self._held(offering.currency_id)}")
        request = SpinGeneralsHubRequest(
            character_id=character, offering_id=offering.currency_id, free=free, amount=amount
        )
        response = self.request(request, SpinGeneralsHubResponse, timeout=timeout)
        rewards = [
            reward.model_copy(update={"rewards": game_data.reward_list(reward.reward_ids)})
            if reward.reward_ids and not reward.rewards
            else reward
            for reward in response.rewards
        ]
        return response.model_copy(update={"character": self._with_cooldown(response.character), "rewards": rewards})

    def _with_cooldown(self, character: GeneralsHubCharacterStatus) -> GeneralsHubCharacterStatus:
        # GeneralsHubQuestVO.parseServerObject (bundle line 47009): LFO plus the character's coolDownInSeconds
        character_def = self._require_game_data().generals_hub_characters.get(character.character_id)
        if character_def is None:
            return character
        return character.model_copy(
            update={"cooldown_ends_at": character.last_free_spin + character_def.cooldown_seconds}
        )

    def _held(self, currency_id: int) -> int:
        return next(
            (
                amount
                for currency, amount in self.client.player.currencies.items()
                if getattr(currency, "currency_id", None) == currency_id
            ),
            0,
        )
