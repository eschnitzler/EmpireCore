"""The activity chest (uac) and the reward hub's pending rewards count (pre), both pushed."""

from typing import Any

from empire_core.rewards.models import ActivityChestInfo, PendingRewardsInfo
from empire_core.state.base import StateBase, read_section


class RewardsState(StateBase):
    def _handle_uac(self, data: Any) -> None:
        if (chest := read_section(ActivityChestInfo, data, "the activity chest")) is not None:
            self.activity_chest = chest

    def _handle_pre(self, data: Any) -> None:
        if (pending := read_section(PendingRewardsInfo, data, "the pending rewards")) is not None:
            self.pending_rewards = pending.amount

    def get_activity_chest(self) -> ActivityChestInfo | None:
        """The activity chest from the last ``uac`` push; None until one arrived.

        The server pushes it and nothing asks for it, so it is only as fresh as the last push;
        ``is_ready()`` says whether the chest can be opened now. It is kept when the session drops.

        Client: ``CastleActivityBonusData.parse_UAC`` (bundle line 110921)
        """
        with self._lock:
            return self.activity_chest

    def get_pending_rewards(self) -> int | None:
        """How many rewards wait in the reward hub, from the last ``pre`` push; None until one arrived.

        The reward hub lists and hands out the rewards over its web service, which the library
        does not reach. Forgotten when the session drops, as the client zeroes it.

        Client: ``RewardHubData.getAmountOfPendingRewards`` (bundle line 29787); ``RewardHubData.reset``
        (bundle line 29783), from ``CastleDestroyGameCommand`` (bundle line 120270)
        """
        with self._lock:
            return self.pending_rewards
