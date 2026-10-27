"""Attack presets, the attack advisor and tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.army.models.units import AttackWave
from empire_core.attack.models.advisor import (
    ActivateAttackAdvisorRequest,
    ActivateAttackAdvisorResponse,
    AttackAdvisorOverviewRequest,
    AttackAdvisorOverviewResponse,
)
from empire_core.attack.models.presets import (
    PRESET_NAME_MAX_LENGTH,
    AttackPreset,
    GetPresetsRequest,
    GetPresetsResponse,
    PresetArmy,
    RenamePresetRequest,
    SavePresetRequest,
    UnlockPresetRequest,
)
from empire_core.attack.models.tools import NO_PACKAGE, BoughtTools, BuyToolsRequest, BuyToolsResponse
from empire_core.enums import AttackAdvisorType
from empire_core.exceptions import PacketError
from empire_core.gamedata import PackageId
from empire_core.map.models.treasure_maps import NO_TREASURE_MAP
from empire_core.protocol.text import SMARTFOX_INVALID_CHARS, is_smartfox_valid
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import Tool, TreasureMapId


class PresetsMixin(ServiceMixin):
    # =========================================================================
    # Presets
    # =========================================================================

    def get_presets(self, *, timeout: float = 5.0) -> list[AttackPreset]:
        """
        Get your unlocked attack preset slots.

        Example:
            for preset in client.attack.get_presets():
                army = preset.army()
                print(preset.index, preset.name, army.to_wave() if army else None)

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SGetPreDefinedAttackSetupVO`` (bundle line 141803), sent by
        ``FightPresetData.loadDataFromServer`` (bundle line 141779)
        """
        return self.request(GetPresetsRequest(), GetPresetsResponse, timeout=timeout).presets

    def save_preset(self, index: int, army: PresetArmy | AttackWave, *, timeout: float = 5.0) -> None:
        """
        Save an army into an unlocked preset slot.

        A wave is saved as the client saves one: its filled slots, without
        support tools.

        Args:
            index: The preset slot, an ``AttackPreset.index`` from :meth:`get_presets`
            army: The army, a ``PresetArmy`` or a wave
            timeout: Timeout in seconds

        Client: ``C2SUpdatePreDefinedAttackSetupVO`` (bundle line 141820), sent by
        ``FightPresetData.savePresetArmy`` (bundle line 141780) from
        ``AttackDialogPresets.handleSavePresetRequested`` (bundle line 101661), which
        saves only an unlocked slot
        """
        preset = army if isinstance(army, PresetArmy) else PresetArmy.from_wave(army)
        self.execute(SavePresetRequest.create(index, preset), timeout=timeout)

    def rename_preset(self, index: int, name: str, *, timeout: float = 5.0) -> None:
        """
        Rename a preset slot.

        Args:
            index: The preset slot, an ``AttackPreset.index`` from :meth:`get_presets`
            name: The new name, at most 15 characters, none of ``SMARTFOX_INVALID_CHARS``
            timeout: Timeout in seconds

        Raises:
            ValueError: The client's rename dialog would refuse the name

        Client: ``C2SUpdatePresetNameVO`` (bundle line 141794), sent by
        ``RenameFightPresetDialog.sendCommand`` (bundle line 45609) after its
        ``validate`` (bundle line 45606) and its 15-character limit (bundle line 45597)
        """
        if len(name) > PRESET_NAME_MAX_LENGTH or not is_smartfox_valid(name):
            raise ValueError(
                f"Preset names are 1 to {PRESET_NAME_MAX_LENGTH} characters without any of "
                f"{''.join(SMARTFOX_INVALID_CHARS)}, got {name!r}"
            )
        self.execute(RenamePresetRequest(index=index, name=name), timeout=timeout)

    def unlock_preset(self, index: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Unlock an attack preset slot, paying its price from the game data.

        Slots unlock in order: the client marks its first locked slot unlocked whatever ``index`` was.

        Args:
            index: The slot to unlock, the next after the ``AttackPreset.index`` values :meth:`get_presets` returns
            spend_rubies: Allow the rubies the slot costs
            timeout: Timeout in seconds

        Raises:
            ValueError: The slot costs rubies, or is not in the game data, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``FightPresetData.unlockPreset`` (bundle line 141889) after ``CastleConfirmCostsDialog``
        (bundle line 101700) shows the slot's price; ``UASCommand`` (bundle line 122134)
        """
        if not spend_rubies:
            slot = self._require_game_data().attack_slots.get(index)
            if slot is None:
                self._require_spend_rubies(
                    spend_rubies, f"preset slot {index} is not in the game data and may cost rubies"
                )
            elif slot.cost_rubies > 0:
                self._require_spend_rubies(spend_rubies, f"preset slot {index} costs {slot.cost_rubies} rubies")
        self.execute(UnlockPresetRequest(index=index), timeout=timeout)

    # =========================================================================
    # Attack advisor
    # =========================================================================

    def activate_attack_advisor(
        self, advisor: AttackAdvisorType, *, timeout: float = 5.0
    ) -> ActivateAttackAdvisorResponse:
        """
        Activate an attack advisor, using one of the activation tokens you hold for it.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``AdvisorAttackActivationComponent.onClick`` (bundle line 56251); ``AACommand``
        (bundle line 121193)
        """
        return self.request(
            ActivateAttackAdvisorRequest(advisor=advisor), ActivateAttackAdvisorResponse, timeout=timeout
        )

    def get_attack_advisor_overview(
        self, advisor: AttackAdvisorType, *, timeout: float = 5.0
    ) -> AttackAdvisorOverviewResponse:
        """
        What an attack advisor's attacks won and cost.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SAdvisorAttackOverviewVO`` (bundle line 105059); ``AAOCommand`` (bundle line 121210)
        """
        return self.request(
            AttackAdvisorOverviewRequest(advisor=advisor), AttackAdvisorOverviewResponse, timeout=timeout
        )

    # =========================================================================
    # Tools
    # =========================================================================

    def buy_tools(
        self,
        castle_id: int,
        tool: Tool | int,
        amount: int,
        *,
        map_id: TreasureMapId | int = NO_TREASURE_MAP,
        package_id: PackageId = NO_PACKAGE,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> BoughtTools:
        """
        Buy tools into one of your castles for rubies, as the attack and defence screens do.

        Args:
            castle_id: The castle the tools go to
            tool: The tool
            amount: How many
            map_id: The treasure map, when the attack starts from an event camp
            package_id: The event package whose price applies
            spend_rubies: Allow the rubies they cost
            timeout: Timeout in seconds

        Returns:
            The tools bought; the coins and rubies after also reach the state

        Raises:
            ValueError: ``spend_rubies`` is False
            UnknownCastleError: The castle list has no such castle
            PacketError: The reply names no tools bought
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleDefenceBuyUnitsDialog.onClick`` (bundle line 22500), priced with the tool's ``costC2``
        (bundle line 22493); ``IBTCommand`` (bundle line 123574)
        """
        self._require_spend_rubies(spend_rubies, "instantly bought tools cost rubies")
        castle = self._require_own_castle(castle_id)
        request = BuyToolsRequest(
            tool=tool,
            amount=amount,
            x=castle.x,
            y=castle.y,
            map_id=map_id,
            kingdom=castle.kingdom_id,
            package_id=package_id,
        )
        response = self.request(request, BuyToolsResponse, timeout=timeout)
        if response.bought is None:
            raise PacketError("The 'ibt' reply names no tools bought")
        return response.bought
