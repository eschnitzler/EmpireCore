"""
Sending attacks, filling their waves the way the game's "Fill waves" button
does, and the saved attack presets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.attack.pacing import AttackSendPacer
from empire_core.attack.service.camps import CampsMixin
from empire_core.attack.service.filling import FillAttackMixin
from empire_core.attack.service.presets import PresetsMixin
from empire_core.attack.service.sending import SendingMixin
from empire_core.attack.service.waves import WavesMixin
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.attack.models.counter import AttackCounterResponse
    from empire_core.client.client import EmpireClient


class AttackService(CampsMixin, FillAttackMixin, WavesMixin, SendingMixin, PresetsMixin, BaseService):
    """
    Send attacks, fill their waves, and read the attack pre-calculation.

    Reached as client.attack.
    """

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self.pacer = AttackSendPacer(lambda: client.config.attack_send_interval)
        self.on_response("hac", self._handle_hidden_alien_camps)

    @property
    def counter(self) -> AttackCounterResponse | None:
        """Your attack counter, from the last ``gai``; None until one arrived."""
        return self.client.state.get_attack_counter()
