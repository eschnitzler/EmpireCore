"""
Account management and configuration system.
Handles loading credentials from files, environment variables, and provides
a robust interface for selecting accounts based on aliases or tags.
"""

import json
import logging
import os
import threading

from pydantic import BaseModel, Field, ValidationError

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

logger = logging.getLogger(__name__)


def _load_env_file() -> None:
    """Merge a .env file, searched for from the current working directory upwards.

    Importing a library must never mutate the caller's ``os.environ``, so this is
    only ever called from :meth:`AccountRegistry.load` when explicitly requested.
    Existing environment variables win: python-dotenv does not override them.
    """
    from dotenv import find_dotenv, load_dotenv

    path = find_dotenv(usecwd=True)
    if not path:
        logger.debug("No .env file found from the current working directory.")
        return
    load_dotenv(path)
    logger.debug(f"Loaded environment variables from '{path}'.")


def _describe_validation_error(e: ValidationError) -> str:
    """
    Summarize a ValidationError as field locations and messages only.

    str(ValidationError) embeds the offending input, so interpolating it into a log
    record writes account passwords to the log at ERROR level.
    """
    parts = []
    for err in e.errors(include_url=False, include_input=False):
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts) or "unknown validation error"


class Account(BaseModel):
    """
    Represents a single game account configuration.
    Wraps credentials and metadata.
    """

    username: str
    # repr=False: repr()/str() of this model ends up in logs and in traceback
    # locals captured by error reporters, so the secret must stay out of it.
    password: str = Field(..., repr=False, description="Plain text password")
    world: str = Field(default="EmpireEx_21", description="Game world/zone (e.g., EmpireEx_21)")
    alias: str | None = Field(default=None, description="Short name for this account (e.g., 'main', 'farmer1')")
    tags: list[str] = Field(default_factory=list, description="Categorization tags (e.g., ['farmer', 'k1'])")
    active: bool = Field(default=True, description="Whether this account should be used")

    def to_empire_config(self) -> EmpireConfig:
        """Convert to EmpireConfig for client usage."""
        return EmpireConfig(username=self.username, password=self.password, default_zone=self.world)

    def has_tag(self, tag: str) -> bool:
        """Check if account has a specific tag (case-insensitive)."""
        return tag.lower() in [t.lower() for t in self.tags]

    def get_client(self) -> EmpireClient:
        """Create and return an EmpireClient for this account."""
        return EmpireClient(
            username=self.username,
            password=self.password,
            config=self.to_empire_config(),
        )


class AccountRegistry:
    """
    Central registry for managing game accounts.
    Sources accounts from:
    1. accounts.json (local development)
    2. Environment variables (production/CI)

    Security:
        accounts.json holds passwords in plain text. Keep it out of version
        control and readable only by its owner (``chmod 600 accounts.json``).
        This is not enforced; the file is read whatever its permissions are.

    Thread Safety:
        The implicit lazy load performed by the query methods is guarded by a
        lock, so concurrent first-time readers cannot observe a partially
        loaded registry. Explicit calls to :meth:`load` are not synchronized.
    """

    def __init__(self):
        self._accounts: list[Account] = []
        self._loaded = False
        self._load_lock = threading.Lock()

    def load(self, file_path: str = "accounts.json", load_env_file: bool = False):
        """
        Load accounts from all sources.
        Prioritizes environment variables, then file: an account whose
        username appears in both sources keeps the env definition.

        Args:
            file_path: Path to the accounts JSON file (as given, or relative to cwd).
            load_env_file: When True, first merge a ``.env`` file found from the
                current working directory upwards into ``os.environ`` (existing
                variables are never overridden). Defaults to False so that merely
                importing ``empire_core`` never mutates the caller's environment.
        """
        self._accounts = []

        if load_env_file:
            _load_env_file()

        # 1. Load from Environment Variables
        self._load_from_env()

        # 2. Load from JSON file (skipping usernames already defined via env)
        self._load_from_file(file_path)

        self._loaded = True
        logger.debug(f"AccountRegistry loaded {len(self._accounts)} active accounts.")

    def _ensure_loaded(self) -> None:
        """
        Load on first use, once, even under concurrent readers.

        Only the load is guarded: reads of an already-loaded registry take the
        fast path without acquiring the lock. Without this, two threads could
        both enter load(), which starts by clearing self._accounts, and one
        would return an empty or partially populated list.
        """
        if self._loaded:
            return
        with self._load_lock:
            if not self._loaded:
                self.load()

    def _add_account(self, account: Account) -> None:
        """Add an account unless its username is already registered."""
        if any(acc.username.lower() == account.username.lower() for acc in self._accounts):
            logger.debug(f"Skipping duplicate account definition for '{account.username}'")
            return
        self._accounts.append(account)

    def _load_from_file(self, path_str: str):
        """Internal: Load from JSON file (as given, or relative to cwd).

        Security: this file stores passwords in plain text. Keep it out of version
        control and restrict it to its owner (``chmod 600 accounts.json``). The
        permissions are not checked or enforced here.
        """
        paths_to_check = [
            path_str,
            os.path.join(os.getcwd(), path_str),
        ]

        target_path = None
        for p in paths_to_check:
            if os.path.exists(p):
                target_path = p
                break

        if not target_path:
            logger.debug(f"Account file '{path_str}' not found. Skipping file load.")
            return

        try:
            with open(target_path, "r") as f:
                data = json.load(f)

            if not isinstance(data, list):
                logger.warning(f"Invalid format in '{target_path}'. Expected a list of accounts.")
                return

            for entry in data:
                try:
                    account = Account(**entry)
                    if account.active:
                        self._add_account(account)
                except ValidationError as e:
                    logger.error(f"Skipping invalid account entry in {target_path}: {_describe_validation_error(e)}")

        except Exception as e:
            logger.error(f"Error reading '{target_path}': {e}")

    def _load_from_env(self):
        """
        Internal: Load from environment variables.

        Two formats are supported per EMPIRE_ACCOUNT_<ALIAS> variable:
        - JSON object: {"username": "u", "password": "p", "world": "EmpireEx_21"}
          (use this if the password contains commas)
        - CSV: <USERNAME>,<PASSWORD>,<WORLD>
        """
        for key, value in os.environ.items():
            if not key.startswith("EMPIRE_ACCOUNT_"):
                continue
            alias = key.replace("EMPIRE_ACCOUNT_", "").lower()
            value = value.strip()

            if value.startswith("{"):
                try:
                    entry = json.loads(value)
                    entry.setdefault("alias", alias)
                    entry.setdefault("tags", ["env"])
                    self._add_account(Account(**entry))
                except ValidationError as e:
                    logger.error(f"Invalid account in ${key}: {_describe_validation_error(e)}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in ${key}: {e.msg} at position {e.pos}")
                continue

            # CSV fallback: USER,PASS[,WORLD]
            parts = value.split(",")
            if len(parts) < 2:
                logger.error(f"Invalid account format in ${key} (expected USER,PASS[,WORLD] or JSON)")
                continue
            if len(parts) > 3:
                logger.warning(
                    f"${key} has more than 3 comma-separated fields; if the password "
                    "contains commas, use the JSON object format instead"
                )

            username = parts[0].strip()
            password = parts[1].strip()
            world = parts[2].strip() if len(parts) > 2 else "EmpireEx_21"

            self._add_account(
                Account(username=username, password=password, world=world, alias=alias, tags=["env"], active=True)
            )

    # === Query Methods ===

    def get_all(self) -> list[Account]:
        """Get all active accounts."""
        self._ensure_loaded()
        return self._accounts

    def get_by_alias(self, alias: str) -> Account | None:
        """Find an account by its alias."""
        self._ensure_loaded()
        for acc in self._accounts:
            if acc.alias and acc.alias.lower() == alias.lower():
                return acc
        return None

    def get_by_username(self, username: str) -> Account | None:
        """Find an account by username."""
        self._ensure_loaded()
        for acc in self._accounts:
            if acc.username.lower() == username.lower():
                return acc
        return None

    def get_by_tag(self, tag: str) -> list[Account]:
        """Get all accounts with a specific tag."""
        self._ensure_loaded()
        return [acc for acc in self._accounts if acc.has_tag(tag)]

    def get_default(self) -> Account | None:
        """Get the first available account (default)."""
        self._ensure_loaded()
        if self._accounts:
            return self._accounts[0]
        return None


# Global Singleton
accounts = AccountRegistry()
