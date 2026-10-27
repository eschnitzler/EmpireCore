"""One consent for spending rubies: every service call that can spend them takes ``spend_rubies``, and only that."""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
import textwrap

import empire_core
from empire_core.services import BaseService

RUBY_REQUESTS = {
    "SkipDungeonCooldownRequest": "sdc, ruby full skip (SkippableCooldownDialog.skipWithRubies, bundle28197–28199)",
    "AllianceUpgradeRequest": "aug, alliance treasury C2 (bundle 91235/70592)",
    "ForgeCraftRequest": "frc, UPRAF 1 pays the relic forge in C2 (bundle line 69578; dll line 18809)",
    "CancelGrandTournamentQuestRequest": "caaq, quest cancelCostC2 defaults199 (current bundle111092)",
    "SkipGrandTournamentCooldownRequest": "scq, getCooldownSkipCosts returns999 (current bundle34981)",
    "FoundAllianceRequest": "afo, non-premium account base C2 price (bundle 44124; dll 18805)",
    "ChangeAllianceNameRequest": "acn, FR==0 charges RENAME_COST_C2 (bundle 69791–69792; dll 18805)",
    "DoubleProductionSlotRequest": "bou, always rubies (getUnitDoublingCosts, bundle line 23546)",
    "SkipHealRequest": "hss, always rubies (updateSkipTooltip, bundle line 83582)",
    "SkipProductionSlotRequest": "sou, always rubies (updateSkipTooltip, bundle line 23557)",
    "UpdateRecruitmentLoopRequest": "url, the loop fee in rubies (AutoRecruitmentPriceData.getCosts, bundle 142396)",
    "DuplicateRecruitmentLoopRequest": "drl, each target's DC rubies (AutoRecruitmentCosts, bundle line 23833)",
    "HealAllRequest": "hra, its C2 price (openReviveAllDialog, bundle lines 83509-83513)",
    "HealUnitsRequest": "hru, a unit's healingCostC2 (bundle line 51110)",
    "RepairAllRequest": "ira, always rubies (getTotalRepairCostC2, bundle line 131460)",
    "FastCompleteRequest": "fco, rubies past the free skip time (calculateSkipCosts, bundle line 139849)",
    "BuyExtensionRequest": "ebe, PREMIUM (CastleExpansionVE, bundle line 86849)",
    "RenameCastleRequest": "arc, CHANGE_CASTLE_NAME_C2 (bundle line 57219)",
    "DonateRequest": "ado, donated C2",
    "ProduceUnitsRequest": "bup, PWR 1 and the unit's costC2 (bundle lines 35218, 19248)",
    "BuildRequest": "ebu, PWR 1 and the building's costC2 (bundle lines 35215, 17950)",
    "UpgradeBuildingRequest": "eup, PWR 1 and the next level's costC2 (bundle line 41106)",
    "UpgradeWallRequest": "eud, PWR 1 and the next level's costC2 (bundle line 35220)",
    "RepairBuildingRequest": "rbu, PWR 1 (bundle line 35221)",
    "SendSupportRequest": "cds, BPC, a ruby horse, a slowdown (getTotalCostsC2, bundle line 27330)",
    "SendTroopsRequest": "same as cds",
    "CreateAttackRequest": "cra, BPC, a ruby horse, a slowdown",
    "HorizonAttackRequest": "abgcam, same as cra",
    "OuterRealmsAttackRequest": "cam, same as cra",
    "SelectSpecialServerCastleRequest": "tsc, OC2 for a castle priced in C2 (bundle line 27953)",
    "RerollChargeCampEffectRequest": "ccr, the reroll's c2Cost (bundle line 140279)",
    "SendTowerSupportRequest": "tde, same as cds",
    "TreasureHuntAttackRequest": "thm, BPC, a ruby horse",
    "CreateMarketMovementRequest": "crm, a ruby horse, a slowdown",
    "SendSpyRequest": "csm, a ruby horse, a slowdown",
    "StartTaxRequest": "txs, tax types 5 and 6 (TAX_RUBY_COSTS)",
    "StartResearchRequest": "res, a research priced in C2",
    "MercenaryPackageRequest": "mpe, the ruby skip of a running mission (MercenaryConst.getSkipC2Cost)",
    "RefreshMercenaryMissionRequest": "rmm, MercenaryConst.REFRESH_MISSION_COST (dll line 19511)",
    "BribeTaxCollectorRequest": "btx, taxBribeVO.finalCostsC2 (CastleBribeDialog.onClick, bundle line 90878)",
    "ResetSkillsRequest": "skr inside the reset cooldown (LegendSkillConst.resetSkipCostC2, skipWithRubies)",
    "SelectBerimondCampRequest": "fsc, OC2 for the ruby camp and PWR (bundle lines 95197, 35237, 142354)",
    "StartPeaceModeRequest": "mps, PlayerConst.PEACE_MODE_C2 (dll line 19560)",
    "StartFactionProtectionRequest": "ffp, FactionConst.getPeaceC2Cost (dll line 19316)",
    "BuyToolsRequest": "ibt, the tool's costC2 (bundle line 22493)",
    "UnlockPresetRequest": "uas, the slot's attackSetupSlots costC2 (bundle line 141850)",
    "ActivateAllianceTowerBuffsRequest": "aatb, getAllianceTowerEffectActivationCost in C2 (bundle line 70999)",
    "IncreaseAllianceTowerBuffsRequest": "iatb, the buffs' calculateBuffCosts in C2 (bundle line 71048)",
    "RerollAlienCampRequest": "rae with C2 (CastleRerollAlienDialog.onSendReroll, bundle line 109749)",
    "BuyTreasureMapPiecesRequest": "tbm, costPiece C2 a piece (CastleTreasureBuyPieceDialog, bundle line 67945)",
    "TreasureMapTransferSkipRequest": "tkt, the map's skipCostC2 (bundle line 99514)",
    "KingdomSkipTransferRequest": "kst, the kingdom's skip travel C2 cost (bundle line 98398)",
    "SelectKingdomCastleRequest": "ksc, OC2 for the ruby castle and PWR (bundle lines 55479, 35239)",
    "SelectSeasonCampRequest": "csc, OC2 for the ruby camp and PWR (bundle lines 55482, 35238)",
    "RelocateCastleRequest": "rst, RELOCATION_COST_C2 after the first (bundle line 109656, dll line 19674)",
    "SkipCraftingRequest": "crsk, PC2 rubies (CraftingSlotVO.getAdjustedSkipCostC2, bundle line 17012)",
    "SkipConstructionCraftingRequest": "sci, PWR 1 and MST - (bundle line 79930)",
    "RefillFusionForgeRequest": "fsr, FSRP 1 (getC2PriceForEnergyPremiumSkip, bundle line 142206)",
    "FuseDecorationRequest": "dff, FFFP 1, the premium fusion (bundle line 35455)",
    "CraftEquipmentRequest": "ceq, EX 1 takes the gems back for removalCostC2 (bundle line 74260)",
    "EnchantEquipmentRequest": "eqe, C2 1 (bundle line 59448)",
    "EnchantRelicRequest": "ere, C2 1 (RelicUpgradeDialogPayment.getCosts, bundle line 86002)",
    "CraftGemRequest": "cge, C2 1, the ruby craft (bundle line 73943)",
    "ExtractGemRequest": "ege, a gem's removalCostC2 (CastleExtractSocketDialog.getCosts, bundle line 65738)",
    "UnlockSymbolRequest": "bus, a premium symbol's costC2 (CastleBuyUnlockedCrestSymbolDialog, bundle line 77181)",
    "ChangePlayerNameRequest": "cpne, playerNameChanges costC2 after the first (getCurrentC2Cost, bundle line 145462)",
    "WheelOfFortuneBuyJackpotRequest": "lwj, LuckyWheelData.jackpotC2Price (bundle line 17639)",
    "WheelOfFortuneIncreaseWinClassRequest": "lwc, LuckyWheelData.increaseWinClassC2 (bundle line 17628)",
    "GachaSpinRequest": "dge, the gacha's cost list from game data the library does not load (bundle line 113936)",
    "BuyArtifactPieceRequest": "sap, artifactPartCosts in C2 (CastleArtifactBuyPieceDialog.setAmount, bundle 114756)",
    "SkipShadyLadyTargetRequest": "bst, targetSkipCostC2 (bundle line 114944)",
    "FortuneTellerReadingRequest": "ftl, the reading's c2Cost (FortuneTellerClassVO.parseXML, bundle line 145167)",
    "DonateItemsRequest": "ddi, an item whose resource is C2 (unfilteredAmountInInventory, bundle line 115730)",
    "ActivateTrainingProgramRequest": "atp, slot 3's program costs c2Cost (OfficersSchoolEffectVO.getCost, 144773)",
    "ProlongTrainingProgramRequest": "ptp, always rubies (OfficersSchoolData.getC2ProlongCosts, bundle line 144743)",
    "RerollTrainingProgramsRequest": "rtp, P 1 is the ruby reroll (hardRerollCosts, bundle line 85714)",
    "UnlockEventRequest": "ule, SC 1 pays the missing resource in rubies (bundle lines 37628, 67853)",
    "SelectEventDifficultyRequest": "sede, C2U 1 rents a locked difficulty for its rentC2Cost (bundle line 145390)",
}

SENT_WITHOUT_CONSENT = {
    "PlayerService.cancel_peace_mode": "mps with -1 ends peace mode; cancelPeaceMode names no price",
    "CastleService.list_missions": "mpe with no mission id only lists the missions",
    "CastleService.start_mission": "sends mpe only for an open mission while none runs, which costs coins",
    "CastleService.collect_mission": "sends mpe only for a mission the client would collect for 0 rubies",
    "CastleService.skip_construction_crafting_time": "sci with a minute skip and PWR 0 spends the skip item",
}

CONSENT_WITHOUT_REQUEST = {
    "CommandersService.premium_send": "the premium commander check the army sends run through",
}

CONSENT_LIKE = re.compile(r"rub(y|ies)|premium|c2|pay|spend|cost|skip|instant|buy|boost|finish|free", re.IGNORECASE)

NOT_CONSENT = {
    "use_premium_commander": "picks the premium commander to lead; the rubies it may cost need spend_rubies",
    "ruby_cost": "heal_all's wire price, which the server checks against the hospital",
    "minute_skip": "a minute skip item, not rubies",
    "horse_booster_id": "picks the horse; one priced in rubies needs spend_rubies",
    "collector_booster": "collector event booster items, not rubies",
    "samurai_medal_boosters": "samurai event booster items, not rubies",
    "shogun_point_boosters": "samurai event booster items, not rubies",
    "yard_boost": "the courtyard capacity effect a fill sizes against, not a purchase",
    "admit_ruby_units": "whether the hospital takes in wounded ruby units, a free setting",
    "pay_with_rubies": "picks the relic forge's ruby price over its coin price; spending them needs spend_rubies",
    "free": "the generals hub's free spin, against a paid one that spends offerings, not rubies",
    "ruby_price": "picks a prebuilt castle's ruby price over its resource price; the rubies need spend_rubies",
    "premium": "picks the officers' school's ruby reroll; the rubies it costs need spend_rubies",
    "ruby_payment": "picks the resource an unlock pays in rubies; the rubies it costs need spend_rubies",
    "unlock_with_rubies": "picks a locked difficulty's ruby rent; the rubies it costs need spend_rubies",
    "food_boost": "the hunter's food production setting, not a purchase",
}


def _services() -> dict[str, type[BaseService]]:
    for info in pkgutil.walk_packages(empire_core.__path__, "empire_core."):
        importlib.import_module(info.name)
    found, todo = {}, list(BaseService.__subclasses__())
    while todo:
        service = todo.pop()
        found[service.__name__] = service
        todo += service.__subclasses__()
    return found


def _called_names(node: ast.AST) -> tuple[set[str], set[str]]:
    """The registered requests a function builds, and the ``self.<method>`` calls it makes."""
    requests, methods = set(), set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        while isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "self":
                methods.add(func.attr)
            if func.attr in RUBY_REQUESTS:
                requests.add(func.attr)
            func = func.value
        if isinstance(func, ast.Name) and func.id in RUBY_REQUESTS:
            requests.add(func.id)
        # One of several requests picked in place: (A if flag else B if other else C)(...)
        if isinstance(func, ast.IfExp):
            requests |= {node.id for node in ast.walk(func) if isinstance(node, ast.Name)} & RUBY_REQUESTS.keys()
    return requests, methods


def _ruby_senders(service: type[BaseService]) -> dict[str, set[str]]:
    """Each method of the service with the registered requests it builds, itself or through ``self``."""
    direct: dict[str, set[str]] = {}
    calls: dict[str, set[str]] = {}
    for name, member in inspect.getmembers(service, inspect.isfunction):
        owner = next(klass for klass in service.__mro__ if name in vars(klass))
        if owner is not service and issubclass(owner, BaseService):
            continue
        tree = ast.parse(textwrap.dedent(inspect.getsource(member)))
        direct[name], calls[name] = _called_names(tree)
    reached = {name: set(found) for name, found in direct.items()}
    changed = True
    while changed:
        changed = False
        for name, callees in calls.items():
            for callee in callees & reached.keys():
                if not reached[callee] <= reached[name]:
                    reached[name] |= reached[callee]
                    changed = True
    return {name: found for name, found in reached.items() if found}


def _takes_consent(method: object) -> bool:
    param = inspect.signature(method).parameters.get("spend_rubies")  # type: ignore[arg-type]
    return param is not None and param.kind is param.KEYWORD_ONLY and param.default is False


def test_every_public_call_that_sends_a_ruby_request_takes_spend_rubies() -> None:
    missing = []
    for service_name, service in _services().items():
        for method, requests in _ruby_senders(service).items():
            qualified = f"{service_name}.{method}"
            if method.startswith("_") or qualified in SENT_WITHOUT_CONSENT:
                continue
            if not _takes_consent(getattr(service, method)):
                missing.append(f"{qualified} sends {sorted(requests)}")
    assert not missing, f"take `*, spend_rubies: bool = False` or list the reason: {missing}"


def test_spend_rubies_is_only_on_calls_that_can_spend_rubies() -> None:
    stray = []
    for service_name, service in _services().items():
        senders = _ruby_senders(service)
        for method, member in inspect.getmembers(service, inspect.isfunction):
            qualified = f"{service_name}.{method}"
            if method.startswith("_"):
                continue
            if "spend_rubies" in inspect.signature(member).parameters and method not in senders:
                if qualified not in CONSENT_WITHOUT_REQUEST:
                    stray.append(qualified)
    assert not stray, stray


def test_no_other_name_asks_for_rubies() -> None:
    wrong = []
    for service_name, service in _services().items():
        for method, member in inspect.getmembers(service, inspect.isfunction):
            if method.startswith("_"):
                continue
            for param in inspect.signature(member).parameters.values():
                if not CONSENT_LIKE.search(param.name) or param.name in NOT_CONSENT:
                    continue
                if param.name != "spend_rubies" or not _takes_consent(member):
                    wrong.append(f"{service_name}.{method}({param})")
    assert not wrong, f"name the consent `*, spend_rubies: bool = False`, or list why it is none: {wrong}"


def test_the_allow_lists_name_real_methods() -> None:
    services = _services()
    for qualified in [*SENT_WITHOUT_CONSENT, *CONSENT_WITHOUT_REQUEST]:
        service_name, method = qualified.split(".")
        assert hasattr(services[service_name], method), qualified
