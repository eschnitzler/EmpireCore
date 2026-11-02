"""The login data (``gbd``), every section of it read through that section's own model."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, ValidationInfo, ValidatorFunctionWrapHandler, field_validator

from empire_core.alliance.models.chat import AllianceChatLogResponse
from empire_core.alliance.models.help import AllianceHelpListResponse
from empire_core.alliance.models.info import GetAllianceInfoResponse
from empire_core.attack.models.counter import AttackCounterResponse
from empire_core.castle.models.castles import GetCastlesResponse
from empire_core.castle.models.details import GetDetailedCastleResponse
from empire_core.castle.models.kingdoms import KingdomInfoResponse
from empire_core.castle.models.landmarks import (
    KingsTowerListResponse,
    LaboratoryListResponse,
    LaboratoryResetResponse,
    MonumentListResponse,
    MonumentResetResponse,
)
from empire_core.castle.models.mercenaries import MercenaryMissionsResponse
from empire_core.castle.models.permanent import PermanentCastleDataResponse
from empire_core.castle.models.research import ResearchInfoResponse
from empire_core.castle.models.tax import TaxInfoResponse
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse
from empire_core.castle.models.villages import VillageListResponse
from empire_core.castle.models.wishing_well import WishingWellResponse
from empire_core.commanders.models.inventory import GemInventoryResponse, InventorySpace, NewRelicsResponse
from empire_core.commanders.models.roster import GetCommandersResponse
from empire_core.commanders.models.skills import GetSkillsResponse
from empire_core.events.models import SpecialEventsResponse, TriggerEventsResponse
from empire_core.map.models.treasure_maps import TreasureHuntInfoResponse, TreasureMapsResponse
from empire_core.messages.models.mailbox import MessagesSentToday, SystemNotificationEvent
from empire_core.movements.models.movement import MovementFilterResponse
from empire_core.player.models.account import (
    BoostedGlobalEffectsResponse,
    DailyResetResponse,
    FoodProductionStatus,
    PlayerGiftsResponse,
)
from empire_core.player.models.coat_of_arms import CoatOfArmsResponse
from empire_core.player.models.credentials import CredentialsStatus
from empire_core.player.models.economy import LootBoxesResponse
from empire_core.player.models.login import (
    Alliance,
    CurrencyResponse,
    ExperienceResponse,
    HonorResponse,
    PlayerIdentityResponse,
    SpecialCurrenciesResponse,
    VipStatusResponse,
)
from empire_core.player.models.progress import (
    AchievementsResponse,
    BoosterInfoResponse,
    GloryPointsResponse,
    GloryTitleResetResponse,
    MightPointsResponse,
    RelocationInfoResponse,
    TitleRanksResponse,
)
from empire_core.player.models.protection import ProtectionResponse
from empire_core.protocol.base import BaseResponse, read_or_none
from empire_core.quests.models import DailyQuests
from empire_core.spy.models import MaxSpiesResponse, PlagueDoctorInfoResponse

logger = logging.getLogger(__name__)


class LoginDataResponse(BaseResponse):
    """
    The login data: every section the client reads after logging in, each through its section's model.

    A section that is not sent, or that its model cannot read, is None; the rest of the login data still
    reads. Sections the library has no model for yet stay as extras. The client reads ``mcd`` from the
    whole payload when the section is missing, and ``nsm`` as a negated flag; neither is modelled here.

    Command: gbd, pushed after a login; ``client.state`` applies each section as it comes.

    Client: ``GBDCommand.exec`` (bundle line 129425), which hands each section to its parser in the order
    the fields here follow (bundle line 129430)
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
    kings_towers: KingsTowerListResponse | None = Field(
        validation_alias="gkl", default=None, description="Your kings' towers; None when not sent or unreadable"
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
    protection: ProtectionResponse | None = Field(
        validation_alias="uap",
        default=None,
        description="Your protection in a kingdom; None when not sent or unreadable",
    )
    second_protection: ProtectionResponse | None = Field(
        validation_alias="gac",
        default=None,
        description="A second protection block, read as a uap; None when not sent or unreadable",
    )
    alliance: Alliance | None = Field(
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
    relocation: RelocationInfoResponse | None = Field(
        validation_alias="gri", default=None, description="Your castle relocation; None when not sent or unreadable"
    )
    plague_doctors: PlagueDoctorInfoResponse | None = Field(
        validation_alias="cpi", default=None, description="Your plague doctors; None when not sent or unreadable"
    )
    commanders: GetCommandersResponse | None = Field(
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
    skills: GetSkillsResponse | None = Field(
        validation_alias="skl", default=None, description="Your legend skills; None when not sent or unreadable"
    )
    construction_item_expiry: ConstructionItemExpiryResponse | None = Field(
        validation_alias="nec",
        default=None,
        description="Your expiring construction items; None when not sent or unreadable",
    )
    attack_counter: AttackCounterResponse | None = Field(
        validation_alias="gai", default=None, description="Your attack counter; None when not sent or unreadable"
    )

    @field_validator(
        "honor",
        "identity",
        "glory_points",
        "glory_title_reset",
        "title_ranks",
        "credentials",
        "special_currencies",
        "coat_of_arms",
        "currencies",
        "experience",
        "castles",
        "monument_reset",
        "laboratory_reset",
        "kings_towers",
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
        mode="wrap",
    )
    @classmethod
    def _section(cls, value: Any, handler: ValidatorFunctionWrapHandler, info: ValidationInfo) -> Any:
        if value is None:
            return None
        return read_or_none(handler, value, warn=logger, what=f"the {info.field_name} login section")
