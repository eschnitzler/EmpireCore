"""The login data (``gbd``), every section of it read through that section's own model."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import (
    AliasPath,
    ConfigDict,
    Field,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from empire_core.alliance.models.chat import AllianceChatLogResponse
from empire_core.alliance.models.help import AllianceHelpListResponse
from empire_core.alliance.models.info import GetAllianceInfoResponse
from empire_core.alliance.models.membership import AllianceMembershipResponse
from empire_core.attack.models.counter import AttackCounterResponse
from empire_core.castle.models.castles import GetCastlesResponse
from empire_core.castle.models.construction_items import ConstructionItemInventory, ConstructionItemSpace
from empire_core.castle.models.details import GetDetailedCastleResponse
from empire_core.castle.models.kingdoms import KingdomInfoResponse
from empire_core.castle.models.landmarks import (
    LaboratoryListResponse,
    LaboratoryResetResponse,
    MonumentListResponse,
    MonumentResetResponse,
    RoyalTowerListResponse,
)
from empire_core.castle.models.mercenaries import MercenaryMissionsResponse
from empire_core.castle.models.permanent import PermanentCastleDataResponse
from empire_core.castle.models.research import ResearchInfoResponse
from empire_core.castle.models.tax import TaxInfoResponse
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, ResourcePoolResponse
from empire_core.castle.models.villages import VillageListResponse
from empire_core.castle.models.wishing_well import WishingWellResponse
from empire_core.commanders.models.inventory import GemInventoryResponse, InventorySpace, NewRelicsResponse
from empire_core.commanders.models.roster import CommanderRoster
from empire_core.commanders.models.skills import SkillList
from empire_core.events.berimond_models import BerimondKingdomStatus
from empire_core.events.models import SpecialEventsResponse, TriggerEventsResponse
from empire_core.map.models.areas import KingdomProtection
from empire_core.map.models.treasure_maps import TreasureHuntInfoResponse, TreasureMapsResponse
from empire_core.messages.models.mailbox import MessagesSentToday, SystemNotificationEvent
from empire_core.movements.models.movement import MovementFilterResponse
from empire_core.player.models.account import (
    BoostedGlobalEffectsResponse,
    DailyResetResponse,
    FoodProductionStatus,
    OfficerTraining,
    PlayerGiftsResponse,
    PlayerIdentityResponse,
    PremiumFlagResponse,
    VipStatusResponse,
)
from empire_core.player.models.coat_of_arms import CoatOfArmsResponse
from empire_core.player.models.credentials import CredentialsStatus
from empire_core.player.models.economy import CurrencyResponse, LootBoxesResponse, SpecialCurrenciesResponse
from empire_core.player.models.progress import (
    AchievementsResponse,
    BoosterInfoResponse,
    ExperienceResponse,
    GloryPointsResponse,
    GloryTitleResetResponse,
    HonorResponse,
    MightPointsResponse,
    RelocationInfoResponse,
    TitleRanksResponse,
)
from empire_core.protocol.base import BaseResponse, read_or_none
from empire_core.protocol.js import js_truthy
from empire_core.quests.models import DailyQuests
from empire_core.spy.models import MaxSpiesResponse, PlagueDoctorInfoResponse

logger = logging.getLogger(__name__)


class LoginDataResponse(BaseResponse):
    """
    The login data: every section the client reads after logging in, each through its section's model.

    A section that is not sent, is falsy, or that its model cannot read, is None; the rest of the login
    data still reads, and which sections were sent is in ``model_fields_set``. Sections the library has
    no model for yet stay as extras. A falsy ``mcd`` gives way to the login data's own ``MTC``, as in the
    client; ``nsm``, a negated flag, is not modelled.

    Command: gbd, pushed after a login; ``client.state`` applies each section as it comes, and a section
    pushed on its own as a login data of that one section. ``gii``, ``csp`` and ``irc`` come only that way.

    Client: ``GBDCommand.exec`` (split.js line 651188), which hands each section to its parser in the
    order the fields here follow; most parsers skip a falsy section, and ``client.state`` keeps the
    exceptions (a falsy ``sei`` still refreshes the events, a falsy ``gatp`` ends the training).
    ``parse_GIE``, ``parse_PGL`` and ``parse_MCD`` (split.js lines 711633, 582271, 672695) also skip a
    block whose ``GE``, ``G`` or ``MTC`` is falsy. ``GIICommand``, ``CSPCommand`` and ``IRCCommand``
    (split.js lines 629668, 631395, 629121) bring the rest
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gbd"

    honor: HonorResponse | None = Field(
        validation_alias="gho",
        default=None,
        description="Your honor and ranking points; None when not sent or unreadable",
    )
    identity: PlayerIdentityResponse | None = Field(
        validation_alias="gpi", default=None, description="Who you are; None when not sent or unreadable"
    )
    glory_points: GloryPointsResponse | None = Field(
        validation_alias="ufa",
        default=None,
        description="Your glory points and title; None when not sent or unreadable",
    )
    glory_title_reset: GloryTitleResetResponse | None = Field(
        validation_alias="uht",
        default=None,
        description="When the glory titles reset; None when not sent or unreadable",
    )
    title_ranks: TitleRanksResponse | None = Field(
        validation_alias="uar", default=None, description="The title ranks; None when not sent or unreadable"
    )
    credentials: CredentialsStatus | None = Field(
        validation_alias="scd", default=None, description="Your credentials' status; None when not sent or unreadable"
    )
    special_currencies: SpecialCurrenciesResponse | None = Field(
        validation_alias="sce", default=None, description="Your special currencies; None when not sent or unreadable"
    )
    coat_of_arms: CoatOfArmsResponse | None = Field(
        validation_alias="gem", default=None, description="Your coat of arms; None when not sent or unreadable"
    )
    premium_flag: PremiumFlagResponse | None = Field(
        validation_alias="gpf",
        default=None,
        description="Whether you own the premium flag; None when not sent or unreadable",
    )
    currencies: CurrencyResponse | None = Field(
        validation_alias="gcu", default=None, description="Your coins and rubies; None when not sent or unreadable"
    )
    experience: ExperienceResponse | None = Field(
        validation_alias="gxp", default=None, description="Your level and XP; None when not sent or unreadable"
    )
    castles: GetCastlesResponse | None = Field(
        validation_alias="gcl", default=None, description="Your castle list; None when not sent or unreadable"
    )
    monument_reset: MonumentResetResponse | None = Field(
        validation_alias="mre", default=None, description="The monuments' reset; None when not sent or unreadable"
    )
    laboratory_reset: LaboratoryResetResponse | None = Field(
        validation_alias="lrr", default=None, description="The laboratories' reset; None when not sent or unreadable"
    )
    royal_towers: RoyalTowerListResponse | None = Field(
        validation_alias="gkl", default=None, description="Your royal towers; None when not sent or unreadable"
    )
    monuments: MonumentListResponse | None = Field(
        validation_alias="gml", default=None, description="Your monuments; None when not sent or unreadable"
    )
    laboratories: LaboratoryListResponse | None = Field(
        validation_alias="gll", default=None, description="Your laboratories; None when not sent or unreadable"
    )
    villages: VillageListResponse | None = Field(
        validation_alias="kgv", default=None, description="Your villages; None when not sent or unreadable"
    )
    protection: KingdomProtection | None = Field(
        validation_alias="uap",
        default=None,
        description="Your protection in a kingdom; None when not sent or unreadable",
    )
    second_protection: KingdomProtection | None = Field(
        validation_alias="gac",
        default=None,
        description="A second protection block, read as a uap; None when not sent or unreadable",
    )
    alliance: AllianceMembershipResponse | None = Field(
        validation_alias="gal", default=None, description="Your alliance membership; None when not sent or unreadable"
    )
    food_production: FoodProductionStatus | None = Field(
        validation_alias="DTS",
        default=None,
        description="Your food production status; None when not sent or unreadable",
    )
    movement_filter: MovementFilterResponse | None = Field(
        validation_alias="mvf", default=None, description="The map's movement filters; None when not sent or unreadable"
    )
    max_spies: MaxSpiesResponse | None = Field(
        validation_alias="gms", default=None, description="Your spies before boosts; None when not sent or unreadable"
    )
    alliance_info: GetAllianceInfoResponse | None = Field(
        validation_alias="ain", default=None, description="Your alliance's details; None when not sent or unreadable"
    )
    alliance_help: AllianceHelpListResponse | None = Field(
        validation_alias="ahl",
        default=None,
        description="Your alliance's help requests; None when not sent or unreadable",
    )
    alliance_chat: AllianceChatLogResponse | None = Field(
        validation_alias="acl",
        default=None,
        description="Your alliance's chat history; None when not sent or unreadable",
    )
    boosters: BoosterInfoResponse | None = Field(
        validation_alias="boi", default=None, description="Your boosters; None when not sent or unreadable"
    )
    trigger_events: TriggerEventsResponse | None = Field(
        validation_alias="tei", default=None, description="The running trigger events; None when not sent or unreadable"
    )
    events: SpecialEventsResponse | None = Field(
        validation_alias="sei", default=None, description="The running events; None when not sent or unreadable"
    )
    treasure_maps: TreasureMapsResponse | None = Field(
        validation_alias="tmp", default=None, description="Your treasure maps; None when not sent or unreadable"
    )
    treasure_hunt: TreasureHuntInfoResponse | None = Field(
        validation_alias="thi", default=None, description="Your treasure hunt; None when not sent or unreadable"
    )
    system_notifications: SystemNotificationEvent | None = Field(
        validation_alias="sne",
        default=None,
        description="Your mailbox's notifications; None when not sent or unreadable",
    )
    messages_sent_today: MessagesSentToday | None = Field(
        validation_alias="mcd",
        default=None,
        description="The messages you sent today; None when not sent or unreadable",
    )
    might_points: MightPointsResponse | None = Field(
        validation_alias="gmu", default=None, description="Your might points; None when not sent or unreadable"
    )
    achievements: AchievementsResponse | None = Field(
        validation_alias="vli", default=None, description="Your achievements; None when not sent or unreadable"
    )
    tax: TaxInfoResponse | None = Field(
        validation_alias="txi", default=None, description="Your tax; None when not sent or unreadable"
    )
    research: ResearchInfoResponse | None = Field(
        validation_alias="rei", default=None, description="Your research; None when not sent or unreadable"
    )
    kingdoms: KingdomInfoResponse | None = Field(
        validation_alias="kpi",
        default=None,
        description="Your kingdoms' unlocks and transfers; None when not sent or unreadable",
    )
    berimond_kingdom_status: BerimondKingdomStatus | None = Field(
        validation_alias=AliasPath("kpi", "fki"),
        default=None,
        description="The Battle for Berimond's kingdom status the kpi carries; None when not sent or unreadable",
    )
    relocation: RelocationInfoResponse | None = Field(
        validation_alias="gri", default=None, description="Your castle relocation; None when not sent or unreadable"
    )
    plague_doctors: PlagueDoctorInfoResponse | None = Field(
        validation_alias="cpi", default=None, description="Your plague doctors; None when not sent or unreadable"
    )
    commanders: CommanderRoster | None = Field(
        validation_alias="gli",
        default=None,
        description="Your commanders and castellans; None when not sent or unreadable",
    )
    daily_quests: DailyQuests | None = Field(
        validation_alias="dql", default=None, description="Your daily quests; None when not sent or unreadable"
    )
    daily_reset: DailyResetResponse | None = Field(
        validation_alias="drt", default=None, description="The daily reset; None when not sent or unreadable"
    )
    mercenary_missions: MercenaryMissionsResponse | None = Field(
        validation_alias="mpe", default=None, description="Your mercenary missions; None when not sent or unreadable"
    )
    vip: VipStatusResponse | None = Field(
        validation_alias="vip", default=None, description="Your VIP status; None when not sent or unreadable"
    )
    permanent_castles: PermanentCastleDataResponse | None = Field(
        validation_alias="gpc", default=None, description="Your permanent castles; None when not sent or unreadable"
    )
    inventory_space: InventorySpace | None = Field(
        validation_alias="esl",
        default=None,
        description="Your equipment and gem inventory space; None when not sent or unreadable",
    )
    new_relics: NewRelicsResponse | None = Field(
        validation_alias="nrf",
        default=None,
        description="Whether new relics wait to be seen; None when not sent or unreadable",
    )
    wishing_well: WishingWellResponse | None = Field(
        validation_alias="rww", default=None, description="The ruby wishing well; None when not sent or unreadable"
    )
    castle_details: GetDetailedCastleResponse | None = Field(
        validation_alias="dcl", default=None, description="Your castles' details; None when not sent or unreadable"
    )
    officer_training: OfficerTraining | None = Field(
        validation_alias="gatp",
        default=None,
        description="The officers' school training running, unset when none runs; None when not sent or unreadable",
    )
    boosted_global_effects: BoostedGlobalEffectsResponse | None = Field(
        validation_alias="bie",
        default=None,
        description="Your boosted global effects; None when not sent or unreadable",
    )
    loot_boxes: LootBoxesResponse | None = Field(
        validation_alias="gls", default=None, description="Your loot boxes; None when not sent or unreadable"
    )
    gems: GemInventoryResponse | None = Field(
        validation_alias="ggm", default=None, description="Your gems and relic gems; None when not sent or unreadable"
    )
    gifts: PlayerGiftsResponse | None = Field(
        validation_alias="pgl", default=None, description="Your gifts; None when not sent or unreadable"
    )
    skills: SkillList | None = Field(
        validation_alias="skl", default=None, description="Your Legendary skills; None when not sent or unreadable"
    )
    construction_item_expiry: ConstructionItemExpiryResponse | None = Field(
        validation_alias="nec",
        default=None,
        description="Your expiring construction items; None when not sent or unreadable",
    )
    attack_counter: AttackCounterResponse | None = Field(
        validation_alias="gai", default=None, description="Your attack counter; None when not sent or unreadable"
    )
    construction_items: ConstructionItemInventory | None = Field(
        validation_alias="gii",
        default=None,
        description="The construction items in storage; None when not sent or unreadable",
    )
    construction_item_space: ConstructionItemSpace | None = Field(
        validation_alias="csp",
        default=None,
        description="Free construction item storage; None when not sent or unreadable",
    )
    resource_pool: ResourcePoolResponse | None = Field(
        validation_alias="irc",
        default=None,
        description="What the citizen in your castle carries; None when not sent or unreadable",
    )

    @property
    def sent_sections(self) -> set[str]:
        """The wire keys of the sections sent, falsy and unreadable ones too."""
        return {_WIRE_KEYS[name] for name in self.model_fields_set if name in _WIRE_KEYS}

    @field_validator(
        "honor",
        "identity",
        "glory_points",
        "glory_title_reset",
        "title_ranks",
        "credentials",
        "special_currencies",
        "coat_of_arms",
        "premium_flag",
        "currencies",
        "experience",
        "castles",
        "monument_reset",
        "laboratory_reset",
        "royal_towers",
        "monuments",
        "laboratories",
        "villages",
        "protection",
        "second_protection",
        "alliance",
        "food_production",
        "movement_filter",
        "max_spies",
        "alliance_info",
        "alliance_help",
        "alliance_chat",
        "boosters",
        "trigger_events",
        "events",
        "treasure_maps",
        "treasure_hunt",
        "system_notifications",
        "messages_sent_today",
        "might_points",
        "achievements",
        "tax",
        "research",
        "kingdoms",
        "berimond_kingdom_status",
        "relocation",
        "plague_doctors",
        "commanders",
        "daily_quests",
        "daily_reset",
        "mercenary_missions",
        "vip",
        "permanent_castles",
        "inventory_space",
        "new_relics",
        "wishing_well",
        "castle_details",
        "boosted_global_effects",
        "loot_boxes",
        "gems",
        "gifts",
        "skills",
        "construction_item_expiry",
        "attack_counter",
        "construction_items",
        "construction_item_space",
        "resource_pool",
        mode="wrap",
    )
    @classmethod
    def _section(cls, value: Any, handler: ValidatorFunctionWrapHandler, info: ValidationInfo) -> Any:
        gate = _GATES.get(info.field_name)
        if not js_truthy(value) or (gate is not None and not (isinstance(value, dict) and js_truthy(value.get(gate)))):
            return None
        return read_or_none(handler, value, warn=logger, what=f"the {info.field_name} login section")

    @field_validator("officer_training", mode="wrap")
    @classmethod
    def _officer_training(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        # parse_GATP (split.js line 715112) ends the running training on a falsy block
        if not js_truthy(value):
            return OfficerTraining()
        return read_or_none(handler, value, warn=logger, what="the officer_training login section")

    @model_validator(mode="before")
    @classmethod
    def _messages_sent_today(cls, data: Any) -> Any:
        if isinstance(data, dict) and not js_truthy(data.get("mcd")) and js_truthy(data.get("MTC")):
            return {**data, "mcd": {"MTC": data["MTC"]}}
        return data


_GATES: dict[str | None, str] = {"boosted_global_effects": "GE", "gifts": "G", "messages_sent_today": "MTC"}


_WIRE_KEYS = {
    name: field.validation_alias
    for name, field in LoginDataResponse.model_fields.items()
    if name not in BaseResponse.model_fields and isinstance(field.validation_alias, str)
}
