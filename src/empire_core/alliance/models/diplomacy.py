"""Alliance diplomacy, auto war, the newsletter and treasury donations.

Commands:
- adp: Change or propose a relation with another alliance
- ard: Refuse another alliance's request
- saw: Turn auto war on or off
- anl: Send the alliance newsletter
- ado: Donate to the alliance treasury
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from empire_core.enums import DiplomacyStatus, Kingdom
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock
from empire_core.protocol.js import ClientInt, js_loose_equals
from empire_core.protocol.text import encode_json_text

from .info import AllianceInfo, alliance_block, alliance_of_ain

# =============================================================================
# ADP - Change a relation
# =============================================================================


class ChangeDiplomacyRequest(BaseRequest):
    """
    Change or propose your alliance's relation with another alliance.

    Command: adp
    Payload: {"AID": alliance_id, "NDR": new_status, "T": tribute}

    ``T`` is always sent; the client sets it only when accepting a peace offer,
    to the offer's percentage, negative when it was demanded.

    Client: ``C2SAllianceChangeDiplomacyVO`` (bundle line 22149), sent by
    ``CastleAllianceRequestDiplomacyDialog.onAccept`` (bundle line 44785),
    ``CastleReceivedPeaceOfferDialog.onAcceptConfirmed`` (bundle line 44856) and
    ``CastleAllianceInfoDialogDiplomacy.sendNewRank`` (bundle line 72379)
    """

    command = "adp"

    alliance_id: int = Field(validation_alias="AID", serialization_alias="AID", description="The other alliance")
    new_status: DiplomacyStatus = Field(
        validation_alias="NDR", serialization_alias="NDR", description="The relation to change to"
    )
    tribute: int = Field(
        validation_alias="T", serialization_alias="T", default=0, description="The peace offer's tribute; 0 otherwise"
    )


class ChangeDiplomacyResponse(BaseResponse):
    """
    The relation after a change, with both alliances.

    Command: adp

    Client: ``ADPCommand.executeCommand`` (bundle line 121361)
    """

    command = "adp"

    old_status: ClientInt = Field(
        validation_alias="ODR",
        serialization_alias="ODR",
        default=0,
        description="The relation before, a DiplomacyStatus value",
    )
    new_status: ClientInt = Field(
        validation_alias="NDR",
        serialization_alias="NDR",
        default=0,
        description="The relation now, a DiplomacyStatus value",
    )
    request_status: ClientInt = Field(
        validation_alias="S", serialization_alias="S", default=0, description="How the request stands"
    )
    own_alliance: AllianceInfo | None = Field(
        validation_alias="AS", serialization_alias="AS", default=None, description="Your alliance"
    )
    other_alliance: AllianceInfo | None = Field(
        validation_alias="AO", serialization_alias="AO", default=None, description="The other alliance"
    )

    @field_validator("own_alliance", "other_alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return alliance_block(value)


# =============================================================================
# ARD - Refuse a request
# =============================================================================


class RefuseDiplomacyRequest(BaseRequest):
    """
    Refuse another alliance's diplomacy request or peace offer.

    Command: ard
    Payload: {"AID": alliance_id}

    Client: ``C2SAllianceRefuseDiplomacyVO`` (bundle line 44795), sent by
    ``CastleAllianceRequestDiplomacyDialog.onRefuse`` (bundle line 44784) and
    ``CastleReceivedPeaceOfferDialog`` (bundle line 44851)
    """

    command = "ard"

    alliance_id: int = Field(validation_alias="AID", serialization_alias="AID", description="The other alliance")


class RefuseDiplomacyResponse(BaseResponse):
    """
    The other alliance after a refusal.

    Command: ard

    Client: ``ARDCommand.executeCommand`` (bundle line 121574)
    """

    command = "ard"

    alliance: AllianceInfo | None = Field(
        validation_alias="A", serialization_alias="A", default=None, description="The other alliance"
    )

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return alliance_block(value)


# =============================================================================
# SAW - Auto war
# =============================================================================


class SetAutoWarRequest(BaseRequest):
    """
    Turn auto war on or off.

    Command: saw
    Payload: {"AW": 1 or 0}

    Client: ``C2SSetAutoWar`` (bundle line 69369), sent by
    ``CastleAllianceDialogDiplomacy.sendAutoWarUpdate`` (bundle line 69284)
    """

    command = "saw"

    auto_war: int = Field(validation_alias="AW", serialization_alias="AW", description="1 for on, 0 for off")


class SetAutoWarResponse(BaseResponse):
    """
    Auto war after the change.

    Command: saw

    Client: ``SAWCommand.executeCommand`` (bundle line 122010)
    """

    command = "saw"

    auto_war: bool = Field(validation_alias="AW", serialization_alias="AW", default=False, description="Auto war is on")

    @field_validator("auto_war", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


# =============================================================================
# ANL - Newsletter
# =============================================================================


class SendNewsletterRequest(BaseRequest):
    """
    Send the alliance newsletter to every member.

    Command: anl
    Payload: {"SJ": subject, "TXT": text}, both encoded as chat text

    Client: ``C2SAllianceNewsletterVO`` (bundle line 69739), sent by
    ``CastleAllianceMessageToAllDialog.onClick`` (bundle line 69715)
    """

    command = "anl"

    subject: str = Field(validation_alias="SJ", serialization_alias="SJ", description="The subject, encoded")
    text: str = Field(validation_alias="TXT", serialization_alias="TXT", description="The text, encoded")

    @classmethod
    def create(cls, subject: str, text: str) -> SendNewsletterRequest:
        """A newsletter, both parts encoded as ``C2SAllianceNewsletterVO`` encodes them."""
        return cls(subject=encode_json_text(subject), text=encode_json_text(text))


class SendNewsletterResponse(BaseResponse):
    """
    The answer to a newsletter; the client reads nothing from it.

    Command: anl

    Client: ``ANLCommand.executeCommand`` (bundle line 121543)
    """

    command = "anl"


# =============================================================================
# ADO - Donate
# =============================================================================


_DONATION_KEYS = {
    "wood": "W",
    "stone": "S",
    "coins": "C1",
    "rubies": "C2",
    "iron": "I",
    "oil": "O",
    "glass": "G",
    "coal": "C",
    "alliance_coins": "AC",
    "rift_coins": "RC",
    "legendary_rift_coins": "LRC",
}


class AllianceDonation(BaseModel):
    """
    What to donate to the alliance treasury.

    These are the donatables the client offers a player: the
    ``allianceFundsDonatables`` rows of items v786.03 with ``directlyByPlayer``,
    each sent under its ``CollectableHelper.getServerKeyByCollectable`` key,
    the keys AllianceStorage reads.

    Client: ``CastleAllianceDonateDialog.showLoaded`` (bundle line 45511)
    """

    wood: int = Field(default=0, description="Wood")
    stone: int = Field(default=0, description="Stone")
    coins: int = Field(default=0, description="Coins")
    rubies: int = Field(default=0, description="Rubies")
    iron: int = Field(default=0, description="Iron")
    oil: int = Field(default=0, description="Olive oil")
    glass: int = Field(default=0, description="Glass")
    coal: int = Field(default=0, description="Charcoal")
    alliance_coins: int = Field(default=0, description="Alliance coins")
    rift_coins: int = Field(default=0, description="Rift coins")
    legendary_rift_coins: int = Field(default=0, description="Legendary rift coins")

    def resource_values(self) -> dict[str, int]:
        """
        The ``RV`` block: each amount above 0 under its key.

        Client: ``CastleAllianceDonateDialog.onDonateForAlliance`` (bundle line 45571)
        """
        return {key: getattr(self, name) for name, key in _DONATION_KEYS.items() if getattr(self, name) > 0}


class DonateRequest(BaseRequest):
    """
    Donate resources from one of your castles to the alliance treasury.

    Command: ado
    Payload: {"AID": castle_id, "KID": kingdom, "RV": {key: amount, ...}}

    ``AID`` is the donating castle, not the alliance.

    Client: ``C2SAllianceDonateVO`` (bundle line 70645), sent by
    ``CastleAllianceDonateDialog.onDonateForAlliance`` (bundle line 45571)
    """

    command = "ado"

    castle_id: int = Field(
        validation_alias="AID", serialization_alias="AID", description="The donating castle, e.g. CastleInfo.castle_id"
    )
    kingdom: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", description="The donating castle's kingdom"
    )
    resources: dict[str, int] = Field(
        validation_alias="RV", serialization_alias="RV", description="The amounts, keyed as AllianceDonation keys them"
    )

    @classmethod
    def create(cls, castle_id: int, kingdom: Kingdom, donation: AllianceDonation) -> DonateRequest:
        """A donation of ``donation`` from ``castle_id``."""
        return cls(castle_id=castle_id, kingdom=kingdom, resources=donation.resource_values())


class DonateResponse(BaseResponse):
    """
    Your currencies and the alliance after a donation; the castle's ``grc`` stays in the extra fields.

    Command: ado

    Client: ``ADOCommand.executeCommand`` (bundle line 121346)
    """

    command = "ado"

    currency: CurrencyBlock = Field(
        validation_alias="gcu",
        serialization_alias="gcu",
        default=None,
        description="Coins and rubies after the donation",
    )
    alliance: AllianceInfo | None = Field(
        validation_alias="ain", serialization_alias="ain", default=None, description="The alliance after the donation"
    )

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return alliance_of_ain(value)


__all__ = [
    "ChangeDiplomacyRequest",
    "ChangeDiplomacyResponse",
    "RefuseDiplomacyRequest",
    "RefuseDiplomacyResponse",
    "SetAutoWarRequest",
    "SetAutoWarResponse",
    "SendNewsletterRequest",
    "SendNewsletterResponse",
    "AllianceDonation",
    "DonateRequest",
    "DonateResponse",
]
