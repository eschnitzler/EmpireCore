"""
The hero you pick as the tutorial's quest character.

Commands:
- hdc: Pick the hero; the server sends the same command to say which one you have, or that none is picked
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from empire_core.enums import Hero
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt


class HeroDecisionRequest(BaseRequest):
    """
    Pick your hero (``hdc``).

    Client: ``HeroDecisionVO`` (bundle line 65997), sent by ``CastleChooseHeroDialog.sendHeroIdToServer``
    (bundle line 42429)
    """

    command: ClassVar[str] = "hdc"

    hero: Hero = Field(validation_alias="HID", description="The hero to pick")


class HeroDecisionResponse(BaseResponse):
    """
    The hero you have picked, or that you have yet to pick one.

    Client: ``HDCommand.executeCommand`` (bundle line 124371), ``CastleUserData.parse_HDC`` (bundle line 10101),
    which opens the choose-hero dialog for -1 and keeps a hero above 0
    """

    command: ClassVar[str] = "hdc"

    hero_id: ClientInt = Field(
        validation_alias="HID", default=0, description="Your hero's id; -1 while you have yet to pick one"
    )

    @property
    def hero(self) -> Hero | int | None:
        """Your hero, None while you have yet to pick one."""
        return known(Hero, self.hero_id) if self.hero_id > 0 else None


__all__ = ["HeroDecisionRequest", "HeroDecisionResponse"]
