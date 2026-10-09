"""The login's version check."""

from enum import IntEnum


class VersionCheckStatus(IntEnum):
    """
    The version check (``vck``) refusals, which are not ``GGEError`` codes.

    Client: ``VCKCommand.VERSION_TOO_LOW`` and ``VERSION_TOO_HIGH`` (dll line 14473),
    matched by ``CastleVCKCommand.executeCommand`` (bundle line 120444)
    """

    VERSION_TOO_LOW = 1
    VERSION_TOO_HIGH = 2
