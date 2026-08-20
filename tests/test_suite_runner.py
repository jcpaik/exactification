from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tests.test_testcase_harness import HarnessFixture
from validation.run_suite import SuiteError, run_suite


class SuiteRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()
        source_fixture = HarnessFixture(self.temporary.name)
        self.case_root = self.repository / "testcases" / "grzesik-style"
        self.case_root.parent.mkdir()
        shutil.copytree(source_fixture.root, self.case_root)
        source_fixture.close()
        (self.repository / "validation").mkdir()
        self.config_path = self.repository / "validation" / "suite.json"
        self.config = {
            "format": "exactification-suite-v1",
            "suite_id": "test-suite",
            "expected_case_ids": ["grzesik-style"],
            "unit_tests": {
                "id": "unit-tests",
                "command": ["{python}", "-c", "raise SystemExit(0)"],
                "cwd": ".",
                "expected_exit_code": 0,
                "timeout_seconds": 30,
            },
            "preflights": [],
            "attempts": [
                {
                    "case_id": "grzesik-style",
                    "case_root": "testcases/grzesik-style",
                    "attempt_id": "attempt-1",
                    "expected_target": "1",
                    "expected_status": "EXACT_SDP_CERTIFICATE",
                    "expected_blocks": 1,
                    "expected_constraints": 1,
                }
            ],
        }
        self.write_config()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_config(self, value: object | None = None) -> None:
        self.config_path.write_text(
            json.dumps(self.config if value is None else value, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_success_summary_contains_subprocess_commands_exit_codes_and_hashes(self) -> None:
        report = run_suite(self.repository, self.config_path)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["coverage"]["missing_case_ids"], [])
        self.assertEqual([item["kind"] for item in report["commands"]], ["unit_tests", "attempt"])
        for command in report["commands"]:
            self.assertIsInstance(command["argv"], list)
            self.assertEqual(command["exit_code"], 0)
            self.assertEqual(len(command["argv_sha256"]), 64)
            self.assertEqual(len(command["stdout_sha256"]), 64)
            self.assertEqual(len(command["stderr_sha256"]), 64)
        self.assertEqual(len(report["attempts"][0]["model_sha256"]), 64)
        self.assertEqual(len(report["attempts"][0]["certificate_sha256"]), 64)

    def test_wrong_expected_target_fails_even_when_harness_passes(self) -> None:
        self.config["attempts"][0]["expected_target"] = "2"
        self.write_config()

        report = run_suite(self.repository, self.config_path)

        self.assertEqual(report["status"], "failed")
        self.assertIn("fixed target mismatch", report["attempts"][0]["failures"])
        self.assertIn("computed target mismatch", report["attempts"][0]["failures"])

    def test_wrong_expected_status_fails(self) -> None:
        self.config["attempts"][0]["expected_status"] = "RIGOROUS_PROBLEM_BOUND"
        self.write_config()

        report = run_suite(self.repository, self.config_path)

        self.assertEqual(report["status"], "failed")
        self.assertIn("status mismatch", report["attempts"][0]["failures"])
        self.assertIn("required status mismatch", report["attempts"][0]["failures"])

    def test_attempt_status_mismatch_propagates_harness_failure(self) -> None:
        path = self.case_root / "attempts" / "attempt-1" / "verification.json"
        verification = json.loads(path.read_text(encoding="utf-8"))
        verification["final_status"] = "RIGOROUS_PROBLEM_BOUND"
        path.write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")

        report = run_suite(self.repository, self.config_path)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(
            report["attempts"][0]["failures"],
            ["manifest-aware harness process failed"],
        )

    def test_missing_expected_coverage_is_a_config_error(self) -> None:
        self.config["expected_case_ids"].append("missing-case")
        self.write_config()

        with self.assertRaisesRegex(SuiteError, "coverage mismatch.*missing"):
            run_suite(self.repository, self.config_path)

    def test_extra_attempt_coverage_is_a_config_error(self) -> None:
        second = deepcopy(self.config["attempts"][0])
        second["case_id"] = "extra-case"
        second["case_root"] = "testcases/extra-case"
        self.config["attempts"].append(second)
        self.write_config()

        with self.assertRaisesRegex(SuiteError, "coverage mismatch.*extra"):
            run_suite(self.repository, self.config_path)

    def test_null_target_discovery_is_outside_fixed_target_suite(self) -> None:
        self.config["attempts"][0]["expected_target"] = None
        self.write_config()

        with self.assertRaisesRegex(SuiteError, "fixed_objective:null"):
            run_suite(self.repository, self.config_path)

    def test_preflight_failure_propagates_but_attempt_is_still_reported(self) -> None:
        self.config["preflights"] = [
            {
                "id": "failing-preflight",
                "command": ["{python}", "-c", "raise SystemExit(7)"],
                "cwd": ".",
                "expected_exit_code": 0,
                "timeout_seconds": 30,
            }
        ]
        self.write_config()

        report = run_suite(self.repository, self.config_path)

        self.assertEqual(report["status"], "failed")
        preflight = next(
            item for item in report["commands"] if item["id"] == "failing-preflight"
        )
        self.assertEqual(preflight["exit_code"], 7)
        self.assertFalse(preflight["pass"])
        self.assertTrue(report["attempts"][0]["pass"])

    def test_duplicate_config_key_is_rejected(self) -> None:
        text = json.dumps(self.config, indent=2)
        self.config_path.write_text(
            text.replace(
                '"format": "exactification-suite-v1",',
                '"format": "exactification-suite-v1",\n  "format": "exactification-suite-v1",',
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(SuiteError, "duplicate JSON object key"):
            run_suite(self.repository, self.config_path)

    def test_working_directory_traversal_is_rejected(self) -> None:
        self.config["unit_tests"]["cwd"] = "../outside"
        self.write_config()

        with self.assertRaisesRegex(SuiteError, "safe repository-relative path"):
            run_suite(self.repository, self.config_path)


if __name__ == "__main__":
    unittest.main()
