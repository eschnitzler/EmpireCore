"""Spy mission types and spy log subtypes."""

from enum import Enum, IntEnum


class SpyType(IntEnum):
    """
    Kind of spy mission, the ST field of ``csm`` and of a spy movement.

    ``SE`` in ``csm`` is the accuracy (50-100) for a military or economy
    mission and the damage (10-50) for sabotage. The client sends plague
    monks with ``cpm``, never with ``csm``.

    Client: ``ClientConstCastle.SPYTYPE_*`` (bundle line 1004),
    ``CastlePostSpyDialog.spyCastle`` (bundle line 38459),
    ``CastleSpyDialogPlagueState.spyCastle`` (bundle line 72135)
    """

    MILITARY = 0
    ECO = 1
    SABOTAGE = 2
    PLAGUE = 3


class SpyLogType(IntEnum):
    """
    Kind of mission a spy log in the mailbox is about: the first number of its header.

    These differ from :class:`SpyType`: a military mission's log is ``DEFENCE``.
    ``SABOTAGE`` (0) is also the subtype of an aborted mission.

    Client: ``MessageConst.SUBTYPE_SPY_*`` (dll line 19516)
    """

    SABOTAGE = 0
    DEFENCE = 1
    ECO = 2
    PLAGUE_MONK = 3


class SpyStep(str, Enum):
    """The command a spy mission was at when it ended."""

    SSI = "ssi"
    CSM = "csm"
    SNE = "sne"
    BSD = "bsd"


class SpyOutcome(str, Enum):
    """How a spy mission ended."""

    SUCCESS = "success"
    """The report was read."""
    SENT = "sent"
    """The mission was sent; its report is not waited for."""
    NO_SPIES_AVAILABLE = "no_spies_available"
    """No spy was free, after polling ``ssi`` for returning spies."""
    RISK_OVER_BUDGET = "risk_over_budget"
    """Even the whole pool stays above the risk ceiling, so nothing was sent."""
    COMMAND_FAILED = "command_failed"
    """A request failed; ``SpyResult.error`` holds why and ``step`` which one."""
    TIMEOUT = "timeout"
    """No report for this mission arrived before the deadline."""
    REPORT_TARGET_MISMATCH = "report_target_mismatch"
    """Only reports for other areas of the target's owner arrived before the deadline."""
    DISCONNECTED = "disconnected"
    """The connection dropped while waiting for the report."""
    CANCELLED = "cancelled"
    """
    The caller cancelled; ``SpyResult.mission`` is set when the spies had
    already left, and they keep going until recalled.
    """
    SPY_CAUGHT = "spy_caught"
    """The spies were caught or kept away."""
    NO_SPY_DATA = "no_spy_data"
    """
    The mission brought no army back, or the server has no report (``bsd``
    error 130 or 66, then in ``SpyResult.error``); the area is not known to
    be empty.
    """
