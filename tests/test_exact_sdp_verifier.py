from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verify.exact_sdp import (
    FormatError,
    PSDTrace,
    TraceStep,
    VerificationFailure,
    certificate_as_json,
    generate_psd_trace,
    parse_certificate,
    parse_model,
    validate_psd_trace,
    verify_certificate,
)


def matrix(*rows: tuple[int | Fraction, ...]) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(tuple(Fraction(entry) for entry in row) for row in rows)


def base_model() -> dict[str, object]:
    return {
        "format": "exact-block-sdp-model-v1",
        "blocks": [{"name": "X", "size": 2}],
        "constraints": [
            {
                "name": "normalization",
                "sense": "eq",
                "expression": {
                    "constant": "-1",
                    "terms": [{"block": "X", "row": 0, "col": 0, "coefficient": "1"}],
                },
            },
            {
                "name": "nonnegative off-diagonal",
                "sense": "ge",
                "expression": {
                    "constant": "0",
                    "terms": [{"block": "X", "row": 0, "col": 1, "coefficient": "1"}],
                },
            },
            {
                "name": "bounded diagonal",
                "sense": "le",
                "expression": {
                    "constant": "-1",
                    "terms": [{"block": "X", "row": 1, "col": 1, "coefficient": "1"}],
                },
            },
        ],
        "objective": {
            "sense": "maximize",
            "expression": {
                "constant": "0",
                "terms": [{"block": "X", "row": 0, "col": 1, "coefficient": "2"}],
            },
        },
    }


def singular_certificate(*, include_trace: bool = True) -> dict[str, object]:
    block: dict[str, object] = {
        "name": "X",
        "matrix": [["1", "1"], ["1", "1"]],
    }
    if include_trace:
        block["psd_trace"] = {
            "algorithm": "symmetric-schur-v1",
            "steps": [{"index": 0, "pivot": "1"}, {"index": 1, "pivot": "0"}],
        }
    return {
        "format": "exact-block-sdp-certificate-v1",
        "claimed_objective": "2",
        "blocks": [block],
    }


def arbitrary_length_model() -> dict[str, object]:
    return {
        "format": "exact-block-sdp-model-v1",
        "blocks": [{"name": "Huge", "size": 1}],
        "constraints": [],
        "objective": {
            "sense": "maximize",
            "expression": {
                "constant": "0",
                "terms": [{"block": "Huge", "row": 0, "col": 0, "coefficient": "1"}],
            },
        },
    }


def arbitrary_length_rational() -> str:
    # A reduced positive rational with a 5,001-digit numerator.  This exceeds
    # Python's default 4,300-digit int-string conversion limit.
    return "1" + "0" * 4_999 + "1/2"


def arbitrary_length_certificate(*, include_trace: bool = True) -> dict[str, object]:
    value = arbitrary_length_rational()
    block: dict[str, object] = {"name": "Huge", "matrix": [[value]]}
    if include_trace:
        block["psd_trace"] = {
            "algorithm": "symmetric-schur-v1",
            "steps": [{"index": 0, "pivot": value}],
        }
    return {
        "format": "exact-block-sdp-certificate-v1",
        "claimed_objective": value,
        "blocks": [block],
    }


class SchurTraceTests(unittest.TestCase):
    def test_positive_definite_matrix(self) -> None:
        value = matrix((4, 2), (2, 2))
        trace = generate_psd_trace(value)

        self.assertEqual(trace.steps, (TraceStep(0, Fraction(4)), TraceStep(1, Fraction(1))))
        self.assertEqual(validate_psd_trace(value, trace), 2)

    def test_singular_psd_matrix(self) -> None:
        value = matrix((1, 1), (1, 1))
        trace = generate_psd_trace(value)

        self.assertEqual(trace.steps, (TraceStep(0, Fraction(1)), TraceStep(1, Fraction(0))))
        self.assertEqual(validate_psd_trace(value, trace), 1)

    def test_zero_coordinate_before_positive_pivot(self) -> None:
        value = matrix((0, 0), (0, 2))
        trace = generate_psd_trace(value)

        self.assertEqual(trace.steps, (TraceStep(0, Fraction(0)), TraceStep(1, Fraction(2))))
        self.assertEqual(validate_psd_trace(value, trace), 1)

    def test_trace_may_use_a_different_symmetric_pivot_order(self) -> None:
        value = matrix((2, 0), (0, 3))
        trace = PSDTrace((TraceStep(1, Fraction(3)), TraceStep(0, Fraction(2))))

        self.assertEqual(validate_psd_trace(value, trace), 2)

    def test_indefinite_matrix_is_rejected_by_emitter(self) -> None:
        value = matrix((1, 2), (2, 1))

        with self.assertRaisesRegex(VerificationFailure, "negative Schur pivot"):
            generate_psd_trace(value)

    def test_zero_diagonal_with_nonzero_row_is_indefinite(self) -> None:
        value = matrix((0, 1), (1, 0))

        with self.assertRaisesRegex(VerificationFailure, "nonzero active row"):
            generate_psd_trace(value)

    def test_fraudulent_trace_is_rejected(self) -> None:
        value = matrix((1, 1), (1, 1))
        trace = PSDTrace((TraceStep(0, Fraction(1)), TraceStep(1, Fraction(1))))

        with self.assertRaisesRegex(VerificationFailure, "claims pivot"):
            validate_psd_trace(value, trace)


class ModelAndCertificateTests(unittest.TestCase):
    def test_exact_constraints_objective_and_rank(self) -> None:
        model = parse_model(base_model())
        certificate = parse_certificate(singular_certificate(), model)

        report = verify_certificate(model, certificate)

        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["objective"], "2")
        self.assertEqual(report["ranks"], {"X": 1})
        self.assertEqual(report["constraints_checked"], 3)

    def test_failed_exact_equality_is_rejected(self) -> None:
        raw_certificate = singular_certificate()
        raw_certificate["blocks"][0]["matrix"] = [["2", "1"], ["1", "1"]]  # type: ignore[index]
        raw_certificate["blocks"][0]["psd_trace"] = {  # type: ignore[index]
            "algorithm": "symmetric-schur-v1",
            "steps": [{"index": 0, "pivot": "2"}, {"index": 1, "pivot": "1/2"}],
        }
        model = parse_model(base_model())
        certificate = parse_certificate(raw_certificate, model)

        with self.assertRaisesRegex(VerificationFailure, "normalization"):
            verify_certificate(model, certificate)

    def test_false_objective_claim_is_rejected(self) -> None:
        raw_certificate = singular_certificate()
        raw_certificate["claimed_objective"] = "3"
        model = parse_model(base_model())
        certificate = parse_certificate(raw_certificate, model)

        with self.assertRaisesRegex(VerificationFailure, "objective claim fails"):
            verify_certificate(model, certificate)

    def test_json_number_is_not_a_rational_string(self) -> None:
        raw_certificate = singular_certificate()
        raw_certificate["claimed_objective"] = 2

        with self.assertRaisesRegex(FormatError, "canonical rational string"):
            parse_certificate(raw_certificate, parse_model(base_model()))

    def test_noncanonical_rational_is_rejected(self) -> None:
        raw_certificate = singular_certificate()
        raw_certificate["claimed_objective"] = "4/2"

        with self.assertRaisesRegex(FormatError, "reduced and canonical"):
            parse_certificate(raw_certificate, parse_model(base_model()))

    def test_asymmetric_certificate_matrix_is_rejected(self) -> None:
        raw_certificate = singular_certificate()
        raw_certificate["blocks"][0]["matrix"] = [["1", "0"], ["1", "1"]]  # type: ignore[index]

        with self.assertRaisesRegex(FormatError, "not symmetric"):
            parse_certificate(raw_certificate, parse_model(base_model()))

    def test_missing_trace_is_rejected_in_checking_mode(self) -> None:
        with self.assertRaisesRegex(FormatError, "missing field.*psd_trace"):
            parse_certificate(singular_certificate(include_trace=False), parse_model(base_model()))

    def test_unknown_certificate_field_is_rejected(self) -> None:
        raw_certificate = singular_certificate()
        raw_certificate["comment"] = "must not be silently ignored"

        with self.assertRaisesRegex(FormatError, "unknown field"):
            parse_certificate(raw_certificate, parse_model(base_model()))

    def test_lower_triangle_affine_coordinate_is_rejected(self) -> None:
        raw_model = base_model()
        raw_model["objective"]["expression"]["terms"][0]["row"] = 1  # type: ignore[index]
        raw_model["objective"]["expression"]["terms"][0]["col"] = 0  # type: ignore[index]

        with self.assertRaisesRegex(FormatError, "row <= col"):
            parse_model(raw_model)

    def test_duplicate_affine_coordinate_is_rejected(self) -> None:
        raw_model = base_model()
        first_term = raw_model["objective"]["expression"]["terms"][0]  # type: ignore[index]
        raw_model["objective"]["expression"]["terms"].append(deepcopy(first_term))  # type: ignore[index]

        with self.assertRaisesRegex(FormatError, "duplicate affine coordinate"):
            parse_model(raw_model)

    def test_arbitrary_length_rational_is_parsed_checked_and_rendered(self) -> None:
        value = arbitrary_length_rational()
        self.assertGreater(len(value.partition("/")[0]), 4_300)
        original_digit_limit = sys.get_int_max_str_digits() if hasattr(sys, "get_int_max_str_digits") else None
        model = parse_model(arbitrary_length_model())
        certificate = parse_certificate(arbitrary_length_certificate(), model)

        report = verify_certificate(model, certificate)
        rendered = certificate_as_json(certificate)

        self.assertEqual(report["objective"], value)
        self.assertEqual(rendered["claimed_objective"], value)
        self.assertEqual(rendered["blocks"][0]["matrix"], [[value]])  # type: ignore[index]
        self.assertEqual(rendered["blocks"][0]["psd_trace"]["steps"][0]["pivot"], value)  # type: ignore[index]
        if original_digit_limit is not None:
            self.assertEqual(sys.get_int_max_str_digits(), original_digit_limit)


class CLITests(unittest.TestCase):
    def test_emit_then_independently_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            model_path = temp / "model.json"
            candidate_path = temp / "candidate.json"
            certificate_path = temp / "certificate.json"
            model_path.write_text(json.dumps(base_model()), encoding="utf-8")
            candidate_path.write_text(json.dumps(singular_certificate(include_trace=False)), encoding="utf-8")

            emitted = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "verify",
                    "emit-traces",
                    str(model_path),
                    str(candidate_path),
                    "-o",
                    str(certificate_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(emitted.returncode, 0, emitted.stderr)

            checked = subprocess.run(
                [sys.executable, "-m", "verify", "check", str(model_path), str(certificate_path), "--json"],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            report = json.loads(checked.stdout)
            self.assertEqual(report["objective"], "2")
            self.assertEqual(report["ranks"], {"X": 1})

    def test_cli_gives_indefinite_candidate_exit_status_one(self) -> None:
        candidate = singular_certificate(include_trace=False)
        candidate["blocks"][0]["matrix"] = [["1", "2"], ["2", "1"]]  # type: ignore[index]
        candidate["claimed_objective"] = "4"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            model_path = temp / "model.json"
            candidate_path = temp / "candidate.json"
            output_path = temp / "out.json"
            model_path.write_text(json.dumps(base_model()), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "verify",
                    "emit-traces",
                    str(model_path),
                    str(candidate_path),
                    "-o",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("negative Schur pivot", result.stderr)

    def test_cli_emits_and_checks_arbitrary_length_rational(self) -> None:
        value = arbitrary_length_rational()
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            model_path = temp / "model.json"
            candidate_path = temp / "candidate.json"
            certificate_path = temp / "certificate.json"
            model_path.write_text(json.dumps(arbitrary_length_model()), encoding="utf-8")
            candidate_path.write_text(
                json.dumps(arbitrary_length_certificate(include_trace=False)), encoding="utf-8"
            )

            emitted = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "verify",
                    "emit-traces",
                    str(model_path),
                    str(candidate_path),
                    "-o",
                    str(certificate_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(emitted.returncode, 0, emitted.stderr)

            checked = subprocess.run(
                [sys.executable, "-m", "verify", "check", str(model_path), str(certificate_path), "--json"],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["objective"], value)


if __name__ == "__main__":
    unittest.main()
