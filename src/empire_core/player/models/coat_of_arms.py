"""
Your coat of arms and the symbols it may show.

Commands:
- gem: your coat of arms, a login section of ``gbd`` and a push
- cem: change your coat of arms
- lca: create the avatar, your first coat of arms, while a quest asks for one
- gus: the premium symbols achievements earned you, and those you unlocked (push)
- bus: unlock an earned premium symbol
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, Field, field_serializer, field_validator

from empire_core.enums import CoatOfArmsBackground, SymbolLayout
from empire_core.gamedata import CoatOfArmsSymbolId
from empire_core.map.models.owners import OwnerCrest
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, list_or_empty, object_or_none
from empire_core.protocol.js import js_int, js_loose_equals

_NO_SYMBOL = -1

_SymbolIds = Annotated[
    tuple[CoatOfArmsSymbolId, ...],
    BeforeValidator(lambda value: tuple(CoatOfArmsSymbolId(js_int(i)) for i in list_or_empty(value))),
]
_Names = Annotated[
    list[str], BeforeValidator(lambda value: [name for name in list_or_empty(value) if isinstance(name, str)])
]


def coat_of_arms_design(crest: OwnerCrest) -> dict[str, int]:
    """
    The coat of arms as the client sends it: no symbol without a layout that shows one, no second symbol with one
    centred symbol, and a plain background in its first colour.

    Client: ``CrestVO.getParamObject`` and ``setBackground`` (bundle lines 10589, 10591),
    ``CastlePremiumMarketPlaceDialogFlag.sendNewCrest`` (bundle line 77020)
    """
    layout = crest.symbol_type
    background = crest.background_type
    return {
        "BGT": int(background),
        "BGC1": crest.background_color1,
        "BGC2": crest.background_color1 if background == CoatOfArmsBackground.PLAIN else crest.background_color2,
        "SPT": int(layout),
        "S1": _NO_SYMBOL if layout == SymbolLayout.NONE else crest.symbol1,
        "SC1": crest.symbol1_color,
        "S2": _NO_SYMBOL if layout in (SymbolLayout.NONE, SymbolLayout.ONE_CENTERED) else crest.symbol2,
        "SC2": crest.symbol2_color,
    }


class CoatOfArmsResponse(BaseResponse, OwnerCrest):
    """
    Your coat of arms, and whether you may change it.

    Command: gem, as a login section of ``gbd``, a push and inside a ``cem`` reply.

    Client: ``GEMCommand.executeCommand`` (bundle line 129540), ``CastleUserData.parse_GEM`` (bundle line 9877),
    which reads only a truthy block
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gem"

    may_change: bool = Field(
        validation_alias="MCE", default=False, description="Whether you may change your coat of arms"
    )

    @field_validator("may_change", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


class ChangeCoatOfArmsRequest(BaseRequest):
    """
    Change your coat of arms (``cem``).

    Client: ``C2SChangeEmblemVO`` (bundle line 77130), sent by ``CastlePremiumMarketPlaceDialogFlag.sendNewCrest``
    (bundle line 77020)
    """

    command = "cem"

    coat_of_arms: OwnerCrest = Field(validation_alias="CAE", description="The new coat of arms")

    @field_serializer("coat_of_arms")
    def _design(self, coat_of_arms: OwnerCrest) -> dict[str, int]:
        return coat_of_arms_design(coat_of_arms)


class ChangeCoatOfArmsResponse(BaseResponse):
    """
    Your coat of arms after the change, and your coins and rubies.

    Client: ``CEMCommand.executeCommand`` (bundle line 125045)
    """

    command = "cem"

    coat_of_arms: CoatOfArmsResponse | None = Field(
        validation_alias="gem", default=None, description="Your new coat of arms"
    )
    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")

    @field_validator("coat_of_arms", mode="before")
    @classmethod
    def _coat_of_arms(cls, value: Any) -> Any:
        return object_or_none(value)


class CreateAvatarRequest(BaseRequest):
    """
    Send your coat of arms as your avatar (``lca``), which the client does before changing your coat of arms
    while a quest asks you to create one.

    Client: ``CastlePremiumMarketPlaceDialogFlag.sendNewCrest`` (bundle line 77020) sends ``{"CAE": crest}`` raw,
    when ``CastleQuestData.foundActiveQuestWithConditionType`` (bundle line 20339) finds a ``createEmblem`` condition
    """

    command = "lca"

    coat_of_arms: OwnerCrest = Field(validation_alias="CAE", description="The coat of arms")

    @field_serializer("coat_of_arms")
    def _design(self, coat_of_arms: OwnerCrest) -> dict[str, int]:
        return coat_of_arms_design(coat_of_arms)


class CreateAvatarResponse(BaseResponse):
    """
    The reply to ``lca``. A refused name (``INVALID_NAME``, ``NAME_ALREADY_IN_USE``, ``NAME_HAS_ONLY_NUMBERS``,
    ``USAGE_OF_BADWORDS``) carries free names like it.

    Client: ``LCACommand.executeCommand`` (bundle line 120618); ``ModernStartscreenPanel.onRegisterError``
    (bundle line 58066) reads a refusal's ``NS``
    """

    command = "lca"

    suggested_names: _Names = Field(
        validation_alias="NS", default_factory=list, description="Free names like the refused one"
    )


class CoatOfArmsSymbolsResponse(BaseResponse):
    """
    The premium coat of arms symbols achievements earned you, and those you unlocked. The game data's
    ``coat_of_arms_symbols`` describes each symbol.

    Command: gus, a push.

    Client: ``GUSCommand.executeCommand`` (bundle line 125060), ``CastleCrestSymbolData.parse_gus``
    (bundle line 111596), which counts an unlocked symbol as earned too and keeps only premium symbols
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gus"

    earned_symbol_ids: _SymbolIds = Field(
        validation_alias="U", default=(), description="Symbols an achievement earned you, unlocked or not"
    )
    unlocked_symbol_ids: _SymbolIds = Field(validation_alias="P", default=(), description="Symbols you unlocked")

    def is_earned(self, symbol_id: CoatOfArmsSymbolId) -> bool:
        """Whether the symbol is earned: listed as earned or as unlocked."""
        return symbol_id in self.earned_symbol_ids or symbol_id in self.unlocked_symbol_ids

    def is_unlocked(self, symbol_id: CoatOfArmsSymbolId) -> bool:
        """Whether you have unlocked the symbol for good."""
        return symbol_id in self.unlocked_symbol_ids


class UnlockSymbolRequest(BaseRequest):
    """
    Unlock an earned premium symbol for good (``bus``), for its coin or ruby price.

    Client: ``C2SBuyUnlockedSymbolVO`` (bundle line 77198), sent by ``CastleBuyUnlockedCrestSymbolDialog.onClick``
    (bundle line 77182)
    """

    command = "bus"

    symbol_id: CoatOfArmsSymbolId = Field(
        validation_alias="CSI", description="The symbol, a coat_of_arms_symbols row of the game data"
    )


class UnlockSymbolResponse(BaseResponse):
    """
    The reply to ``bus``, which carries nothing the client reads.

    Client: ``BUSCommand.executeCommand`` (bundle line 125032)
    """

    command = "bus"


__all__ = [
    "UnlockSymbolRequest",
    "UnlockSymbolResponse",
    "ChangeCoatOfArmsRequest",
    "ChangeCoatOfArmsResponse",
    "CreateAvatarRequest",
    "CreateAvatarResponse",
    "CoatOfArmsResponse",
    "CoatOfArmsSymbolsResponse",
    "coat_of_arms_design",
]
