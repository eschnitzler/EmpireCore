"""Every command the library registers exists in the committed snapshot of the client's command tables."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "tests" / "data" / "client_commands.json"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "extract_client_commands", ROOT / "scripts" / "extract_client_commands.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()
TABLES = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

# Commands the library knows that the client has no constant for, each with why it stays.
NOT_IN_CLIENT: dict[tuple[str, str], str] = {
    ("server", "lwta"): "the client registers LWTACommand under C2S_LAUNCH_WOLFKING_TAUNT_ATTACK (bundle line 124330)",
}


def test_every_registered_command_is_in_the_client():
    missing = [
        (side, command, where)
        for side, command, where in script.missing_commands(TABLES)
        if (side, command) not in NOT_IN_CLIENT
    ]

    assert missing == []


def test_the_allowlist_holds_only_commands_still_missing():
    for side, command in NOT_IN_CLIENT:
        assert command not in TABLES[side], f"{command} is in the client now; drop it from NOT_IN_CLIENT"
        assert command in script.library_commands()[side], f"the library no longer registers {command}"


def test_the_snapshot_records_its_release():
    assert TABLES["generated_by"] == "scripts/extract_client_commands.py"
    assert TABLES["bundle_release"] and TABLES["dll_release"]
    assert len(TABLES["client"]) > 400 and len(TABLES["server"]) > 400


def test_the_snapshot_is_rendered_as_the_script_writes_it():
    assert SNAPSHOT.read_text(encoding="utf-8") == script.render(TABLES)


def test_a_dropped_command_fails_the_check():
    tables = {**TABLES, "client": {k: v for k, v in TABLES["client"].items() if k != "gaa"}}

    assert ("client", "gaa") in [(side, command) for side, command, _ in script.missing_commands(tables)]
    assert script.changes(TABLES, tables) == [
        "client dropped gaa (ClientConstSF.C2S_GET_AREAS, ConstantsSmartFox.C2S_GET_AREAS)"
    ]


def _check(tmp_path, bundle: str, out: Path) -> int:
    (tmp_path / "bundle.js").write_text(bundle, encoding="utf-8")
    (tmp_path / "dll.js").write_text('BasicSmartfoxConstants.S2C_P="p";', encoding="utf-8")
    argv = ["--bundle", str(tmp_path / "bundle.js"), "--dll", str(tmp_path / "dll.js"), "--out", str(out)]
    return script.main([*argv, "--bundle-release", "b2", "--dll-release", "d2", "--check"])


def test_a_new_release_alone_passes_the_check(tmp_path):
    out = tmp_path / "snapshot.json"
    out.write_text(
        script.render(script.snapshot('ClientConstSF.C2S_A="a";', 'BasicSmartfoxConstants.S2C_P="p";', "b1", "d1"))
    )

    assert _check(tmp_path, 'ClientConstSF.C2S_A="a";', out) == 0
    assert _check(tmp_path, 'ClientConstSF.C2S_B="a";', out) == 1


# Server messages the library reads without a response model: the SmartFox system messages
RAW_SERVER_COMMANDS = {"apiOK", "joinOK", "roundTripRes", "rlu"}


def test_every_server_command_the_state_reads_has_a_response_model():
    import empire_core.protocol.models  # noqa: F401  fills the registry
    from empire_core.protocol.base import get_response_model

    raw = {
        command
        for side, command, _ in script.raw_commands()
        if side == "server" and get_response_model(command) is None
    }
    assert raw <= RAW_SERVER_COMMANDS, f"give these a response model: {sorted(raw - RAW_SERVER_COMMANDS)}"


def test_raw_commands_cover_the_code_outside_the_models():
    found = {(side, command) for side, command, _ in script.raw_commands()}

    # state/manager.py's _DISPATCH and _SECTION_PUSHES, a waiter, a handler, and the keepalive and vck frames
    assert {
        ("server", "abr"),
        ("server", "gxp"),
        ("server", "gbd"),
        ("server", "acm"),
        ("client", "pin"),
        ("client", "vck"),
    } <= found


def test_raw_commands_read_each_kind_of_use(tmp_path):
    package = tmp_path / "empire_core"
    package.mkdir()
    (package / "mod.py").write_text(
        "_DISPATCH = {'aaa': 'h'}\n"
        "_SECTION_PUSHES = frozenset({'bbb'})\n"
        "client.on_response('ccc', f)\n"
        "connection.request(packet, 'ddd', timeout=1)\n"
        "connection.wait_for_result(cmd_id='eee', waiter=w)\n"
        "Packet.build_xt(zone, 'fff', {})\n"
        "if cmd_id == 'ggg': pass\n"
        "send(f'%xt%{zone}%hhh%1%{body}%')\n"
        "log('iii')\n"
    )

    assert sorted(script.raw_commands(package)) == [
        ("client", "fff", "empire_core/mod.py:6"),
        ("client", "hhh", "empire_core/mod.py:8"),
        ("server", "aaa", "empire_core/mod.py:1"),
        ("server", "bbb", "empire_core/mod.py:2"),
        ("server", "ccc", "empire_core/mod.py:3"),
        ("server", "ddd", "empire_core/mod.py:4"),
        ("server", "eee", "empire_core/mod.py:5"),
        ("server", "ggg", "empire_core/mod.py:7"),
    ]


class TestExtract:
    def test_named_and_minified_holders(self):
        source = (
            'ClientConstSF.C2S_LOGIN="lli",ClientConstSF.S2C_LOGIN="lli";'
            "var f=function(){return function ConstantsSmartFox(){}}();"
            'f.C2S_RENAME_CASTLE="arc",f.S2C_RENAME_CASTLE="arc",f.THIRD_PARTY_GET_MAPPING="tgm";'
            "var f=function(){return function OtherConstants(){}}();"
            'f.S2C_PING="pin";'
            'if(e==ClientConstSF.C2S_LOGIN)x.C2S_LOGIN=="lli"'
        )

        assert script.extract(source) == {
            "client": {"arc": ["ConstantsSmartFox.C2S_RENAME_CASTLE"], "lli": ["ClientConstSF.C2S_LOGIN"]},
            "server": {
                "arc": ["ConstantsSmartFox.S2C_RENAME_CASTLE"],
                "lli": ["ClientConstSF.S2C_LOGIN"],
                "pin": ["OtherConstants.S2C_PING"],
            },
        }

    def test_system_messages_and_sent_server_constants(self):
        # BasicSmartfoxClient.handleSystemMessage and activatePing (dll lines 7228, 7168)
        source = (
            'BasicSmartfoxClient.S2C_PING="pin",BasicSmartfoxClient.C2S_A="a";'
            't.sendMessage(BasicSmartfoxClient.S2C_PING,[""]);t.sendMessage(BasicSmartfoxClient.C2S_A,[]);'
            "BasicSmartfoxClient.prototype.handleSystemMessage=function(e){switch(n){"
            'case"apiOK":x();break;case"joinOK":y();break;default:z()}};switch(k){case"notSystem":}'
        )

        tables = script.extract(source)

        assert tables["client"] == {
            "a": ["BasicSmartfoxClient.C2S_A"],
            "pin": ["BasicSmartfoxClient.S2C_PING (sent)"],
        }
        assert tables["server"] == {
            "apiOK": ["BasicSmartfoxClient.handleSystemMessage"],
            "joinOK": ["BasicSmartfoxClient.handleSystemMessage"],
            "pin": ["BasicSmartfoxClient.S2C_PING"],
        }

    def test_snapshot_merges_the_bundle_and_dll(self):
        data = script.snapshot('ClientConstSF.C2S_A="a";', 'BasicSmartfoxConstants.C2S_A="a";', "b1", "d1")

        assert data["client"] == {"a": ["BasicSmartfoxConstants.C2S_A", "ClientConstSF.C2S_A"]}
        assert (data["bundle_release"], data["dll_release"], data["server"]) == ("b1", "d1", {})

    def test_changes_show_renames_and_releases(self):
        old = {"bundle_release": "b1", "dll_release": "d1", "client": {"a": ["X.C2S_A"]}, "server": {}}
        new = {"bundle_release": "b2", "dll_release": "d1", "client": {"a": ["X.C2S_B"]}, "server": {"p": ["X.S2C_P"]}}

        assert script.changes(old, new) == [
            "bundle_release: b1 -> b2",
            "client a: X.C2S_A -> X.C2S_B",
            "server added p (X.S2C_P)",
        ]


BUNDLE = (
    'ClientConstSF.C2S_A="a",ClientConstSF.S2C_A="a",ClientConstSF.C2S_B="b",ClientConstSF.S2C_B="b",'
    'ClientConstSF.S2C_GDI="gdi",ClientConstSF.S2C_GPF="gpf";'
    "var c=function(e){function C2SAVO(){}return n.__extends(C2SAVO,e),"
    "C2SAVO.prototype.getCmdId=function(){return a.ClientConstSF.C2S_A},C2SAVO}(o.BasicCommandVO);"
    "var d=function(e){function C2SBVO(){}return n.__extends(C2SBVO,e),"
    "C2SBVO.prototype.getCmdId=function(){return a.ClientConstSF.C2S_B},C2SBVO}(o.BasicCommandVO);"
    "x.sendCommandVO(new r.C2SAVO(1)),x.sendCommandVO(new l.CoreC2SXVO(2));"
    "var g=function(e){function CastleCommand(){}return n.__extends(CastleCommand,e),"
    "CastleCommand.prototype.executeCommand=function(e,t){return this.d.isDelayedCommand(this.cmdId)"
    "?this.d.addDelayCommand(this.cmdId,this,[e,t]):this.exec([e,t]),!1},"
    'CastleCommand.prototype.exec=function(e){throw new Error("method needs to be overriden")},'
    "CastleCommand}(o.BasicCommand);"
    "var h=function(e){function ACommand(){}return n.__extends(ACommand,e),"
    "ACommand.prototype.executeCommand=function(e,t){switch(e){case a.ERROR.ALL_OK:break;"
    "default:this.showErrorDialog(e,t)}return!1},ACommand}(l.CastleCommand);"
    "var k=function(e){function GPFCommand(){}return n.__extends(GPFCommand,e),"
    'Object.defineProperty(GPFCommand.prototype,"cmdId",{get:function(){return s.ClientConstSF.S2C_GDI}}),'
    "GPFCommand.prototype.executeCommand=function(t,i){return e.prototype.executeCommand.call(this,t,i)},"
    "GPFCommand.prototype.exec=function(e){var t=s.int(e[0]),i=e[1];switch(t){case a.ERROR.ALL_OK:"
    "var n=JSON.parse(i[1]);r.parse_GPF(n);break;default:this.showErrorDialog(t,i)}},GPFCommand}(l.CastleCommand);"
    "var m=function(e){function BCommand(){}return n.__extends(BCommand,e),"
    "BCommand.prototype.exec=function(e){var t=s.int(e[0]),i=e[1];switch(t){case a.ERROR.ALL_OK:break;"
    "default:this.showErrorDialog(t,i)}},BCommand}(l.CastleCommand);"
    "i.set(s.ClientConstSF.S2C_A,new h.ACommand),i.set(s.ClientConstSF.S2C_GPF,new k.GPFCommand),"
    "i.set(s.ClientConstSF.S2C_B,new m.BCommand);"
)
DLL = (
    'BasicSmartfoxConstants.C2S_X="core_x",BasicSmartfoxConstants.C2S_Y="y";'
    "var f=function(e){function CoreC2SXVO(){}return i.__extends(CoreC2SXVO,e),"
    "CoreC2SXVO.prototype.getCmdId=function(){return s.BasicSmartfoxConstants.C2S_X},"
    "CoreC2SXVO}(n(124).BasicCommandVO);"
    "u.BasicModel.smartfoxClient.sendMessage(s.BasicSmartfoxConstants.C2S_Y,[]);"
    "BasicSmartfoxClient.prototype.handleSystemMessage=function(e){switch(n){"
    'case"apiOK":x();break;default:z()}};'
)


class TestUsage:
    def test_handlers_are_keyed_by_registration(self):
        # GPFCommand's cmdId getter returns S2C_GET_DETAILPLAYERINFO; it is registered under S2C_PREMIUM_FLAG_INFO
        assert TABLES["handlers"]["gpf"] == ["GPFCommand"]
        assert "GPFCommand" not in TABLES["handlers"]["gdi"]

    def test_requests_count_constructions_across_the_bundle_and_dll(self):
        # CoreC2SSetInviteCodeVO is defined in the dll and constructed in the bundle
        assert TABLES["requests"]["core_sic"] == ["CoreC2SSetInviteCodeVO"]
        assert TABLES["requests"]["pin"] == ["BasicSmartfoxClient.S2C_PING (sent)"]

    def test_requests_are_constructed_classes_and_direct_sends(self):
        assert script.usage((BUNDLE, DLL))["requests"] == {
            "a": ["C2SAVO"],
            "core_x": ["CoreC2SXVO"],
            "y": ["BasicSmartfoxConstants.C2S_Y (sent)"],
        }

    def test_handlers_follow_registrations_and_payload_reads(self):
        assert script.usage((BUNDLE, DLL))["handlers"] == {
            "a": ["ACommand (ack)"],
            "apiOK": ["BasicSmartfoxClient.handleSystemMessage"],
            "b": ["BCommand (ack)"],
            "gpf": ["GPFCommand"],
        }

    def test_an_unresolvable_constant_raises(self):
        with pytest.raises(ValueError, match="C2S_NONE"):
            script.usage(("x.sendMessage(a.ClientConstSF.C2S_NONE,[]);",))
