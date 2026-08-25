"""Smoke tests: the package imports, and a client can be built offline.

Everything here goes through the real ``EmpireClient.__init__`` (the deeper
suites hand-wire instances with ``__new__``), so this is what catches a
constructor that starts reaching for the network or forgets to attach a
service.
"""

import threading

import empire_core
from empire_core import EmpireClient
from empire_core.services import (
    AllianceService,
    ArmyService,
    CastleService,
    CommandersService,
    RankingService,
    SpyService,
    get_registered_services,
)

SERVICE_TYPES = {
    "alliance": AllianceService,
    "castle": CastleService,
    "army": ArmyService,
    "commanders": CommandersService,
    "spy": SpyService,
    "ranking": RankingService,
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


def test_every_registered_service_is_attached_to_a_real_client() -> None:
    client = EmpireClient(username="user", password="pass")
    try:
        for name, service_type in SERVICE_TYPES.items():
            service = getattr(client, name)
            assert isinstance(service, service_type), name
            assert service.client is client
        # No registered service may go unattached, or client.<name> would be a
        # silent AttributeError for consumers.
        for name in get_registered_services():
            assert hasattr(client, name), name
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
