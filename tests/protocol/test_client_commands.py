"""Every command the library registers exists in the committed snapshot of the client's command tables."""

import importlib.util
import json
import sys
from pathlib import Path

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
NOT_IN_CLIENT = {
    ("server", "aha"): "HelpAllResponse: the client sends aha but registers no handler for a reply to it",
    ("server", "ahc"): "HelpMemberResponse: the client sends ahc but registers no handler for a reply to it",
    ("client", "pin"): "the client sends pin under the name BasicSmartfoxClient.S2C_PING (activatePing, dll line 7168)",
    ("server", "apiOK"): "an XML system message action (handleSystemMessage), not an %xt% command",
    ("server", "joinOK"): "an XML system message action (handleSystemMessage), not an %xt% command",
    ("server", "roundTripRes"): "an XML system message action (handleSystemMessage), not an %xt% command",
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


def test_raw_commands_cover_the_code_outside_the_models():
    found = {(side, command) for side, command, _ in script.raw_commands()}

    # state/manager.py's _DISPATCH and _SECTION_PUSHES, a waiter, a handler and the keepalive f-string
    assert {("server", "abr"), ("server", "gxp"), ("server", "gbd"), ("server", "acm"), ("client", "pin")} <= found


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
