"""
The base class every service shares.

Services give each part of the game its own API (alliance, castle, ...).
Each lives in its area package (``empire_core.alliance.service``, ...) and is built
by ``EmpireClient.__init__``; this package holds only the base class.

Usage:
    client = EmpireClient(...)
    client.alliance.send_chat("Hello!")
"""

from .base import BaseService

__all__ = ["BaseService"]
