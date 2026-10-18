"""The player's commanders and castellans (gli) and legend and sceat skills (skl)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from empire_core.commanders.models.roster import CommanderRoster
from empire_core.commanders.models.skills import SkillList
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_truthy
from empire_core.state.base import StateBase, loaded

if TYPE_CHECKING:
    from empire_core.gamedata import LegendSkill

logger = logging.getLogger(__name__)


class CommanderState(StateBase):
    def _parse_commanders(self, data: dict[str, Any]) -> bool:
        """Apply a ``gli`` section: the whole commander and castellan list; whether it was applied.

        Client: ``CastleLordData.parse_GLI`` (bundle line 38553), which does nothing without a block
        """
        gli = data.get("gli")
        if not isinstance(gli, dict):
            return False
        roster = read_or_none(CommanderRoster.model_validate, gli, warn=logger, what="the commander list")
        if roster is None:
            return False
        self.commanders = roster
        return True

    def _parse_skills(self, data: dict[str, Any]) -> bool:
        """Apply a ``skl`` section: the legend and sceat skills; whether it was applied.

        Client: ``CastleLegendSkillData.parse_SKL`` (bundle line 112051), from ``GBDCommand.exec``
        (bundle line 129381) and ``EGOCommand`` (bundle line 122801) when the section is truthy,
        and from ``SKLCommand`` (bundle line 129742)
        """
        skl = data.get("skl")
        if not (js_truthy(skl) and isinstance(skl, dict)):
            return False
        skills = read_or_none(SkillList.model_validate, skl, warn=logger, what="the skill list")
        if skills is None:
            return False
        self.skills = skills
        return True

    def add_legend_skills(self, bought: Mapping[LegendSkill | int, LegendSkill | int | None]) -> None:
        """Apply the legend skill levels a ``skp`` reply bought, each with the level it replaces.

        ``client.player.add_legend_skill_point`` calls it with the replaced levels from the game data.
        Nothing is applied before a skill list arrived.

        Client: ``CastleLegendSkillData.parse_SKP`` (bundle line 112073)
        """
        with self._lock:
            if self.skills is None:
                return
            held = list(self.skills.legend_skill_ids)
            for skill, previous in bought.items():
                if previous is not None and previous in held:
                    held.remove(previous)
                if skill not in held:
                    held.append(skill)
            self.skills = self.skills.model_copy(update={"legend_skill_ids": tuple(held)})

    def get_commanders(self) -> CommanderRoster:
        """Your commanders and castellans as the last ``gli`` listed them.

        The login gbd brings them, and so does every reply that carries the list (``gli``,
        ``arl``, ``gla``, ``seq``, ``sdi``, ``sti`` and the attack and conquer info replies).
        A copy: changing it changes nothing in state.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.commanders, "Commanders").model_copy(deep=True)

    def get_skills(self) -> SkillList | None:
        """Your legend and sceat skills as the last ``skl`` listed them; None until one arrived.

        The login gbd brings them, and so do a ``skl`` reply or push and an ``ego`` push
        that carries one. A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.skills is None else self.skills.model_copy(deep=True)
