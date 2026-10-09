"""One consent for spending rubies: every service call that can spend them takes ``spend_rubies``, and only that."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

import pytest

import empire_core
from empire_core.services import BaseService

CONSENT_NAME = re.compile(r"rub(y|ies)|premium|c2|pay|spend|cost", re.IGNORECASE)

NOT_CONSENT = {
    "use_premium_commander": "picks the premium commander to lead; the rubies it may cost need spend_rubies",
}

SPENDERS = {
    "AllianceService": {"donate"},
    "ArmyService": {"produce_units", "double_production_slot", "heal_units", "heal_all", "skip_heal"},
    "AttackService": {"send_attack"},
    "CastleService": {
        "rename",
        "build",
        "upgrade_building",
        "finish_construction",
        "upgrade_defense",
        "repair_building",
        "repair_all",
        "buy_expansion",
        "start_tax",
        "send_resources",
        "send_support",
        "send_troops",
    },
    "CommandersService": {"premium_send"},
    "PlayerService": {"start_research"},
    "SpyService": {"send_spy_mission", "send_instant_spy", "execute_instant_spy", "send_sabotage"},
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


def _methods(service: type[BaseService]) -> list[tuple[str, inspect.Signature]]:
    return [
        (name, inspect.signature(member))
        for name, member in inspect.getmembers(service, inspect.isfunction)
        if not name.startswith("_")
    ]


def test_every_ruby_consent_is_a_keyword_only_spend_rubies_that_defaults_to_false() -> None:
    wrong = []
    for service_name, service in _services().items():
        for method, signature in _methods(service):
            for param in signature.parameters.values():
                if param.annotation not in ("bool", bool) or not CONSENT_NAME.search(param.name):
                    continue
                if param.name in NOT_CONSENT:
                    continue
                if (param.name, param.kind, param.default) != ("spend_rubies", param.KEYWORD_ONLY, False):
                    wrong.append(f"{service_name}.{method}({param})")
    assert not wrong, f"name the consent to spend rubies `*, spend_rubies: bool = False`: {wrong}"


@pytest.mark.parametrize(("service_name", "method"), [(s, m) for s, methods in SPENDERS.items() for m in methods])
def test_each_call_that_can_spend_rubies_asks_for_spend_rubies(service_name: str, method: str) -> None:
    signature = inspect.signature(getattr(_services()[service_name], method))
    assert "spend_rubies" in signature.parameters


def test_the_list_of_spenders_is_every_method_with_spend_rubies() -> None:
    with_consent = {
        (service_name, method)
        for service_name, service in _services().items()
        for method, signature in _methods(service)
        if "spend_rubies" in signature.parameters
    }
    listed = {(s, m) for s, methods in SPENDERS.items() for m in methods}
    assert with_consent == listed
