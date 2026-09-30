"""
Base classes and common types for GGE protocol models.

GGE Protocol Format:
- Request: %xt%{zone}%{command}%{room id}%{params...}%, a JSON command's one param being its JSON
- Response: %xt%{command}%{request id}%{status}%{payload}%
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from enum import IntEnum
from typing import Annotated, Any, ClassVar, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

# Type variable for generic response payloads
T = TypeVar("T")

# Default zone for packet building
DEFAULT_ZONE = "EmpireEx_21"

# The room id a command carries before any room is joined
NO_ROOM = -1

# Registry mapping command -> response model class
_response_registry: dict[str, type["BaseResponse"]] = {}


def smartfox_text(text: str) -> str:
    """
    Escape a string command param as the client does: each ``%`` becomes ``&percnt;`` and each ``'`` is dropped.

    Client: ``TextValide.getValideSmartFoxText`` (dll line 5816)
    """
    return text.replace("%", "&percnt;").replace("'", "")


def json_text(payload: Any) -> str:
    """``payload`` as ``JSON.stringify`` writes it: no spaces, non-ASCII kept as is."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def build_command(zone: str, command: str, params: list[str | int | None], room_id: int = NO_ROOM) -> str:
    """
    The frame for a command with these params, as the client puts it on the wire.

    A 0 goes out as ``0``, any other empty param (``""``, None) as
    ``<RoundHouseKick>``, and each string through :func:`smartfox_text`.

    Client: ``BasicSmartfoxClient.sendMessage`` and ``sendCommand`` (dll line 7171, 7198)
    """
    fields: list[str] = []
    for param in params:
        if isinstance(param, str):
            fields.append(smartfox_text(param) if param else "<RoundHouseKick>")
        elif param is None:
            fields.append("<RoundHouseKick>")
        else:
            fields.append(str(param))
    return "%".join(["", "xt", zone, command, str(room_id), *fields, ""])


class GGECommand:
    """Registry of all GGE protocol commands."""

    # Authentication
    LLI = "lli"  # Login
    LRE = "lre"  # Register
    VPN = "vpn"  # Check username availability
    VLN = "vln"  # Check if user exists
    LPP = "lpp"  # Password recovery
    VCK = "vck"  # Version check before the login
    SLT = "slt"  # Login token push after a persistent login

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

    # Player
    GDI = "gdi"  # Get detailed player info (castles, captures)
    WSP = "wsp"  # Search player by name

    # Attack
    ACI = "aci"  # Attack pre-calculation for a castle
    ADI = "adi"  # Attack pre-calculation for an NPC camp
    ABI = "abi"  # Attack pre-calculation for a boss dungeon
    ALI = "ali"  # Attack pre-calculation for a landmark
    AVI = "avi"  # Attack pre-calculation for a village
    AII = "aii"  # Attack pre-calculation for an isle resource
    COI = "coi"  # Conquest pre-calculation for an outpost
    CCI = "cci"  # Conquest pre-calculation for a capital
    CTI = "cti"  # Conquest pre-calculation for a metropolis
    CRA = "cra"  # Create/send attack
    CSM = "csm"  # Send spy mission
    SSI = "ssi"  # Spy screen info
    GAS = "gas"  # Get attack presets
    SAS = "sas"  # Save an attack preset
    MSD = "msd"  # Shorten a dungeon's cooldown with a minute skip
    SDC = "sdc"  # Skip a dungeon's cooldown
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
    DFC = "dfc"  # Read a castle's keep, wall and moat setup
    DFK = "dfk"  # Set the keep's tools and unit settings
    DFW = "dfw"  # Set the wall's tools and unit split
    DFM = "dfm"  # Set the moat's tools
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
    GLI = "gli"  # Get commander info
    ARL = "arl"  # Rename a commander or castellan
    GEI = "gei"  # Get equipment inventory
    EEQ = "eeq"  # Equip or unequip an item
    GCS = "gcs"  # Get tavern offerings
    SCT = "sct"  # Make offering
    SIN = "sin"  # Building inventory
    SOB = "sob"  # Store building
    SDS = "sds"  # Sell from inventory


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

    def to_packet(self, zone: str = DEFAULT_ZONE, room_id: int = NO_ROOM) -> str:
        """
        The frame that sends this request: ``%xt%{zone}%{command}%{room id}%{json}%``.

        Args:
            zone: Game zone (default: EmpireEx_21)
            room_id: The joined room's id (from ``joinOK``); -1 before one is joined

        Client: ``BasicSmartfoxClient.sendCommandVO`` (dll line 7177)
        """
        return build_command(zone, self.command, [json_text(self.to_payload())], room_id)

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
    #
    # "E" is not reserved: an aci response uses it for the player's crest, and
    # a response whose payload happens to use the key for something else must
    # still parse, so anything that is not an integer is treated as no error.
    error_code: int = Field(alias="E", default=0)

    @field_validator("error_code", mode="before")
    @classmethod
    def _ignore_non_numeric_error_codes(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return 0
        return value

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


def object_or_none(value: Any) -> Any:
    """A reply block that is an object, else None: the client reads keys off it only when it is one."""
    return value if isinstance(value, (dict, BaseModel)) else None


def list_or_empty(value: Any) -> Any:
    """A reply value that is an array, else no entries."""
    return value if isinstance(value, list) else []


_M = TypeVar("_M", bound=BaseModel)


def readable_list(
    model: type[_M],
    value: Any,
    *,
    accept: Callable[[Any], Any] | None = None,
    keep: Callable[[Any], Any] | None = None,
    parse: Callable[[Any], _M] | None = None,
    warn: logging.Logger | None = None,
    what: str = "entries",
) -> list[_M]:
    """
    Each entry of an array read as ``model``, so one unreadable entry costs only itself.

    A null entry, or one ``keep`` rejects, is skipped quietly. Where the client
    would throw on a bad entry instead, skipping it is a deliberate leniency: it
    costs only that entry. One ``accept`` rejects or that fails validation is unreadable:
    it is skipped too, and with ``warn`` those are counted in one warning that
    shows the first. Anything but an array reads as no entries.
    """
    if not isinstance(value, list):
        return []
    read = parse or model.model_validate
    rows: list[_M] = []
    failed: list[Any] = []
    for entry in value:
        if isinstance(entry, model):
            rows.append(entry)
        elif entry is None:
            continue
        elif accept is not None and not accept(entry):
            failed.append(entry)
        elif keep is not None and not keep(entry):
            continue
        else:
            try:
                rows.append(read(entry))
            except ValidationError:
                failed.append(entry)
    if warn is not None and failed:
        warn.warning(f"Skipped {len(failed)}/{len(value)} unreadable {what}, first: {failed[0]!r:.200}")
    return rows


_T = TypeVar("_T")


def read_or_none(
    read: Callable[[Any], _T], value: Any, *, warn: logging.Logger | None = None, what: str = "an entry"
) -> _T | None:
    """``read(value)``, or None when validation fails, so an unreadable block costs only itself."""
    try:
        return read(value)
    except ValidationError:
        if warn is not None:
            warn.warning(f"Could not read {what}")
        return None


class CurrencyTotals(BasePayload):
    """
    Coins and rubies after an action, the ``gcu`` block.

    Client: ``CurrencyData.parseGCU`` (bundle line 141191), which reads
    ``CollectableItemC1VO.SERVER_KEY`` "C1" (bundle line 7995) and
    ``CollectableItemC2VO.SERVER_KEY`` "C2" (bundle line 4876).
    """

    coins: int | float | None = Field(
        alias="C1", default=None, description="Coins; None when the reply has no number for it"
    )
    rubies: int | float | None = Field(
        alias="C2", default=None, description="Rubies; None when the reply has no number for it"
    )

    @field_validator("coins", "rubies", mode="before")
    @classmethod
    def _number_or_none(cls, value: Any) -> Any:
        # parseGCU assigns the value as it comes; a value that is no number is not a total
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


CurrencyBlock = Annotated[CurrencyTotals | None, BeforeValidator(object_or_none)]
"""A ``gcu`` block, or None when a reply sends none or something that is not an object."""


_E = TypeVar("_E", bound=IntEnum)


def enum_or_none(enum: type[_E], value: int) -> _E | None:
    """The member of ``enum`` for a reply's int, or None when the client defines no such value."""
    try:
        return enum(value)
    except ValueError:
        return None


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


__all__ = [
    # Command registry
    "GGECommand",
    # Constants
    "DEFAULT_ZONE",
    "NO_ROOM",
    # Packet building
    "build_command",
    "json_text",
    "smartfox_text",
    "CurrencyBlock",
    "CurrencyTotals",
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
    "enum_or_none",
    "list_or_empty",
    "object_or_none",
    "read_or_none",
    "readable_list",
    # Response registry
    "get_response_model",
    "parse_response",
]
