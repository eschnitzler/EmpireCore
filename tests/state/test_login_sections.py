"""GameState login sections kept as models: commanders (gli), skills (skl), your alliance (ain) and chat (acl, acm)."""

import time

import pytest
from pydantic import ValidationError

from empire_core.client.client import EmpireClient
from empire_core.commanders.models.roster import CommanderRoster
from empire_core.enums import OnlineState
from empire_core.protocol.packet import Packet

PLAYER = {"gpi": {"PID": 7, "PN": "me"}, "gal": {"AID": 300, "R": 8, "N": "Guild", "ACF": 22, "SA": 0}}


def commander(cid: int, picture: int = 1, **extra) -> dict:
    return {"ID": cid, "WID": 2, "VIS": picture, "N": f"c{cid}", "GID": -1, "W": 2, "D": 1, "SPR": 0, "EQ": [], **extra}


def castellan(cid: int, picture: int) -> dict:
    return {"ID": cid, "WID": 1, "VIS": picture, "LICID": -1, "N": "", "W": 0, "D": 0, "SPR": 0, "EQ": []}


SKILLS = {"SID": [251, 221], "RS": 0, "SP": 550, "RC": 1, "SIDS": [45, 44], "SSA": []}


def alliance(aid: int = 300, **extra) -> dict:
    block = {
        "AID": aid,
        "N": "Guild",
        "CF": 22,
        "MP": 1000,
        "D": "",
        "ALL": "en",
        "A": "",
        "AA": 3,
        "AW": 1,
        "AP": 5,
        "STO": {"W": 2},
        "MF": 1,
        "IF": 0,
        "SRFU": 4,
        "HRFU": 2,
        "M": [
            {"OID": 7, "N": "me", "R": 8, "AID": aid},
            {"OID": 8, "N": "other", "R": 0, "AID": aid},
        ],
        "AMI": [[7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [8, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0]],
    }
    block.update(extra)
    return {"A": block}


def message(pid: int, text: str, age: float = 60) -> dict:
    return {"PID": pid, "PN": f"p{pid}", "MT": text, "MA": age}


class TestCommanders:
    def test_login_list_is_kept_in_the_clients_order(self, state):
        assert state.get_commanders() is None
        castellans = [castellan(1, 5), castellan(2, 0), castellan(3, 99)]
        gli = {"C": [commander(9), commander(2), commander(5)], "B": castellans}
        state.update_from_packet("gbd", {**PLAYER, "gli": gli})

        roster = state.get_commanders()
        assert [c.commander_id for c in roster.commanders] == [2, 5, 9]
        # BaronVO.PIC_ID_ORDER: an unlisted portrait sorts first, then 0 ... 5
        assert [c.picture_id for c in roster.castellans] == [99, 0, 5]
        assert state.get_last_packet_time("gli") is not None

    def test_replies_carrying_the_list_replace_it(self, state):
        state.update_from_packet("gbd", {**PLAYER, "gli": {"C": [commander(1)], "B": []}})
        before = state.get_commanders()

        state.update_from_packet("arl", {"gli": {"C": [commander(1, N="renamed")], "B": []}})
        assert state.get_commanders().commanders[0].name == "renamed"
        assert before.commanders[0].name == "c1"

        state.update_from_packet("gli", {"C": [commander(1), commander(4)], "B": []})
        assert len(state.get_commanders().commanders) == 2

        state.update_from_packet("aci", {"gaa": {}, "gli": {"C": [commander(3)], "B": []}})
        assert [c.commander_id for c in state.get_commanders().commanders] == [3]

    def test_an_error_reply_is_not_applied(self, state):
        state.update_from_packet("gbd", {**PLAYER, "gli": {"C": [commander(1)], "B": []}})
        state.update_from_packet("gli", {"C": [], "B": []}, error_code=1)
        state.update_from_packet("arl", {"gli": {"C": [], "B": []}}, error_code=1)
        assert len(state.get_commanders().commanders) == 1

    def test_the_response_model_sorts_too(self):
        roster = CommanderRoster.model_validate({"C": [commander(3), commander(1)], "B": []})
        assert [c.commander_id for c in roster.commanders] == [1, 3]


class TestSkills:
    def test_login_section_push_and_ego(self, state):
        state.update_from_packet("gbd", {**PLAYER, "skl": SKILLS})
        assert state.get_skills().legend_skill_ids == [251, 221]

        state.update_from_packet("skl", {**SKILLS, "SID": [1]})
        assert state.get_skills().legend_skill_ids == [1]

        state.update_from_packet("ego", {"skl": {**SKILLS, "SID": [2]}})
        assert state.get_skills().legend_skill_ids == [2]

    def test_a_falsy_section_is_not_read(self, state):
        # GBDCommand.exec and EGOCommand: n.skl&&parse_SKL(n.skl)
        state.update_from_packet("gbd", {**PLAYER, "skl": SKILLS})
        state.update_from_packet("ego", {"skl": None})
        state.update_from_packet("gbd", {"skl": 0})
        assert state.get_skills().total_points == 550


class TestOwnAlliance:
    def test_login_section_is_your_alliance(self, state):
        assert state.get_own_alliance() is None
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance()})
        own = state.get_own_alliance()
        assert own.alliance_id == 300 and own.member_count == 2
        assert state.get_last_packet_time("ain") is not None

    def test_another_alliances_details_are_not_kept(self, state):
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance()})
        state.update_from_packet("ain", alliance(aid=555, N="Others"))
        assert state.get_own_alliance().name == "Guild"

    def test_keys_a_reply_leaves_out_keep_their_values(self, state):
        # AllianceInfoVO.fillFromParamObject keeps AA, AW, AP when null, STO, ACLS, aee when falsy,
        # and the forge fields unless MF and IF are both sent
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance()})
        update = alliance(N="Renamed", MF=None, IF=None, SRFU=None, HRFU=None)
        for key in ("AA", "AW", "AP", "STO"):
            del update["A"][key]
        state.update_from_packet("acn", update)

        own = state.get_own_alliance()
        assert own.name == "Renamed"
        assert (own.application_count, own.auto_war, own.aqua_points) == (3, True, 5)
        assert own.storage is not None and own.storage.wood == 2
        assert (own.is_able_to_forge, own.soft_relic_forge_uses, own.hard_relic_forge_uses) == (True, 4, 2)

    def test_nested_replies_apply_their_ain(self, state):
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance()})
        state.update_from_packet("akm", {"ain": alliance(M=[{"OID": 7, "N": "me", "R": 8, "AID": 300}])})
        assert state.get_own_alliance().member_count == 1

    def test_leaving_forgets_the_alliance_and_chat(self, state):
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance(), "acl": {"CM": [message(8, "hi")]}})
        state.update_from_packet("aqi", {"gal": {"AID": -1}})
        assert state.get_own_alliance() is None
        assert state.get_alliance_chat() == []
        assert state.local_player.alliance is None

    def test_a_gal_with_no_alliance_forgets_them(self, state):
        # CastleUserData.parse_GAL: _allianceID<0 resets the chat and my alliance
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance(), "acl": {"CM": [message(8, "hi")]}})
        state.update_from_packet("gal", {"AID": 0})
        assert state.get_own_alliance() is not None
        state.update_from_packet("gal", {"AID": -1})
        assert state.get_own_alliance() is None and state.get_alliance_chat() == []

    def test_reset_forgets_everything(self, state):
        gli = {"C": [commander(1)], "B": []}
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance(), "acl": {"CM": [message(8, "hi")]}, "gli": gli})
        state.update_from_packet("skl", SKILLS)
        state.reset()
        assert state.get_own_alliance() is None and state.get_alliance_chat() == []
        assert state.get_commanders() is None and state.get_skills() is None


class TestAllianceChat:
    def test_history_grows_with_acm(self, state):
        state.update_from_packet("gbd", {**PLAYER, "acl": {"CM": [message(8, "one"), message(8, "two")]}})
        state.update_from_packet("acm", {"CM": message(8, "three", age=0)})
        assert [m.message_text for m in state.get_alliance_chat()] == ["one", "two", "three"]
        assert state.get_last_packet_time("acm") is not None

    def test_an_acl_reply_replaces_the_history(self, state):
        # The login acl and a get_chat_log() reply list the same messages; the history keeps them once
        history = {"CM": [message(8, "one"), message(8, "two")]}
        state.update_from_packet("gbd", {**PLAYER, "acl": history})
        state.update_from_packet("acl", history)
        assert [m.message_text for m in state.get_alliance_chat()] == ["one", "two"]

    def test_an_unreadable_acl_keeps_the_history_unstamped(self, state):
        state.update_from_packet("gbd", {**PLAYER, "acl": {"CM": [message(8, "one")]}})
        stamped = state.get_last_packet_time("acl")
        state.update_from_packet("acl", {"raw": "%xt%acl%1%0%"})
        assert [m.message_text for m in state.get_alliance_chat()] == ["one"]
        assert state.get_last_packet_time("acl") == stamped

    def test_messages_are_read_only(self, state):
        state.update_from_packet("acl", {"CM": [message(8, "one")]})
        (first,) = state.get_alliance_chat()
        with pytest.raises(ValidationError):
            first.message_text = "changed"

    def test_messages_are_dated_when_read(self, state):
        state.update_from_packet("acl", {"CM": [message(8, "old", age=120)]})
        (old,) = state.get_alliance_chat()
        assert abs(old.sent_at - (time.time() - 120)) < 5

    def test_an_acm_marks_its_sender_online(self, state):
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance()})
        member = next(m for m in state.get_own_alliance().members if m.player_id == 8)
        assert not member.is_online

        state.update_from_packet("acm", {"CM": message(8, "hello")})
        member = next(m for m in state.get_own_alliance().members if m.player_id == 8)
        assert member.activity_tier == OnlineState.ONLINE

    def test_an_acm_without_a_message_adds_nothing(self, state):
        state.update_from_packet("acm", {})
        state.update_from_packet("acm", {"CM": message(8, "x")}, error_code=5)
        assert state.get_alliance_chat() == []

    def test_snapshot_is_a_copy(self, state):
        state.update_from_packet("acl", {"CM": [message(8, "one")]})
        snapshot = state.get_alliance_chat()
        state.update_from_packet("acm", {"CM": message(8, "two")})
        assert len(snapshot) == 1


class TestSnapshots:
    def test_changing_a_returned_model_changes_nothing_in_state(self, state):
        gli = {"C": [commander(1)], "B": []}
        state.update_from_packet("gbd", {**PLAYER, "ain": alliance(), "gli": gli})
        state.update_from_packet("skl", SKILLS)

        state.get_commanders().commanders.clear()
        state.get_skills().legend_skill_ids.append(999)
        state.get_own_alliance().members.clear()

        assert len(state.get_commanders().commanders) == 1
        assert 999 not in state.get_skills().legend_skill_ids
        assert state.get_own_alliance().members


class TestStamps:
    def test_another_alliances_ain_is_not_stamped(self, state):
        state.update_from_packet("gbd", PLAYER)
        state.update_from_packet("ain", alliance(aid=999))
        assert state.get_own_alliance() is None
        assert state.get_last_packet_time("ain") is None

    def test_an_unreadable_section_reply_is_not_applied_or_stamped(self, state):
        state.update_from_packet("gbd", {**PLAYER, "gli": {"C": [commander(1)], "B": []}})
        stamped = state.get_last_packet_time("gli")
        state.update_from_packet("gli", {"raw": "%xt%gli%1%0%"})
        state.update_from_packet("skl", {"raw": "%xt%skl%1%0%"})
        assert len(state.get_commanders().commanders) == 1
        assert state.get_last_packet_time("gli") == stamped
        assert state.get_skills() is None and state.get_last_packet_time("skl") is None

    def test_a_block_that_does_not_validate_is_not_stamped(self, state):
        state.update_from_packet("gbd", PLAYER)
        state.update_from_packet("skl", {**SKILLS, "SID": ["not an id"]})
        assert state.get_skills() is None
        assert state.get_last_packet_time("skl") is None


class TestClientRouting:
    def test_the_client_skips_an_error_reply(self):
        client = EmpireClient(username="u", password="p")
        client.state.update_from_packet("gbd", {**PLAYER, "gli": {"C": [commander(1)], "B": []}})
        client._on_packet(Packet.from_bytes(b'%xt%gli%1%5%{"C":[],"B":[]}%'))
        roster = client.state.get_commanders()
        assert roster is not None and len(roster.commanders) == 1
        client._on_packet(Packet.from_bytes(b'%xt%gli%1%0%{"C":[],"B":[]}%'))
        roster = client.state.get_commanders()
        assert roster is not None and roster.commanders == []
