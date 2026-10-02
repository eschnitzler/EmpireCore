"""The player's commanders and castellans (gli) and legend and sceat skills (skl)."""

import logging
from typing import Any

from empire_core.commanders.models.roster import CommanderRoster
from empire_core.commanders.models.skills import SkillList
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_truthy
from empire_core.state.base import StateBase

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

    def get_commanders(self) -> CommanderRoster | None:
        """Your commanders and castellans as the last ``gli`` listed them; None until one arrived.

        The login gbd brings them, and so does every reply that carries the list (``gli``,
        ``arl``, ``gla``, ``seq``, ``sdi``, ``sti`` and the attack and conquer info replies).
        A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.commanders is None else self.commanders.model_copy(deep=True)

    def get_skills(self) -> SkillList | None:
        """Your legend and sceat skills as the last ``skl`` listed them; None until one arrived.

        The login gbd brings them, and so do a ``skl`` reply or push and an ``ego`` push
        that carries one. A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.skills is None else self.skills.model_copy(deep=True)
