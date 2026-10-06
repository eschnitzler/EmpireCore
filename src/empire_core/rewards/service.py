"""
The free rewards: read whether each is available, and collect it.

Nothing here spends rubies: no request of these rewards carries a cost, so none needs a
``spend_rubies`` guard. Each collect sends what the client's button sends; the client only
enables that button when the matching read says the reward is there, and the server refuses
the rest.
"""

from __future__ import annotations

import threading

from empire_core.enums import CollectableKind, LoginBonusSpecial
from empire_core.exceptions import (
    CommandError,
    EmpireTimeoutError,
    LoginBonusUnavailableError,
    NotInAllianceError,
    PacketError,
)
from empire_core.gamedata import Collectable
from empire_core.protocol.base import BaseResponse
from empire_core.protocol.packet import Packet
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

from .models import (
    LOGIN_BONUS_REQUIRED_XP,
    ActivityChestInfo,
    CollectLoginBonusRequest,
    CollectLoginBonusResponse,
    CollectLostAndFoundRequest,
    CollectPatchNoteRewardsRequest,
    CollectStartupBonusRequest,
    GetLoginBonusRequest,
    GetLoginBonusResponse,
    GetLostAndFoundRequest,
    GetLostAndFoundResponse,
    GetPatchNoteRewardsRequest,
    GetPatchNoteRewardsResponse,
    GetStartupBonusRequest,
    GetStartupBonusResponse,
    GetWeeklyHonorRequest,
    GetWeeklyHonorResponse,
    LoginBonus,
    LostAndFoundItem,
    OpenActivityChestRequest,
    PendingRewardsInfo,
    RedeemWeeklyHonorRequest,
    RedeemWeeklyHonorResponse,
)


class RewardsService(BaseService):
    """
    The daily login bonus, the startup bonus, lost and found, the activity chest, the weekly honour
    reward, the patch note rewards, and the pending rewards count.

    Reached as client.rewards.
    """

    def __init__(self, client) -> None:
        super().__init__(client)
        self._activity_chest: ActivityChestInfo | None = None
        self._pending_rewards: int | None = None
        self._activity_lock = threading.Lock()
        self.on_response("uac", self._handle_activity_chest)
        self.on_response("pre", self._handle_pending_rewards)

    def _reset(self) -> None:
        """
        Forget the pending rewards count; the client resets it when the session drops.

        Client: ``CastleDestroyGameCommand`` (bundle line 120270) resets every model, and
        ``RewardHubData.reset`` (bundle line 29783) zeroes the count
        """
        with self._activity_lock:
            self._pending_rewards = None

    # =========================================================================
    # Daily login bonus
    # =========================================================================

    def get_login_bonus(self, timeout: float = 5.0) -> GetLoginBonusResponse:
        """
        Get the daily login bonus: today's rewards to pick one from, and what was collected.

        ``today`` is the day to collect; ``has_anything_to_collect`` says whether a pick, or an
        alliance or VIP bonus you may have, is left.

        The client asks for it only from ``LOGIN_BONUS_REQUIRED_XP`` XP on, and below that the
        server sends no ``alb`` at all (seen live), so nothing is sent then.

        Raises:
            LoginBonusUnavailableError: Your XP is below ``LOGIN_BONUS_REQUIRED_XP``, or not known yet
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SGetLoginBonusVO`` (bundle line 39171), sent by ``GBDCommand`` (bundle line
        129389) only with ``userXP >= CastleLoginBonusData.REQUIRED_XP`` (bundle line 39163);
        ``ALBCommand`` (bundle line 124772)
        """
        self._require_login_bonus_xp()
        return self.request(GetLoginBonusRequest(), GetLoginBonusResponse, timeout=timeout)

    def collect_login_bonus(self, reward: Collectable, timeout: float = 5.0) -> LoginBonus:
        """
        Pick one of today's login bonus rewards.

        Args:
            reward: One of ``get_login_bonus().today.rewards``; sent as its ``send_key``, and its unit id for units
            timeout: Timeout in seconds

        Returns:
            The login bonus after the pick

        Raises:
            ValueError: A reward with no key to send: one the client has no type for, or a currency
                whose key is unknown (see ``Collectable.send_key``); nothing is sent
            LoginBonusUnavailableError: Your XP is below ``LOGIN_BONUS_REQUIRED_XP``, or not known yet
            CommandError: The server refused the pick (already picked, another day, ...)
            PacketError: The reply carries no login bonus
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleDailyLoginBonusDialog.performDailyRewardButtonSelection`` (bundle line 39228)
        sends ``C2SCatchLoginBonusVO(getServerKeyByCollectable(item), unitId or -1)``; ``CLBCommand``
        (bundle line 124790)
        """
        unit_id = reward.item if reward.kind is CollectableKind.UNITS and isinstance(reward.item, int) else -1
        request = CollectLoginBonusRequest(unit_id=unit_id, reward_key=reward.send_key)
        self._require_login_bonus_xp()
        return self._collect_login_bonus(request, timeout)

    def collect_login_bonus_special(self, special: LoginBonusSpecial, timeout: float = 5.0) -> LoginBonus:
        """
        Collect today's alliance or VIP login bonus.

        The client offers the alliance bonus only to an alliance member, so outside one nothing is
        sent. It offers the VIP bonus only while VIP is active, which the state does not know: the
        server decides that one.

        Args:
            special: ``LoginBonusSpecial.ALLIANCE`` or ``LoginBonusSpecial.VIP``
            timeout: Timeout in seconds

        Returns:
            The login bonus after the pick

        Raises:
            ValueError: ``special`` is not a ``LoginBonusSpecial``
            LoginBonusUnavailableError: Your XP is below ``LOGIN_BONUS_REQUIRED_XP``, or not known yet
            NotInAllianceError: The alliance bonus while you are in no alliance; nothing is sent
            CommandError: The server refused it
            PacketError: The reply carries no login bonus
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleDailyLoginBonusDialog.performDailySpecialBonusButtonSelection`` (bundle
        lines 39229-39237) sends ``C2SCatchLoginBonusVO(null, -1, "ALLI" or "VIP")``, the alliance
        one enabled only with ``isInAlliance`` (bundle line 39230; ``allianceID >= 0``, bundle line 9986)
        """
        special = LoginBonusSpecial(special)
        self._require_login_bonus_xp()
        player = self.client.state.get_local_player()
        alliance_id = None if player is None else player.alliance_id
        if special is LoginBonusSpecial.ALLIANCE and (alliance_id is None or alliance_id < 0):
            raise NotInAllianceError()
        return self._collect_login_bonus(CollectLoginBonusRequest(special=special), timeout)

    def _collect_login_bonus(self, request: CollectLoginBonusRequest, timeout: float) -> LoginBonus:
        # CLBCommand (bundle line 124790) parses the reply's alb unconditionally
        bonus = self.request(request, CollectLoginBonusResponse, timeout=timeout).login_bonus
        if bonus is None:
            raise PacketError("'clb' reply carries no login bonus")
        return bonus

    def _require_login_bonus_xp(self) -> None:
        player = self.client.state.get_local_player()
        xp = player.xp if player is not None and "xp" in player.model_fields_set else None
        if xp is None or xp < LOGIN_BONUS_REQUIRED_XP:
            raise LoginBonusUnavailableError(xp, LOGIN_BONUS_REQUIRED_XP)

    # =========================================================================
    # Startup login bonus
    # =========================================================================

    def get_startup_bonus(self, timeout: float = 5.0) -> GetStartupBonusResponse:
        """
        Get the startup (beginner) login bonus; ``collectable`` says whether its next reward waits.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SGetSLI`` (bundle line 54338), ``SLICommand`` (bundle line 129798)
        """
        return self.request(GetStartupBonusRequest(), GetStartupBonusResponse, timeout=timeout)

    def collect_startup_bonus(self, timeout: float = 5.0) -> bool:
        """
        Collect the next startup login bonus reward.

        Returns:
            True when the server accepted it, False when it refused it

        Client: ``C2SStartupLoginBonusCollectVO`` (bundle line 104974), sent by
        ``CastleStartupLoginBonusDialog.onClick`` (bundle line 57261) from a button enabled only
        for the next reward while it can be collected (bundle line 57258)
        """
        return self.execute(CollectStartupBonusRequest(), timeout=timeout)

    # =========================================================================
    # Lost and found
    # =========================================================================

    def get_lost_and_found(self, timeout: float = 5.0) -> list[LostAndFoundItem]:
        """
        Get the items in lost and found: those that found no room in their inventory.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SGetLostAndFoundListVO`` (bundle line 107124), ``LFECommand`` (bundle line 125350)
        """
        return self.request(GetLostAndFoundRequest(), GetLostAndFoundResponse, timeout=timeout).items

    def collect_lost_and_found(self, item_id: int, timeout: float = 5.0) -> bool:
        """
        Collect an item from lost and found into its inventory.

        Args:
            item_id: A ``LostAndFoundItem.item_id`` from :meth:`get_lost_and_found`
            timeout: Timeout in seconds

        Returns:
            True when the server accepted it, False when it refused it (the client keeps the
            button disabled while the item's inventory is full)

        Client: ``C2SCollectLostAndFoundItemVO`` (bundle line 107195), ``LostAndFoundListItem.onCollect``
        (bundle line 107151)
        """
        return self.execute(CollectLostAndFoundRequest(item_id=item_id), timeout=timeout)

    # =========================================================================
    # Activity chest
    # =========================================================================

    @property
    def activity_chest(self) -> ActivityChestInfo | None:
        """
        The activity chest from the last ``uac`` push; None until one arrived.

        The server pushes it and nothing asks for it, so it is only as fresh as the last push;
        ``is_ready()`` says whether the chest can be opened now.

        Client: ``CastleActivityBonusData.parse_UAC`` (bundle line 110921)
        """
        with self._activity_lock:
            return self._activity_chest

    on_activity_chest = Event[ActivityChestInfo]()
    """
    Call ``callback`` with each ``uac`` push, after :attr:`activity_chest` is updated.

    Detach it again with ``on_activity_chest.remove(callback)``, a no-op if it is not registered.
    """

    def _handle_activity_chest(self, response: BaseResponse) -> None:
        if not isinstance(response, ActivityChestInfo):
            return
        with self._activity_lock:
            self._activity_chest = response
        self._fire(self.on_activity_chest, response)

    def open_activity_chest(self, timeout: float = 10.0) -> ActivityChestInfo | None:
        """
        Open the activity chest, and wait for the next chest the server pushes.

        The client sends this only once :attr:`activity_chest` has no time left, and waits for
        no reply: the server sends none (seen live). What follows is a ``uac`` with the next
        chest, which updates :attr:`activity_chest` as any push does; a ``uac`` still naming the
        opened chest, ready, is not taken for it.

        Returning None on a timeout is this method's own rule: with no reply to the open, only
        the next chest tells that it opened. A ``uac`` that comes later still updates
        :attr:`activity_chest`.

        Args:
            timeout: Seconds to wait for the next ``uac``

        Returns:
            The next chest, or None when none came within ``timeout``: the request went out,
            but nothing tells whether the chest opened

        Raises:
            ValueError: No chest is known yet, or it is not ready (see ``ActivityChestInfo.is_ready``);
                nothing is sent
            CommandError: The server answered with an error ``uac``
            PacketError: The ``uac`` is not an object
            ReceiveThreadError: Called on the receive thread; nothing is sent
            ConnectionClosedError / NetworkError: The connection dropped, or the send failed

        Client: ``C2SOpenActivityChest`` (bundle line 104948), sent by ``CastleActivityBonusDialog.onClick``
        (bundle line 104934) only with ``remainingTimeTillNextActivityBonus <= 0`` and with no reply
        handled (no ``uoa`` command in the table at bundle line 120368); ``UACCommand`` (bundle
        line 129828) reads the next chest
        """
        opened = self.activity_chest
        if opened is None or not opened.is_ready():
            raise ValueError(f"the activity chest is not ready to open: {opened!r}")

        def next_chest(packet: Packet) -> bool:
            if not isinstance(packet.payload, dict):
                return True
            chest = ActivityChestInfo.model_validate(packet.payload)
            return chest.next_reward_id != opened.next_reward_id or not chest.is_ready()

        connection = self.client.connection
        try:
            packet = connection.request(
                self.client.frame(OpenActivityChestRequest()), "uac", timeout=timeout, accepts=next_chest
            )
        except EmpireTimeoutError:
            return None
        if packet.error_code != 0:
            raise CommandError("uac", packet.error_code, packet.payload)
        if not isinstance(packet.payload, dict):
            raise PacketError("'uac' push is not an object")
        return ActivityChestInfo.model_validate(packet.payload)

    # =========================================================================
    # Weekly honour reward
    # =========================================================================

    def get_weekly_honor(self, timeout: float = 5.0) -> GetWeeklyHonorResponse:
        """
        Get your weekly honour rank; ``is_ready`` says whether last week's reward waits.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SGetWeeklyHonorRankVO`` (bundle line 69926), ``GWHCommand`` (bundle line 124364)
        """
        return self.request(GetWeeklyHonorRequest(), GetWeeklyHonorResponse, timeout=timeout)

    def redeem_weekly_honor(self, timeout: float = 5.0) -> RedeemWeeklyHonorResponse:
        """
        Redeem last week's honour reward.

        The client enables its button only with honour and a waiting reward. The reply's coins
        and rubies reach ``client.state`` as any ``gcu`` does.

        Returns:
            Your coins, rubies and units after the reward

        Raises:
            CommandError: The server refused it (no reward waits)
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SRedeemWeeklyHonorBonus`` (bundle line 69934), sent by
        ``CastleWeeklyHighscoreRewardDialog.collect`` (bundle line 45392); ``RWBCommand`` (bundle line 124426)
        """
        return self.request(RedeemWeeklyHonorRequest(), RedeemWeeklyHonorResponse, timeout=timeout)

    # =========================================================================
    # Patch note rewards
    # =========================================================================

    def get_patch_note_rewards(self, message_id: int, timeout: float = 5.0) -> tuple[Collectable, ...]:
        """
        Get a patch note's rewards; the header's ``collected`` says whether they were collected.

        Args:
            message_id: A patch note's ``MessageInfo.message_id`` in ``client.messages.mailbox``
            timeout: Timeout in seconds

        Raises:
            ValueError: ``message_id`` is no patch note in the mailbox, or its header names no patch
                note id; nothing is sent
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleChangelistDialog.requestRewards`` (bundle line 136088) sends
        ``C2SGetPatchNoteRewardsVO`` (bundle line 136140) when the dialog opens; ``GPNCommand``
        (bundle line 125302)
        """
        patch_note_id, _ = self._patch_note(message_id)
        request = GetPatchNoteRewardsRequest(patch_note_id=patch_note_id)
        return self.request(request, GetPatchNoteRewardsResponse, timeout=timeout).rewards

    def collect_patch_note_rewards(self, message_id: int, timeout: float = 5.0) -> bool:
        """
        Collect a patch note's rewards.

        As the dialog does, the rewards are read first (a ``gpn``), and only a patch note not
        collected yet that has rewards is collected. The mailbox copy of the message keeps its
        header: the client marks only its own copy collected.

        Args:
            message_id: A patch note's ``MessageInfo.message_id`` in ``client.messages.mailbox``
            timeout: Timeout in seconds for each request

        Returns:
            True when the server accepted it, False when it refused it

        Raises:
            ValueError: ``message_id`` is no patch note in the mailbox, its header names no patch
                note id or says it was collected, or it has no rewards; the collect is not sent
            CommandError / EmpireTimeoutError / ConnectionClosedError: the reward read failed;
                see :meth:`EmpireClient.send`

        Client: ``CastleChangelistDialog.collectRewards`` (bundle line 136119) sends
        ``C2SCollectPatchNoteRewardsVO`` (bundle line 136131) from a button enabled only while the
        header's ``collected`` is false and shown only with rewards (``updateCollectButton``,
        bundle line 136114); ``CPNCommand`` (bundle line 125269)
        """
        patch_note_id, collected = self._patch_note(message_id)
        if collected:
            raise ValueError(f"the patch note {message_id} was collected")
        if not self.get_patch_note_rewards(message_id, timeout=timeout):
            raise ValueError(f"the patch note {message_id} has no rewards")
        request = CollectPatchNoteRewardsRequest(patch_note_id=patch_note_id, message_id=message_id)
        return self.execute(request, timeout=timeout)

    def _patch_note(self, message_id: int) -> tuple[int, bool]:
        message = next((m for m in self.client.messages.mailbox if m.message_id == message_id), None)
        header = None if message is None else message.patch_note_header()
        if header is None or header.patch_note_id is None:
            raise ValueError(f"message {message_id} is no patch note in the mailbox")
        return header.patch_note_id, header.collected

    # =========================================================================
    # Pending rewards
    # =========================================================================

    @property
    def pending_rewards(self) -> int | None:
        """
        How many rewards wait in the reward hub, from the last ``pre`` push; None until one arrived.

        The reward hub lists and hands out the rewards over its web service, which the library
        does not reach.

        Client: ``RewardHubData.getAmountOfPendingRewards`` (bundle line 29787)
        """
        with self._activity_lock:
            return self._pending_rewards

    on_pending_rewards = Event[PendingRewardsInfo]()
    """
    Call ``callback`` with each ``pre`` push, after :attr:`pending_rewards` is updated.

    Detach it again with ``on_pending_rewards.remove(callback)``, a no-op if it is not registered.

    Client: ``PRECommand.executeCommand`` (bundle line 120837) dispatches ``PRE_ARRIVED``
    """

    def _handle_pending_rewards(self, response: BaseResponse) -> None:
        if not isinstance(response, PendingRewardsInfo):
            return
        with self._activity_lock:
            self._pending_rewards = response.amount
        self._fire(self.on_pending_rewards, response)


__all__ = ["RewardsService"]
