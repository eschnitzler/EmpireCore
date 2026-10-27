"""What the player sections share: your player and your currencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import Currency
    from empire_core.state.models import Player


class PlayerBaseMixin(ServiceMixin):
    @property
    def local_player(self) -> Player:
        """A snapshot of the local player.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_local_player()

    @property
    def currencies(self) -> dict[Currency | str, int]:
        """A snapshot of the special currencies (``Currency`` -> amount)."""
        return self.client.state.get_special_currencies()
