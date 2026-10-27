"""Legend skills, opening loot boxes and choosing titles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.commanders.models.skills import (
    AddSkillPointRequest,
    AddSkillPointResponse,
    GetSkillsRequest,
    GetSkillsResponse,
    ResetSkillsRequest,
)
from empire_core.enums import MysteryBoxKey, TitleSystem
from empire_core.player.models.economy import LootBoxKeys, OpenLootBoxRequest, OpenLootBoxResponse
from empire_core.player.models.progress import SelectTitleRequest, SelectTitleResponse
from empire_core.player.service.base import PlayerBaseMixin

if TYPE_CHECKING:
    from empire_core.gamedata import LegendSkill, LootBox

# LegendSkillConst.BASE_COST, EXPONENT, BASE_SKILL_POINTS, POINTS_FACTOR (dll line 19477)
_RESET_BASE_RUBIES = 20
_RESET_EXPONENT = 5
_RESET_BASE_POINTS = 50
_RESET_RUBIES_PER_POINT = 30


class SkillsMixin(PlayerBaseMixin):
    def get_skills(self, *, timeout: float = 5.0) -> GetSkillsResponse:
        """
        The player's legend and sceat skills.

        Args:
            timeout: Timeout in seconds

        Returns:
            The ``skl`` response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetSkillsRequest(), GetSkillsResponse, timeout=timeout)

    def add_legend_skill_point(self, skill: LegendSkill, *, timeout: float = 5.0) -> AddSkillPointResponse:
        """
        Buy a legend skill level with skill points: the next level of a skill you hold, or the first of one you don't.

        The client offers it when the skill is not at its last level, its tier and node are unlocked,
        enough points are left (``SkillList.available_points``) and no sceat skill is being activated;
        the server checks the same. Each level bought replaces the one before it in :attr:`skills`.

        Client: ``CastleLegendSkillItem.onClick`` and ``canBuy`` (bundle lines 35643, 35652),
        ``CastleLegendSkillData.parse_SKP`` (bundle line 112073)

        Args:
            skill: The level to buy, e.g. ``LegendSkill.GATE_REDUCTION_T0_G1_L2`` when holding level 1
            timeout: Timeout in seconds

        Returns:
            The levels bought

        Raises:
            CommandError: The server refused: ``ADD_LEGEND_SKILL_FAILED``,
                ``ADD_LEGEND_SKILL_REQUIRED_SKILL_MISSING``, ``ADD_LEGEND_SKILL_NOT_ENOUGH_SKILL_POINTS`` or
                ``ADD_LEGEND_SKILL_TIER_LOCKED``
            GameDataNotLoadedError: The game data cannot be loaded
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        skills = self._require_game_data().legend_skills
        response = self.request(AddSkillPointRequest(skill=skill), AddSkillPointResponse, timeout=timeout)
        self.client.state.add_legend_skills(
            {bought: row.previous_skill_id if (row := skills.get(bought)) else None for bought in response.skill_ids}
        )
        return response

    def reset_skills(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> GetSkillsResponse:
        """
        Take back every legend skill point, and the sceat skills with them.

        Free once the reset cooldown of 15 days has run out. Inside it the same request skips the
        cooldown for ``20 * resets**5 + (points spent + 50) * 30`` rubies, priced from a fresh skill
        list unless ``spend_rubies`` allows any price.

        Client: ``CastleLegendSkillClassicSublayer.onClick`` (bundle line 78657) opens
        ``CastleLegendSkillCooldownDialog`` inside the cooldown, whose ``skipWithRubies`` sends the
        same request (bundle line 78885); ``LegendSkillConst.resetSkipCostC2`` and
        ``RESET_COOLDOWN_IN_SECONDS`` (dll lines 19474, 19470); ``CastleLegendSkillData.resetSkills``
        (bundle line 112104) then asks for the skill list

        Args:
            spend_rubies: Allow the rubies a reset inside the cooldown costs
            timeout: Timeout in seconds, for each request

        Returns:
            The skill list after the reset, also kept in :attr:`skills`

        Raises:
            ValueError: The cooldown is running and ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        if not spend_rubies:
            skills = self.get_skills(timeout=timeout)
            if skills.seconds_until_reset > 0:
                spent = skills.spent_points(game_data=self._require_game_data())
                rubies = (
                    int(_RESET_BASE_RUBIES * skills.reset_count**_RESET_EXPONENT)
                    + (spent + _RESET_BASE_POINTS) * _RESET_RUBIES_PER_POINT
                )
                self._require_spend_rubies(
                    spend_rubies, f"resetting the skills inside the cooldown costs {rubies} rubies"
                )
        self.execute(ResetSkillsRequest(), timeout=timeout)
        return self.get_skills(timeout=timeout)

    def open_loot_box(
        self,
        loot_box: LootBox,
        key: MysteryBoxKey = MysteryBoxKey.COMMON,
        *,
        open_all: bool = False,
        timeout: float = 5.0,
    ) -> OpenLootBoxResponse:
        """
        Open a loot box, or every box of the kind, with a mystery box key.

        The common key never runs out; a rarer one must be held (:attr:`currencies`) and opens one box
        only. The box type's key progress in :attr:`loot_boxes` is set to the reply's; the box count is
        not lowered, as in the client, and :meth:`get_loot_boxes` reads the new one. Reward ids in the
        reply are resolved through the game data.

        Client: ``RewardHubDialogMysteryBoxItem.fillItem`` (bundle line 92191) enables the single open
        with a held or common key and the open-all with the common key only; ``OLECommand`` (bundle line 124819)

        Args:
            loot_box: The box to open, as :attr:`loot_boxes` lists it
            key: The key to open it with
            open_all: Open every box of the kind; the common key only
            timeout: Timeout in seconds

        Returns:
            What the boxes gave, and the keys won

        Raises:
            ValueError: ``open_all`` with a key other than the common one, or a rarer key not held
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        if key is not MysteryBoxKey.COMMON:
            if open_all:
                raise ValueError("only the common key opens every box of a kind")
            held = (
                amount for currency, amount in self.currencies.items() if getattr(currency, "currency_id", None) == key
            )
            if next(held, 0) <= 0:
                raise ValueError(f"no {key.name} mystery box key is held")
        response = self.request(
            OpenLootBoxRequest(loot_box_id=loot_box, key=key, open_all=open_all), OpenLootBoxResponse, timeout=timeout
        )
        game_data = self._require_game_data()
        if response.reward_ids and not response.rewards:
            response = response.model_copy(update={"rewards": game_data.reward_list(response.reward_ids)})
        box = game_data.loot_boxes.get(response.loot_box_id)
        if box is not None:
            self.client.state.set_loot_box_keys(
                LootBoxKeys(loot_box_type_id=box.loot_box_type_id, keys=response.key_progress)
            )
        return response

    def select_titles(
        self, prefix: TitleSystem, suffix: TitleSystem | None = None, *, timeout: float = 5.0
    ) -> SelectTitleResponse:
        """
        Choose the title systems shown before and after your name.

        The dialog offers a system once you hold one of its titles (``held_titles``). The reply's
        systems replace those of :attr:`title_ranks`.

        Client: ``CastleTitleSelectDialog.confirmSelection`` (bundle line 45050),
        ``CastleTitleData.parseSTE`` (bundle line 21041)

        Args:
            prefix: The system shown before your name
            suffix: The system shown after it; None for none
            timeout: Timeout in seconds

        Returns:
            The systems the server set

        Raises:
            CommandError: The server refused: ``TITLE_NOT_AVAILABLE``, ``TITLE_SYSTEM_NOT_AVAILABLE`` or
                ``TITLE_ON_COOLDOWN``
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        selected = self.request(
            SelectTitleRequest(prefix=prefix, suffix=suffix or ""), SelectTitleResponse, timeout=timeout
        )
        self.client.state.select_title_systems(selected)
        return selected
