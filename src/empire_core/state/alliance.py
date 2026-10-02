"""Your own alliance's details (ain) and the alliance chat history (acl, acm)."""

import logging
from typing import Any

from empire_core.alliance.models.chat import AllianceChatLogResponse, ChatMessageData
from empire_core.alliance.models.info import AllianceInfo, alliance_of_ain
from empire_core.enums import OnlineState
from empire_core.protocol.base import read_or_none
from empire_core.protocol.js import js_int, js_truthy
from empire_core.state.base import StateBase

logger = logging.getLogger(__name__)

# Keys AllianceInfoVO.fillFromParamObject leaves as they were when a reply sends them as null
_KEPT_WHEN_NULL = ("AA", "AW", "AP")
# ... and when it sends them falsy
_KEPT_WHEN_FALSY = ("STO", "ACLS", "aee")
_FORGE_KEYS = ("MF", "IF", "SRFU", "HRFU")
_AMI_LOGIN_ACTIVITY = 4


class AllianceState(StateBase):
    def _parse_own_alliance(self, data: dict[str, Any]) -> bool:
        """Apply an ``ain`` section when it is about your own alliance; whether it was applied.

        Other alliances' details (``client.alliance.get_alliance_info(other_id)``) are not kept.
        A reply for the same alliance is read over the last one: the keys the client keeps
        when a reply leaves them out (``AA``, ``AW``, ``AP``, ``STO``, ``ACLS``, ``aee``, and
        ``MF``, ``IF``, ``SRFU``, ``HRFU`` unless both ``MF`` and ``IF`` are sent) keep their values.

        Client: ``CastleAllianceData.parse_AIN`` (bundle line 11560) and ``parseAllianceInfo``
        (bundle line 11605), which keeps the alliance whose ``AID`` is ``userData.allianceID`` as
        ``myAllianceVO``; ``AllianceInfoVO.fillFromParamObject`` (bundle line 25928)
        """
        if "ain" not in data:
            return False
        block = alliance_of_ain(data["ain"])
        player = self.local_player
        if block is None or player is None or player.AID is None:
            return False
        if js_int(block["AID"]) != js_int(player.AID):
            return False
        raw = dict(block)
        previous = self._own_alliance_raw
        if previous is not None and js_int(previous.get("AID")) == js_int(raw["AID"]):
            for key in _KEPT_WHEN_NULL:
                if raw.get(key) is None and key in previous:
                    raw[key] = previous[key]
            for key in _KEPT_WHEN_FALSY:
                if not js_truthy(raw.get(key)) and key in previous:
                    raw[key] = previous[key]
            if raw.get("MF") is None or raw.get("IF") is None:
                for key in _FORGE_KEYS:
                    raw.pop(key, None)
                    if key in previous:
                        raw[key] = previous[key]
        return self._store_own_alliance(raw)

    def _store_own_alliance(self, raw: dict[str, Any]) -> bool:
        alliance = read_or_none(AllianceInfo.model_validate, raw, warn=logger, what="your alliance's details")
        if alliance is None:
            return False
        self._own_alliance_raw = raw
        self.own_alliance = alliance
        return True

    def _forget_own_alliance(self) -> None:
        self._own_alliance_raw = None
        self.own_alliance = None
        self.alliance_chat = ()

    def _apply_gal_reset(self, data: dict[str, Any]) -> None:
        """Forget your alliance's details and chat when a ``gal`` says you are in none.

        Client: ``CastleUserData.parse_GAL`` (bundle line 9869): ``_allianceID<0`` runs
        ``chatData.resetHistory`` and ``allianceData.resetMyAlliance``
        """
        gal = data.get("gal")
        if isinstance(gal, dict) and js_int(gal.get("AID")) < 0:
            self._forget_own_alliance()

    def _handle_aqi(self, data: Any) -> None:
        """Handle the reply to leaving your alliance: the chat and details are forgotten, its ``gal`` applied.

        Client: ``AQICommand.executeCommand`` (bundle line 121557): ``resetHistory``, ``parse_GAL(i.gal)``,
        ``resetMyAlliance``
        """
        self.alliance_chat = ()
        if isinstance(data, dict) and "gal" in data:
            self._handle_gbd({"gal": data["gal"]})
        self._forget_own_alliance()

    def _parse_chat_history(self, data: dict[str, Any], *, replace: bool = False) -> bool:
        """Add an ``acl`` section's messages to the chat history, after the ones already there;
        whether it was applied.

        ``replace`` starts the history over with them instead, for an ``acl`` reply: the client
        asks for the history only at login, when it is empty, so a reply to
        ``client.alliance.get_chat_log()`` would otherwise list every message twice.

        Client: ``CastleChatData.parseHistory`` (bundle line 111294), which appends every ``CM`` entry
        """
        acl = data.get("acl")
        if not isinstance(acl, dict):
            return False
        log = read_or_none(AllianceChatLogResponse.model_validate, acl, warn=logger, what="the alliance chat log")
        if log is None:
            return False
        self.alliance_chat = (*(() if replace else self.alliance_chat), *log.chat_log)
        return True

    def _handle_acm(self, data: Any) -> None:
        """Add an ``acm`` message to the chat history, and mark its sender online in your alliance.

        Client: ``CastleChatData.parseSingleMessage`` (bundle line 111288), from ``ACMCommand``
        (bundle line 121317): it appends the message, then sets the sender's ``AMI`` login
        activity to ``ONLINESTATE_ONLINE`` when the player id is 0 or more
        """
        block = data.get("CM") if isinstance(data, dict) else None
        if not isinstance(block, dict):
            return
        message = read_or_none(ChatMessageData.model_validate, block, warn=logger, what="an alliance chat message")
        if message is None:
            return
        self.alliance_chat = (*self.alliance_chat, message)
        raw = self._own_alliance_raw
        if message.player_id < 0 or raw is None or not isinstance(rows := raw.get("AMI"), list):
            return
        index = next(
            (
                i
                for i in range(len(rows) - 1, -1, -1)
                if isinstance(rows[i], list) and rows[i] and js_int(rows[i][0]) == message.player_id
            ),
            None,
        )
        if index is None:
            return
        row = list(rows[index]) + [0] * max(0, _AMI_LOGIN_ACTIVITY + 1 - len(rows[index]))
        row[_AMI_LOGIN_ACTIVITY] = int(OnlineState.ONLINE)
        self._store_own_alliance({**raw, "AMI": [*rows[:index], row, *rows[index + 1 :]]})

    def get_own_alliance(self) -> AllianceInfo | None:
        """Your alliance's details and members, from the last ``ain`` about it; None in no alliance or before one.

        The login gbd brings it, and so do ``client.alliance.get_alliance_info(your_id)`` and the
        replies that carry it (``acd``, ``acn``, ``ado``, ``akm``, ``arm``, ``cal``). An ``acm`` marks its
        sender online here. A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.own_alliance is None else self.own_alliance.model_copy(deep=True)

    def get_alliance_chat(self) -> list[ChatMessageData]:
        """The alliance chat history, oldest first; a copy of the list, of read-only messages.

        The login gbd's ``acl`` starts it, an ``acl`` reply (``client.alliance.get_chat_log()``)
        replaces it, and every ``acm`` adds one. Leaving the alliance, a ``gal`` with no alliance
        and a disconnect start it over.
        """
        with self._lock:
            return list(self.alliance_chat)
