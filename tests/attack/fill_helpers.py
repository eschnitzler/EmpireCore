"""A client set up to fill attacks from, shared by the attack fill tests."""

from __future__ import annotations

from typing import ClassVar

from empire_core.enums import Kingdom
from tests.service_helpers import make_client, stub_player, xt_packet

OWN = [(12345, Kingdom.GREEN)]


class FillClient:
    """Game data and an inventory to fill from."""

    UNITS: ClassVar[dict[str, list]] = {
        "units": [
            {
                "wodID": 601,
                "name": "Barracks",
                "type": "Sword",
                "role": "melee",
                "meleeAttack": "100",
                "fightType": "0",
            },
            {
                "wodID": 611,
                "name": "Workshop",
                "type": "Ram",
                "typ": "Attack",
                "slotTypes": "1,2,9",
                "gateBonus": "30",
                "fightType": "1",
            },
        ],
        "buildings": [
            {"wodID": 501, "comment2": "Castlewall", "level": "1", "wallBonus": "30"},
            {"wodID": 450, "comment2": "Gate", "level": "1", "gateBonus": "30"},
        ],
        # A daimyo rank jumps at a rank boundary, so the level is looked up and
        # never counted off from the first row.
        "daimyoCastles": [{"id": "1", "rank": "1", "level": "81", "wallBonus": "110", "gateBonus": "110"}],
        "daimyoTownships": [
            {"id": "25", "rank": "3", "level": "110", "wallBonus": "100", "gateBonus": "100"},
            {"id": "26", "rank": "4", "level": "116", "wallBonus": "100", "gateBonus": "100"},
        ],
        "leaguetypes": [
            {"leaguetypeID": "1", "eventID": "80", "minLevel": 10, "maxLevel": "69", "countVictoryMin": "16"},
            {"leaguetypeID": "2", "eventID": "80", "minLevel": 70, "maxLevel": "369", "countVictoryMin": "81"},
        ],
        "eventAutoScalingCamps": [{"eventAutoScalingCampID": "3", "camplevel": "70"}],
    }

    def build(self, inventory):
        from empire_core.gamedata import GameData

        client = make_client({"gui": xt_packet("gui", {"I": inventory})}, castles=OWN)
        client.game_data = GameData.parse("test", self.UNITS)
        client.state.local_player = stub_player(level=70)
        return client
