"""Your alliance's upgrades, settings and gifts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.alliance.models.gifts import AllianceGift, CollectAllianceGiftRequest, CollectAllianceGiftResponse
from empire_core.alliance.models.info import AllianceInfo, GetAllianceInfoRequest, GetAllianceInfoResponse
from empire_core.alliance.models.settings import (
    ALLIANCE_RENAME_RUBIES,
    ChangeAllianceDescriptionRequest,
    ChangeAllianceDescriptionResponse,
    ChangeAllianceLanguageRequest,
    ChangeAllianceLanguageResponse,
    ChangeAllianceNameRequest,
    ChangeAllianceNameResponse,
    SetAllianceEmblemRequest,
    SetAllianceEmblemResponse,
    alliance_name,
    settings_alliance_payload,
)
from empire_core.alliance.models.upgrades import AllianceUpgradeRequest, AllianceUpgradeResponse
from empire_core.alliance.service.own import OwnAllianceMixin, _echoed
from empire_core.enums import AllianceBuffType, CollectableKind
from empire_core.exceptions import PacketError
from empire_core.map.models.owners import AllianceCrest
from empire_core.protocol.base import BaseRequest

if TYPE_CHECKING:
    from empire_core.gamedata import AllianceCrestColor, AllianceCrestLayout

_UPGRADABLE_BUFFS = frozenset(AllianceBuffType) - {AllianceBuffType.NOBLE_HOUSE}
# AllianceBuffData.CUSTOMIZABLE_BUFFS (bundle line 27759)
_CUSTOMIZABLE_BUFFS = frozenset(
    {
        AllianceBuffType.RAGE_POINT_BOOST,
        AllianceBuffType.COOLDOWN_REDUCTION_KHAN,
        AllianceBuffType.COOLDOWN_REDUCTION_NOMADS,
        AllianceBuffType.ALIEN_ATTACK_BOOST,
        AllianceBuffType.DAIMYO_ATTACK_BOOST,
        AllianceBuffType.KHAN_DEFENSE_BOOST,
        AllianceBuffType.HEALING_SPEED_BOOST,
        AllianceBuffType.COOLDOWN_REDUCTION_SAMURAI_CAMP,
        AllianceBuffType.COOLDOWN_REDUCTION_DAIMYO,
        AllianceBuffType.TEMP_RAID_BOSS_COMMON_ATTACK_BOOST,
        AllianceBuffType.TEMP_RAID_BOSS_RARE_ATTACK_BOOST,
        AllianceBuffType.TEMP_RAID_BOSS_EPIC_ATTACK_BOOST,
        AllianceBuffType.TEMP_RAID_BOSS_LEGENDARY_ATTACK_BOOST,
    }
)


class AllianceSettingsMixin(OwnAllianceMixin):
    def upgrade(
        self,
        building_type: AllianceBuffType | int,
        level: int = 1,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> AllianceUpgradeResponse:
        """Upgrade a permanent alliance buff or buy/prolong a temporary boost.

        Fresh alliance details determine the actual treasury cost. Consent covers
        alliance treasury rubies, not personal rubies. The server enforces rank
        permissions and available funds through typed CommandError refusals.

        Client: C2SAllianceUpgradeVO (27432–27435), OpenAllianceBuyBoosterCommand
        (91124–91173), AllianceInfoVO.getUpgradeCosts (26031), customizable
        dialog (91199/91219), forge dialog (69522/69528), AUGCommand (121660).
        """
        if isinstance(building_type, bool) or building_type not in _UPGRADABLE_BUFFS:
            raise ValueError(f"unsupported alliance upgrade {building_type}")
        if isinstance(level, bool) or level < 1 or (building_type not in _CUSTOMIZABLE_BUFFS and level != 1):
            raise ValueError("only customizable temporary boosts accept a selected level")
        data = self._require_game_data()
        rows = {row.level: row for row in data.alliance_buffs.values() if row.series_id == building_type}
        if not rows:
            raise ValueError(f"unknown alliance buff series {building_type}")
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        with self.client.connection.command_lock("aug", timeout=timeout):
            preflight_sequence = self.client.state.alliance_upgrade_sequence()
            with (
                self.client.connection.command_lock("ain", timeout=timeout),
                self.client.state.alliance_info_read(alliance_id),
            ):
                preflight, preflight_payload = self._request_membership(
                    GetAllianceInfoRequest(alliance_id=alliance_id), GetAllianceInfoResponse, timeout=timeout
                )
            details = _echoed(preflight.alliance, "ain")
            preflight_sequence = self.client.state.require_alliance_upgrade_preflight(
                preflight_sequence, membership_revision=revision, alliance_id=alliance_id, payload=preflight_payload
            )
            current = next((row for row in details.buildings if row.building_type == building_type), None)
            if details.alliance_id != alliance_id:
                raise PacketError("alliance preflight names a different alliance")
            if (
                current is None
                or not {"building_type", "level", "cooldown"} <= current.model_fields_set
                or current.level not in rows
            ):
                raise ValueError("fresh alliance details contain no known current buff level")
            maximum = rows[current.level].max_level
            next_row = rows.get(min(current.level + 1, maximum))
            if next_row is None:
                raise ValueError("unknown next alliance buff level")
            temporary = next_row.duration_seconds != -1
            if not temporary and current.level >= maximum:
                raise ValueError("alliance buff is already at its maximum level")
            if temporary and next_row.required_buff_id != -1:
                required = data.alliance_buffs.get(next_row.required_buff_id)
                if required is None or not any(
                    row.building_type == required.series_id and row.level >= required.level for row in details.buildings
                ):
                    raise ValueError("temporary boost prerequisite is not satisfied")
            if building_type in _CUSTOMIZABLE_BUFFS:
                if not temporary or level not in rows or level > maximum:
                    raise ValueError("unknown temporary boost level")
                if current.cooldown > 0 and level != current.level:
                    raise ValueError("an active temporary boost can only be prolonged at its current level")
                cost_row = rows[level]
            else:
                cost_row = next_row
            if any(cost.kind == CollectableKind.OTHER or cost.amount < 0 for cost in cost_row.costs):
                raise ValueError("unknown alliance upgrade cost")
            rubies = sum(cost.amount for cost in cost_row.costs if cost.kind == CollectableKind.RUBIES)
            self._require_spend_rubies(
                spend_rubies, f"alliance treasury upgrade costs {rubies} rubies" if rubies else None
            )
            self.client.state.require_alliance_upgrade_preflight(
                preflight_sequence, membership_revision=revision, alliance_id=alliance_id
            )
            with self._own_alliance():
                response, payload = self._request_membership(
                    AllianceUpgradeRequest(building_type=building_type, level=level),
                    AllianceUpgradeResponse,
                    timeout=timeout,
                )
            self.client.state.apply_alliance_settings(
                {
                    "A": {
                        "AID": alliance_id,
                        "STO": payload["STO"],
                        "ABL": [row.to_payload() for row in response.buildings],
                    }
                },
                membership_revision=revision,
                alliance_id=alliance_id,
                command="aug",
                payload=payload,
            )
            return response

    def set_description(self, text: str, *, timeout: float = 5.0) -> AllianceInfo:
        """Change the alliance description, returning echoed alliance details.

        Text follows the client's trim, double encoding and 1000-character wire limit.
        Client: CastleChangeDescriptionDialog.sendDescription (bundle 69775–69778).
        """
        return self._change_settings(
            ChangeAllianceDescriptionRequest(text=text, text_type=1), ChangeAllianceDescriptionResponse, timeout=timeout
        )

    def set_announcement(self, text: str, *, timeout: float = 5.0) -> AllianceInfo:
        """Change the alliance announcement, returning echoed alliance details.

        Client: CastleChangeAnouncementDialog.sendDescription (bundle 70504).
        """
        return self._change_settings(
            ChangeAllianceDescriptionRequest(text=text, text_type=0), ChangeAllianceDescriptionResponse, timeout=timeout
        )

    def rename(self, name: str, *, spend_rubies: bool = False, timeout: float = 5.0) -> AllianceInfo:
        """Rename the alliance; a fresh free rename avoids the 10,000-ruby charge.

        Without consent this first requests alliance details to check free renames.
        Client: CastleNameAllianceDialog.showLoaded (bundle 69791–69792),
        AllianceConst.RENAME_COST_C2 (dll line 18805).
        """
        alliance_name(name)
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        with self.client.connection.command_lock("acn", timeout=timeout):
            if not spend_rubies:
                details = self.get_alliance_info(alliance_id, timeout=timeout)
                self._require_spend_rubies(
                    spend_rubies,
                    f"renaming the alliance costs {ALLIANCE_RENAME_RUBIES} rubies"
                    if details.free_renames == 0
                    else None,
                )
            self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
            return self._change_settings(
                ChangeAllianceNameRequest(name=name),
                ChangeAllianceNameResponse,
                membership=(alliance_id, revision),
                timeout=timeout,
            )

    def set_language(self, language: str, *, timeout: float = 5.0) -> AllianceInfo:
        """Set the alliance language code, returning echoed alliance details.

        Client: CastleAllianceDialogManagement.onLanguageSelect (bundle 69621).
        """
        return self._change_settings(
            ChangeAllianceLanguageRequest(language=language), ChangeAllianceLanguageResponse, timeout=timeout
        )

    def set_emblem(
        self, layout_id: AllianceCrestLayout | int, color_ids: list[AllianceCrestColor | int], *, timeout: float = 5.0
    ) -> AllianceCrest:
        """Save an available alliance crest, returning the acknowledged selection.

        Temporary layouts must still be held. The server pushes authoritative crest
        state separately; this acknowledgment does not fabricate a crest update.
        Client: AllianceCrestCreationDialog.update/doSave (bundle 45205–45211),
        C2SSetAllianceEmblemVO (69672–69674), SAECommand (122004).
        """
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        data = self._require_game_data()
        layout = data.alliance_crest_layouts.get(layout_id)
        if layout is None:
            raise ValueError(f"unknown alliance crest layout {layout_id}")
        if len(color_ids) != layout.color_count or any(color not in data.alliance_crest_colors for color in color_ids):
            raise ValueError("the crest needs one known colour for each layout colour")
        if layout.max_duration > 0:
            details = self.get_alliance_info(alliance_id, timeout=timeout)
            if not any(row.layout_id == layout_id and row.seconds_left > 0 for row in details.crest_layouts):
                raise ValueError("the temporary crest layout is not currently held")
        self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
        with self._own_alliance():
            self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
            self.request(
                SetAllianceEmblemRequest(layout_id=layout_id, color_ids=color_ids),
                SetAllianceEmblemResponse,
                timeout=timeout,
            )
        self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
        return AllianceCrest(layout_id=layout_id, color_ids=list(color_ids))

    def _change_settings(
        self,
        request: BaseRequest,
        response_type: type[GetAllianceInfoResponse],
        *,
        membership: tuple[int, int] | None = None,
        timeout: float,
    ) -> AllianceInfo:
        with self.client.connection.command_lock(request.command, timeout=timeout):
            alliance_id, revision = membership or (
                self._require_local_alliance_id(),
                self.client.state.membership_revision,
            )
            with self._own_alliance():
                self.client.state.apply_alliance_settings({}, membership_revision=revision, alliance_id=alliance_id)
                response, payload = self._request_membership(request, response_type, timeout=timeout)
            alliance = _echoed(response.alliance, request.command)
            if alliance.alliance_id != alliance_id:
                raise PacketError(f"'{request.command}' reply names a different alliance")
            self.client.state.apply_alliance_settings(
                settings_alliance_payload(request.command, payload),
                membership_revision=revision,
                alliance_id=alliance_id,
                command=request.command,
                payload=payload,
            )
            return alliance

    @property
    def gifts(self) -> list[AllianceGift]:
        """Your unexpired alliance gifts, soonest expiration first; received through pushes."""
        return self.client.state.get_alliance_gifts()

    def collect_gift(self, gift_id: int, *, timeout: float = 5.0) -> CollectAllianceGiftResponse:
        """Collect a gift and return the unpacked rewards.

        Client: AllianceGiftScrollItem.onMouseClick (bundle 105236),
        AGCCommand (121823) and CastleAllianceGiftData.parse_AGC (131937–131939).
        """
        alliance_id = self._require_local_alliance_id()
        revision = self.client.state.membership_revision
        with self._own_alliance():
            response = self.request(
                CollectAllianceGiftRequest(gift_id=gift_id), CollectAllianceGiftResponse, timeout=timeout
            )
        self.client.state.apply_alliance_gift_collection(
            response.gift_id, membership_revision=revision, alliance_id=alliance_id
        )
        return response
