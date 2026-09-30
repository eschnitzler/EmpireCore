"""Tests for the alliance models."""

import logging

import pytest
from pydantic import ValidationError

from empire_core.alliance.models.chat import AllianceChatLogResponse, AllianceChatMessageResponse
from empire_core.alliance.models.help import (
    AllianceHelpListResponse,
    AllianceHelpRequestChanged,
    BuildingHelpParams,
    HealHelpParams,
    RecruitHelpParams,
)
from empire_core.alliance.models.info import AllianceInfo, AllianceMember, AllianceStorage, GetAllianceInfoResponse
from empire_core.enums import AllianceRank, HelpType
from empire_core.protocol.models import parse_response


class TestAllianceInfoMemberInfo:
    """AMI is an unvalidated positional server array that has drifted format before.

    model_post_init exceptions are NOT wrapped by pydantic, so anything raised
    here escapes model_validate un-wrapped and defeats `except ValidationError`.
    """

    @pytest.mark.parametrize(
        "ami",
        [
            [5],  # entry is a bare int -> len() fails
            [None],  # entry is None
            [[1, 2]],  # entry too short
            [[[1, 2], 0, 0, 0, 3]],  # unhashable player id
            [{"OID": 1, "AT": 3}],  # drifted to dicts
            "not-a-list",  # whole field drifted
        ],
    )
    def test_malformed_ami_does_not_raise(self, ami):
        try:
            info = AllianceInfo.model_validate({"AID": 1, "AMI": ami})
        except ValidationError:
            # Rejecting the field outright is acceptable; crashing is not.
            return
        assert info.alliance_id == 1

    def test_malformed_ami_entry_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.alliance.models.info"):
            AllianceInfo.model_validate({"AID": 1, "AMI": [5]})
        assert [r for r in caplog.records if r.levelno >= logging.WARNING], "malformed AMI logged nothing"

    def test_valid_ami_still_populates_activity_tier(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 1,
                "M": [{"OID": 7, "N": "online_guy"}, {"OID": 8, "N": "afk_guy"}],
                "AMI": [[7, 0, 0, 0, 0], [8, 0, 0, 0, 4]],
            }
        )
        by_name = {m.name: m for m in info.members}
        assert by_name["online_guy"].activity_tier == 0
        assert by_name["online_guy"].is_online
        assert by_name["afk_guy"].activity_tier == 4
        assert not by_name["afk_guy"].is_online
        assert info.online_count == 1

    def test_good_entries_survive_a_bad_neighbour(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 1,
                "M": [{"OID": 7, "N": "good"}],
                "AMI": [5, [7, 0, 0, 0, 2]],
            }
        )
        assert info.members[0].activity_tier == 2


GOLDEN_AIN = {
    "A": {
        "AID": 301,
        "N": "Test Alliance",
        "A": "Welcome to the alliance",
        "MP": 4213377,
        "ML": 50,
        "STO": {"W": 120000, "S": 98000, "O": 45000, "C1": 3000, "C2": 12, "I": 400, "G": 7},
        "ABL": [{"BT": 1, "L": 5, "CD": -1}, {"BT": 2, "L": 3, "CD": 3600}],
        "M": [
            {
                "OID": 7001,
                "N": "LeaderGuy",
                "L": 70,
                "LL": 812,
                "AR": 0,
                "AID": 301,
                "MP": 1200000,
                "RPT": 0,
                "AP": [[0, 12345, 640, 655, 1], [2, 22222, 300, 400, 4]],
                "E": {"BGT": 1, "BGC1": 2, "SPT": 3, "S1": 4, "IS": 1},
            },
            {
                "OID": 7002,
                "N": "OfficerGal",
                "L": 70,
                "AR": 4,
                "AID": 301,
                "RPT": 7200,
                "AP": [[0, 12346, 641, 656, 1]],
            },
        ],
        "AMI": [[7001, 0, 0, 0, 0], [7002, 0, 0, 0, 2]],
    }
}


class TestGoldenAllianceInfo:
    def test_registry_parses_ain_into_the_alliance_response(self):
        response = parse_response("ain", GOLDEN_AIN)
        assert isinstance(response, GetAllianceInfoResponse)
        assert response.success is True

    def test_alliance_header_fields(self):
        info = GetAllianceInfoResponse.model_validate(GOLDEN_AIN).alliance
        assert info is not None
        assert info.alliance_id == 301
        assert info.name == "Test Alliance"
        assert info.announcement == "Welcome to the alliance"
        assert info.might == 4213377
        assert info.external_member_level == 50
        assert info.member_count == 2

    def test_storage_and_buildings(self):
        info = GetAllianceInfoResponse.model_validate(GOLDEN_AIN).alliance
        assert info is not None
        assert info.storage is not None
        assert (info.storage.wood, info.storage.stone, info.storage.oil) == (120000, 98000, 45000)
        assert [(b.building_type, b.level, b.cooldown) for b in info.buildings] == [(1, 5, -1), (2, 3, 3600)]

    def test_storage_reads_every_donatable_key(self):
        storage = AllianceStorage.model_validate(
            {"C1": 3000, "C2": 12, "O": 45000, "G": 7, "C": 9, "FD": 1, "AC": 2, "LRC": 3, "AIN": 4}
        )
        assert (storage.coins, storage.rubies, storage.oil, storage.glass, storage.coal) == (3000, 12, 45000, 7, 9)
        assert (storage.fury_doubloons, storage.alliance_coins, storage.legendary_rift_coins) == (1, 2, 3)
        assert storage.alliance_influence == 4

    def test_storage_amounts_are_floored_and_default_to_zero(self):
        # parseStorageFromServer reads STO[key] || 0; ACollectableItemVO.amount floors it
        storage = AllianceStorage.model_validate({"W": 10.9, "S": None, "I": "abc", "C1": "25"})
        assert (storage.wood, storage.stone, storage.iron, storage.coins, storage.rubies) == (10, 0, 0, 25, 0)

    def test_members_get_their_activity_tier_from_ami(self):
        response = GetAllianceInfoResponse.model_validate(GOLDEN_AIN)
        by_name = {m.name: m for m in response.members}
        assert by_name["LeaderGuy"].activity_tier == 0
        assert by_name["OfficerGal"].activity_tier == 2
        assert [m.name for m in response.online_members] == ["LeaderGuy"]

    def test_member_castles_parse_from_the_positional_ap_array(self):
        response = GetAllianceInfoResponse.model_validate(GOLDEN_AIN)
        leader = response.members[0]
        assert [(c.kingdom_id, c.area_id, c.x, c.y, c.area_type) for c in leader.castle_positions] == [
            (0, 12345, 640, 655, 1),
            (2, 22222, 300, 400, 4),
        ]

    def test_member_derived_flags(self):
        response = GetAllianceInfoResponse.model_validate(GOLDEN_AIN)
        by_name = {m.name: m for m in response.members}
        assert by_name["LeaderGuy"].is_leader is True
        assert by_name["OfficerGal"].is_officer is True
        assert by_name["OfficerGal"].has_bird is True
        assert by_name["OfficerGal"].bird_end_time is not None
        assert by_name["LeaderGuy"].bird_end_time is None

    @pytest.mark.parametrize(
        ("rank", "leader", "officer", "enum"),
        [
            (0, True, False, AllianceRank.LEADER),
            (1, False, True, AllianceRank.COLEADER),
            (7, False, True, AllianceRank.SERGEANT),
            (8, False, False, AllianceRank.MEMBER),
            (9, False, False, AllianceRank.APPLICANT),
            (12, False, False, None),
        ],
    )
    def test_rank_zero_is_the_leader(self, rank, leader, officer, enum):
        member = AllianceMember.model_validate({"OID": 1, "AID": 5, "AR": rank})
        assert (member.is_leader, member.is_officer, member.alliance_rank_enum) == (leader, officer, enum)

    def test_typed_member_emblem(self):
        leader = GetAllianceInfoResponse.model_validate(GOLDEN_AIN).members[0]
        assert leader.emblem is not None
        assert (leader.emblem.background_type, leader.emblem.symbol1, leader.emblem.is_set) == (1, 4, True)

    def test_an_emblem_that_is_not_an_object_reads_as_none(self):
        assert AllianceMember.model_validate({"OID": 1, "E": 7}).emblem is None


class TestGoldenChatPayloads:
    def test_incoming_message_decodes(self):
        payload = {"CM": {"PN": "LeaderGuy", "MT": "100&percnt; ready, said &quot;go&quot;", "PID": 7001}}
        response = AllianceChatMessageResponse.model_validate(payload)
        assert response.player_name == "LeaderGuy"
        assert response.player_id == 7001
        assert response.decoded_text == '100% ready, said "go"'
        assert response.message_text.startswith("100&percnt;")

    def test_missing_chat_block_yields_empty_accessors(self):
        response = AllianceChatMessageResponse.model_validate({})
        assert (response.player_name, response.message_text, response.decoded_text) == ("", "", "")
        assert response.player_id == 0

    def test_chat_log_reads_the_cm_list(self):
        payload = {
            "CM": [
                {"PID": 7001, "PN": "LeaderGuy", "MT": "line&145;s one", "MA": 3600},
                {"PID": "7002", "PN": "OfficerGal", "MT": "two<br />lines", "MA": "12"},
            ]
        }
        response = AllianceChatLogResponse.model_validate(payload)
        assert [e.decoded_text for e in response.chat_log] == ["line's one", "two\nlines"]
        assert [e.player_id for e in response.chat_log] == [7001, 7002]
        assert [e.age_seconds for e in response.chat_log] == [3600, 12]

    def test_a_cl_list_is_not_the_chat_log(self):
        payload = {"CL": [{"PID": 7001, "PN": "LeaderGuy", "MT": "hi", "MA": 5}]}
        assert AllianceChatLogResponse.model_validate(payload).chat_log == []

    def test_a_message_reads_missing_fields_as_parse_obj_does(self):
        message = AllianceChatLogResponse.model_validate({"CM": [{}]}).chat_log[0]
        assert (message.player_id, message.player_name, message.message_text, message.decoded_text) == (0, "", "", "")
        assert message.age_seconds is None

    def test_an_age_reads_as_the_client_multiplies_it(self):
        response = AllianceChatLogResponse.model_validate({"CM": [{"MA": "soon"}, {"MA": None}, {"MA": "1.5"}]})
        assert [e.age_seconds for e in response.chat_log] == [None, 0, 1.5]

    def test_an_acm_push_carries_the_message_age(self):
        payload = {"CM": {"PID": 7001, "PN": "LeaderGuy", "MT": "hi", "MA": 0}}
        response = AllianceChatMessageResponse.model_validate(payload)
        assert response.chat_message is not None
        assert response.chat_message.age_seconds == 0


class TestAllianceInfoFlags:
    def test_settings_read_as_alliance_info_vo_does(self):
        from empire_core.alliance.models.info import AllianceInfo

        info = AllianceInfo.model_validate(
            {
                "CF": "1200",
                "HF": 3000,
                "IS": 1,
                "IA": 0,
                "KA": 1,
                "AW": 1,
                "HP": 0,
                "SP": 1,
                "AA": 3,
                "AP": 12.5,
                "A": None,
            }
        )
        assert (info.fame_points, info.highest_fame_points, info.application_count, info.aqua_points) == (
            1200,
            3000,
            3,
            12.5,
        )
        assert (info.is_searching_members, info.is_accepting_members, info.is_king_alliance, info.auto_war) == (
            True, False, True, True,
        )  # fmt: skip
        assert (info.can_be_invited_to_hard_pact, info.can_be_invited_to_soft_pact, info.announcement) == (
            False,
            True,
            " ",
        )


class TestAllianceInfoText:
    def test_description_and_announcement_read_as_chat_text(self):
        from empire_core.alliance.models.info import AllianceInfo

        info = AllianceInfo.model_validate({"D": "Say &quot;hi&quot;<br />now", "A": "", "RT": "30"})
        assert info.description == 'Say "hi"\nnow'
        assert info.announcement == " "
        # parseChatJSONMessage: &percnt; before %5C, and brackets become spaces
        assert AllianceInfo.model_validate({"D": "[TAG] 100&percnt;5C"}).description == " TAG  100\\"
        assert AllianceInfo.model_validate({}).announcement == " "
        assert info.refresh_seconds == 30

    def test_forge_fields_are_read_only_with_mf_and_if(self):
        from empire_core.alliance.models.info import AllianceInfo

        assert AllianceInfo.model_validate({"MF": 1, "SRFU": 4}).soft_relic_forge_uses == 0
        both = AllianceInfo.model_validate({"MF": 1, "IF": 0, "SRFU": 4})
        assert (both.is_able_to_forge, both.soft_relic_forge_uses) == (True, 4)


def test_ain_parseint_fields_read_as_javascript_parseint():
    from empire_core.alliance.models.info import AllianceInfo

    info = AllianceInfo.model_validate({"AID": "12abc", "MP": "1e3", "ML": None, "AA": 7.9})
    assert (info.alliance_id, info.might, info.external_member_level, info.application_count) == (12, 1, 0, 7)


class TestAllianceMemberInfoGuard:
    """AMI rows as AdditionalMemberInfoVO.parseAMI reads them, without failing the reply."""

    def test_a_scalar_ami_entry_is_skipped(self, caplog):
        with caplog.at_level("WARNING"):
            info = AllianceInfo.model_validate({"AID": 1, "AMI": [5, [7, 0, 0, 0, 1]]})
        assert [row.player_id for row in info.member_info] == [7]
        assert "malformed AMI entries" in caplog.text

    def test_short_and_unreadable_fields_read_as_zero(self):
        payload = {
            "AID": 7,
            "AMI": [
                ["not-an-int", 0, 0, 0, 2],
                [11, 0, 0, 0],
                [12, 0, 0, 0, "x"],
                [13, 0, 0, 0, 3],
            ],
        }
        info = AllianceInfo.model_validate(payload)
        assert [(row.player_id, row.login_activity) for row in info.member_info] == [(0, 2), (11, 0), (12, 0), (13, 3)]

    def test_a_full_row(self):
        info = AllianceInfo.model_validate({"AMI": [[42, 1000, 5, 250000, 1, 1, 2, 0, 1, 3, 180]]})
        row = info.member_info[0]
        assert (row.player_id, row.given_coins, row.given_rubies, row.given_resources, row.login_activity) == (
            42,
            1000,
            5,
            250000,
            1,
        )
        assert (row.capital_count, row.metropolis_count, row.kings_tower_count) == (1, 2, 0)
        assert (row.monument_count, row.laboratory_count, row.daily_fame) == (1, 3, 180)

    def test_a_non_list_ami_reads_as_empty(self):
        assert AllianceInfo.model_validate({"AID": 1, "AMI": "nope"}).member_info == []


class TestAllianceLandmarksAndDiplomacy:
    """AllianceInfoVO.parseStatusList and AllianceLandmarksList.parseCompleteLandmarksList."""

    CAPITAL = [3, 500, 600, 900001, 4242, 1, 1, 1, 0, 0, "Capital"]

    def test_landmark_lists_are_map_rows(self):
        info = AllianceInfo.model_validate(
            {
                "ACA": [self.CAPITAL],
                "ATC": [[22, 10, 20, 900002, 4243]],
                "AKT": [[23, 30, 40, 900003, 4244, 0, -1]],
                "AMO": [[26, 50, 60, 900004, 4245, 1, 3]],
                "ALA": [[28, 70, 80, 900005, 4246, 2, 0]],
            }
        )
        assert [(i.item_type, i.location_id, i.owner_id) for i in info.capitals] == [(3, 900001, 4242)]
        assert [i.location_id for i in info.metropolises] == [900002]
        assert [i.location_id for i in info.kings_towers] == [900003]
        assert [i.location_id for i in info.monuments] == [900004]
        assert [i.location_id for i in info.laboratories] == [900005]

    def test_an_unreadable_landmark_row_is_skipped(self, caplog):
        with caplog.at_level("WARNING"):
            info = AllianceInfo.model_validate({"ACA": [[99, "?", "?", "?"], self.CAPITAL]})
        assert [i.x for i in info.capitals] == [500]
        assert "alliance landmark rows" in caplog.text

    def test_diplomacy_entries(self):
        info = AllianceInfo.model_validate(
            {"ADL": [{"AID": 55, "AN": "Other", "AS": 3, "AC": 1}, "junk", {"AID": "56", "AS": 0, "AC": 0}]}
        )
        assert [(d.alliance_id, d.alliance_name, d.status, d.status_confirmed) for d in info.alliance_diplomacy] == [
            (55, "Other", 3, 1),
            (56, None, 0, 0),
        ]


class TestAllianceInfoOffersAndCrests:
    """AllianceInfoVO.fillFromParamObject's PO and ACLS, and parseAllianceCrestForAlliance's aee."""

    def test_a_demanded_peace_offer(self):
        info = AllianceInfo.model_validate({"AID": 1, "PO": {"T": -25, "TS": 3600}})
        assert info.peace_offer is not None
        assert (info.peace_offer.is_demanded, info.peace_offer.tribute_percentage) == (True, 25)
        assert info.peace_offer.remaining_seconds == 3600

    def test_an_offered_tribute(self):
        offer = AllianceInfo.model_validate({"AID": 1, "PO": {"T": 10, "TS": 60}}).peace_offer
        assert offer is not None and (offer.is_demanded, offer.tribute_percentage) == (False, 10)

    def test_no_peace_offer(self):
        assert AllianceInfo.model_validate({"AID": 1}).peace_offer is None
        assert AllianceInfo.model_validate({"AID": 1, "PO": "x"}).peace_offer is None

    def test_crest_layouts(self):
        info = AllianceInfo.model_validate(
            {"AID": 1, "ACLS": [{"ACLI": 4, "ACLET": 86400, "ACIA": 1, "ACLCS": [1, 2]}, {"ACLI": 5}, 7]}
        )
        assert [(c.layout_id, c.seconds_left, c.is_active, c.colors) for c in info.crest_layouts] == [
            (4, 86400, True, [1, 2]),
            (5, 0, False, None),
        ]

    def test_the_crest_and_its_fallback(self):
        info = AllianceInfo.model_validate(
            {"AID": 1, "aee": {"ACCA": {"ACLI": 3, "ACCS": [9, 8]}, "ACFB": {"ACLI": 1, "ACCS": [2]}}}
        )
        assert info.crests is not None and info.crests.crest is not None and info.crests.fallback_crest is not None
        assert (info.crests.crest.layout_id, info.crests.crest.color_ids) == (3, [9, 8])
        assert info.crests.fallback_crest.layout_id == 1

    def test_a_fallback_needs_both_layout_and_colours(self):
        crests = AllianceInfo.model_validate({"AID": 1, "aee": {"ACFB": {"ACLI": 1}}}).crests
        assert crests is not None and (crests.crest, crests.fallback_crest) == (None, None)


class TestAllianceInfoMembers:
    def test_members_are_sorted_by_rank_and_carry_their_ami_row(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 5,
                "M": [{"OID": 2, "AID": 5, "AR": 8}, {"OID": 1, "AID": 5, "AR": 0}, {"OID": 3, "AID": 5, "AR": 4}],
                "AMI": [[1, 100, 2, 300, 0, 1, 0, 0, 0, 0, 50], [3, 0, 0, 0, 3]],
            }
        )
        assert [m.player_id for m in info.members] == [1, 3, 2]
        leader, officer, member = info.members
        assert leader.member_info is not None and (leader.member_info.given_coins, leader.member_info.daily_fame) == (
            100,
            50,
        )
        assert (leader.activity_tier, officer.activity_tier, member.activity_tier) == (0, 3, None)
        assert member.member_info is None
        assert info.leader is leader

    def test_no_leader(self):
        assert AllianceInfo.model_validate({"AID": 5, "M": [{"OID": 2, "AID": 5, "AR": 8}]}).leader is None

    def test_application_count_defaults_to_twelve(self):
        assert AllianceInfo.model_validate({"AID": 1}).application_count == 12
        assert AllianceInfo.model_validate({"AID": 1, "AA": None}).application_count == 12

    def test_an_alliance_block_without_an_aid_is_none(self):
        assert GetAllianceInfoResponse.model_validate({"A": {"N": "x"}}).alliance is None


class TestAllianceHelpEntries:
    """As AllianceHelpRequestData.parseHelpRequestEntry (bundle line 133416) reads them."""

    def test_each_help_type_gets_its_params(self):
        entries = AllianceHelpListResponse.model_validate(
            {
                "AHL": [
                    {"LID": 1, "TID": 1, "OP": {"RID": 4, "AID": 5, "SID": 6, "RLID": 7}},
                    {"LID": 2, "TID": 2, "OP": {"RID": 8, "T": 1, "AID": 5, "SID": 9}},
                    {"LID": 3, "TID": 4, "OP": {"KID": 2, "AID": 5, "OID": 10}},
                ],
                "TSL": -1,
            }
        ).requests
        assert isinstance(entries[0].params, RecruitHelpParams) and entries[0].params.recruitment_list_id == 7
        assert isinstance(entries[1].params, HealHelpParams) and entries[1].params.hospital_list_id == 1
        assert isinstance(entries[2].params, BuildingHelpParams) and entries[2].params.object_id == 10
        assert [e.help_type_enum for e in entries] == [HelpType.RECRUITMENT, HelpType.HEAL_UNIT, HelpType.BUILD]

    def test_an_entry_the_client_cannot_read_costs_only_itself(self, caplog):
        with caplog.at_level(logging.WARNING):
            entries = AllianceHelpListResponse.model_validate(
                {"AHL": [{"LID": 1, "TID": 9, "OP": {}}, {"LID": 2, "TID": 3}, {"LID": 3, "TID": 3, "OP": {}}]}
            ).requests
        assert [e.list_id for e in entries] == [3]
        assert "2/3 unreadable alliance help requests" in caplog.text

    @pytest.mark.parametrize(("rt", "expected"), [(90, 90), ("90", 90), (-1, -1), (-5, -1), (None, -1)])
    def test_the_expiry_reads_as_rt_above_minus_one(self, rt, expected):
        entry = AllianceHelpRequestChanged.model_validate({"LID": 1, "TID": 3, "OP": {}, "RT": rt}).request
        assert entry is not None and entry.remaining_seconds == expected

    def test_already_confirmed_is_truthy(self):
        entry = AllianceHelpRequestChanged.model_validate({"LID": 1, "TID": 3, "OP": {}, "AC": 1}).request
        assert entry is not None and entry.already_confirmed is True

    def test_an_unreadable_push_has_no_request(self):
        assert AllianceHelpRequestChanged.model_validate({"LID": 1, "TID": 99}).request is None

    def test_the_repair_cooldown(self):
        assert AllianceHelpListResponse.model_validate({"TSL": -1}).repair_help_cooldown_seconds == 0
        assert AllianceHelpListResponse.model_validate({"TSL": 800}).repair_help_cooldown_seconds == 10000
        assert AllianceHelpListResponse.model_validate({"TSL": 20000}).repair_help_cooldown_seconds == 0


class TestReviewFollowUps:
    def test_a_missing_or_garbage_rank_is_no_rank(self):
        info = AllianceInfo.model_validate(
            {"AID": 5, "M": [{"OID": 1, "AID": 5}, {"OID": 2, "AID": 5, "AR": "x"}, {"OID": 3, "AID": 5, "AR": 8}]}
        )
        # parseInt gives NaN, which never equals 0
        assert [m.alliance_rank for m in info.members] == [8, None, None]
        assert info.leader is None
        assert not any(m.is_leader or m.is_officer for m in info.members)
        assert all(m.alliance_rank_enum is None for m in info.members[1:])

    def test_members_without_a_rank_go_last(self):
        info = AllianceInfo.model_validate(
            {"AID": 5, "M": [{"OID": 1, "AR": 4}, {"OID": 2, "AR": 0}, {"OID": 3}, {"OID": 4, "AR": 8}, {"OID": 5}]}
        )
        assert [m.player_id for m in info.members] == [2, 1, 4, 3, 5]

    def test_the_owner_record_does_not_read_cf_hf_or_ti(self):
        member = AllianceMember.model_validate({"OID": 1, "CF": 3, "HF": 9, "TI": 50})
        assert not {"glory_points", "highest_glory_points", "title_index"} & set(AllianceMember.model_fields)
        assert member.model_extra == {"CF": 3, "HF": 9, "TI": 50}

    def test_live_acls_colours_under_accs_stay_extra(self):
        (layout,) = AllianceInfo.model_validate({"AID": 1, "ACLS": [{"ACLI": 4, "ACCS": [1, 2]}]}).crest_layouts
        assert layout.colors is None
        assert layout.model_extra == {"ACCS": [1, 2]}

    def test_a_help_entry_with_a_name_that_is_not_text_is_kept(self):
        entry = AllianceHelpRequestChanged.model_validate({"LID": 1, "TID": 3, "OP": {}, "PN": 5}).request
        assert entry is not None and entry.player_name is None
