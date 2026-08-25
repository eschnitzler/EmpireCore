"""
Base classes and common types for GGE protocol models.

GGE Protocol Format:
- Request: %xt%{zone}%{command}%1%{json_payload}%
- Response: %{command}%{zone}%{error_code}%{json_payload}%

Special character encoding for text fields (chat messages, etc.):
- percent -> &percnt;
- quote -> &quot;
- apostrophe -> &145;
- newline -> <br /> or <br>
- backslash -> %5C
"""

from __future__ import annotations

import json
from enum import IntEnum
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Type variable for generic response payloads
T = TypeVar("T")

# Default zone for packet building
DEFAULT_ZONE = "EmpireEx_21"

# Registry mapping command -> response model class
_response_registry: dict[str, type["BaseResponse"]] = {}


class GGECommand:
    """Registry of all GGE protocol commands."""

    # Authentication
    LLI = "lli"  # Login
    LRE = "lre"  # Register
    VPN = "vpn"  # Check username availability
    VLN = "vln"  # Check if user exists
    LPP = "lpp"  # Password recovery

    # Chat
    ACM = "acm"  # Alliance chat message (send/receive)
    ACL = "acl"  # Get alliance chat log

    # Alliance
    AIN = "ain"  # Get alliance info (includes member list)
    AHC = "ahc"  # Help member
    AHA = "aha"  # Help all
    AHR = "ahr"  # Ask for help (request)

    # Castle
    GCL = "gcl"  # Get castles list
    DCL = "dcl"  # Get detailed castle info
    JCA = "jca"  # Jump to castle
    ARC = "arc"  # Rename castle
    RST = "rst"  # Relocate castle
    GRC = "grc"  # Get resources
    GPA = "gpa"  # Get production

    # Map
    GAM = "gam"  # Get active movements
    GAA = "gaa"  # Get map chunk (area)
    FNM = "fnm"  # Find NPC on map
    ADI = "adi"  # Get area/target detailed info

    # Player
    GDI = "gdi"  # Get detailed player info (castles, captures)
    WSP = "wsp"  # Search player by name

    # Attack
    CRA = "cra"  # Create/send attack
    CSM = "csm"  # Send spy mission
    SSI = "ssi"  # Spy screen info
    GAS = "gas"  # Get attack presets
    MSD = "msd"  # Skip attack cooldown (rubies)
    SDC = "sdc"  # Skip defense cooldown
    CDS = "cds"  # Send support troops

    # Building
    EBU = "ebu"  # Build (erect building)
    EUP = "eup"  # Upgrade building
    EMO = "emo"  # Move building
    SBD = "sbd"  # Sell building
    EDO = "edo"  # Destroy building
    FCO = "fco"  # Fast complete (skip construction)
    MSB = "msb"  # Time skip building
    EUD = "eud"  # Upgrade wall/defense
    RBU = "rbu"  # Repair building
    IRA = "ira"  # Repair all
    EBE = "ebe"  # Buy extension
    ETC = "etc"  # Collect extension gift

    # Army / Production
    BUP = "bup"  # Build units / produce
    SPL = "spl"  # Get production queue (LID: 0=soldiers, 1=tools)
    BOU = "bou"  # Double production slot
    MCU = "mcu"  # Cancel production
    GUI = "gui"  # Get units inventory
    DUP = "dup"  # Delete units

    # Hospital
    HRU = "hru"  # Heal units
    HCS = "hcs"  # Cancel heal
    HSS = "hss"  # Skip heal (rubies)
    HDU = "hdu"  # Delete wounded
    HRA = "hra"  # Heal all

    # Defense
    DFC = "dfc"  # Get defense configuration
    DFK = "dfk"  # Change keep defense
    DFW = "dfw"  # Change wall defense
    DFM = "dfm"  # Change moat defense
    SDI = "sdi"  # Get support defense info (alliance member castle defense)

    # Shop
    SBP = "sbp"  # Buy package
    GBC = "gbc"  # Set buying castle

    # Events
    SEI = "sei"  # Get events info
    PEP = "pep"  # Get event points
    HGH = "hgh"  # Get ranking/highscore (also used by alliance search)
    LLSP = "llsp"  # Get ranking list by position
    SEDE = "sede"  # Select event difficulty

    # Messages / notifications
    SNE = "sne"  # System notification event (push)
    BSD = "bsd"  # Battle/spy report data

    # Gifts
    CLB = "clb"  # Collect daily login bonus
    GPG = "gpg"  # Send gift to player

    # Quests
    QSC = "qsc"  # Complete message quest
    QDR = "qdr"  # Complete donation quest
    FCQ = "fcq"  # Complete condition
    CTR = "ctr"  # Tracking

    # Account
    GPI = "gpi"  # Player-identity sub-packet inside gbd (not sent standalone; see GDI)
    VPM = "vpm"  # Register email
    GNCI = "gnci"  # Get name change info
    CPNE = "cpne"  # Change username
    SCP = "scp"  # Change password
    RMC = "rmc"  # Request email change
    MNS = "mns"  # Email change status
    CMC = "cmc"  # Cancel email change
    FCS = "fcs"  # Facebook connection status

    # Settings
    ANI = "ani"  # Animation settings
    MVF = "mvf"  # Movement filter settings
    OPT = "opt"  # Misc options
    HFL = "hfl"  # Hospital filter settings

    # Misc
    TXI = "txi"  # Tax info
    TXS = "txs"  # Start tax collection
    TXC = "txc"  # Collect tax
    GBL = "gbl"  # Get bookmarks list
    RUI = "rui"  # Ruin info
    RMB = "rmb"  # Ruin message
    GFC = "gfc"  # Get friends/contacts
    SEM = "sem"  # Send email/message
    GLI = "gli"  # Get commander info
    GCS = "gcs"  # Get tavern offerings
    SCT = "sct"  # Make offering
    SIN = "sin"  # Building inventory
    SOB = "sob"  # Store building
    SDS = "sds"  # Sell from inventory


class HelpType(IntEnum):
    """Types of help requests in alliance."""

    HEAL = 2  # Heal wounded soldiers
    REPAIR = 3  # Repair building
    RECRUIT = 6  # Recruit soldiers


class ProductionListType(IntEnum):
    """Types of production lists."""

    SOLDIERS = 0
    TOOLS = 1


class BasePayload(BaseModel):
    """Base class for all protocol payloads."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",  # Allow extra fields we don't know about
    )

    def to_payload(self) -> dict[str, Any]:
        """
        Convert the model to a payload dict suitable for sending.

        Uses field aliases (e.g., "M" instead of "message") and
        excludes None values.
        """
        return self.model_dump(by_alias=True, exclude_none=True)


class BaseRequest(BasePayload):
    """Base class for request payloads sent to the server."""

    command: ClassVar[str]  # The command code (e.g., "acm", "lli")

    # Set only where the server answers under a different command than the one
    # sent (a castle jump goes out as 'jca' and comes back as 'jaa'). Waiting on
    # the request command there times out on every call.
    response_command: ClassVar[str | None] = None

    def to_packet(self, zone: str = DEFAULT_ZONE) -> str:
        """
        Build the full XT packet string ready to send.

        Format: %xt%{zone}%{command}%1%{json_payload}%

        Note: The request ID is always 1 - GGE doesn't use it for
        request/response matching.

        Args:
            zone: Game zone (default: EmpireEx_21)

        Returns:
            The formatted packet string
        """
        payload = self.to_payload()
        return f"%xt%{zone}%{self.command}%1%{json.dumps(payload)}%"

    @classmethod
    def get_command(cls) -> str:
        """Get the command code for this request type."""
        return cls.command

    @classmethod
    def get_response_command(cls) -> str:
        """The command the server's answer to this request arrives under."""
        return cls.response_command or cls.command


class BaseResponse(BasePayload):
    """
    Base class for response payloads received from the server.

    Responses can be instantiated directly from payload dicts:
        response = AllianceChatMessageResponse(**payload)
        # or
        response = AllianceChatMessageResponse.model_validate(payload)

    Each response class should define a `command` class variable to enable
    automatic lookup via `get_response_model()`. Commands must be unique;
    a class that shares a command with another (and is parsed manually
    instead) must opt out with ``class Foo(BaseResponse, register=False)``.
    """

    command: ClassVar[str]  # The command code this response handles

    # Server error code from the payload. The packet-header error code is
    # raised as CommandError before parsing, so this is usually 0.
    error_code: int = Field(alias="E", default=0)

    @property
    def success(self) -> bool:
        """Whether the server reported no error for this response."""
        return self.error_code == 0

    def __init_subclass__(cls, register: bool = True, **kwargs: Any) -> None:
        """Register response subclasses by their command."""
        super().__init_subclass__(**kwargs)
        # Only register if the class defines its own command
        if register and "command" in cls.__dict__:
            existing = _response_registry.get(cls.command)
            if existing is not None and existing is not cls:
                raise TypeError(
                    f"Duplicate response registration for command '{cls.command}': "
                    f"{existing.__module__}.{existing.__qualname__} vs {cls.__module__}.{cls.__qualname__}. "
                    "Pass register=False on the class that is parsed manually."
                )
            _response_registry[cls.command] = cls


def get_response_model(command: str) -> type[BaseResponse] | None:
    """
    Get the response model class for a command.

    Args:
        command: The command code (e.g., "acm", "gam")

    Returns:
        The response model class, or None if not registered
    """
    return _response_registry.get(command)


def parse_response(command: str, payload: dict[str, Any]) -> BaseResponse | None:
    """
    Parse a response payload into the appropriate model.

    Args:
        command: The command code
        payload: The payload dict from the server

    Returns:
        The parsed response model, or None if no model is registered
    """
    model_cls = get_response_model(command)
    if model_cls is None:
        return None
    return model_cls.model_validate(payload)


class Position(BaseModel):
    """A position on the game map."""

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom: int = Field(alias="KID", default=0)

    model_config = ConfigDict(populate_by_name=True)


class ResourceAmount(BaseModel):
    """Resource amounts."""

    wood: int = Field(alias="W", default=0)
    stone: int = Field(alias="S", default=0)
    food: int = Field(alias="F", default=0)
    coins: int = Field(alias="C", default=0)
    rubies: int = Field(alias="R", default=0)

    model_config = ConfigDict(populate_by_name=True)


class UnitCount(BaseModel):
    """A unit type and count pair."""

    unit_id: int = Field(alias="UID")
    count: int = Field(alias="C")

    model_config = ConfigDict(populate_by_name=True)


class PlayerInfo(BaseModel):
    """Basic player information."""

    player_id: int = Field(alias="PID")
    player_name: str = Field(alias="PN")
    alliance_id: int | None = Field(alias="AID", default=None)
    alliance_name: str | None = Field(alias="AN", default=None)

    model_config = ConfigDict(populate_by_name=True)


# Text encoding/decoding utilities for chat messages
def encode_chat_text(text: str) -> str:
    """
    Encode text for sending in chat messages.

    Converts special characters to their encoded forms:
    - % -> &percnt;
    - " -> &quot;
    - ' -> &145;
    - \n -> <br />
    - backslash -> %5C
    """
    result = text
    # '%' must be encoded before backslash, otherwise the '%' introduced
    # by the '%5C' replacement would itself get re-encoded.
    result = result.replace("%", "&percnt;")
    result = result.replace("\\", "%5C")
    result = result.replace('"', "&quot;")
    result = result.replace("'", "&145;")
    result = result.replace("\n", "<br />")
    return result


def decode_chat_text(text: str) -> str:
    """
    Decode text received in chat messages.

    Converts encoded forms back to special characters:
    - &percnt; -> %
    - &quot; -> "
    - &145; -> '
    - <br /> or <br> -> \n
    - %5C -> backslash
    """
    result = text
    result = result.replace("<br />", "\n")
    result = result.replace("<br>", "\n")
    # '%5C' must be decoded before '&percnt;' so a literal '%5C' typed by
    # a user (encoded as '&percnt;5C') doesn't turn into a backslash.
    result = result.replace("%5C", "\\")
    result = result.replace("&percnt;", "%")
    result = result.replace("&quot;", '"')
    result = result.replace("&145;", "'")
    return result


__all__ = [
    # Command registry
    "GGECommand",
    # Constants
    "DEFAULT_ZONE",
    # Enums
    "HelpType",
    "ProductionListType",
    # Base classes
    "BasePayload",
    "BaseRequest",
    "BaseResponse",
    # Common types
    "Position",
    "ResourceAmount",
    "UnitCount",
    "PlayerInfo",
    # Utilities
    "encode_chat_text",
    "decode_chat_text",
    # Response registry
    "get_response_model",
    "parse_response",
]
