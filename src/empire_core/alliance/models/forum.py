"""Alliance forum topics, posts and visibility."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import AllianceRank, ForumRankGroup
from empire_core.gamedata.lenient import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_truthy
from empire_core.protocol.text import decode_json_text, encode_json_text

logger = logging.getLogger(__name__)


def _decoded_text(value: Any) -> str:
    """Client: ``TextValide.parseChatJSONMessage`` (i420/dllsplit.js line 5820)."""
    if not js_truthy(value):
        return ""
    if not isinstance(value, str):
        raise ValueError("forum text must be a string")
    return decode_json_text(value)


class ForumTopic(BasePayload):
    """A topic summary. Client: ``CastleForumTopicVO.parseGAT`` (bundle line 68085)."""

    topic_id: ClientInt = Field(validation_alias="TID", description="Topic id")
    name: str = Field(validation_alias="N", description="Topic title")
    author: str = Field(validation_alias="CN", description="Topic creator's name")
    created_at: float = Field(validation_alias="CT", description="Creation time as Unix seconds")
    author_rank: EnumOrInt[AllianceRank] = Field(validation_alias="CR", description="Creator's alliance rank")
    visible_ranks: list[EnumOrInt[ForumRankGroup]] = Field(validation_alias="RG", description="Visible rank groups")
    reply_count: ClientInt = Field(validation_alias="RC", description="Number of replies")
    last_poster: str = Field(validation_alias="LRN", description="Last poster's name")
    last_post_at: float = Field(validation_alias="LRT", description="Last post time as Unix seconds")
    was_read: bool = Field(validation_alias="R", description="Whether you have read the topic")

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> str:
        return _decoded_text(value)

    @field_validator("was_read", mode="before")
    @classmethod
    def _read(cls, value: Any) -> bool:
        return js_truthy(value)


class ForumPost(BasePayload):
    """A forum post. Client: ``CastleForumPostVO.parseGTRItem`` (bundle line 68066)."""

    reply_id: ClientInt = Field(validation_alias="RID", description="Reply id")
    text: str = Field(validation_alias="RT", description="Post text")
    author: str = Field(validation_alias="PN", description="Poster's name")
    author_rank: EnumOrInt[AllianceRank] = Field(validation_alias="AR", description="Poster's alliance rank")
    created_at: float = Field(validation_alias="T", description="Creation time as Unix seconds")

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return _decoded_text(value)


class GetForumTopicsRequest(BaseRequest):
    """List visible topics. Client: ``C2SGetAllianceTopicsVO`` (bundle line 68817)."""

    command = "gat"


class GetForumTopicsResponse(BaseResponse):
    """Topic overview. Client: ``CastleAllianceForumData.parseGAT`` (bundle line 8055)."""

    command = "gat"
    topic_count: ClientInt = Field(validation_alias="TC", description="Total topics including hidden topics")
    topics: list[ForumTopic] = Field(validation_alias="T", description="Visible topics, latest post first")

    @field_validator("topics", mode="before")
    @classmethod
    def _topics(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("forum topics must be an array")
        return sorted(
            readable_list(
                ForumTopic, value, accept=lambda row: isinstance(row, dict), warn=logger, what="forum topics"
            ),
            key=lambda t: t.last_post_at,
            reverse=True,
        )


class GetForumTopicRequest(BaseRequest):
    """Open a topic. Client: ``C2SGetAllianceTopicRepliesVO`` (bundle line 68872)."""

    command = "gtr"
    topic_id: int = Field(validation_alias="TID", description="Topic id")


class GetForumTopicResponse(BaseResponse):
    """A topic's posts. Client: ``CastleForumTopicDetailVO.parseGTR`` (bundle line 68044)."""

    command = "gtr"
    name: str = Field(validation_alias="TN", description="Topic title")
    author: str = Field(validation_alias="CN", description="Topic creator's name")
    visible_ranks: list[EnumOrInt[ForumRankGroup]] = Field(validation_alias="RG", description="Visible rank groups")
    posts: list[ForumPost] = Field(default_factory=list, validation_alias="R", description="Topic posts")

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> str:
        return _decoded_text(value)

    @field_validator("posts", mode="before")
    @classmethod
    def _posts(cls, value: Any) -> Any:
        if not js_truthy(value):
            return []
        if not isinstance(value, list):
            raise ValueError("forum posts must be an array")
        return readable_list(
            ForumPost, value, accept=lambda row: isinstance(row, dict), warn=logger, what="forum posts"
        )


class GetUnreadTopicCountRequest(BaseRequest):
    """Ask for unread topics. Client: ``C2SGetAllianceUnreadTopicsCount`` (bundle line 68148)."""

    command = "utc"


class GetUnreadTopicCountResponse(BaseResponse):
    """Unread topic count. Client: ``CastleAllianceForumData.parseUTC`` (bundle line 8064)."""

    command = "utc"
    count: ClientInt = Field(validation_alias="UTC", description="Unread topic count")


def forum_text(text: str, maximum: int) -> str:
    """Validate once-encoded UTF-16 length, then encode for the constructor.

    Client: ``CastleAllianceForumData.getForumValidText`` (bundle line 8084),
    ``ClientConstUtils.getTrimmedText`` (bundle line 1979), and ``AllianceConst``
    (i420/dllsplit.js line 18805).
    """
    trimmed = text.strip(
        "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
        "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
    )
    encoded = encode_json_text(trimmed)
    if not 2 <= len(encoded.encode("utf-16-le", errors="surrogatepass")) // 2 <= maximum:
        raise ValueError(f"forum text must encode to 2–{maximum} characters")
    return encode_json_text(encoded)


class CreateForumTopicRequest(BaseRequest):
    """Create a topic. Client: ``C2SAllianceTopicCreateVO`` (bundle line 68760)."""

    command = "atc"
    name: str = Field(validation_alias="N", description="Topic title")
    visible_ranks: list[ForumRankGroup] = Field(validation_alias="RG", description="Visible rank groups")
    text: str = Field(validation_alias="R", description="Opening post")

    @field_serializer("name")
    def _name(self, value: str) -> str:
        return forum_text(value, 38)

    @field_serializer("text")
    def _text(self, value: str) -> str:
        return forum_text(value, 2000)


class CreateForumTopicResponse(BaseResponse):
    """Creation accepted. Client: ``ATCCommand.executeCommand`` (bundle line 121725)."""

    command = "atc"


class ReplyToForumTopicRequest(BaseRequest):
    """Reply to a topic. Client: ``C2SAllianceAnswerTopicVO`` (bundle line 68863)."""

    command = "aat"
    topic_id: int = Field(validation_alias="TID", description="Topic id")
    text: str = Field(validation_alias="RT", description="Reply text")

    @field_serializer("text")
    def _text(self, value: str) -> str:
        return forum_text(value, 2000)


class ReplyToForumTopicResponse(BaseResponse):
    """Reply accepted. Client: ``AATCommand.executeCommand`` (bundle line 121682)."""

    command = "aat"


class DeleteForumTopicRequest(BaseRequest):
    """Delete a topic. Client: ``C2SAllianceTopicDeleteVO`` (bundle line 69002)."""

    command = "atd"
    topic_id: int = Field(validation_alias="TID", description="Topic id")


class DeleteForumTopicResponse(BaseResponse):
    """Deletion accepted. Client: ``ATDCommand.executeCommand`` (bundle line 121739)."""

    command = "atd"


class DeleteForumReplyRequest(BaseRequest):
    """Delete a post. Client: ``C2SAllianceDeleteTopicAnswerVO`` (bundle line 68993)."""

    command = "ada"
    topic_id: int = Field(validation_alias="TID", description="Topic id")
    reply_id: int = Field(validation_alias="RID", description="Reply id")


class DeleteForumReplyResponse(BaseResponse):
    """Deletion accepted. Client: ``ADACommand.executeCommand`` (bundle line 121711)."""

    command = "ada"


class SetForumVisibilityRequest(BaseRequest):
    """Change visibility. Client: ``C2SAllianceTopicChangeRanks`` (bundle line 68769)."""

    command = "acr"
    topic_id: int = Field(validation_alias="TID", description="Topic id")
    visible_ranks: list[ForumRankGroup] = Field(validation_alias="RG", description="Visible rank groups")


class SetForumVisibilityResponse(BaseResponse):
    """Changed topic if included. Client: ``ACRCommand.executeCommand`` (bundle line 121696)."""

    command = "acr"
    topic: GetForumTopicResponse | None = Field(default=None, validation_alias="gtr", description="Changed topic")
