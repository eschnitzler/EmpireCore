"""Tests for account loading, login configuration, and the account pool."""

import json
import logging
import os
import stat
import threading
import time

import pytest
from pydantic import ValidationError

import empire_core.pool as pool_module
from empire_core.accounts import Account, AccountRegistry
from empire_core.config import LOGIN_DEFAULTS, EmpireConfig, ServerError, default_config, generate_aid, resolve_aid
from empire_core.exceptions import LoginCooldownError, LoginError
from empire_core.pool import AccountPool, PoolExhaustedError
from empire_core.protocol.errors import GGEError


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
class TestCredentialFilePermissions:
    """A plaintext credential file readable beyond its owner must be flagged."""

    @staticmethod
    def _write(tmp_path, mode: int):
        path = tmp_path / "accounts.json"
        path.write_text(json.dumps([{"username": "permuser", "password": "SuperSecret123"}]))
        path.chmod(mode)
        return path

    @pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o777])
    def test_loose_permissions_warn(self, tmp_path, caplog, mode):
        path = self._write(tmp_path, mode)
        registry = AccountRegistry()
        with caplog.at_level(logging.WARNING):
            registry.load(file_path=str(path))

        # The accounts still load - this is a warning, not a hard failure.
        assert registry.get_by_username("permuser") is not None
        assert "chmod 600" in caplog.text
        assert str(path) in caplog.text
        # Never echo the secret while complaining about the file holding it.
        assert "SuperSecret123" not in caplog.text

    @pytest.mark.parametrize("mode", [0o600, 0o400])
    def test_owner_only_permissions_are_silent(self, tmp_path, caplog, mode):
        path = self._write(tmp_path, mode)
        registry = AccountRegistry()
        with caplog.at_level(logging.WARNING):
            registry.load(file_path=str(path))

        assert registry.get_by_username("permuser") is not None
        assert "chmod 600" not in caplog.text

    def test_warning_reports_the_actual_mode(self, tmp_path, caplog):
        path = self._write(tmp_path, 0o644)
        registry = AccountRegistry()
        with caplog.at_level(logging.WARNING):
            registry.load(file_path=str(path))
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert oct(mode) in caplog.text


class TestDefaultConfigIsNotSharedMutableState:
    """``EmpireClient(config=None)`` aliases the one module-level ``default_config``.

    Sharing is only safe because that instance cannot be mutated: otherwise a
    single ``client.config.default_zone = ...`` would silently repoint the zone,
    timeouts and credentials of every other default-constructed client in the
    process.
    """

    def test_default_config_is_an_empire_config(self):
        assert isinstance(default_config, EmpireConfig)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("default_zone", "EmpireEx_99"),
            ("game_url", "wss://example.invalid/"),
            ("request_timeout", 999.0),
            ("username", "hijacked"),
            ("password", "hijacked"),
        ],
    )
    def test_shared_default_rejects_mutation(self, field, value):
        original = getattr(default_config, field)
        with pytest.raises(ValidationError):
            setattr(default_config, field, value)
        assert getattr(default_config, field) == original

    def test_user_constructed_config_stays_mutable(self):
        # Consumers (dreambot's birder service) build a fresh EmpireConfig() and
        # assign credentials onto it. Freezing the whole class would break them,
        # so only the shared default instance is frozen.
        cfg = EmpireConfig()
        cfg.username = "bob"
        cfg.password = "s3cret"
        cfg.default_zone = "EmpireEx_1"
        assert (cfg.username, cfg.password, cfg.default_zone) == ("bob", "s3cret", "EmpireEx_1")

    def test_derived_copy_of_the_default_is_usable(self):
        # The documented way to start from the defaults and change something.
        cfg = EmpireConfig(**default_config.model_dump())
        cfg.default_zone = "EmpireEx_1"
        assert cfg.default_zone == "EmpireEx_1"
        assert default_config.default_zone != "EmpireEx_1"


class TestServerErrorCodeTable:
    """``config.ServerError`` used to be a second, contradictory error-code table."""

    def test_login_cooldown_matches_the_authoritative_table(self):
        assert ServerError.LOGIN_COOLDOWN == GGEError.LOGIN_COOLDOWN

    @pytest.mark.parametrize("name", ["INVALID_CREDENTIALS", "SESSION_EXPIRED"])
    def test_codes_that_contradict_ggeerror_are_gone(self, name):
        # 401 was both ServerError.INVALID_CREDENTIALS and GGEError.REWARD_ID_NOT_FOUND;
        # 440 was both SESSION_EXPIRED and C2_CONFIRMATION_REQUIRED. Keeping a second
        # name for the same number guarantees one of the two readings is a lie.
        assert not hasattr(ServerError, name)

    def test_unresolved_conflicts_are_documented(self):
        doc = ServerError.__doc__ or ""
        assert "401" in doc and "440" in doc, "the unresolved code conflicts must stay written down"


class TestLoginFingerprint:
    """LOGIN_DEFAULTS['AID'] is a device/install id sent to the game server."""

    LEAKED_LITERAL = "1745592024940879420"

    def test_no_shared_hardcoded_install_id(self):
        # Shipping one literal makes every user of the published library present
        # an identical fingerprint - trivially correlatable and mass-bannable.
        assert LOGIN_DEFAULTS["AID"] != self.LEAKED_LITERAL

    def test_default_aid_looks_like_a_browser_aid(self):
        aid = LOGIN_DEFAULTS["AID"]
        assert isinstance(aid, str)
        assert aid.isdigit()
        assert len(aid) == len(self.LEAKED_LITERAL)

    def test_generated_ids_differ(self):
        assert len({generate_aid() for _ in range(5)}) > 1

    def test_env_var_pins_the_id_for_a_stable_fingerprint(self, monkeypatch):
        monkeypatch.setenv("EMPIRE_AID", "1234567890123456789")
        assert resolve_aid() == "1234567890123456789"

    def test_blank_env_var_falls_back_to_a_generated_id(self, monkeypatch):
        monkeypatch.setenv("EMPIRE_AID", "   ")
        aid = resolve_aid()
        assert aid.isdigit() and aid != self.LEAKED_LITERAL

    def test_process_id_is_exposed_so_it_can_be_persisted(self):
        # Resolved once at import, and readable, so a consumer can store it and
        # pin it back via EMPIRE_AID on the next run.
        from empire_core.config import AID

        assert LOGIN_DEFAULTS["AID"] == AID


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


class FakeRegistry(AccountRegistry):
    """A registry with a fixed account list and no file or environment sources.

    Subclasses the real registry rather than duck-typing it so the injection
    point stays type-checked: if AccountPool ever needs more of the registry
    API, that shows up here instead of only at runtime.
    """

    def __init__(self, accounts: list[Account]):
        super().__init__()
        self._accounts = accounts
        self._loaded = True

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

    def test_lease_accepts_a_login_that_returns_nothing(self, monkeypatch):
        """login() reports failure by raising; its return value carries no information.

        The pool used to treat a falsy return as failure. EmpireClient.login()
        has no False path, so that guard was dead - and actively a trap: the
        recommended change to ``login() -> None`` would have turned every
        successful lease into a spurious LoginError.
        """

        class QuietLoginClient(FakeClient):
            def login(self) -> None:  # type: ignore[override]
                self.is_logged_in = True
                return None

        monkeypatch.setattr(Account, "get_client", lambda self: QuietLoginClient(self.username))
        pool = AccountPool(registry=FakeRegistry([Account(username="alpha", password="p")]))
        client = pool.lease()
        assert client is not None
        assert client.is_logged_in
        assert pool.busy_count == 1

    def test_lease_failure_is_reported_by_the_raised_exception(self, monkeypatch):
        # The surviving contract: a client whose login() raises is not leased.
        class RaisingLoginClient(FakeClient):
            def login(self) -> bool:
                raise LoginError("bad credentials")

        monkeypatch.setattr(Account, "get_client", lambda self: RaisingLoginClient(self.username))
        pool = AccountPool(registry=FakeRegistry([Account(username="alpha", password="p")]))
        with pytest.raises(LoginError):
            pool.lease()
        assert pool.busy_count == 0


class TestLeaseByUsernameMatchesRegistrySemantics:
    """The username branch built its own candidate list and skipped every filter."""

    @pytest.fixture(autouse=True)
    def _fake_clients(self, monkeypatch):
        monkeypatch.setattr(Account, "get_client", lambda self: FakeClient(self.username))

    def test_username_match_is_case_insensitive(self):
        # AccountRegistry.get_by_username and Account.has_tag both fold case.
        pool = AccountPool(registry=FakeRegistry([Account(username="alpha", password="p")]))
        client = pool.lease(username="ALPHA")
        assert client is not None
        assert client.username == "alpha"

    def test_inactive_account_is_not_leasable_by_name(self):
        pool = AccountPool(registry=FakeRegistry([Account(username="dormant", password="p", active=False)]))
        assert pool.lease(username="dormant") is None
        assert pool.busy_count == 0

    def test_tag_filter_applies_to_the_username_branch(self):
        pool = AccountPool(registry=FakeRegistry([Account(username="alpha", password="p", tags=["Farmer"])]))
        assert pool.lease(username="alpha", tag="scanner") is None
        client = pool.lease(username="alpha", tag="FARMER")
        assert client is not None


class TestLeasedContextManager:
    """Without scoping, a caller exception between lease() and release() leaks
    the busy slot and a live connected client for the lifetime of the process."""

    def test_releases_on_normal_exit(self, fake_accounts):
        _, clients = fake_accounts
        pool = AccountPool()
        with pool.leased() as client:
            leased = client.username
            assert pool.busy_count == 1
        assert pool.busy_count == 0
        assert clients[leased].closed

    def test_releases_when_the_caller_raises(self, fake_accounts):
        _, clients = fake_accounts
        pool = AccountPool()
        leased = None
        with pytest.raises(RuntimeError, match="caller blew up"):
            with pool.leased() as client:
                leased = client.username
                raise RuntimeError("caller blew up")

        assert leased is not None
        assert pool.busy_count == 0, "the busy slot leaked - the account is unusable until restart"
        assert clients[leased].closed, "the websocket and receive thread leaked"

    def test_account_becomes_leasable_again_after_a_failure(self, fake_accounts):
        pool = AccountPool()
        with pytest.raises(RuntimeError):
            with pool.leased(username="alpha"):
                raise RuntimeError("boom")
        again = pool.leased(username="alpha")
        with again as client:
            assert client.username == "alpha"

    def test_no_available_account_raises_instead_of_yielding_none(self, fake_accounts):
        pool = AccountPool()
        with pytest.raises(PoolExhaustedError):
            with pool.leased(tag="nonexistent-tag"):
                pass
        assert pool.busy_count == 0

    def test_pool_exhausted_is_an_empire_error(self):
        from empire_core.exceptions import EmpireError

        assert issubclass(PoolExhaustedError, EmpireError)
