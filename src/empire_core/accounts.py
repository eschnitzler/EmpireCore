"""
Account management and configuration system.
Handles loading credentials from files, environment variables, and provides
a robust interface for selecting accounts based on aliases or tags.
"""

import json
import logging
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

logger = logging.getLogger(__name__)

# Load .env file if present
load_dotenv()


class Account(BaseModel):
    """
    Represents a single game account configuration.
    Wraps credentials and metadata.
    """

    username: str
    password: str = Field(..., description="Plain text password")
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
    """

    def __init__(self):
        self._accounts: list[Account] = []
        self._loaded = False

    def load(self, file_path: str = "accounts.json"):
        """
        Load accounts from all sources.
        Prioritizes environment variables, then file: an account whose
        username appears in both sources keeps the env definition.
        """
        self._accounts = []

        # 1. Load from Environment Variables
        self._load_from_env()

        # 2. Load from JSON file (skipping usernames already defined via env)
        self._load_from_file(file_path)

        self._loaded = True
        logger.debug(f"AccountRegistry loaded {len(self._accounts)} active accounts.")

    def _add_account(self, account: Account) -> None:
        """Add an account unless its username is already registered."""
        if any(acc.username.lower() == account.username.lower() for acc in self._accounts):
            logger.debug(f"Skipping duplicate account definition for '{account.username}'")
            return
        self._accounts.append(account)

    def _load_from_file(self, path_str: str):
        """Internal: Load from JSON file (as given, or relative to cwd)."""
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
                    logger.error(f"Skipping invalid account entry in {target_path}: {e}")

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
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(f"Invalid JSON account in ${key}: {e}")
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
        if not self._loaded:
            self.load()
        return self._accounts

    def get_by_alias(self, alias: str) -> Account | None:
        """Find an account by its alias."""
        if not self._loaded:
            self.load()
        for acc in self._accounts:
            if acc.alias and acc.alias.lower() == alias.lower():
                return acc
        return None

    def get_by_username(self, username: str) -> Account | None:
        """Find an account by username."""
        if not self._loaded:
            self.load()
        for acc in self._accounts:
            if acc.username.lower() == username.lower():
                return acc
        return None

    def get_by_tag(self, tag: str) -> list[Account]:
        """Get all accounts with a specific tag."""
        if not self._loaded:
            self.load()
        return [acc for acc in self._accounts if acc.has_tag(tag)]

    def get_default(self) -> Account | None:
        """Get the first available account (default)."""
        if not self._loaded:
            self.load()
        if self._accounts:
            return self._accounts[0]
        return None


# Global Singleton
accounts = AccountRegistry()
