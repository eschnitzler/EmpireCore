"""Commanders and castellans, their generals, and their equipment.

- CommandersService reads and renames the player's commanders and castellans, says
  whether the premium commander leads for free, and changes generals: assigning one
  to a commander, choosing its abilities, unlocking and resetting its skills,
  feeding it xp items, unlocking it and raising its stars with shards, and spinning
  the generals hub for them. A general's skills widen the flanks whatever the target is.
- EquipmentService reads the equipment inventory, moves items on and off
  commanders and castellans, sells items and gems, sets gems in worn items and takes
  them out, crafts and enchants items, relics and gems, and reads and sets the
  auto-sell rules.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, TypeVar

from empire_core.commanders.models.auto_sell import (
    AUTO_SELL_RARENESSES,
    AUTO_SELL_SLOTS,
    MAX_GEM_LEVEL,
    AutoSellRules,
    GetAutoSellRequest,
    GetAutoSellResponse,
    SetAutoSellEquipmentRequest,
    SetAutoSellGemsRequest,
)
from empire_core.commanders.models.crafting import (
    CraftEquipmentRequest,
    CraftEquipmentResponse,
    CraftGemRequest,
    CraftGemResponse,
    EnchantEquipmentRequest,
    EnchantEquipmentResponse,
    EnchantRelicRequest,
    EnchantRelicResponse,
    ExtractGemRequest,
    ExtractGemResponse,
    GetNewRelicsRequest,
    NewRelicItemsResponse,
)
from empire_core.commanders.models.equipment import (
    BindGemRequest,
    EquipEquipmentRequest,
    Equipment,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
    RelicGem,
    SellEquipmentRequest,
    SellGemRequest,
)
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
from empire_core.commanders.models.inventory import (
    GemInventoryResponse,
    GemStack,
    GetGemsRequest,
    GetInventorySpaceRequest,
    InventorySpace,
)
from empire_core.commanders.models.roster import (
    PREMIUM_COMMANDER_ID,
    Castellan,
    Commander,
    CommanderRoster,
    GetCommandersRequest,
    GetCommandersResponse,
    RenameCommanderRequest,
    RenameCommanderResponse,
    SelectedAbility,
)
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
from empire_core.exceptions import PacketError, PremiumCommanderCostError
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.commanders.models.inventory import NewRelicsResponse
    from empire_core.gamedata import Currency, Gem, General, GeneralsHubCharacter

_Sent = TypeVar("_Sent")


class CommandersService(BaseService):
    """
    Your commanders and castellans, renaming them, and their generals.

    Reached as client.commanders.
    """

    @property
    def roster(self) -> CommanderRoster:
        """Your commanders and castellans as the last ``gli`` listed them.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_commanders()

    def get_all(self, *, timeout: float = 5.0) -> GetCommandersResponse:
        """
        Get commanders and castellans in one request.

        Args:
            timeout: Timeout in seconds

        Returns:
            The full gli response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetCommandersRequest(), GetCommandersResponse, timeout=timeout)

    def get_commanders(self, *, timeout: float = 5.0) -> list[Commander]:
        """
        Get every commander, whether or not it leads an army now.

        Args:
            timeout: Timeout in seconds

        Returns:
            List of Commander objects

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.get_all(timeout=timeout).commanders

    def get_castellans(self, *, timeout: float = 5.0) -> list[Castellan]:
        """
        Get all available castellans.

        Args:
            timeout: Timeout in seconds

        Returns:
            List of Castellan objects

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.get_all(timeout=timeout).castellans

    @property
    def travelling_commanders(self) -> list[Commander]:
        """
        The commanders leading one of your movements in state, returning ones included; nothing is sent.

        Only as fresh as the movements in state.

        Raises:
            StateNotLoadedError: No login has brought the roster

        Client: ``LordVO.isAvailableForMovement`` (bundle line 26607), false while any map movement
        that ``isMyMovement`` (``BasicMapmovementVO``, bundle line 19436) has the lord as its ``lordVO``,
        whichever way it travels
        """
        movements = self.client.state.get_all_movements()
        leading = {m.commander.commander_id for m in movements if m.is_mine and m.commander is not None}
        return [c for c in self.roster.commanders if c.commander_id in leading]

    @property
    def idle_commanders(self) -> list[Commander]:
        """
        The commanders free to lead an army: those not in :attr:`travelling_commanders`; nothing is sent.

        Raises:
            StateNotLoadedError: No login has brought the roster
        """
        away = {c.commander_id for c in self.travelling_commanders}
        return [c for c in self.roster.commanders if c.commander_id not in away]

    def rename(self, commander_id: int, name: str, *, timeout: float = 5.0) -> CommanderRoster:
        """
        Rename a commander or castellan.

        Args:
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            name: The new name; the game's dialog allows 3 to 15 characters
            timeout: Timeout in seconds

        Returns:
            Your commanders and castellans after the rename, from the ``arl`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        request = RenameCommanderRequest(commander_id=commander_id, name=name)
        return self.request(request, RenameCommanderResponse, timeout=timeout).commander_roster

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

    def assign_general(self, commander_id: int, general_id: int, *, timeout: float = 5.0) -> CommanderRoster:
        """
        Assign a general to a commander; ``general_id=-1`` takes its general away.

        Args:
            commander_id: A ``Commander.commander_id`` from
                ``client.commanders.get_commanders()``
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            timeout: Timeout in seconds

        Returns:
            Your commanders and castellans after the change, from the ``gla`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        request = AssignGeneralRequest(commander_id=commander_id, general_id=general_id)
        return self.request(request, AssignGeneralResponse, timeout=timeout).commander_roster

    def set_general_abilities(
        self, general_id: int, abilities: Iterable[tuple[int, int | None]], *, timeout: float = 5.0
    ) -> None:
        """
        Choose a general's abilities.

        Args:
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            abilities: ``(slot_id, ability_id)`` pairs, ``-1`` or ``None`` to clear a slot.
                The client sends every slot it shows. An ability id comes from
                ``GameData.require().general_ability(name, level)``
            timeout: Timeout in seconds
        """
        slots = [SelectedAbility(slot_id=slot_id, ability_id=ability_id) for slot_id, ability_id in abilities]
        self.execute(SetGeneralAbilitiesRequest(general_id=general_id, abilities=slots), timeout=timeout)

    def unlock_general_skill(self, skill_id: int, *, timeout: float = 5.0) -> None:
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

    def reset_general_skills(self, general_id: int, *, timeout: float = 5.0) -> None:
        """
        Reset a general's skill tree.

        Args:
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            timeout: Timeout in seconds
        """
        self.execute(ResetGeneralSkillsRequest(general_id=general_id), timeout=timeout)

    def add_general_xp(self, general_id: int, currency_id: int, amount: int, *, timeout: float = 5.0) -> None:
        """
        Feed a general xp items.

        Args:
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            currency_id: The xp item's ``currencyID``, e.g.
                ``GameData.require().currency("GXP1").currency_id``
                (``GeneralsLevelUpDialogListItem.sendXPSelected``, bundle line 74485)
            amount: How many of the item to use
            timeout: Timeout in seconds
        """
        self.execute(
            AddGeneralXpRequest(general_id=general_id, currency_id=currency_id, amount=amount), timeout=timeout
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

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self._premium_send_lock = threading.Lock()
        # Premium sends this client made since the vip stamped at that time: (vip stamp, count)
        self._own_premium_sends: tuple[float | None, int] = (None, 0)

    def free_premium_commanders(self, now: float | None = None) -> int | None:
        """
        How many more times today the premium commander (``PREMIUM_COMMANDER_ID``) can lead for free.

        Your VIP level's ``free_premium_commanders_per_day`` less those used today, and 0
        while no VIP time runs. It comes from state, kept current by the login data's
        ``vip`` and every ``vip`` the server pushes. A premium send this client made
        (:meth:`premium_send`) counts as used until the next ``vip`` arrives.
        A premium account makes the premium commander free on top of this:
        :meth:`premium_commander_is_free` counts both.

        Example:
            if client.commanders.premium_commander_is_free():
                client.movements.send_support(..., commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

        Args:
            now: Wall-clock time to measure the VIP time left at, ``time.time()`` when not given

        Returns:
            The count, 0 at least, or None before the login data brought your VIP

        Raises:
            GameDataNotLoadedError: VIP time runs and the game data cannot be loaded

        Client: ``CastleVIPData.remainingPremiumCommanders`` (bundle line 47554), the
        ``freePremiumCommandersPerDay`` of ``currentActiveVIPLevel`` (bundle line 47546), which
        is a level with none unless ``vipModeActive`` (bundle line 47550); ``parse_VIP``
        (bundle line 47527) reads ``UPG``, from ``GBDCommand`` (bundle line 129381),
        ``VIPCommand`` (bundle line 129941) and ``SBPCommand`` (bundle line 128320)
        """
        state = self.client.state
        player = state.get_local_player()
        received_at = state.get_last_packet_time("vip")
        if received_at is None:
            return None
        elapsed = (time.time() if now is None else now) - received_at
        if player.vip_time_left - elapsed <= 0:
            return 0
        game_data = self._require_game_data()
        level = game_data.vip_level(player.vip_points)
        per_day = level.free_premium_commanders_per_day if level is not None else 0
        counted_at, own_sends = self._own_premium_sends
        used = player.used_premium_commanders + (own_sends if counted_at == received_at else 0)
        return max(0, per_day - used)

    def premium_commander_is_free(self) -> bool:
        """
        Whether leading with the premium commander now costs no rubies: a premium account
        runs, or :meth:`free_premium_commanders` is 1 or more.

        False when neither is known yet.

        Raises:
            GameDataNotLoadedError: No premium account runs, VIP time does, and the game data cannot be loaded

        Client: ``CastlePostAttackDialog.startAttack`` (bundle line 38360), which sends with a
        free premium commander left and otherwise asks for
        ``getFinalCostsC2(TravelConst.TRAVEL_PREMIUM_COMMANDER_COSTS_C2)`` rubies, 0 while
        ``premiumAccountVO.isActive``; ``TRAVEL_PREMIUM_COMMANDER_COSTS_C2`` is 125 (dll line 19872)
        """
        return self._premium_account_runs() or (self.free_premium_commanders() or 0) >= 1

    def premium_send(
        self, commander_id: int, use_premium_commander: bool, send: Callable[[], _Sent], *, spend_rubies: bool = False
    ) -> _Sent:
        """
        Run ``send`` and return what it returns, refusing it first when the premium commander leads and may cost
        rubies, unless ``spend_rubies``.

        The army sends go through this: ``client.movements.send_support``,
        ``client.movements.send_troops``, ``client.attack.send_attack`` and
        ``client.attack.send_treasure_hunt_attack``. The premium commander
        leads when ``use_premium_commander`` is set or ``commander_id`` is ``PREMIUM_COMMANDER_ID``;
        the client always sends the two together.

        Library policy, not client behaviour: the server sends no ``vip`` with the send's
        reply (``CRACommand``, bundle line 125954; ``CDSCommand``, bundle line 125939; ``CATCommand``,
        bundle line 125924), so a
        premium send that the server accepts while no premium account runs counts as one
        used in :meth:`free_premium_commanders` until the next ``vip`` arrives. The check and the
        send hold one lock, so two premium sends at once cannot both take the last free one.

        Args:
            commander_id: The leader's ``commander_id``
            use_premium_commander: The send's ``BPC`` flag
            send: Sends the request and raises when the server refuses it
            spend_rubies: Send even when the premium commander may cost rubies

        Raises:
            PremiumCommanderCostError: The premium commander leads, :meth:`premium_commander_is_free`
                is False and ``spend_rubies`` is False
            GameDataNotLoadedError: See :meth:`premium_commander_is_free`

        Client: ``CastlePostAttackDialog.startAttack`` (bundle line 38360) sends ``BPC`` 1
        exactly when the selected commander is ``TravelConst.COMMANDER_PREMIUM``
        """
        if not (use_premium_commander or commander_id == PREMIUM_COMMANDER_ID):
            return send()
        with self._premium_send_lock:
            premium_account = self._premium_account_runs()
            if not (spend_rubies or premium_account or (self.free_premium_commanders() or 0) >= 1):
                raise PremiumCommanderCostError(self.free_premium_commanders())
            vip_at = self.client.state.get_last_packet_time("vip")
            sent = send()
            if not premium_account:
                counted_at, own_sends = self._own_premium_sends
                self._own_premium_sends = (vip_at, own_sends + 1 if counted_at == vip_at else 1)
            return sent

    def _premium_account_runs(self) -> bool:
        return self.client.state.get_boosts().is_premium_active()


class EquipmentService(BaseService):
    """
    The equipment inventory: putting items on and off commanders and castellans, selling items and gems,
    setting gems and taking them out, crafting and enchanting, and the auto-sell rules.

    Reached as client.equipment. What a leader
    wears comes with ``client.commanders`` (``gli`` ``EQ``).
    """

    @property
    def gems(self) -> GemInventoryResponse | None:
        """The gems and relic gems in your inventory; None until a ``ggm`` or ``gec`` arrived."""
        return self.client.state.get_gems()

    @property
    def inventory_space(self) -> InventorySpace | None:
        """The equipment and gem inventory space, from the last ``esl``; None until one arrived."""
        return self.client.state.get_inventory_space()

    @property
    def new_relics(self) -> NewRelicsResponse:
        """Whether new relics wait to be seen, from the last ``nrf``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_new_relics()

    def get_inventory(self, *, timeout: float = 5.0) -> list[Equipment]:
        """
        The items in the player's inventory, the ones no leader wears.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetEquipmentInventoryRequest(), GetEquipmentInventoryResponse, timeout=timeout).items

    def equip(self, equipment_id: int, commander_id: int, *, timeout: float = 5.0) -> None:
        """
        Put an item on a commander or castellan.

        The client moves an item between leaders by taking it off the first
        and then putting it on the second. The reply carries no data; re-read
        ``client.commanders.get_all()`` to see the change.

        Args:
            equipment_id: An item in the inventory, its ``Equipment.equipment_id``
                from :meth:`get_inventory`
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds
        """
        request = EquipEquipmentRequest(equipment_id=equipment_id, commander_id=commander_id, equip=1)
        self.execute(request, timeout=timeout)

    def unequip(self, equipment_id: int, commander_id: int, *, timeout: float = 5.0) -> None:
        """
        Take an item off a commander or castellan.

        Args:
            equipment_id: An item the leader wears, the ``Equipment.equipment_id`` of an
                entry in its ``equipment`` list from ``client.commanders.get_all()``
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds
        """
        request = EquipEquipmentRequest(equipment_id=equipment_id, commander_id=commander_id, equip=0)
        self.execute(request, timeout=timeout)

    def sell_equipment(self, equipment_id: int, *, commander_id: int | None = None, timeout: float = 5.0) -> None:
        """
        Sell an item for coins.

        The reply's commanders, coins and inventory space reach ``client.state``.

        Args:
            equipment_id: An item in the inventory, its ``Equipment.equipment_id`` from :meth:`get_inventory`
            commander_id: The commander wearing a relic sold straight off it, as the relic enchanter sells
                one (``RelicUpgradeDialogStatus.confirmSellCallback``, bundle line 36757); None for an
                inventory item
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        request = SellEquipmentRequest(
            equipment_id=equipment_id, commander_id=-1 if commander_id is None else commander_id
        )
        self.execute(request, timeout=timeout)

    def sell_gem(self, gem: Gem | GemStack | RelicGem, *, timeout: float = 5.0) -> None:
        """
        Sell a gem, or a relic gem, for coins.

        Args:
            gem: A gem, a ``GemStack`` or ``RelicGem`` of :attr:`gems`
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        gem_id, relic = self._gem(gem)
        self.execute(SellGemRequest(gem_id=gem_id, relic_gem=relic), timeout=timeout)

    def bind_gem(
        self, gem: Gem | GemStack | RelicGem, equipment_id: int, commander_id: int, *, timeout: float = 5.0
    ) -> None:
        """
        Set a gem in an item a commander or castellan wears.

        A gem already set in the item is not taken back: the client shows it broken
        (``CastleReplaceSocketDialog.renderIcons``, bundle line 42224). Taking it back costs rubies or
        relic fragments and is not offered here. Setting a gem costs coins: the gem level's
        ``insertCostC1``, or ``RelicItemConst.INSERT_RELIC_GEM_C1_COST`` (95000, dll line 19669) for a
        relic gem (``ACastleSocketDialog.getCosts``, bundle line 32488).

        Args:
            gem: A gem, a ``GemStack`` or ``RelicGem`` of :attr:`gems`
            equipment_id: The worn item's ``Equipment.equipment_id``, from ``client.commanders.get_all()``
            commander_id: The ``commander_id`` of the commander or castellan wearing it; the client sets gems
                only in a worn item (``EquipmentGemClickHandler.addGemToEquipment``, bundle line 73572)
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        gem_id, relic = self._gem(gem)
        request = BindGemRequest(gem_id=gem_id, equipment_id=equipment_id, commander_id=commander_id, relic_gem=relic)
        self.execute(request, timeout=timeout)

    def get_auto_sell(self, *, timeout: float = 5.0) -> AutoSellRules:
        """
        The auto-sell rules: which new equipment and gems the server sells as they drop.

        The client asks for them only while the auto-sell subscription effect runs.

        Args:
            timeout: Timeout in seconds

        Returns:
            The rules, from the ``asg`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        response = self.request(GetAutoSellRequest(), GetAutoSellResponse, timeout=timeout)
        return AutoSellRules(equipment=response.equipment, gems=response.gems)

    def set_auto_sell(self, rules: AutoSellRules, *, timeout: float = 5.0) -> None:
        """
        Replace the auto-sell rules, the equipment ones and then the gem ones, as the client saves them.

        Every gem colour is sent, 0 for one ``rules.gems`` leaves out.

        Client: ``AutoSellVO.sendConfigToServer`` (bundle line 120132)

        Args:
            rules: The rules; the equipment from ``AUTO_SELL_SLOTS`` and ``AUTO_SELL_RARENESSES``,
                gem levels 0 to ``MAX_GEM_LEVEL``
            timeout: Timeout in seconds

        Raises:
            ValueError: A rule the auto-sell dialog cannot set, or a gem colour the game data lacks
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        for rule in rules.equipment:
            if rule.slot not in AUTO_SELL_SLOTS or rule.rareness not in AUTO_SELL_RARENESSES:
                raise ValueError(f"the auto-sell dialog has no box for {rule.slot!r} at {rule.rareness!r}")
        colors = self._require_game_data().gem_colors
        for color, level in rules.gems.items():
            if color not in colors:
                raise ValueError(f"gem colour {color} is not in the game data")
            if not 0 <= level <= MAX_GEM_LEVEL:
                raise ValueError(f"gem level {level} is outside 0 to {MAX_GEM_LEVEL}")
        gems = {color: rules.gems.get(color, 0) for color in colors}
        self.execute(SetAutoSellEquipmentRequest(equipment=rules.equipment), timeout=timeout)
        self.execute(SetAutoSellGemsRequest(gems=gems), timeout=timeout)

    def get_gems(self, *, timeout: float = 5.0) -> GemInventoryResponse:
        """
        The gems and relic gems in your inventory; the reply also reaches :attr:`gems`.

        Client: ``CastleEquipmentSublayer.updateEquipmentData`` (bundle line 25717)
        """
        return self.request(GetGemsRequest(), GemInventoryResponse, timeout=timeout)

    def get_inventory_space(self, *, timeout: float = 5.0) -> InventorySpace:
        """
        The equipment and gem inventory space; the reply also reaches :attr:`inventory_space`.

        Raises:
            PacketError: The reply could not be read

        Client: ``AMerchantBuyDialog.onInventorySpaceData`` (bundle line 41333), ``ESLCommand`` (bundle line 123933)
        """
        self.execute(GetInventorySpaceRequest(), timeout=timeout)
        space = self.client.state.get_inventory_space()
        if space is None:
            raise PacketError("The esl reply could not be read")
        return space

    def get_new_relics(self, *, timeout: float = 5.0) -> NewRelicItemsResponse:
        """
        The relic items and relic gems you have not seen yet.

        Client: the equipment dialog's ``showLoaded`` (bundle line 8801)
        """
        return self.request(GetNewRelicsRequest(), NewRelicItemsResponse, timeout=timeout)

    def craft_equipment(
        self,
        equipment_ids: Sequence[int],
        *,
        extract_gems: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> Equipment:
        """
        Craft a new item from inventory items. The items are used up, and so are their gems unless
        ``extract_gems`` takes them back first.

        Taking a gem back costs its level's rubies, a relic gem relic fragments, so ``extract_gems``
        needs ``spend_rubies``. The reply's inventory space reaches :attr:`inventory_space`.

        Args:
            equipment_ids: The inventory items used up, their ``Equipment.equipment_id``
            extract_gems: Take the items' gems back into the inventory first
            spend_rubies: Allow the rubies ``extract_gems`` costs
            timeout: Timeout in seconds

        Returns:
            The crafted item

        Raises:
            ValueError: ``extract_gems`` without ``spend_rubies``
            CommandError: The server refused

        Client: ``CraftingEquipmentClickHandler.onClick`` and ``extractGems`` (bundle lines 74125, 74129),
        ``CastleExtractGemsDialog.calculateRemovalCostsForGems`` (bundle line 74260)
        """
        self._require_spend_rubies(spend_rubies, "taking the items' gems back costs rubies" if extract_gems else None)
        request = CraftEquipmentRequest(extract_gems=extract_gems, equipment_ids=tuple(equipment_ids))
        return self.request(request, CraftEquipmentResponse, timeout=timeout).equipment

    def enchant_equipment(
        self, equipment_id: int, *, pay_with_rubies: bool = False, spend_rubies: bool = False, timeout: float = 5.0
    ) -> Equipment:
        """
        Enchant an item one level, for coins or, with ``pay_with_rubies``, rubies.

        Returns:
            The item after

        Raises:
            ValueError: ``pay_with_rubies`` without ``spend_rubies``
            CommandError: The server refused; ``ENCHANTING_FAILED`` when the enchantment's chance failed

        Client: the enchant dialog's pay buttons (bundle lines 59446-59448), ``EQECommand`` (bundle line 123900)
        """
        self._require_spend_rubies(spend_rubies, "the ruby enchantment costs rubies" if pay_with_rubies else None)
        request = EnchantEquipmentRequest(pay_with_rubies=pay_with_rubies, equipment_id=equipment_id)
        return self.request(request, EnchantEquipmentResponse, timeout=timeout).equipment

    def enchant_relic(
        self,
        relic: Equipment | RelicGem,
        *,
        pay_with_rubies: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> Equipment | RelicGem:
        """
        Enchant a relic item or relic gem one level, for relic fragments and coins or, with
        ``pay_with_rubies``, rubies.

        Args:
            relic: A relic item (``Equipment.is_relic``), or a relic gem, one set in an item too
            pay_with_rubies: Pay in rubies instead of coins
            spend_rubies: Allow those rubies
            timeout: Timeout in seconds

        Returns:
            The relic item or relic gem after

        Raises:
            ValueError: ``relic`` is an item that is no relic, or ``pay_with_rubies`` without ``spend_rubies``
            CommandError: The server refused; ``ENCHANTING_FAILED`` when the enchantment's chance failed
            PacketError: The reply carries no relic

        Client: ``RelicUpgradeDialog.onBuyButtonClicked`` (bundle line 29490),
        ``RelicUpgradeDialogPayment.getCosts`` (bundle line 86002)
        """
        is_equipment = isinstance(relic, Equipment)
        if isinstance(relic, Equipment) and not relic.is_relic:
            raise ValueError(f"item {relic.equipment_id} is no relic")
        self._require_spend_rubies(spend_rubies, "the ruby enchantment costs rubies" if pay_with_rubies else None)
        request = EnchantRelicRequest(
            pay_with_rubies=pay_with_rubies,
            relic_id=relic.equipment_id if isinstance(relic, Equipment) else relic.gem_id,
            is_equipment=is_equipment,
        )
        response = self.request(request, EnchantRelicResponse, timeout=timeout)
        upgraded = response.equipment if is_equipment else response.relic_gem
        if upgraded is None:
            raise PacketError("The ere reply carries no relic")
        return upgraded

    def craft_gem(
        self,
        gem: Gem | GemStack,
        used_gems: Sequence[Gem | GemStack],
        *,
        pay_with_rubies: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> CraftGemResponse:
        """
        Craft a gem a level up from a gem and gems around it. The gems around it are used up.

        The craft can fail; its reply says whether it worked (``CraftGemResponse.crafted``). The ruby craft,
        ``pay_with_rubies``, needs ``spend_rubies``. The reply's inventory space reaches :attr:`inventory_space`.

        Args:
            gem: The centre gem, crafted a level up
            used_gems: The gems in the outer slots, used up
            pay_with_rubies: The ruby craft
            spend_rubies: Allow its rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: ``pay_with_rubies`` without ``spend_rubies``
            CommandError: The server refused

        Client: ``CastleGemData.craftGem`` (bundle line 144476), ``CraftingGemClickHandler.handleDialogClick``
        (bundle lines 73941-73943)
        """
        self._require_spend_rubies(spend_rubies, "the ruby gem craft costs rubies" if pay_with_rubies else None)
        request = CraftGemRequest(
            gem_id=self._gem(gem)[0],
            pay_with_rubies=pay_with_rubies,
            used_gem_ids=tuple(self._gem(used)[0] for used in used_gems),
        )
        return self.request(request, CraftGemResponse, timeout=timeout)

    def extract_gem(
        self,
        equipment: Equipment,
        *,
        commander_id: int | None = None,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Take the gem out of an item, back into the inventory.

        A gem costs its level's rubies, so it needs ``spend_rubies``; a relic gem costs relic fragments.

        Args:
            equipment: An inventory item, or one a commander wears, with a gem
            commander_id: The commander or castellan wearing it; None for an inventory item
            spend_rubies: Allow the rubies a gem costs
            timeout: Timeout in seconds

        Raises:
            ValueError: The item has no gem, or a gem without ``spend_rubies``
            CommandError: The server refused

        Client: ``CastleGemData.extractGem`` (bundle line 144483), ``CastleExtractSocketDialog.getCosts``
        (bundle line 65738)
        """
        relic_gem = equipment.relic_info.gem if equipment.relic_info is not None else None
        if relic_gem is None and not equipment.has_gem:
            raise ValueError(f"item {equipment.equipment_id} has no gem")
        self._require_spend_rubies(spend_rubies, "taking a gem out costs rubies" if relic_gem is None else None)
        request = ExtractGemRequest(
            equipment_id=equipment.equipment_id, commander_id=-1 if commander_id is None else commander_id
        )
        self.request(request, ExtractGemResponse, timeout=timeout)

    @staticmethod
    def _gem(gem: Gem | GemStack | RelicGem) -> tuple[int, bool]:
        """The gem id the client sends for ``gem``, and whether it is a relic gem."""
        if isinstance(gem, RelicGem):
            return gem.gem_id, True
        return (gem.gem_id if isinstance(gem, GemStack) else int(gem)), False
