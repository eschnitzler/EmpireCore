"""Equipment, gems and relics: the inventory, crafting, enchanting and selling."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

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
from empire_core.commanders.models.inventory import (
    GemInventoryResponse,
    GemStack,
    GetGemsRequest,
    GetInventorySpaceRequest,
    InventorySpace,
)
from empire_core.exceptions import PacketError
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.commanders.models.inventory import NewRelicsResponse
    from empire_core.gamedata import Gem


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
