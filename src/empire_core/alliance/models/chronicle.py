"""Alliance chronicle and subscriber count.

Commands:
- all: Your alliance's chronicle, the log on the alliance overview
- asc: How many of your alliance's members have a subscription
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field, field_validator

from empire_core.enums import AllianceBuffType, AllianceChronicleAction, DiplomacyStatus
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_loose_equals, js_number_or_none, js_parse_int, js_string
from empire_core.texts import PlainText, has_text, text

if TYPE_CHECKING:
    from empire_core.gamedata import DaimyoContractDef, GameData

logger = logging.getLogger(__name__)

Action = AllianceChronicleAction


def _at(values: list[Any], index: int) -> Any:
    return values[index] if index < len(values) else None


def _number(values: list[Any], index: int) -> int | float | None:
    return js_number_or_none(_at(values, index))


def _name(values: list[Any], index: int) -> str | None:
    value = _at(values, index)
    return None if value is None else js_string(value)


def _member(enum: type[DiplomacyStatus] | type[AllianceBuffType], value: Any) -> Any:
    number = js_parse_int(value)
    return None if number is None else known(enum, number)


# =============================================================================
# Chronicle entry details, by action
# =============================================================================


@dataclass(frozen=True)
class ChronicleDiplomacy:
    """
    A diplomacy entry: ``CHANGE_DIPLOMACY``, ``GET_REQUEST_DIPLOMACY``, ``SEND_REQUEST_DIPLOMACY`` or
    ``REFUSE_DIPLOMACY``.

    Client: ``AllianceActionListItemVO.getActionText`` (bundle line 66342) reads ``AV[1]`` and ``AV[2]``
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.CHANGE_DIPLOMACY,
        Action.GET_REQUEST_DIPLOMACY,
        Action.SEND_REQUEST_DIPLOMACY,
        Action.REFUSE_DIPLOMACY,
    )

    alliance_name: str | None
    """The other alliance's name, ``AV[1]``."""
    status: DiplomacyStatus | int | None
    """The status changed to or asked for, ``AV[2]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleDiplomacy:
        return cls(_name(values, 1), _member(DiplomacyStatus, _at(values, 2)))


@dataclass(frozen=True)
class ChronicleBuff:
    """
    An alliance upgrade (``UPGRADE``), or a boost bought or extended (``ACTIVATE_TEMP_BUFF``, ``EXTEND_TEMP_BUFF``).

    Client: ``AllianceActionListItemVO.getActionText`` (bundle lines 66344-66348) reads the buff
    from ``AV[0]``, and for an ``UPGRADE`` of ``MEMBERS`` or ``FORGE_UPGRADE`` fills the text with the rest
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.UPGRADE,
        Action.ACTIVATE_TEMP_BUFF,
        Action.EXTEND_TEMP_BUFF,
    )

    buff: AllianceBuffType | int | None
    """What was upgraded or boosted, ``AV[0]``."""
    level: int | float | None = None
    """The smithy's new level, ``AV[1]`` of a ``FORGE_UPGRADE``; None for any other buff."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleBuff:
        buff = _member(AllianceBuffType, _at(values, 0))
        return cls(buff, _number(values, 1) if buff == AllianceBuffType.FORGE_UPGRADE else None)


@dataclass(frozen=True)
class ChronicleAmount:
    """
    An amount, ``AV[0]``: coins, rubies, resources or glory donated, paid, won or received.

    For the donations and ``MEMBER_EARN_FAME`` the client reads ``AV[0]`` as the amount, taking the
    singular text for 1 (``AllianceActionListItemVO.getActionText``, bundle line 66350); for the
    others only their text's ``{0}`` (``dialog_alliance_chronic<action>``) says so.
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.MEMBER_DONATE_COINS,
        Action.MEMBER_DONATE_RUBIES,
        Action.MEMBER_DONATE_RESOURCES,
        Action.MEMBER_EARN_FAME,
        Action.DONATE_COINS_BY_LEVEL_UP,
        Action.DONATE_RUBIES_BY_LEVEL_UP,
        Action.DONATE_RESOURCES_BY_LEVEL_UP,
        Action.PRIZE_COINS_OF_LAST_ROUND,
        Action.PRIZE_RUBIES_OF_LAST_ROUND,
        Action.TRIBUTE_PAY_COINS,
        Action.TRIBUTE_PAY_RUBIES,
        Action.TRIBUTE_PAY_RESOURCES,
        Action.TRIBUTE_GET_COINS,
        Action.TRIBUTE_GET_RUBIES,
        Action.TRIBUTE_GET_RESOURCES,
        Action.REWARD_COINS,
        Action.REWARD_RUBIES,
    )

    amount: int | float | None
    """The amount, ``AV[0]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleAmount:
        return cls(_number(values, 0))


@dataclass(frozen=True)
class ChronicleLevel:
    """The alliance's level after ``LEVEL_UP`` or ``LEVEL_DOWN``, ``AV[0]``: their text's ``{0}``."""

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (Action.LEVEL_UP, Action.LEVEL_DOWN)

    level: int | float | None
    """The level reached, ``AV[0]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleLevel:
        return cls(_number(values, 0))


@dataclass(frozen=True)
class ChroniclePlace:
    """
    The place the alliance came in, ``AV[0]``, of ``TOURNAMENT_RANK`` and ``ALLIANCE_RANK_OF_LAST_ROUND``:
    their text's ``{0}``.
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.TOURNAMENT_RANK,
        Action.ALLIANCE_RANK_OF_LAST_ROUND,
    )

    place: int | float | None
    """The place, ``AV[0]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChroniclePlace:
        return cls(_number(values, 0))


@dataclass(frozen=True)
class ChronicleTournamentPrize:
    """
    The alliance tournament's prize, ``TOURNAMENT_REWARD``: its text's ``{0}`` coins and ``{1}`` rubies.

    ``AV[2]`` is the name the overview shows, :attr:`AllianceChronicleEntry.named_alliance_name`.
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (Action.TOURNAMENT_REWARD,)

    coins: int | float | None
    """Coins won, ``AV[0]``."""
    rubies: int | float | None
    """Rubies won, ``AV[1]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleTournamentPrize:
        return cls(_number(values, 0), _number(values, 1))


@dataclass(frozen=True)
class ChronicleText:
    """
    ``AV[0]``, which the client puts in the text as it is: the new name of ``CHANGE_NAME``, and on an
    alliance battle ground the tower defeated, the penalty increase in percent or the statuettes gained.

    Client: ``AllianceActionListItemVO.getActionText`` (bundle line 66352)
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.CHANGE_NAME,
        Action.ALLIANCE_BATTLE_GROUND_OWNED_TOWER_DEFEATED,
        Action.ALLIANCE_BATTLE_GROUND_MALUS_INCREASED,
        Action.ALLIANCE_BATTLE_GROUND_POINTS_GAINED,
    )

    text: str | None
    """``AV[0]`` as text."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleText:
        return cls(_name(values, 0))


@dataclass(frozen=True)
class ChronicleMember:
    """
    The member thrown out, demoted or promoted (``MEMBER_KICKED``, ``MEMBER_DEMOTE``, ``MEMBER_PROMOTE``):
    their text's ``{1}``. Nothing in the client reads ``AV[0]`` of these entries.
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.MEMBER_KICKED,
        Action.MEMBER_DEMOTE,
        Action.MEMBER_PROMOTE,
    )

    member_name: str | None
    """The member's name, ``AV[1]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleMember:
        return cls(_name(values, 1))


@dataclass(frozen=True)
class ChronicleDaimyoContract:
    """
    A daimyo alliance contract completed: ``DAIMYO_ALLIANCE_CASTLE_CONTRACT_COMPLETED`` or
    ``DAIMYO_ALLIANCE_TOWNSHIP_CONTRACT_COMPLETED``.

    Client: ``AllianceActionListItemVO.getActionText`` (bundle lines 66354-66357) reads the
    contract from ``AV[0]``
    """

    ACTIONS: ClassVar[tuple[AllianceChronicleAction, ...]] = (
        Action.DAIMYO_ALLIANCE_CASTLE_CONTRACT_COMPLETED,
        Action.DAIMYO_ALLIANCE_TOWNSHIP_CONTRACT_COMPLETED,
    )

    contract_id: int | None
    """The contract, ``AV[0]``."""

    @classmethod
    def from_values(cls, values: list[Any]) -> ChronicleDaimyoContract:
        return cls(js_parse_int(_at(values, 0)))

    def series_position(self, game_data: GameData) -> tuple[DaimyoContractDef, int, int]:
        """
        The contract, its level within its rank (from 1) and how many levels the rank has.

        Both actions look the contract up among the daimyo castle contracts, a township's
        too, as the client does.

        Raises:
            KeyError: The castle contracts have no such contract

        Client: ``SamuraiDaimyoDataXml.getContractSeriesIndex`` and ``getNumberOfContractsForSeries``
        (bundle lines 13915-13925), with ``CONTRACT_TYPE_CASTLE`` (bundle lines 66354-66357)
        """
        contracts = game_data.daimyo_castle_contracts
        if self.contract_id is None or self.contract_id not in contracts:
            raise KeyError(f"no daimyo castle contract {self.contract_id}")
        contract = contracts[self.contract_id]
        series = [row.contract_id for row in contracts.values() if row.rank == contract.rank]
        return contract, series.index(contract.contract_id) + 1, len(series)


ChronicleDetails = (
    ChronicleDiplomacy
    | ChronicleBuff
    | ChronicleAmount
    | ChronicleLevel
    | ChroniclePlace
    | ChronicleTournamentPrize
    | ChronicleText
    | ChronicleMember
    | ChronicleDaimyoContract
)
"""What a chronicle entry's ``AV`` holds, by action: :attr:`AllianceChronicleEntry.details`."""

_DETAILS: dict[int, type[ChronicleDetails]] = {
    action: details
    for details in (
        ChronicleDiplomacy,
        ChronicleBuff,
        ChronicleAmount,
        ChronicleLevel,
        ChroniclePlace,
        ChronicleTournamentPrize,
        ChronicleText,
        ChronicleMember,
        ChronicleDaimyoContract,
    )
    for action in details.ACTIONS
}

_NAMED_BY_PLAYER = frozenset(
    {
        Action.CONQUERED_CAPITAL,
        Action.CONQUERED_METROPOLIS,
        Action.LOSING_CAPITAL,
        Action.LOSING_METROPOLIS,
        Action.LOST_CAPITAL,
        Action.LOST_METROPOLIS,
        Action.ABANDONED_CAPITAL,
        Action.ABANDONED_METROPOLIS,
        Action.MEMBER_INACTIVE_KICK,
        Action.NEW_KINGS_NAME,
        Action.METROPOLIS_OWNER_JOINED,
        Action.CAPITAL_OWNER_JOINED,
    }
)
"""The entries whose text names ``PN`` (bundle lines 66349 and 66353)."""

_DONATIONS = frozenset(
    {
        Action.MEMBER_EARN_FAME,
        Action.MEMBER_DONATE_RESOURCES,
        Action.MEMBER_DONATE_COINS,
        Action.MEMBER_DONATE_RUBIES,
    }
)

_UPGRADE_BUFF_TEXT_IDS = {
    AllianceBuffType.DEFENSE_SPEED_BOOST: "dialog_alliance_defenseBoost",
    AllianceBuffType.MARKET_SPEED_BOOST: "dialog_alliance_marketBoost",
    AllianceBuffType.DEPOSIT_BONUS: "dialog_alliance_depositBonus",
    AllianceBuffType.MARAUDER_BONUS: "dialog_alliance_permanentBoost_lootCapacity",
    AllianceBuffType.ATTACK_SPEED_BOOST: "dialog_alliance_movementBoost",
}
"""``AllianceActionListItemVO.getAllianceBuffTextId`` (bundle line 66364); any other buff is ``""``."""


# =============================================================================
# ALL - Chronicle
# =============================================================================


class AllianceChronicleRequest(BaseRequest):
    """
    Ask for your alliance's chronicle.

    Command: all
    Payload: {}

    Client: ``C2SAllianceActionListVO`` (bundle line 70469)
    """

    command = "all"


class AllianceChronicleEntry(BasePayload):
    """
    One entry of your alliance's chronicle.

    ``details`` types what ``action_values`` holds for the action; ``describe()`` writes the
    entry's line as the overview shows it.

    Client: ``AllianceActionListItemVO.parseActionListItem`` (bundle line 66338)
    """

    player_id: ClientInt = Field(alias="PID", default=0, description="The player the entry is about")
    player_name: str | None = Field(alias="PN", default=None, description="The player's name")
    seconds_ago: ClientInt = Field(alias="MA", default=0, description="Seconds since the action")
    action: ClientInt = Field(alias="A", default=0, description="What happened, an AllianceChronicleAction value")
    action_values: list[Any] = Field(
        alias="AV", default_factory=list, description="The action's text arguments as sent; typed by details"
    )

    @field_validator("player_name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return value if isinstance(value, str) else None

    @field_validator("action_values", mode="before")
    @classmethod
    def _values(cls, value: Any) -> Any:
        return value if isinstance(value, list) else []

    @property
    def action_type(self) -> AllianceChronicleAction | None:
        """``action`` as an :class:`AllianceChronicleAction`, None for an action the client does not define."""
        return enum_or_none(AllianceChronicleAction, self.action)

    @property
    def details(self) -> ChronicleDetails | None:
        """
        What ``action_values`` holds for this action, typed; None for an action whose values nothing reads.

        An entry about a player (a capital or metropolis taken or lost, a member removed for
        inactivity, a new Storm Lord, an owner who joined) names them in ``player_name`` instead.
        """
        details = _DETAILS.get(self.action)
        return None if details is None else details.from_values(self.action_values)

    @property
    def is_deleted_player(self) -> bool:
        """
        The entry's player has deleted their account since; the overview shows "Deleted player".

        Client: ``CastleAllianceDialogOverview.fillActionList`` (bundle line 70410), ``PN`` starting ``!!!_``
        """
        return (self.player_name or "").startswith("!!!_")

    @property
    def named_alliance_id(self) -> int | None:
        """
        The alliance the overview links for an entry no player made (``player_id`` -1), ``AV[0]``.

        None for an entry a player made, and for ``TOURNAMENT_REWARD`` and ``TOURNAMENT_RANK``, which link none.

        Client: ``CastleAllianceDialogOverview.fillActionList`` (bundle lines 70410-70420)
        """
        if self.player_id != -1 or self.action in (Action.TOURNAMENT_REWARD, Action.TOURNAMENT_RANK):
            return None
        return js_parse_int(_at(self.action_values, 0))

    @property
    def named_alliance_name(self) -> str | None:
        """
        The name the overview shows for an entry no player made (``player_id`` -1): ``AV[1]``, or
        ``AV[2]`` for ``TOURNAMENT_REWARD``; None for ``TOURNAMENT_RANK`` and an entry a player made.

        Client: ``CastleAllianceDialogOverview.fillActionList`` (bundle lines 70410-70420)
        """
        if self.player_id != -1 or self.action == Action.TOURNAMENT_RANK:
            return None
        return _name(self.action_values, 2 if self.action == Action.TOURNAMENT_REWARD else 1)

    def describe(self, game_data: GameData | None = None, *, lang: str = "en", skin: str = "") -> str:
        """
        The entry's line in the chronicle, as the alliance overview writes it.

        Fetches the language file on first use, as :func:`empire_core.texts.text` does.

        Args:
            game_data: The game data; only a daimyo contract entry needs it
            lang: Language code (default: "en")
            skin: The skin of the special server played on, such as ``"Maya"``, whose own texts
                the client prefers there (in the Great Empire only); empty elsewhere

        Raises:
            ValueError: A daimyo contract entry without ``game_data``
            KeyError: A daimyo contract the game data lacks, where the client fails too

        Client: ``AllianceActionListItemVO.getActionText`` (bundle lines 66341-66358), its text id
        through ``SpecialServerHelper.checkTextIDForSkinText`` (bundle line 1679)
        """
        key = f"dialog_alliance_chronic{self.action}"
        if skin and has_text(f"{key}_{skin}", lang):
            key = f"{key}_{skin}"
        values = self.action_values
        action = self.action
        if action in ChronicleDiplomacy.ACTIONS:
            status = text(f"dialog_allianceDiplomacy_status{js_string(_at(values, 2))}", lang=lang)
            return text(key, PlainText(_name(values, 1) or ""), status, lang=lang)
        if action == Action.UPGRADE:
            buff = _at(values, 0)
            if js_loose_equals(buff, AllianceBuffType.MEMBERS) or js_loose_equals(buff, AllianceBuffType.FORGE_UPGRADE):
                return text(f"{key}_{js_string(buff)}", *values[1:], lang=lang)
            name = text(_UPGRADE_BUFF_TEXT_IDS.get(_member(AllianceBuffType, buff), ""), lang=lang)
            return text(f"{key}_1", name, lang=lang)
        if action in (Action.ACTIVATE_TEMP_BUFF, Action.EXTEND_TEMP_BUFF):
            return text(f"{key}_{js_string(_at(values, 0))}", lang=lang)
        if action in _NAMED_BY_PLAYER:
            return text(key, PlainText(self.player_name or ""), lang=lang)
        if action in _DONATIONS:
            single = "_singleDigit" if js_loose_equals(_at(values, 0), 1) else ""
            return text(key + single, *values, lang=lang)
        if action in ChronicleText.ACTIONS or action == Action.ALLIANCE_BATTLE_GROUND_MALUS_RESET:
            return text(key, PlainText(_name(values, 0) or ""), lang=lang, grouping=False)
        if action in ChronicleDaimyoContract.ACTIONS:
            if game_data is None:
                raise ValueError("describing a daimyo contract entry needs the game data")
            contract, level, levels = ChronicleDaimyoContract.from_values(values).series_position(game_data)
            return text(key, contract.rank, level, levels, lang=lang)
        return text(key, *values, lang=lang)


class AllianceChronicleResponse(BaseResponse):
    """
    Your alliance's chronicle.

    Command: all

    Client: ``ALLCommand.executeCommand`` (bundle line 121528) into
    ``CastleAllianceData.parse_ALL`` (bundle line 11565), which reads ``AL``
    with ``AllianceInfoVO.parseActionList`` (bundle line 25962) and reverses it
    """

    command = "all"

    alliance_id: ClientInt = Field(alias="AID", default=0, description="Your alliance's id")
    entries: list[AllianceChronicleEntry] = Field(
        alias="AL", default_factory=list, description="The entries, newest first"
    )

    @field_validator("entries", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        rows = readable_list(
            AllianceChronicleEntry, value, accept=lambda e: isinstance(e, dict), warn=logger, what="chronicle entries"
        )
        return rows[::-1]


# =============================================================================
# ASC - Subscriber count
# =============================================================================


class AllianceSubscriberCountRequest(BaseRequest):
    """
    Ask how many of your alliance's members have a subscription.

    Command: asc
    Payload: {}

    Client: ``C2SGetAllianceSubscriberCountEventVO`` (bundle line 120106)
    """

    command = "asc"


class AllianceSubscriberCountResponse(BaseResponse):
    """
    How many of your alliance's members have a subscription.

    Command: asc

    Client: ``ASCCommand.executeCommand`` (bundle line 128655) into
    ``SubscriptionData.parseASC`` (bundle line 120005); the treasury's
    subscriptions tab shows it against the member limit
    (``CastleAllianceDialogTreasurySubscriptions.updateSubscriberCount``, bundle line 70697)
    """

    command = "asc"

    subscriber_count: ClientInt = Field(
        alias="ASC", default=0, description="Members of your alliance with a subscription"
    )


__all__ = [
    "ChronicleAmount",
    "ChronicleBuff",
    "ChronicleDaimyoContract",
    "ChronicleDetails",
    "ChronicleDiplomacy",
    "ChronicleLevel",
    "ChronicleMember",
    "ChroniclePlace",
    "ChronicleText",
    "ChronicleTournamentPrize",
    "AllianceChronicleRequest",
    "AllianceChronicleEntry",
    "AllianceChronicleResponse",
    "AllianceSubscriberCountRequest",
    "AllianceSubscriberCountResponse",
]
