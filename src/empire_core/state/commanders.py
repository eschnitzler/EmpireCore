"""The player's commanders and castellans (gli) and Legendary and sceat skills (skl)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from empire_core.commanders.models.roster import CommanderRoster
from empire_core.commanders.models.skills import SkillList
from empire_core.state.base import StateBase, loaded
from empire_core.state.login_data import LoginDataResponse

if TYPE_CHECKING:
    from empire_core.gamedata import LegendarySkill

logger = logging.getLogger(__name__)


class CommanderState(StateBase):
    def _parse_commanders(self, login: LoginDataResponse) -> bool:
        """Apply a ``gli`` section: the whole commander and castellan list; whether it was applied.

        Client: ``CastleLordData.parse_GLI`` (bundle line 38553), which does nothing without a block
        """
        if login.commanders is None:
            return False
        self.commanders = login.commanders
        return True

    def _parse_skills(self, login: LoginDataResponse) -> bool:
        """Apply a ``skl`` section: the Legendary and sceat skills; whether it was applied.

        Client: ``CastleLegendSkillData.parse_SKL`` (bundle line 112051), from ``GBDCommand.exec``
        (bundle line 129381) and ``EGOCommand`` (bundle line 122801) when the section is truthy,
        and from ``SKLCommand`` (bundle line 129742)
        """
        if login.skills is None:
            return False
        self.skills = login.skills
        return True

    def add_legendary_skills(self, bought: Mapping[LegendarySkill | int, LegendarySkill | int | None]) -> None:
        """Apply the Legendary skill levels a ``skp`` reply bought, each with the level it replaces.

        ``client.player.add_legendary_skill_point`` calls it with the replaced levels from the game data.
        Nothing is applied before a skill list arrived.

        Client: ``CastleLegendSkillData.parse_SKP`` (bundle line 112073)
        """
        with self._lock:
            if self.skills is None:
                return
            held = list(self.skills.legendary_skill_ids)
            for skill, previous in bought.items():
                if previous is not None and previous in held:
                    held.remove(previous)
                if skill not in held:
                    held.append(skill)
            self.skills = self.skills.model_copy(update={"legendary_skill_ids": tuple(held)})

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
        """Your Legendary and sceat skills as the last ``skl`` listed them; None until one arrived.

        The login gbd brings them, and so do a ``skl`` reply or push and an ``ego`` push
        that carries one. A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.skills is None else self.skills.model_copy(deep=True)
