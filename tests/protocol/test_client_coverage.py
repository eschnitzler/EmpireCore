"""Where each client command stands, from the committed snapshot and coverage rules; no client bundle needed."""

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TABLES = json.loads((ROOT / "tests" / "data" / "client_commands.json").read_text(encoding="utf-8"))
RULES = json.loads((ROOT / "tests" / "data" / "client_coverage.json").read_text(encoding="utf-8"))


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
COVERAGE = {row.command: row for row in script.classify(TABLES, RULES)}
RAW = {(side, command) for side, command, _ in script.raw_commands()}


def _bucket(bucket: str) -> set[str]:
    return {command for command, row in COVERAGE.items() if row.bucket == bucket}


class TestCommittedCoverage:
    def test_every_command_is_in_one_bucket(self):
        assert set(COVERAGE) == set(TABLES["client"]) | set(TABLES["server"])
        assert {row.bucket for row in COVERAGE.values()} <= set(script.BUCKETS)

    def test_every_remaining_command_has_an_owner(self):
        unowned = sorted(command for command in _bucket("remaining") if not COVERAGE[command].detail)

        assert unowned == [], "give these an issue in client_coverage.json owners, or an unowned note"

    def test_every_owned_command_is_remaining(self):
        owned = {command for commands in RULES["owners"].values() for command in commands} | set(RULES["unowned"])

        assert sorted(owned - _bucket("remaining")) == [], "these are done, ack-only, excluded or dead; drop them"

    def test_the_library_uses_no_dead_command(self):
        models = script.library_models()
        used = set(models["client"]) | set(models["server"]) | {command for _, command in RAW}

        assert sorted(used & _bucket("dead")) == []

    def test_login_sections_without_a_handler_are_handled_by_gbd(self):
        # GBDCommand.exec reads n.drt (CastleTimerData.parse_DRT) and n.gac (parse_UAP)
        assert TABLES["handlers"]["drt"] == TABLES["handlers"]["gac"] == ["GBDCommand (section)"]
        assert COVERAGE["drt"].bucket == COVERAGE["gac"].bucket == "done"

    def test_a_handler_that_drops_its_parsed_payload_is_ack_only(self):
        # MOTCommand.executeCommand: case a.ERROR.ALL_OK:JSON.parse(t[1]);break;
        assert TABLES["handlers"]["mot"] == ["MOTCommand (ack)"]
        assert COVERAGE["mot"].bucket == "ack-only"

    def test_every_exclusion_is_still_needed(self):
        excluded = {command for commands in RULES["excluded"].values() for command in commands}

        assert sorted(excluded - _bucket("excluded")) == [], "these are done or dead; drop them from excluded"

    @pytest.mark.parametrize("command", sorted(RULES["covered_without_model"]))
    def test_covered_without_model_is_needed_and_true(self, command):
        entry = RULES["covered_without_model"][command]
        others = {name: other for name, other in RULES["covered_without_model"].items() if name != command}
        rules = {**RULES, "covered_without_model": others}

        assert COVERAGE[command].bucket == "done"
        assert {row.command: row for row in script.classify(TABLES, rules)}[command].bucket != "done"
        if "raw" in entry:
            assert (entry["raw"], command) in RAW
        elif "model" in entry:
            module, name = entry["model"].rsplit(".", 1)
            from empire_core.protocol.base import EmpireModel

            model = getattr(importlib.import_module(module), name)
            assert issubclass(model, EmpireModel)
            if "field" in entry:
                assert model.model_fields[entry["field"]].validation_alias == command
        else:
            from empire_core.state.manager import _NESTED_SECTIONS

            assert _NESTED_SECTIONS[command] == tuple(entry["sections"])

    def test_registered_handlers_and_raw_sends_are_live(self):
        handled = {"gch", "nch", "gfl", "cmt", "vpm", "core_cps", "core_spe", "core_spl", "core_tci", "core_gpi"}
        handled |= {"core_gic", "core_sic", "gpf", "lcb", "mot", "core_nfo", "tee", "drt", "gac"}

        assert sorted(handled & _bucket("dead")) == []
        assert COVERAGE["pin"].bucket == "done"

    def test_ruby_wishing_well_and_event_packages_are_not_excluded(self):
        assert {"rww", "sbp", "gbc"}.isdisjoint(_bucket("excluded"))

    def test_the_report_is_stable(self):
        report = script.coverage_report(TABLES, script.classify(TABLES, RULES))

        counts = {bucket: len(_bucket(bucket)) for bucket in script.BUCKETS}

        assert sum(counts.values()) == len(COVERAGE)
        assert all(f"| {bucket} | {count} |" in report for bucket, count in counts.items())
        assert TABLES["bundle_release"] in report


class TestClassify:
    TABLES = {
        "bundle_release": "b1",
        "dll_release": "d1",
        "client": {name: [] for name in ("sent", "both", "gone", "paid", "raw")},
        "server": {name: [] for name in ("both", "ack", "push", "gone", "paid")},
        "requests": {"sent": ["V"], "both": ["V"], "paid": ["V"], "raw": ["X.C2S_RAW (sent)"]},
        "handlers": {"both": ["H"], "ack": ["H (ack)"], "push": ["H"], "paid": ["H (ack)"]},
    }
    MODELS = {"client": {"sent": ["Request"], "both": ["Request"]}, "server": {"both": ["Response"]}}
    RULES = {
        "excluded": {"payments": ["paid"]},
        "covered_without_model": {"raw": {"raw": "client", "note": "sent raw"}},
        "owners": {"9": ["push"]},
        "unowned": {},
    }

    def test_buckets(self):
        rows = script.classify(self.TABLES, self.RULES, self.MODELS)

        assert rows == [
            script.Coverage("ack", "ack-only"),
            script.Coverage("both", "done"),
            script.Coverage("gone", "dead"),
            script.Coverage("paid", "excluded", "payments"),
            script.Coverage("push", "remaining", "#9", ("reply",)),
            script.Coverage("raw", "done", "sent raw"),
            script.Coverage("sent", "done"),
        ]

    def test_report(self):
        report = script.coverage_report(self.TABLES, script.classify(self.TABLES, self.RULES, self.MODELS))

        assert report.startswith("# Client coverage: bundle b1, dll d1\n")
        assert "| done | 3 |" in report
        assert "| `push` | reply | #9 |" in report
        assert "- payments: `paid`" in report
        assert "- `raw`: sent raw" in report


def test_coverage_alone_reports_on_the_committed_snapshot(capsys):
    assert script.main(["--coverage"]) == 0

    assert capsys.readouterr().out == script.coverage_report(TABLES, script.classify(TABLES, RULES))
