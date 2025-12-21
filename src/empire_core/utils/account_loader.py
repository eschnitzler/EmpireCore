import json
import os
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

def load_accounts_from_file(path: str = "accounts.json") -> List[Dict[str, str]]:
    """
    Loads accounts from a JSON file.
    Expected format: [{"username": "...", "password": "..."}, ...]
    """
    if not os.path.exists(path):
        # Fallback to looking in project root if we are in a subdir or tests
        # This is a simple heuristic.
        paths_to_check = [
            path,
            os.path.join("..", path),
            os.path.join("..", "..", path), # e.g. from tests/
            os.path.join(os.getcwd(), path)
        ]
        
        found_path = None
        for p in paths_to_check:
            if os.path.exists(p):
                found_path = p
                break
        
        if not found_path:
            logger.warning(f"Account file '{path}' not found.")
            return []
        
        path = found_path

    try:
        with open(path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                logger.error(f"Invalid format in '{path}'. Expected a list.")
                return []
    except Exception as e:
        logger.error(f"Error loading accounts from '{path}': {e}")
        return []

def get_test_account() -> Optional[Dict[str, str]]:
    """Returns the first available account from accounts.json, or None."""
    accounts = load_accounts_from_file()
    if accounts:
        return accounts[0]
    return None

def get_first_account_config() -> Optional["EmpireConfig"]:
    """
    Returns an EmpireConfig for the first available account.
    Useful for examples and scripts.
    """
    from empire_core.config import EmpireConfig
    
    account = get_test_account()
    if account:
        return EmpireConfig(
            username=account.get("username", ""),
            password=account.get("password", "")
        )
    return None
