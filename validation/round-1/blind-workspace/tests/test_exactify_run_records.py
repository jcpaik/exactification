from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
SCRIPT = WORKSPACE / "exactify" / "make_run_records.py"
SPEC = importlib.util.spec_from_file_location("exactify_make_run_records", SCRIPT)
assert SPEC and SPEC.loader
RUN_RECORDS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUN_RECORDS
SPEC.loader.exec_module(RUN_RECORDS)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RunRecordCliTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.case = self.root / "case"
        self.input = self.case / "input"
        self.attempt = self.case / "attempts" / "attempt-1"
        self.input.mkdir(parents=True)
        self.attempt.mkdir(parents=True)

        self.write_json(self.input / "manifest.json", {"id": "portable-case"})
        (self.input / "model.json").write_text('{"format":"model"}\n', encoding="utf-8")
        (self.attempt / "candidate.json").write_text("candidate\n", encoding="utf-8")
        self.write_json(
            self.attempt / "commands.json",
            [
                {
                    "argv": ["python3", "-m", "verify", "check"],
                    "exit_code": 0,
                    "purpose": "fresh exact check",
                }
            ],
        )
        self.write_json(
            self.attempt / "discovery.json",
            {
                "seeds": [],
                "precision_ladder": {"decimal_digits": [80]},
                "relation_height_ladder": [8, 16],
                "denominator_ladder_bits": [64, 96],
                "objective_branches": [{"value": "0", "status": "accepted"}],
                "nullity_branches": {"X": [1]},
                "public_matching_construction_used": False,
            },
        )

    def write_json(self, path: Path, value) -> None:
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def cli(self, *extra: str) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--case-root",
            str(self.case),
            "--attempt-id",
            "attempt-1",
            "--commands-json",
            "attempts/attempt-1/commands.json",
            "--discovery-json",
            "attempts/attempt-1/discovery.json",
            "--started-utc",
            "2026-01-02T03:04:05Z",
            "--ended-utc",
            "2026-01-02T04:05:06Z",
            *extra,
        ]
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def settings(self, *, replace: bool = False) -> object:
        return RUN_RECORDS.Settings(
            case_root=self.case,
            attempt_id="attempt-1",
            commands_json=Path("attempts/attempt-1/commands.json"),
            discovery_json=Path("attempts/attempt-1/discovery.json"),
            started_utc="2026-01-02T03:04:05Z",
            ended_utc="2026-01-02T04:05:06Z",
            replace=replace,
        )

    def test_hashes_portable_paths_excludes_self_and_is_deterministic(self) -> None:
        first = self.cli()
        self.assertEqual(first.returncode, 0, first.stderr)

        run_path = self.attempt / "run.json"
        first_bytes = run_path.read_bytes()
        record = json.loads(first_bytes)
        self.assertEqual(record["case_id"], "portable-case")
        self.assertEqual(record["repository"]["commit"], "not_inspected_blind_policy")
        self.assertEqual(record["repository"]["dirty_worktree"], "not_inspected_blind_policy")
        self.assertEqual(record["consumed_file_sha256"]["input/model.json"], digest(self.input / "model.json"))
        self.assertEqual(
            record["generated_file_sha256"]["attempts/attempt-1/candidate.json"],
            digest(self.attempt / "candidate.json"),
        )
        self.assertNotIn("attempts/attempt-1/run.json", record["generated_file_sha256"])
        self.assertEqual(record["denominator_ladder"], [64, 96])
        self.assertNotIn("denominator_ladder_bits", record)

        second = self.cli("--replace")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(run_path.read_bytes(), first_bytes)

    def test_existing_run_requires_replace_and_remains_unchanged(self) -> None:
        self.assertEqual(self.cli().returncode, 0)
        run_path = self.attempt / "run.json"
        original = run_path.read_bytes()

        second = self.cli()
        self.assertEqual(second.returncode, 2)
        self.assertIn("--replace", second.stderr)
        self.assertEqual(run_path.read_bytes(), original)

    def test_rejects_attempt_and_metadata_traversal(self) -> None:
        unsafe_attempt = self.cli("--attempt-id", "../escape")
        self.assertEqual(unsafe_attempt.returncode, 2)
        self.assertIn("safe path component", unsafe_attempt.stderr)

        unsafe_metadata = self.cli("--commands-json", "attempts/../attempts/attempt-1/commands.json")
        self.assertEqual(unsafe_metadata.returncode, 2)
        self.assertIn("traversal", unsafe_metadata.stderr)
        self.assertFalse((self.attempt / "run.json").exists())

    def test_rejects_symlink_escape_from_hashed_tree(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        link = self.input / "escape.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink unavailable: {error}")

        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes the allowed root", result.stderr)
        self.assertFalse((self.attempt / "run.json").exists())

    def test_rejects_duplicate_json_keys(self) -> None:
        (self.attempt / "commands.json").write_text(
            '[{"argv":["first"],"argv":["second"],"exit_code":0,"purpose":"check"}]\n',
            encoding="utf-8",
        )
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate JSON key", result.stderr)
        self.assertFalse((self.attempt / "run.json").exists())

    def test_generates_without_optional_packages(self) -> None:
        def missing(distribution: str) -> str:
            raise RUN_RECORDS.metadata.PackageNotFoundError(distribution)

        output = RUN_RECORDS.generate_run_record(self.settings(), version_lookup=missing)
        record = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            record["tool_versions"],
            {
                "mpmath": "not_available",
                "numpy": "not_available",
                "python_flint": "not_available",
                "sympy": "not_available",
            },
        )

    def test_generator_contains_no_suite_configuration(self) -> None:
        self.assertFalse(hasattr(RUN_RECORDS, "CONFIG"))


if __name__ == "__main__":
    unittest.main()
