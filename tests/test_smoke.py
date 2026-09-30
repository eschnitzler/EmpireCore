"""Smoke tests: the package imports, and a client can be built offline.

Everything here goes through the real ``EmpireClient.__init__`` (the deeper
suites hand-wire instances with ``__new__``), so this is what catches a
constructor that starts reaching for the network or forgets to attach a
service.
"""

import threading

import empire_core
from empire_core import EmpireClient
from empire_core.alliance.service import AllianceService
from empire_core.army.service import ArmyService
from empire_core.attack.service import AttackService
from empire_core.castle.service import CastleService
from empire_core.commanders.service import CommandersService, EquipmentService, SkillsService
from empire_core.defense.service import DefenseService
from empire_core.events.service import EventsService
from empire_core.map.service import MapService
from empire_core.messages.service import MessagesService
from empire_core.movements.service import MovementsService
from empire_core.player.service import PlayerService
from empire_core.ranking.service import RankingService
from empire_core.services.base import BaseService
from empire_core.spy.service import SpyService

SERVICE_TYPES = {
    "alliance": AllianceService,
    "castle": CastleService,
    "army": ArmyService,
    "attack": AttackService,
    "commanders": CommandersService,
    "equipment": EquipmentService,
    "skills": SkillsService,
    "spy": SpyService,
    "ranking": RankingService,
    "map": MapService,
    "messages": MessagesService,
    "movements": MovementsService,
    "defense": DefenseService,
    "player": PlayerService,
    "events": EventsService,
}


def test_package_importable() -> None:
    assert empire_core is not None


def test_game_event_exported() -> None:
    from empire_core import GameEvent

    assert GameEvent is not None


def test_constructing_a_client_touches_no_network() -> None:
    # Construction must be cheap and offline: consumers build clients in
    # constructors, tests and config validation paths.
    client = EmpireClient(username="user", password="pass")
    try:
        assert client.connection.connected is False
        assert client.is_logged_in is False
    finally:
        client.close()


def test_constructing_a_client_starts_no_threads() -> None:
    before = threading.active_count()
    client = EmpireClient(username="user", password="pass")
    try:
        assert threading.active_count() == before
    finally:
        client.close()


def test_a_client_has_exactly_the_documented_services() -> None:
    client = EmpireClient(username="user", password="pass")
    try:
        for name, service_type in SERVICE_TYPES.items():
            service = getattr(client, name)
            assert type(service) is service_type, name
            assert service.client is client
        attached = {name for name, value in vars(client).items() if isinstance(value, BaseService)}
        assert attached == set(SERVICE_TYPES)
    finally:
        client.close()


def test_credentials_fall_back_to_the_config() -> None:
    from empire_core.config import EmpireConfig

    config = EmpireConfig(username="from-config", password="pw")
    client = EmpireClient(config=config)
    try:
        assert client.username == "from-config"
        assert client.password == "pw"
    finally:
        client.close()


def test_close_is_idempotent() -> None:
    client = EmpireClient(username="user", password="pass")
    client.close()
    client.close()
    assert client.is_logged_in is False
