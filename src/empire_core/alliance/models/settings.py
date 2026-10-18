"""Alliance settings requests and their echoed details."""

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, field_serializer, model_validator

from empire_core.alliance.models.info import GetAllianceInfoResponse
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.text import encode_json_text, is_smartfox_valid

if TYPE_CHECKING:
    from empire_core.gamedata import AllianceCrestColor, AllianceCrestLayout

# Client: AllianceConst (dllsplit line 18805).
ALLIANCE_NAME_MIN_LENGTH = 5
ALLIANCE_NAME_MAX_LENGTH = 15
ALLIANCE_DESCRIPTION_MAX_LENGTH = 1000
ALLIANCE_RENAME_RUBIES = 10000

_JS_WHITESPACE = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def alliance_description(text: str) -> str:
    """Client: getForumValidText/getTrimmedText (bundle lines 8090/1979)."""
    return encode_json_text(text.strip(_JS_WHITESPACE))


def alliance_name(name: str) -> None:
    """Validate a name as the alliance dialog does.

    Client: TextValide.isUsernameValide (dll lines 5783–5789),
    CastleNameAllianceDialog.validate (bundle lines 69801–69804).
    """
    if (
        not ALLIANCE_NAME_MIN_LENGTH
        <= len(name.encode("utf-16-le", errors="surrogatepass")) // 2
        <= ALLIANCE_NAME_MAX_LENGTH
    ):
        raise ValueError(f"alliance names must have {ALLIANCE_NAME_MIN_LENGTH}–{ALLIANCE_NAME_MAX_LENGTH} characters")
    if not is_smartfox_valid(name) or any(char in name for char in "!=?+#<>|"):
        raise ValueError("alliance name contains characters the client refuses")


class ChangeAllianceDescriptionRequest(BaseRequest):
    """Client: C2SAllianceChangeDescriptionVO (bundle lines 45319–45322).

    Description text goes through getForumValidText first (8090), then the
    constructor encodes again and truncates the encoded string to 1000.
    Announcement sendDescription (70504) also encodes twice on the valid branch.
    """

    command = "acd"
    text: str = Field(validation_alias="TXT", description="Description or announcement text")
    text_type: Literal[0, 1] = Field(validation_alias="T", description="0 for announcement, 1 for description")

    @field_serializer("text")
    def _text(self, text: str) -> str:
        if self.text_type == 1:
            text = alliance_description(text)
        elif is_smartfox_valid(text) or not text:
            text = encode_json_text(text)
        else:
            for char in '+#<>"$':
                text = text.replace(char, "")
            text = text.replace("%", "&percnt;").replace("'", "")
        encoded = encode_json_text(text).encode("utf-16-le", errors="surrogatepass")
        return encoded[: ALLIANCE_DESCRIPTION_MAX_LENGTH * 2].decode("utf-16-le", errors="surrogatepass")


class ChangeAllianceDescriptionResponse(GetAllianceInfoResponse):
    """Client: ACDCommand.executeCommand (bundle lines 121304–121305), reads ain."""

    command = "acd"

    @model_validator(mode="before")
    @classmethod
    def _nested(cls, value: Any) -> Any:
        return value.get("ain", {}) if isinstance(value, dict) else value


class ChangeAllianceNameRequest(BaseRequest):
    """Client: C2SAllianceChangeNameVO (bundle lines 69815–69817)."""

    command = "acn"
    name: str = Field(validation_alias="AN", description="New alliance name")

    @field_serializer("name")
    def _name(self, name: str) -> str:
        return encode_json_text(name)


class ChangeAllianceNameResponse(GetAllianceInfoResponse):
    """Client: ACNCommand.executeCommand (bundle lines 121354–121355), reads A."""

    command = "acn"


class ChangeAllianceLanguageRequest(BaseRequest):
    """Client: C2SChangeAllianceLanguageVO (bundle lines 42844–42846)."""

    command = "cal"
    language: str = Field(validation_alias="ALL", description="Alliance language code")


class ChangeAllianceLanguageResponse(GetAllianceInfoResponse):
    """Client: CALCommand.executeCommand (bundle lines 121690–121691), reads A."""

    command = "cal"


class SetAllianceEmblemRequest(BaseRequest):
    """Client: C2SSetAllianceEmblemVO (bundle lines 69672–69674)."""

    command = "sae"
    layout_id: EnumOrInt["AllianceCrestLayout"] = Field(validation_alias="ACLI", description="Crest layout id")
    color_ids: list[EnumOrInt["AllianceCrestColor"]] = Field(
        validation_alias="ACCS", description="Colours for the layout"
    )


class SetAllianceEmblemResponse(BaseResponse):
    """Client: SAECommand.executeCommand (bundle line 122004), acknowledgment only."""

    command = "sae"


def settings_alliance_payload(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The ain-shaped section consumed by each settings handler."""
    return payload.get("ain", {}) if command == "acd" else payload


__all__ = [
    "ALLIANCE_NAME_MIN_LENGTH",
    "ALLIANCE_NAME_MAX_LENGTH",
    "ALLIANCE_DESCRIPTION_MAX_LENGTH",
    "ALLIANCE_RENAME_RUBIES",
    "ChangeAllianceDescriptionRequest",
    "ChangeAllianceDescriptionResponse",
    "ChangeAllianceNameRequest",
    "ChangeAllianceNameResponse",
    "ChangeAllianceLanguageRequest",
    "ChangeAllianceLanguageResponse",
    "SetAllianceEmblemRequest",
    "SetAllianceEmblemResponse",
]
