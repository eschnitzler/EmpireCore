"""Tests for account loading and the account pool."""

import json
import logging
import os
import threading
import time

import pytest

import empire_core.pool as pool_module
from empire_core.accounts import Account, AccountRegistry
from empire_core.config import EmpireConfig
from empire_core.exceptions import LoginCooldownError, LoginError
from empire_core.pool import AccountPool


@pytest.fixture
def isolated_environ(monkeypatch):
    """Give the test a private os.environ so dotenv writes cannot leak."""
    monkeypatch.setattr(os, "environ", dict(os.environ))
    return os.environ


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

    def test_malformed_file_entry_does_not_log_password(self, tmp_path, caplog):
        accounts_file = tmp_path / "accounts.json"
        # Misspelled 'username': pydantic reports the missing field and, by default,
        # embeds the whole offending entry — password included — in its message.
        accounts_file.write_text(json.dumps([{"usrname": "bob", "password": "SuperSecret123"}]))
        registry = AccountRegistry()
        with caplog.at_level(logging.ERROR):
            registry.load(file_path=str(accounts_file))
        assert registry.get_by_username("bob") is None
        assert "SuperSecret123" not in caplog.text

    def test_dotenv_not_read_unless_opted_in(self, isolated_environ, monkeypatch, tmp_path):
        (tmp_path / ".env").write_text("EMPIRE_ACCOUNT_DOTENVOFF=dotuser,dotpass\n")
        monkeypatch.chdir(tmp_path)

        registry = AccountRegistry()
        registry.load(file_path="nonexistent.json")
        assert registry.get_by_alias("dotenvoff") is None
        assert "EMPIRE_ACCOUNT_DOTENVOFF" not in isolated_environ

    def test_dotenv_read_when_opted_in(self, isolated_environ, monkeypatch, tmp_path):
        (tmp_path / ".env").write_text("EMPIRE_ACCOUNT_DOTENVON=dotuser,dotpass\n")
        monkeypatch.chdir(tmp_path)

        registry = AccountRegistry()
        registry.load(file_path="nonexistent.json", load_env_file=True)
        acc = registry.get_by_alias("dotenvon")
        assert acc is not None
        assert acc.username == "dotuser"

    def test_malformed_env_json_does_not_log_password(self, monkeypatch, caplog):
        # Short entry on purpose: pydantic middle-truncates long input_value reprs,
        # which would hide the leak for incidental reasons rather than because it is fixed.
        monkeypatch.setenv("EMPIRE_ACCOUNT_B", '{"password": "SecretPW"}')
        registry = AccountRegistry()
        with caplog.at_level(logging.ERROR):
            registry.load(file_path="nonexistent.json")
        assert registry.get_by_alias("b") is None
        assert "SecretPW" not in caplog.text


class TestCredentialFileDocs:
    """accounts.json holds plaintext credentials; the API docs must say so."""

    @pytest.mark.parametrize("obj", [AccountRegistry, AccountRegistry._load_from_file])
    def test_loader_documents_file_permissions(self, obj):
        doc = obj.__doc__ or ""
        assert "plain text" in doc.lower(), f"{obj.__name__} docstring omits the plaintext warning"
        assert "chmod 600" in doc, f"{obj.__name__} docstring omits the permission guidance"


class SlowRegistry(AccountRegistry):
    """Registry whose load is slow enough to expose the lazy-load race."""

    ACCOUNT_COUNT = 3

    def __init__(self):
        super().__init__()
        self.load_calls = 0

    def load(self, file_path: str = "accounts.json", load_env_file: bool = False):
        self.load_calls += 1
        return super().load(file_path=file_path, load_env_file=load_env_file)

    def _load_from_env(self):
        for i in range(self.ACCOUNT_COUNT):
            self._add_account(Account(username=f"u{i}", password="p"))
            time.sleep(0.02)

    def _load_from_file(self, path_str: str):
        return  # never read the developer's real accounts.json


class TestAccountRegistryThreadSafety:
    def test_concurrent_getters_never_observe_partial_load(self):
        registry = SlowRegistry()
        thread_count = 8
        observed: list[int] = []
        lock = threading.Lock()

        def worker(index: int):
            # Staggered starts: unguarded, a late thread's load() clears
            # _accounts while an earlier thread is about to read it.
            time.sleep(index * 0.015)
            count = len(registry.get_all())
            with lock:
                observed.append(count)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert observed == [SlowRegistry.ACCOUNT_COUNT] * thread_count
        # The guarded lazy-load path must run load() exactly once.
        assert registry.load_calls == 1

    def test_explicit_reload_still_allowed(self):
        registry = SlowRegistry()
        assert len(registry.get_all()) == SlowRegistry.ACCOUNT_COUNT
        registry.load(file_path="nonexistent.json")
        assert registry.load_calls == 2
        assert len(registry.get_all()) == SlowRegistry.ACCOUNT_COUNT


class TestSecretsNotInRepr:
    """Logging a model or capturing traceback locals must not leak credentials."""

    SECRET = "SuperSecret123"

    def test_account_repr_hides_password(self):
        acc = Account(username="bob", password=self.SECRET)
        assert self.SECRET not in repr(acc)
        assert self.SECRET not in str(acc)
        # The field itself must still be readable by callers.
        assert acc.password == self.SECRET

    def test_empire_config_repr_hides_password(self):
        cfg = EmpireConfig(username="bob", password=self.SECRET)
        assert self.SECRET not in repr(cfg)
        assert self.SECRET not in str(cfg)
        assert cfg.password == self.SECRET

    def test_derived_config_repr_hides_password(self):
        # to_empire_config() copies the password across, so cover that path too.
        cfg = Account(username="bob", password=self.SECRET).to_empire_config()
        assert self.SECRET not in repr(cfg)
        assert self.SECRET not in str(cfg)

    def test_formatted_account_hides_password(self):
        acc = Account(username="bob", password=self.SECRET)
        assert self.SECRET not in f"{acc}"


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

    def test_injected_registry_is_used_instead_of_global(self, monkeypatch):
        # No monkeypatching of module globals: two pools, two disjoint account sets.
        monkeypatch.setattr(Account, "get_client", lambda self: FakeClient(self.username))
        pool_a = AccountPool(registry=FakeRegistry([Account(username="only_a", password="p")]))
        pool_b = AccountPool(registry=FakeRegistry([Account(username="only_b", password="p")]))

        assert [a.username for a in pool_a.all_accounts] == ["only_a"]
        assert [a.username for a in pool_b.all_accounts] == ["only_b"]

        client_a = pool_a.lease()
        assert client_a is not None and client_a.username == "only_a"
        # Leasing from one pool must not affect the other.
        assert pool_b.busy_count == 0
        assert pool_b.lease() is not None

    def test_default_registry_is_the_global_singleton(self, fake_accounts):
        # Backwards compatibility: no registry argument -> module-global registry.
        pool = AccountPool()
        assert [a.username for a in pool.all_accounts] == ["alpha", "beta"]

    def test_get_client_failure_raises_and_does_not_crash(self, fake_accounts, monkeypatch):
        # account.get_client() raising must not blow up with UnboundLocalError,
        # and must not be reported as 'no accounts available' either.
        def broken_get_client(self: Account):
            raise RuntimeError("cannot build client")

        monkeypatch.setattr(Account, "get_client", broken_get_client)
        pool = AccountPool()
        with pytest.raises(LoginError) as exc_info:
            pool.lease()
        # The underlying bug must stay reachable for debugging.
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert not isinstance(exc_info.value.__cause__, AttributeError)
        assert pool.busy_count == 0

    def test_no_candidates_still_returns_none(self, fake_accounts):
        # 'nothing configured/available' stays distinguishable from 'everything failed'.
        pool = AccountPool()
        assert pool.lease(tag="nonexistent-tag") is None
        assert pool.lease(username="not-a-real-user") is None
        assert pool.busy_count == 0

    def test_all_candidates_on_cooldown_raises_with_cause(self, fake_accounts, monkeypatch):
        def cooldown_get_client(self: Account):
            raise LoginCooldownError(cooldown=42)

        monkeypatch.setattr(Account, "get_client", cooldown_get_client)
        pool = AccountPool()
        with pytest.raises(LoginError) as exc_info:
            pool.lease()
        assert isinstance(exc_info.value.__cause__, LoginCooldownError)
        assert exc_info.value.__cause__.cooldown == 42
        assert pool.busy_count == 0

    def test_login_returning_false_raises(self, fake_accounts, monkeypatch):
        monkeypatch.setattr(Account, "get_client", lambda self: FakeClient(self.username, login_ok=False))
        pool = AccountPool()
        with pytest.raises(LoginError):
            pool.lease()
        assert pool.busy_count == 0
