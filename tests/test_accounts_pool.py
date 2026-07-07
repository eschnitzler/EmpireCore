"""Tests for account loading and the account pool."""

import json

import pytest

import empire_core.pool as pool_module
from empire_core.accounts import Account, AccountRegistry
from empire_core.pool import AccountPool


class TestAccountRegistryEnv:
    def test_csv_env_account(self, monkeypatch):
        monkeypatch.setenv("EMPIRE_ACCOUNT_MAIN", "user1,pass1,EmpireEx_21")
        registry = AccountRegistry()
        registry.load(file_path="nonexistent.json")
        acc = registry.get_by_alias("main")
        assert acc is not None
        assert acc.username == "user1"
        assert acc.password == "pass1"

    def test_json_env_account_with_comma_password(self, monkeypatch):
        payload = json.dumps({"username": "user2", "password": "pa,ss,word", "world": "EmpireEx_21"})
        monkeypatch.setenv("EMPIRE_ACCOUNT_ALT", payload)
        registry = AccountRegistry()
        registry.load(file_path="nonexistent.json")
        acc = registry.get_by_username("user2")
        assert acc is not None
        assert acc.password == "pa,ss,word"
        assert acc.alias == "alt"

    def test_env_takes_priority_over_file(self, monkeypatch, tmp_path):
        accounts_file = tmp_path / "accounts.json"
        accounts_file.write_text(json.dumps([{"username": "shared", "password": "from_file"}]))
        monkeypatch.setenv("EMPIRE_ACCOUNT_X", "shared,from_env")

        registry = AccountRegistry()
        registry.load(file_path=str(accounts_file))
        acc = registry.get_by_username("shared")
        assert acc is not None
        # Documented priority: env wins
        assert acc.password == "from_env"
        # And no duplicate entry exists
        assert len([a for a in registry.get_all() if a.username == "shared"]) == 1

    def test_invalid_csv_skipped(self, monkeypatch):
        monkeypatch.setenv("EMPIRE_ACCOUNT_BAD", "only_username")
        registry = AccountRegistry()
        registry.load(file_path="nonexistent.json")
        assert registry.get_by_alias("bad") is None

    def test_inactive_file_accounts_skipped(self, tmp_path):
        accounts_file = tmp_path / "accounts.json"
        accounts_file.write_text(
            json.dumps(
                [
                    {"username": "on", "password": "p"},
                    {"username": "off", "password": "p", "active": False},
                ]
            )
        )
        registry = AccountRegistry()
        registry.load(file_path=str(accounts_file))
        assert registry.get_by_username("on") is not None
        assert registry.get_by_username("off") is None


class FakeClient:
    def __init__(self, username: str, login_ok: bool = True):
        self.username = username
        self.is_logged_in = False
        self.closed = False
        self._login_ok = login_ok

    def login(self) -> bool:
        self.is_logged_in = self._login_ok
        return self._login_ok

    def close(self) -> None:
        self.closed = True
        self.is_logged_in = False


class FakeRegistry:
    def __init__(self, accounts: list[Account]):
        self._accounts = accounts

    def get_all(self) -> list[Account]:
        return self._accounts


@pytest.fixture
def fake_accounts(monkeypatch):
    accs = [
        Account(username="alpha", password="p", tags=["Farmer"]),
        Account(username="beta", password="p", tags=["scanner"]),
    ]
    clients: dict[str, FakeClient] = {}

    def fake_get_client(self: Account):
        client = FakeClient(self.username)
        clients[self.username] = client
        return client

    monkeypatch.setattr(pool_module, "accounts", FakeRegistry(accs))
    monkeypatch.setattr(Account, "get_client", fake_get_client)
    return accs, clients


class TestAccountPool:
    def test_lease_and_release(self, fake_accounts):
        _, clients = fake_accounts
        pool = AccountPool()
        client = pool.lease()
        assert client is not None
        assert pool.busy_count == 1

        pool.release(client)
        assert pool.busy_count == 0
        assert clients[client.username].closed

    def test_release_closes_non_logged_in_client(self, fake_accounts):
        # A client leased with login=False must still be closed on release,
        # otherwise its websocket and receive thread leak.
        _, clients = fake_accounts
        pool = AccountPool()
        client = pool.lease(login=False)
        assert client is not None
        assert not client.is_logged_in

        pool.release(client)
        assert clients[client.username].closed

    def test_tag_filter_case_insensitive(self, fake_accounts):
        pool = AccountPool()
        client = pool.lease(tag="farmer")
        assert client is not None
        assert client.username == "alpha"

    def test_busy_account_not_re_leased(self, fake_accounts):
        pool = AccountPool()
        first = pool.lease(username="alpha")
        assert first is not None
        second = pool.lease(username="alpha")
        assert second is None

    def test_get_client_failure_does_not_crash(self, fake_accounts, monkeypatch):
        # account.get_client() raising must not blow up with UnboundLocalError
        def broken_get_client(self: Account):
            raise RuntimeError("cannot build client")

        monkeypatch.setattr(Account, "get_client", broken_get_client)
        pool = AccountPool()
        assert pool.lease() is None
        assert pool.busy_count == 0
