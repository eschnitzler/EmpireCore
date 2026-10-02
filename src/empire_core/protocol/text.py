"""
The client's text codecs for strings it sends in and reads out of JSON commands.

The two are not inverses: decoding turns square brackets into spaces and
reads ``&percnt;`` before ``%5C``, exactly as the client does.
"""

from __future__ import annotations


def encode_json_text(text: str) -> str:
    """
    Encode text the way the client does before it puts it in a command.

    Replaces ``%``, ``'``, ``"``, a carriage return, a backslash and a newline, in
    that order, and turns tabs into spaces.

    Client: ``TextValide.getValideSmartFoxJSONTextMessage`` (dll line 5817)
    """
    result = text.replace("%", "&percnt;").replace("'", "&145;").replace('"', "&quot;")
    result = result.replace("\r", "<br />").replace("\\", "%5C").replace("\n", "<br />")
    return result.replace("\t", " ")


def decode_json_text(text: str | None) -> str:
    """
    Decode server text the way the client does.

    Replaces ``&percnt;``, ``&quot;``, ``&145;``, ``<br />`` and ``%5C`` in that
    order and turns square brackets into spaces; nothing reads as ``""``.

    Client: ``TextValide.parseChatJSONMessage`` (dll line 5820)
    """
    if not text:
        return ""
    result = text.replace("&percnt;", "%").replace("&quot;", '"').replace("&145;", "'")
    result = result.replace("<br />", "\n").replace("%5C", "\\")
    return result.replace("[", " ").replace("]", " ")


SMARTFOX_INVALID_CHARS: tuple[str, ...] = (
    "%", "&", "*", "/", "(", ")", "[", "]", "{", "}", '"', "'", "\\",
    "´", "`", "^", "°", "§", "€", "²", "³", ",", ";", "µ", "$",
)  # fmt: skip
"""Characters the client refuses in a name it checks.

Client: ``TextValide.invalidChars`` (dll line 5831)
"""


def is_smartfox_valid(text: str) -> bool:
    """
    Whether the client accepts ``text`` as a name: not blank, and none of :data:`SMARTFOX_INVALID_CHARS`.

    Client: ``TextValide.isSmartFoxValide`` (dll line 5777)
    """
    return bool(text.strip()) and not any(char in text for char in SMARTFOX_INVALID_CHARS)


__all__ = ["SMARTFOX_INVALID_CHARS", "decode_json_text", "encode_json_text", "is_smartfox_valid"]
