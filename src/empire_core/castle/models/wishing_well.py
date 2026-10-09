"""
The ruby wishing well.

Commands:
- rww: the wishing well's level and time, a login section of ``gbd`` and a reply
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import TimedResponse
from empire_core.protocol.js import ClientInt, ClientNumber


class WishingWellResponse(TimedResponse):
    """
    The ruby wishing well: its level and whether it can be started, runs, or waits to be collected.

    Command: rww, as a login section of ``gbd`` and a successful reply; a reply refused for lack of
    resources is not read.

    Client: ``RWWCommand`` (bundle line 126903), ``CastleRubyWishingWellData.parse_RWW`` (bundle line 21255),
    ``isReadyToStart``, ``isReadyToCollect``, ``isRunning`` and ``getRemainingSecondsCalculated``
    (bundle lines 21248-21262)
    """

    command = "rww"

    level: ClientInt = Field(
        validation_alias="L", serialization_alias="L", default=-1, description="The wishing well's level, -1 for none"
    )
    seconds: ClientNumber = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=-1,
        description="Seconds left when the values were read: -1 ready to start, 0 ready to collect",
    )

    @property
    def is_ready_to_start(self) -> bool:
        """Whether the wishing well can be started, as last read."""
        return self.seconds == -1

    @property
    def is_ready_to_collect(self) -> bool:
        """Whether the wishing well waits to be collected, as last read."""
        return self.seconds == 0

    @property
    def is_running(self) -> bool:
        """Whether the wishing well runs, as last read."""
        return not (self.is_ready_to_start or self.is_ready_to_collect)

    def remaining_seconds(self, now: float | None = None) -> int:
        """Whole seconds until it is done, 0 at least."""
        return int(max(0.0, self.seconds - self._elapsed(now)))


__all__ = ["WishingWellResponse"]
