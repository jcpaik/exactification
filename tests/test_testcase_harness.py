from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from validation.testcase_harness import (
    ATTEMPT_JSON_ARTIFACTS,
    ATTEMPT_TEXT_ARTIFACTS,
    HarnessError,
    main,
    validate_attempt,
)
from verify.exact_sdp import load_certificate, load_model, verify_certificate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarnessFixture:
    def __init__(self, directory: str, *, fixed_objective: str = "1") -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.workspace = Path(self.temporary.name) / "workspace"
        self.root = self.workspace / "testcases" / "grzesik-style"
        self.input = self.root / "input"
        self.attempt = self.root / "attempts" / "attempt-1"
        self.input.mkdir(parents=True)
        self.attempt.mkdir(parents=True)

        self.model = {
            "format": "exact-block-sdp-model-v1",
            "blocks": [{"name": "U", "size": 1}],
            "constraints": [
                {
                    "name": "grzesik_style_slack",
                    "sense": "ge",
                    "expression": {
                        "constant": "0",
                        "terms": [
                            {
                                "block": "U",
                                "row": 0,
                                "col": 0,
                                "coefficient": "120",
                            }
                        ],
                    },
                }
            ],
            "objective": {
                "sense": "minimize",
                "expression": {
                    "constant": "0",
                    "terms": [
                        {
                            "block": "U",
                            "row": 0,
                            "col": 0,
                            "coefficient": "1",
                        }
                    ],
                },
            },
        }
        self.approximate = {
            "format": "approximate-block-sdp-solution-v1",
            "numeric_type": "decimal",
            "claimed_precision_digits": 50,
            "claimed_objective": "1.0",
            "blocks": [{"name": "U", "matrix": [["1.0"]]}],
        }
        self.candidate = {
            "format": "exact-block-sdp-certificate-v1",
            "claimed_objective": "1",
            "blocks": [{"name": "U", "matrix": [["1"]]}],
        }
        self.certificate = deepcopy(self.candidate)
        self.certificate["blocks"][0]["psd_trace"] = {
            "algorithm": "symmetric-schur-v1",
            "steps": [{"index": 0, "pivot": "1"}],
        }

        self.write_json(self.input / "model.json", self.model)
        self.write_json(self.input / "approximate_solution.json", self.approximate)
        self.manifest = {
            "format": "exactification-testcase-v1",
            "id": "grzesik-style",
            "title": "Grzesik-style target-binding regression",
            "field": "Q",
            "model": "model.json",
            "approximate_solution": "approximate_solution.json",
            "fixed_objective": fixed_objective,
            "solution_side": "affine_psd_blocks",
            "blind_input_policy": {
                "exact_certificate_included": False,
                "oracle_paths_mounted": False,
            },
            "files": {
                "model.json": {"sha256": sha256(self.input / "model.json")},
                "approximate_solution.json": {
                    "sha256": sha256(self.input / "approximate_solution.json")
                },
            },
        }
        self.write_json(self.input / "manifest.json", self.manifest)
        self.write_json(self.attempt / "candidate.json", self.candidate)
        self.write_json(self.attempt / "certificate.json", self.certificate)

        low_model = load_model(self.input / "model.json")
        low_certificate = load_certificate(
            self.attempt / "certificate.json", low_model
        )
        verifier_report = verify_certificate(low_model, low_certificate)
        self.write_json(self.attempt / "verifier-output.json", verifier_report)
        self.write_json(
            self.attempt / "verification.json",
            {
                "case_id": "grzesik-style",
                "attempt_id": "attempt-1",
                "model_sha256": sha256(self.input / "model.json"),
                "certificate_sha256": sha256(self.attempt / "certificate.json"),
                "verifier_exit_code": 0,
                "blocks_covered": True,
                "constraints_covered": True,
                "final_status": "EXACT_SDP_CERTIFICATE",
            },
        )
        self.write_json(
            self.attempt / "run.json", {"attempt_id": "attempt-1", "commands": []}
        )
        self.write_json(self.attempt / "objective-candidates.json", [])
        self.write_json(self.attempt / "spectra.json", {})
        self.write_json(self.attempt / "kernels.json", {})
        (self.attempt / "proof.md").write_text("# Exact proof\n", encoding="utf-8")
        self.write_run_provenance()

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def rewrite_manifest(self) -> None:
        self.write_json(self.input / "manifest.json", self.manifest)

    def write_run_provenance(self) -> None:
        run_path = self.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))

        consumed_paths = [
            self.input / "manifest.json",
            self.input / "model.json",
            self.input / "approximate_solution.json",
        ]
        generated_paths = [
            self.attempt / filename
            for filename in ATTEMPT_JSON_ARTIFACTS
            if filename != "run.json"
        ] + [self.attempt / filename for filename in ATTEMPT_TEXT_ARTIFACTS]
        operational = self.attempt / "operational-failures.json"
        if operational.exists() or operational.is_symlink():
            generated_paths.append(operational)

        run["consumed_file_sha256"] = {
            path.relative_to(self.workspace).as_posix(): sha256(path)
            for path in consumed_paths
        }
        run["generated_file_sha256"] = {
            path.relative_to(self.workspace).as_posix(): sha256(path)
            for path in generated_paths
        }
        self.write_json(run_path, run)

    def close(self) -> None:
        self.temporary.cleanup()


class TestcaseHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.container = tempfile.TemporaryDirectory()
        self.fixture = HarnessFixture(self.container.name)

    def tearDown(self) -> None:
        self.fixture.close()
        self.container.cleanup()

    def test_valid_attempt_emits_complete_exact_report(self) -> None:
        report = validate_attempt(self.fixture.root, "attempt-1")

        self.assertEqual(report["status"], "EXACT_SDP_CERTIFICATE")
        self.assertEqual(report["model"]["sha256"], sha256(self.fixture.input / "model.json"))
        self.assertEqual(
            report["objective"],
            {
                "sense": "minimize",
                "computed": "1",
                "certificate_claim": "1",
                "fixed": "1",
                "pass": True,
            },
        )
        self.assertEqual(
            report["constraints"],
            [
                {
                    "name": "grzesik_style_slack",
                    "sense": "ge",
                    "value": "120",
                    "pass": True,
                }
            ],
        )
        self.assertEqual(
            report["blocks"],
            [{"name": "U", "size": 1, "rank": 1, "pass": True}],
        )

    def test_cli_prints_machine_readable_report(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main([str(self.fixture.root), "attempt-1"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["format"], "exactification-harness-report-v1")

    def test_duplicate_manifest_key_is_rejected(self) -> None:
        manifest_path = self.fixture.input / "manifest.json"
        text = manifest_path.read_text(encoding="utf-8")
        manifest_path.write_text(
            text.replace(
                '"format": "exactification-testcase-v1",',
                '"format": "exactification-testcase-v1",\n  "format": "exactification-testcase-v1",',
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(HarnessError, "duplicate JSON object key"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_duplicate_approximate_key_is_rejected(self) -> None:
        path = self.fixture.input / "approximate_solution.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                '"numeric_type": "decimal",',
                '"numeric_type": "decimal",\n  "numeric_type": "decimal",',
                1,
            ),
            encoding="utf-8",
        )
        self.fixture.manifest["files"]["approximate_solution.json"]["sha256"] = sha256(path)
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "duplicate JSON object key"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_duplicate_certificate_key_is_rejected_by_trusted_parser(self) -> None:
        path = self.fixture.attempt / "certificate.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                '"claimed_objective": "1",',
                '"claimed_objective": "1",\n  "claimed_objective": "1",',
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(HarnessError, "duplicate JSON object key"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_noncanonical_fixed_objective_is_rejected(self) -> None:
        self.fixture.manifest["fixed_objective"] = "2/2"
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "reduced and canonical"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_null_fixed_objective_is_exploration_not_acceptance(self) -> None:
        self.fixture.manifest["fixed_objective"] = None
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "must be non-null"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_manifest_id_must_match_case_directory(self) -> None:
        self.fixture.manifest["id"] = "different-case"
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "does not match case directory"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_missing_required_manifest_field_is_rejected(self) -> None:
        del self.fixture.manifest["solution_side"]
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "missing field.*solution_side"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_blind_policy_cannot_include_an_exact_certificate(self) -> None:
        self.fixture.manifest["blind_input_policy"][
            "exact_certificate_included"
        ] = True
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "exclusion must be false"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_parent_traversal_model_path_is_rejected(self) -> None:
        self.fixture.manifest["model"] = "../model.json"
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "must not contain"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_symlink_escape_model_path_is_rejected(self) -> None:
        outside = Path(self.container.name) / "outside-model.json"
        self.fixture.write_json(outside, self.fixture.model)
        link = self.fixture.input / "escaped-model.json"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.fixture.manifest["model"] = "escaped-model.json"
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "path escapes"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_certificate_parent_traversal_is_rejected(self) -> None:
        with self.assertRaisesRegex(HarnessError, "must not contain"):
            validate_attempt(
                self.fixture.root, "attempt-1", certificate="../certificate.json"
            )

    def test_symlink_escape_certificate_path_is_rejected(self) -> None:
        outside = Path(self.container.name) / "outside-certificate.json"
        self.fixture.write_json(outside, self.fixture.certificate)
        link = self.fixture.attempt / "escaped-certificate.json"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaisesRegex(HarnessError, "path escapes"):
            validate_attempt(
                self.fixture.root,
                "attempt-1",
                certificate="escaped-certificate.json",
            )

    def test_approximate_block_schema_is_enforced(self) -> None:
        self.fixture.approximate["blocks"].append(
            {"name": "extra", "matrix": [["0"]]}
        )
        self.fixture.write_json(
            self.fixture.input / "approximate_solution.json", self.fixture.approximate
        )
        self.fixture.manifest["files"]["approximate_solution.json"]["sha256"] = sha256(
            self.fixture.input / "approximate_solution.json"
        )
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "unknown block"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_declared_hash_mismatch_is_rejected(self) -> None:
        self.fixture.manifest["files"]["model.json"]["sha256"] = "0" * 64
        self.fixture.rewrite_manifest()

        with self.assertRaisesRegex(HarnessError, "SHA-256 mismatch"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_raw_verifier_passes_but_harness_rejects_wrong_manifest_target(self) -> None:
        self.fixture.manifest["fixed_objective"] = "24/625"
        self.fixture.rewrite_manifest()
        model = load_model(self.fixture.input / "model.json")
        certificate = load_certificate(self.fixture.attempt / "certificate.json", model)

        self.assertEqual(verify_certificate(model, certificate)["objective"], "1")
        with self.assertRaisesRegex(HarnessError, "manifest.fixed_objective 24/625"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_missing_required_attempt_artifact_is_rejected(self) -> None:
        (self.fixture.attempt / "proof.md").unlink()

        with self.assertRaisesRegex(HarnessError, "proof.md"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_status_mismatch_is_rejected(self) -> None:
        verification_path = self.fixture.attempt / "verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        verification["final_status"] = "RIGOROUS_PROBLEM_BOUND"
        self.fixture.write_json(verification_path, verification)

        with self.assertRaisesRegex(HarnessError, "does not match required status"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_legacy_verification_status_is_rejected(self) -> None:
        verification_path = self.fixture.attempt / "verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        verification["status"] = verification.pop("final_status")
        self.fixture.write_json(verification_path, verification)

        with self.assertRaisesRegex(HarnessError, "status is forbidden"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_nonzero_command_requires_operational_failure_record(self) -> None:
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["commands"] = [{"command": ["backend"], "exit_code": 130}]
        self.fixture.write_json(run_path, run)

        with self.assertRaisesRegex(HarnessError, "operational-failures.json is required"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_declared_operational_failure_must_have_nonempty_event_record(self) -> None:
        verification_path = self.fixture.attempt / "verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        verification["recoverable_failure_count"] = 1
        self.fixture.write_json(verification_path, verification)
        self.fixture.write_json(
            self.fixture.attempt / "operational-failures.json",
            {
                "format": "exactification-operational-failures-v1",
                "events": [],
            },
        )

        with self.assertRaisesRegex(HarnessError, "must record the declared failure event"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_recorded_operational_failure_can_coexist_with_success(self) -> None:
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["commands"] = [{"command": ["backend"], "exit_code": 130}]
        self.fixture.write_json(run_path, run)
        self.fixture.write_json(
            self.fixture.attempt / "operational-failures.json",
            {
                "format": "exactification-operational-failures-v1",
                "events": [{"phase": "rank", "exit_code": 130}],
            },
        )
        self.fixture.write_run_provenance()

        report = validate_attempt(self.fixture.root, "attempt-1")

        self.assertIn(
            "operational-failures.json", report["attempt_artifact_sha256"]
        )

    def test_run_provenance_maps_are_checked_and_reported(self) -> None:
        self.fixture.write_run_provenance()

        report = validate_attempt(self.fixture.root, "attempt-1")

        self.assertEqual(
            len(report["run_provenance"]["consumed_file_sha256"]), 3
        )
        self.assertEqual(
            len(report["run_provenance"]["generated_file_sha256"]), 8
        )

    def test_run_provenance_maps_are_required(self) -> None:
        for field in ("consumed_file_sha256", "generated_file_sha256"):
            with self.subTest(field=field):
                self.fixture.write_run_provenance()
                run_path = self.fixture.attempt / "run.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                del run[field]
                self.fixture.write_json(run_path, run)

                with self.assertRaisesRegex(HarnessError, rf"{field} is required"):
                    validate_attempt(self.fixture.root, "attempt-1")

    def test_consumed_hash_mismatch_is_rejected(self) -> None:
        self.fixture.write_run_provenance()
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        model_key = "testcases/grzesik-style/input/model.json"
        run["consumed_file_sha256"][model_key] = "0" * 64
        self.fixture.write_json(run_path, run)

        with self.assertRaisesRegex(HarnessError, "consumed_file_sha256.*SHA-256 mismatch"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_consumed_map_must_cover_primary_approximation(self) -> None:
        self.fixture.write_run_provenance()
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        del run["consumed_file_sha256"][
            "testcases/grzesik-style/input/approximate_solution.json"
        ]
        self.fixture.write_json(run_path, run)

        with self.assertRaisesRegex(HarnessError, "does not cover required public inputs"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_generated_map_must_cover_required_artifacts(self) -> None:
        self.fixture.write_run_provenance()
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        del run["generated_file_sha256"][
            "testcases/grzesik-style/attempts/attempt-1/proof.md"
        ]
        self.fixture.write_json(run_path, run)

        with self.assertRaisesRegex(HarnessError, "does not cover required attempt artifacts"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_provenance_path_traversal_is_rejected(self) -> None:
        self.fixture.write_run_provenance()
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["consumed_file_sha256"]["../outside.json"] = "0" * 64
        self.fixture.write_json(run_path, run)

        with self.assertRaisesRegex(HarnessError, "not canonical and relative"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_provenance_symlink_escape_is_rejected(self) -> None:
        self.fixture.write_run_provenance()
        outside = Path(self.container.name) / "outside-run-input.json"
        self.fixture.write_json(outside, {})
        link = self.fixture.workspace / "leaked.json"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        run_path = self.fixture.attempt / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["consumed_file_sha256"]["leaked.json"] = sha256(outside)
        self.fixture.write_json(run_path, run)

        with self.assertRaisesRegex(HarnessError, "path escapes"):
            validate_attempt(self.fixture.root, "attempt-1")

    def test_saved_verifier_output_mismatch_is_rejected(self) -> None:
        path = self.fixture.attempt / "verifier-output.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        report["objective"] = "2"
        self.fixture.write_json(path, report)

        with self.assertRaisesRegex(HarnessError, "fresh verifier report"):
            validate_attempt(self.fixture.root, "attempt-1")


if __name__ == "__main__":
    unittest.main()
