"""Messages: the mailbox, mail and spy reports."""

from empire_core.enums import MessageType

from .models import (
    MAX_MAILBOX_ARCHIVE_SIZE,
    MAX_MAILBOX_BATTLE_AND_SPY_REPORTS,
    MAX_MAILBOX_SIZE,
    MESSAGE_TYPE_SPY_NPC,
    MESSAGE_TYPE_SPY_PLAYER,
    SPY_VALIDITY,
    ForwardSpyLogRequest,
    GetSpyReportRequest,
    MessageInfo,
    SpyLogHeader,
    SpyReportArea,
    SpyReportResponse,
    SystemNotificationEvent,
    repair_header,
)

__all__ = [
    "MAX_MAILBOX_SIZE",
    "MAX_MAILBOX_ARCHIVE_SIZE",
    "MAX_MAILBOX_BATTLE_AND_SPY_REPORTS",
    "repair_header",
    "ForwardSpyLogRequest",
    "GetSpyReportRequest",
    "MESSAGE_TYPE_SPY_NPC",
    "MESSAGE_TYPE_SPY_PLAYER",
    "MessageInfo",
    "SPY_VALIDITY",
    "SpyLogHeader",
    "SpyReportArea",
    "SpyReportResponse",
    "SystemNotificationEvent",
    "MessageType",
]
