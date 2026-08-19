"""Manifest-aware validation for exactification testcase attempts.

The low-level :mod:`verify` package deliberately checks only a v1 exact model
and certificate.  This module supplies the testcase-level gates that do not
belong in that generic proof format: public-input integrity, the manifest's
fixed objective, attempt completeness, and workflow status.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Mapping, Sequence

from verify.exact_sdp import (
    Certificate,
    ExactSDPError,
    FormatError,
    Model,
    VerificationFailure,
    load_certificate,
    load_model,
    verify_certificate,
)


HARNESS_REPORT_FORMAT = "exactification-harness-report-v1"
MANIFEST_FORMAT = "exactification-testcase-v1"
APPROXIMATE_FORMAT = "approximate-block-sdp-solution-v1"
SOLUTION_SIDE = "affine_psd_blocks"
SUCCESS_STATUSES = {
    "EXACT_SDP_CERTIFICATE",
    "RIGOROUS_PROBLEM_BOUND",
    "SHARP_OR_OPTIMAL",
}
ATTEMPT_JSON_ARTIFACTS = (
    "run.json",
    "objective-candidates.json",
    "spectra.json",
    "kernels.json",
    "candidate.json",
    "certificate.json",
    "verifier-output.json",
    "verification.json",
)
ATTEMPT_TEXT_ARTIFACTS = ("proof.md",)

_RATIONAL_RE = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")
_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ATTEMPT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_URI_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


class HarnessError(Exception):
    """A testcase or attempt violates the reusable testcase contract."""


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HarnessError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise HarnessError(f"nonstandard JSON value {value!r} is forbidden")


def load_json_strict(path: Path) -> Any:
    """Load RFC-8259 JSON while rejecting ambiguous extensions and duplicates."""

    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(
                source,
                object_pairs_hook=_duplicate_safe_object,
                # Preserve allowed metadata numbers without a binary-float
                # round trip.  Exact proof fields are separately required to
                # use canonical strings by the trusted verifier.
                parse_float=Decimal,
                parse_constant=_reject_constant,
            )
    except HarnessError as error:
        raise HarnessError(f"{path}: {error}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HarnessError(f"cannot read JSON file {path}: {error}") from error


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise HarnessError(f"{path}: expected an object")
    return value


def _array(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise HarnessError(f"{path}: expected an array")
    return value


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        qualifier = "nonempty " if nonempty else ""
        raise HarnessError(f"{path}: expected a {qualifier}string")
    return value


def _positive_integer(value: Any, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise HarnessError(f"{path}: expected a positive integer")
    return value


def _canonical_fraction(value: Any, path: str) -> Fraction:
    if not isinstance(value, str) or _RATIONAL_RE.fullmatch(value) is None:
        raise HarnessError(f"{path}: expected a canonical rational string")
    result = Fraction(value)
    if str(result) != value:
        raise HarnessError(
            f"{path}: rational must be reduced and canonical; use {str(result)!r}"
        )
    return result


def _decimal_string(value: Any, path: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise HarnessError(f"{path}: expected a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise HarnessError(f"{path}: invalid decimal string {value!r}") from error
    if not parsed.is_finite():
        raise HarnessError(f"{path}: decimal must be finite")
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise HarnessError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_relative_path(
    base: Path,
    raw_path: Any,
    field: str,
    *,
    must_exist: bool = True,
) -> Path:
    spelling = _string(raw_path, field)
    if "\\" in spelling:
        raise HarnessError(f"{field}: paths must use '/' separators")
    if _URI_SCHEME_RE.match(spelling):
        raise HarnessError(f"{field}: URI schemes are forbidden")
    pure = PurePosixPath(spelling)
    if pure.is_absolute() or ".." in pure.parts:
        raise HarnessError(f"{field}: path must be relative and must not contain '..'")
    if spelling.endswith("/") or not pure.parts:
        raise HarnessError(f"{field}: expected a file path")

    base_resolved = base.resolve(strict=True)
    candidate = base.joinpath(*pure.parts)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as error:
        raise HarnessError(f"{field}: cannot resolve {spelling!r}: {error}") from error
    if not _is_within(resolved, base_resolved):
        raise HarnessError(f"{field}: path escapes {base}")
    if must_exist and not resolved.is_file():
        raise HarnessError(f"{field}: expected an existing file at {spelling!r}")
    return resolved


def _manifest_input_directory(case_root: Path) -> tuple[Path, Path]:
    canonical = case_root / "input" / "manifest.json"
    legacy = case_root / "manifest.json"
    if canonical.is_file():
        return canonical.parent, canonical
    if legacy.is_file():
        return legacy.parent, legacy
    raise HarnessError(f"{case_root}: missing input/manifest.json")


def _workspace_root(case_root: Path) -> Path:
    """Return the root whose public testcase tree is ``testcases/``.

    Run provenance paths are workspace-relative so the same immutable metadata
    works in the repository and in a copied blind workspace.  Requiring the
    conventional tree also prevents a caller from silently choosing a broader
    filesystem root for provenance resolution.
    """

    if case_root.parent.name != "testcases":
        raise HarnessError(
            "case root must be an immediate child of a workspace testcases/ directory"
        )
    try:
        workspace = case_root.parent.parent.resolve(strict=True)
        testcases = (workspace / "testcases").resolve(strict=True)
    except OSError as error:
        raise HarnessError(f"cannot resolve testcase workspace: {error}") from error
    if case_root.parent.resolve(strict=True) != testcases:
        raise HarnessError("case root does not belong to the resolved workspace testcases/")
    return workspace


def _required_manifest_fields(manifest: Mapping[str, Any]) -> None:
    required = {
        "format",
        "id",
        "title",
        "field",
        "model",
        "approximate_solution",
        "fixed_objective",
        "solution_side",
        "blind_input_policy",
    }
    missing = sorted(required - manifest.keys())
    if missing:
        raise HarnessError(f"manifest: missing field(s): {', '.join(missing)}")


def _required_status(manifest: Mapping[str, Any]) -> str:
    claim = manifest.get("claim")
    if claim is None:
        return "EXACT_SDP_CERTIFICATE"
    claim_object = _object(claim, "manifest.claim")
    status = claim_object.get("required_status", "EXACT_SDP_CERTIFICATE")
    status = _string(status, "manifest.claim.required_status")
    if status not in SUCCESS_STATUSES:
        raise HarnessError(
            "manifest.claim.required_status: expected EXACT_SDP_CERTIFICATE, "
            "RIGOROUS_PROBLEM_BOUND, or SHARP_OR_OPTIMAL"
        )
    return status


def _parse_manifest(
    manifest_path: Path, case_root: Path
) -> tuple[Mapping[str, Any], Fraction | None, str]:
    manifest = _object(load_json_strict(manifest_path), "manifest")
    _required_manifest_fields(manifest)
    if manifest["format"] != MANIFEST_FORMAT:
        raise HarnessError(f"manifest.format: expected {MANIFEST_FORMAT!r}")
    case_id = _string(manifest["id"], "manifest.id")
    if _SLUG_RE.fullmatch(case_id) is None:
        raise HarnessError("manifest.id: expected a lowercase hyphenated slug")
    if case_root.name != case_id:
        raise HarnessError(
            f"manifest.id {case_id!r} does not match case directory {case_root.name!r}"
        )
    _string(manifest["title"], "manifest.title")
    if manifest["field"] != "Q":
        raise HarnessError("manifest.field: the trusted v1 harness currently requires 'Q'")
    if manifest["solution_side"] != SOLUTION_SIDE:
        raise HarnessError(f"manifest.solution_side: expected {SOLUTION_SIDE!r}")
    policy = _object(
        manifest["blind_input_policy"], "manifest.blind_input_policy"
    )
    for flag in (
        "exact_certificate_included",
        "published_certificate_included",
        "oracle_paths_mounted",
        "published_serialized_solution_read",
    ):
        if flag not in policy:
            continue
        if type(policy[flag]) is not bool:
            raise HarnessError(
                f"manifest.blind_input_policy.{flag}: expected a boolean"
            )
        if policy[flag]:
            raise HarnessError(
                f"manifest.blind_input_policy.{flag}: blind input exclusion must be false"
            )

    fixed_raw = manifest["fixed_objective"]
    fixed = None if fixed_raw is None else _canonical_fraction(
        fixed_raw, "manifest.fixed_objective"
    )
    return manifest, fixed, _required_status(manifest)


def _validate_approximate_solution(path: Path, model: Model) -> dict[str, Any]:
    approximate = _object(load_json_strict(path), "approximate_solution")
    required = {"format", "numeric_type", "claimed_objective", "blocks"}
    missing = sorted(required - approximate.keys())
    if missing:
        raise HarnessError(
            f"approximate_solution: missing field(s): {', '.join(missing)}"
        )
    if approximate["format"] != APPROXIMATE_FORMAT:
        raise HarnessError(
            f"approximate_solution.format: expected {APPROXIMATE_FORMAT!r}"
        )
    if approximate["numeric_type"] != "decimal":
        raise HarnessError("approximate_solution.numeric_type: expected 'decimal'")
    precision_fields = [
        name
        for name in ("claimed_precision_bits", "claimed_precision_digits")
        if name in approximate
    ]
    if len(precision_fields) != 1:
        raise HarnessError(
            "approximate_solution: exactly one claimed precision field is required"
        )
    precision_name = precision_fields[0]
    precision = _positive_integer(
        approximate[precision_name], f"approximate_solution.{precision_name}"
    )
    _decimal_string(
        approximate["claimed_objective"], "approximate_solution.claimed_objective"
    )

    expected = model.block_sizes
    seen: set[str] = set()
    for position, raw_block in enumerate(
        _array(approximate["blocks"], "approximate_solution.blocks")
    ):
        block_path = f"approximate_solution.blocks[{position}]"
        block = _object(raw_block, block_path)
        missing_block = {"name", "matrix"} - block.keys()
        if missing_block:
            raise HarnessError(
                f"{block_path}: missing field(s): {', '.join(sorted(missing_block))}"
            )
        name = _string(block["name"], f"{block_path}.name")
        if name not in expected:
            raise HarnessError(f"{block_path}.name: unknown block {name!r}")
        if name in seen:
            raise HarnessError(f"{block_path}.name: duplicate block {name!r}")
        seen.add(name)
        size = expected[name]
        rows = _array(block["matrix"], f"{block_path}.matrix")
        if len(rows) != size:
            raise HarnessError(
                f"{block_path}.matrix: expected {size} rows, found {len(rows)}"
            )
        matrix: list[list[Decimal]] = []
        for row_index, raw_row in enumerate(rows):
            row = _array(raw_row, f"{block_path}.matrix[{row_index}]")
            if len(row) != size:
                raise HarnessError(
                    f"{block_path}.matrix[{row_index}]: expected {size} entries, "
                    f"found {len(row)}"
                )
            matrix.append(
                [
                    _decimal_string(
                        entry,
                        f"{block_path}.matrix[{row_index}][{column_index}]",
                    )
                    for column_index, entry in enumerate(row)
                ]
            )
        # Producers normally print symmetric entries identically.  Permit the
        # contract's small formatting/rounding asymmetry at the claimed scale.
        decimal_digits = (
            precision
            if precision_name == "claimed_precision_digits"
            # A conservative integer lower bound for bits * log10(2).
            else max(1, precision * 30102 // 100000)
        )
        relative_tolerance = Decimal(10) ** -max(1, decimal_digits - 2)
        for row in range(size):
            for column in range(row + 1, size):
                left = matrix[row][column]
                right = matrix[column][row]
                scale = max(Decimal(1), abs(left), abs(right))
                if abs(left - right) > relative_tolerance * scale:
                    raise HarnessError(
                        f"{block_path}.matrix: entries ({row},{column}) and "
                        f"({column},{row}) are not symmetric to the claimed precision"
                    )

    missing_blocks = sorted(expected.keys() - seen)
    if missing_blocks:
        raise HarnessError(
            "approximate_solution.blocks: missing block(s): "
            + ", ".join(missing_blocks)
        )
    return {
        "sha256": _sha256(path),
        "precision": {"kind": precision_name, "value": precision},
        "blocks_checked": len(expected),
    }


def _hash_record(record: Any, path: str) -> str:
    if isinstance(record, str):
        expected = record
    else:
        obj = _object(record, path)
        if set(obj) != {"sha256"}:
            raise HarnessError(f"{path}: expected only a sha256 field")
        expected = _string(obj["sha256"], f"{path}.sha256")
    if _SHA256_RE.fullmatch(expected) is None:
        raise HarnessError(f"{path}: expected a lowercase SHA-256 hex digest")
    return expected


def _validate_declared_hashes(
    manifest: Mapping[str, Any], input_directory: Path
) -> list[dict[str, str]]:
    records: list[tuple[str, Any, str]] = []
    for field_name in ("files", "hashes"):
        if field_name not in manifest:
            continue
        mapping = _object(manifest[field_name], f"manifest.{field_name}")
        for relative, record in mapping.items():
            records.append((relative, record, f"manifest.{field_name}[{relative!r}]"))

    # Compatibility with the existing Grzesik manifest.  New manifests should
    # prefer the explicit files mapping above.
    source = manifest.get("source")
    if isinstance(source, dict):
        for key, filename in (
            ("sdp_sha256", "discovery.dat-s"),
            ("result_sha256", "discovery.result"),
        ):
            if key in source and not any(relative == filename for relative, _, _ in records):
                records.append((filename, source[key], f"manifest.source.{key}"))

    checked: list[dict[str, str]] = []
    seen: set[str] = set()
    for relative, record, record_path in records:
        if relative in seen:
            raise HarnessError(f"manifest: duplicate hash declaration for {relative!r}")
        seen.add(relative)
        artifact = _safe_relative_path(
            input_directory, relative, f"{record_path}.path"
        )
        expected = _hash_record(record, record_path)
        actual = _sha256(artifact)
        if actual != expected:
            raise HarnessError(
                f"{record_path}: SHA-256 mismatch for {relative!r}; "
                f"expected {expected}, found {actual}"
            )
        checked.append({"path": relative, "sha256": actual})
    return checked


def _constraint_value(constraint: Any, certificate: Certificate) -> Fraction:
    matrices = {
        name: block.matrix for name, block in certificate.block_map.items()
    }
    value = constraint.expression.constant
    for term in constraint.expression.terms:
        value += term.coefficient * matrices[term.block][term.row][term.col]
    return value


def _constraint_passes(sense: str, value: Fraction) -> bool:
    return (
        (sense == "eq" and value == 0)
        or (sense == "ge" and value >= 0)
        or (sense == "le" and value <= 0)
    )


def _attempt_directory(case_root: Path, attempt_id: str) -> Path:
    if _ATTEMPT_ID_RE.fullmatch(attempt_id) is None or attempt_id in {".", ".."}:
        raise HarnessError("attempt_id: expected a safe filename-like identifier")
    attempts_root = case_root / "attempts"
    if not attempts_root.is_dir():
        raise HarnessError(f"{case_root}: missing attempts directory")
    attempts_resolved = attempts_root.resolve(strict=True)
    candidate = attempts_root / attempt_id
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise HarnessError(f"attempt {attempt_id!r}: cannot resolve directory: {error}") from error
    if not _is_within(resolved, attempts_resolved) or not resolved.is_dir():
        raise HarnessError(f"attempt {attempt_id!r}: path escapes the attempts directory")
    return resolved


def _workspace_relative(path: Path, workspace: Path, field: str) -> str:
    try:
        return path.resolve(strict=True).relative_to(workspace).as_posix()
    except (OSError, ValueError) as error:
        raise HarnessError(f"{field}: file is outside the testcase workspace") from error


def _validate_run_hash_map(
    run: Mapping[str, Any], field: str, workspace: Path
) -> list[dict[str, str]] | None:
    if field not in run:
        return None
    mapping = _object(run[field], f"run.json.{field}")
    checked: list[dict[str, str]] = []
    for spelling in sorted(mapping):
        location = f"run.json.{field}[{spelling!r}]"
        if not isinstance(spelling, str) or not spelling:
            raise HarnessError(f"{location}: expected a nonempty path key")
        if "\\" in spelling or _URI_SCHEME_RE.match(spelling):
            raise HarnessError(f"{location}: expected a safe workspace-relative path")
        pure = PurePosixPath(spelling)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or spelling.endswith("/")
            or pure.as_posix() != spelling
        ):
            raise HarnessError(f"{location}: path spelling is not canonical and relative")
        artifact = _safe_relative_path(workspace, spelling, f"{location}.path")
        expected = _string(mapping[spelling], f"{location}.sha256")
        if _SHA256_RE.fullmatch(expected) is None:
            raise HarnessError(f"{location}: expected a lowercase SHA-256 hex digest")
        actual = _sha256(artifact)
        if actual != expected:
            raise HarnessError(
                f"{location}: SHA-256 mismatch; expected {expected}, found {actual}"
            )
        checked.append({"path": spelling, "sha256": actual})
    return checked


def _metadata_marker_is_true(value: Any) -> bool:
    if value is None or value is False or value == 0:
        return False
    if isinstance(value, str) and value.strip().lower() in {
        "",
        "0",
        "false",
        "no",
        "none",
    }:
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _metadata_declares_operational_failure(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in {
                "consumed_file_sha256",
                "generated_file_sha256",
                "metadata_input_sha256",
            }:
                continue
            if (
                ("operational" in normalized or "recoverable" in normalized)
                and ("failure" in normalized or "event" in normalized)
                and _metadata_marker_is_true(child)
            ):
                return True
            if _metadata_declares_operational_failure(child):
                return True
    elif isinstance(value, list):
        return any(_metadata_declares_operational_failure(child) for child in value)
    return False


def _run_has_operational_failure(
    run: Mapping[str, Any], verification: Mapping[str, Any]
) -> bool:
    declared = _metadata_declares_operational_failure(run) or (
        _metadata_declares_operational_failure(verification)
    )
    if "commands" not in run:
        return declared
    for position, raw_command in enumerate(_array(run["commands"], "run.json.commands")):
        command = _object(raw_command, f"run.json.commands[{position}]")
        if "exit_code" in command:
            exit_code = command["exit_code"]
            if exit_code is not None and type(exit_code) is not int:
                raise HarnessError(
                    f"run.json.commands[{position}].exit_code: expected an integer or null"
                )
            if exit_code != 0:
                declared = True
        if command.get("timed_out") is True or command.get("signal") not in (None, ""):
            declared = True
    return declared


def _validate_operational_failures(path: Path, *, required: bool) -> None:
    document = _object(load_json_strict(path), "operational-failures.json")
    if document.get("format") != "exactification-operational-failures-v1":
        raise HarnessError(
            "operational-failures.json.format: expected "
            "'exactification-operational-failures-v1'"
        )
    events = _array(document.get("events"), "operational-failures.json.events")
    if required and not events:
        raise HarnessError(
            "operational-failures.json.events must record the declared failure event"
        )
    for position, event in enumerate(events):
        _object(event, f"operational-failures.json.events[{position}]")


def _validate_run_provenance(
    run: Mapping[str, Any],
    *,
    workspace: Path,
    manifest_path: Path,
    model_path: Path,
    approximate_path: Path,
    attempt_directory: Path,
    generated_filenames: Sequence[str],
) -> dict[str, list[dict[str, str]] | None]:
    consumed = _validate_run_hash_map(run, "consumed_file_sha256", workspace)
    generated = _validate_run_hash_map(run, "generated_file_sha256", workspace)

    if consumed is not None:
        listed = {record["path"] for record in consumed}
        required = {
            _workspace_relative(manifest_path, workspace, "manifest provenance"),
            _workspace_relative(model_path, workspace, "model provenance"),
            _workspace_relative(
                approximate_path, workspace, "approximate-solution provenance"
            ),
        }
        missing = sorted(required - listed)
        if missing:
            raise HarnessError(
                "run.json.consumed_file_sha256 does not cover required public inputs: "
                + ", ".join(missing)
            )

    if generated is not None:
        listed = {record["path"] for record in generated}
        required = {
            _workspace_relative(
                attempt_directory / filename,
                workspace,
                f"generated artifact {filename}",
            )
            for filename in generated_filenames
        }
        missing = sorted(required - listed)
        if missing:
            raise HarnessError(
                "run.json.generated_file_sha256 does not cover required attempt artifacts: "
                + ", ".join(missing)
            )
    return {
        "consumed_file_sha256": consumed,
        "generated_file_sha256": generated,
    }


def _validate_attempt_artifacts(
    attempt_directory: Path,
    attempt_id: str,
    model: Model,
    certificate_path: Path,
    certificate: Certificate,
    verifier_report: Mapping[str, Any],
    required_status: str,
    case_id: str,
    model_hash: str,
    certificate_hash: str,
    workspace: Path,
    manifest_path: Path,
    model_path: Path,
    approximate_path: Path,
) -> tuple[str, dict[str, str], dict[str, list[dict[str, str]] | None]]:
    artifact_hashes: dict[str, str] = {}
    parsed: dict[str, Any] = {}
    for filename in ATTEMPT_JSON_ARTIFACTS:
        path = _safe_relative_path(
            attempt_directory, filename, f"attempt artifact {filename}"
        )
        parsed[filename] = load_json_strict(path)
        artifact_hashes[filename] = _sha256(path)
    for filename in ATTEMPT_TEXT_ARTIFACTS:
        path = _safe_relative_path(
            attempt_directory, filename, f"attempt artifact {filename}"
        )
        try:
            if not path.read_text(encoding="utf-8").strip():
                raise HarnessError(f"attempt artifact {filename}: file is empty")
        except (OSError, UnicodeError) as error:
            raise HarnessError(f"cannot read attempt artifact {filename}: {error}") from error
        artifact_hashes[filename] = _sha256(path)

    if certificate_path.name != "certificate.json":
        artifact_hashes[certificate_path.name] = certificate_hash

    run = _object(parsed["run.json"], "run.json")
    if "attempt_id" in run and run["attempt_id"] != attempt_id:
        raise HarnessError("run.json.attempt_id does not match the attempt directory")

    candidate_path = attempt_directory / "candidate.json"
    try:
        candidate = load_certificate(candidate_path, model, require_traces=False)
    except ExactSDPError as error:
        raise HarnessError(f"candidate.json: {error}") from error
    if candidate.claimed_objective != certificate.claimed_objective:
        raise HarnessError("candidate.json and certificate.json claim different objectives")
    if {
        name: block.matrix for name, block in candidate.block_map.items()
    } != {
        name: block.matrix for name, block in certificate.block_map.items()
    }:
        raise HarnessError("candidate.json and certificate.json contain different matrices")

    saved_verifier = _object(parsed["verifier-output.json"], "verifier-output.json")
    for key in ("objective", "blocks_checked", "constraints_checked", "ranks"):
        if saved_verifier.get(key) != verifier_report.get(key):
            raise HarnessError(
                f"verifier-output.json.{key} does not match the fresh verifier report"
            )

    verification = _object(parsed["verification.json"], "verification.json")
    if "status" in verification:
        raise HarnessError(
            "verification.json.status is forbidden; use exactly final_status"
        )
    if "final_status" not in verification:
        raise HarnessError("verification.json.final_status is required")
    status = _string(
        verification["final_status"],
        "verification.json.final_status",
    )
    if status not in SUCCESS_STATUSES:
        raise HarnessError(f"verification.json: {status!r} is not a successful status")
    if status != required_status:
        raise HarnessError(
            f"verification status {status!r} does not match required status "
            f"{required_status!r}"
        )

    exact_matches = {
        "case_id": case_id,
        "attempt_id": attempt_id,
        "model_sha256": model_hash,
        "certificate_sha256": certificate_hash,
    }
    for key, expected in exact_matches.items():
        if key in verification and verification[key] != expected:
            raise HarnessError(
                f"verification.json.{key} does not match the validated attempt"
            )
    if "verifier_exit_code" in verification and verification["verifier_exit_code"] != 0:
        raise HarnessError("verification.json.verifier_exit_code must be zero")
    if "blocks_covered" in verification and verification["blocks_covered"] is not True:
        raise HarnessError("verification.json.blocks_covered must be true")
    if (
        "constraints_covered" in verification
        and verification["constraints_covered"] is not True
    ):
        raise HarnessError("verification.json.constraints_covered must be true")

    if required_status in {"RIGOROUS_PROBLEM_BOUND", "SHARP_OR_OPTIMAL"}:
        if verification.get("theorem_adapter_passed") is not True:
            raise HarnessError(
                "verification.json.theorem_adapter_passed must be true for the required status"
            )
    if required_status == "SHARP_OR_OPTIMAL":
        if verification.get("matching_witness_passed") is not True:
            raise HarnessError(
                "verification.json.matching_witness_passed must be true for the required status"
            )

    operational_required = _run_has_operational_failure(run, verification)
    operational_candidate = attempt_directory / "operational-failures.json"
    operational_present = operational_candidate.exists() or operational_candidate.is_symlink()
    if operational_required and not operational_present:
        raise HarnessError(
            "operational-failures.json is required because run/verification metadata "
            "declares a recoverable operational event"
        )
    if operational_present:
        operational_path = _safe_relative_path(
            attempt_directory,
            "operational-failures.json",
            "attempt artifact operational-failures.json",
        )
        _validate_operational_failures(
            operational_path,
            required=operational_required,
        )
        artifact_hashes["operational-failures.json"] = _sha256(operational_path)

    generated_filenames = [
        filename for filename in ATTEMPT_JSON_ARTIFACTS if filename != "run.json"
    ] + list(ATTEMPT_TEXT_ARTIFACTS)
    if operational_present:
        generated_filenames.append("operational-failures.json")
    provenance = _validate_run_provenance(
        run,
        workspace=workspace,
        manifest_path=manifest_path,
        model_path=model_path,
        approximate_path=approximate_path,
        attempt_directory=attempt_directory,
        generated_filenames=generated_filenames,
    )
    return status, artifact_hashes, provenance


def validate_attempt(
    case_root: str | Path,
    attempt_id: str,
    *,
    certificate: str = "certificate.json",
) -> dict[str, Any]:
    """Validate one complete testcase attempt and return a JSON-ready report."""

    root = Path(case_root)
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise HarnessError(f"cannot resolve case root {case_root!r}: {error}") from error
    if not root.is_dir():
        raise HarnessError(f"case root {root} is not a directory")
    workspace = _workspace_root(root)

    input_directory, manifest_path = _manifest_input_directory(root)
    manifest, fixed_objective, required_status = _parse_manifest(
        manifest_path, root
    )
    model_path = _safe_relative_path(
        input_directory, manifest["model"], "manifest.model"
    )
    approximate_path = _safe_relative_path(
        input_directory,
        manifest["approximate_solution"],
        "manifest.approximate_solution",
    )
    try:
        model = load_model(model_path)
    except ExactSDPError as error:
        raise HarnessError(f"model: {error}") from error
    model_hash = _sha256(model_path)
    approximate_report = _validate_approximate_solution(approximate_path, model)
    declared_hashes = _validate_declared_hashes(manifest, input_directory)

    attempt_directory = _attempt_directory(root, attempt_id)
    certificate_path = _safe_relative_path(
        attempt_directory, certificate, "certificate path"
    )
    try:
        exact_certificate = load_certificate(certificate_path, model)
        verifier_report = verify_certificate(model, exact_certificate)
    except (FormatError, VerificationFailure, ExactSDPError) as error:
        raise HarnessError(f"certificate: {error}") from error
    objective = Fraction(verifier_report["objective"])
    if exact_certificate.claimed_objective != objective:
        # The low-level verifier already enforces this.  Keep the explicit
        # harness gate visible because the report binds all three values.
        raise HarnessError("certificate claim does not equal the computed objective")
    if fixed_objective is not None and objective != fixed_objective:
        raise HarnessError(
            f"computed objective {objective} does not equal manifest.fixed_objective "
            f"{fixed_objective}"
        )

    certificate_hash = _sha256(certificate_path)
    status, artifact_hashes, run_provenance = _validate_attempt_artifacts(
        attempt_directory,
        attempt_id,
        model,
        certificate_path,
        exact_certificate,
        verifier_report,
        required_status,
        manifest["id"],
        model_hash,
        certificate_hash,
        workspace,
        manifest_path,
        model_path,
        approximate_path,
    )

    constraints = []
    for constraint_spec in model.constraints:
        value = _constraint_value(constraint_spec, exact_certificate)
        passed = _constraint_passes(constraint_spec.sense, value)
        if not passed:
            # Again, this should be unreachable after verify_certificate; it
            # prevents report-generation code from silently diverging.
            raise HarnessError(
                f"constraint {constraint_spec.name!r} failed during report generation"
            )
        constraints.append(
            {
                "name": constraint_spec.name,
                "sense": constraint_spec.sense,
                "value": str(value),
                "pass": True,
            }
        )

    blocks = [
        {
            "name": block.name,
            "size": block.size,
            "rank": verifier_report["ranks"][block.name],
            "pass": True,
        }
        for block in model.blocks
    ]
    return {
        "format": HARNESS_REPORT_FORMAT,
        "status": status,
        "required_status": required_status,
        "case_id": manifest["id"],
        "attempt_id": attempt_id,
        "manifest": {
            "path": str(manifest_path.relative_to(root)),
            "sha256": _sha256(manifest_path),
        },
        "model": {
            "path": str(model_path.relative_to(root)),
            "sha256": model_hash,
            "blocks_checked": verifier_report["blocks_checked"],
            "constraints_checked": verifier_report["constraints_checked"],
        },
        "approximate_solution": {
            "path": str(approximate_path.relative_to(root)),
            **approximate_report,
        },
        "certificate": {
            "path": str(certificate_path.relative_to(root)),
            "sha256": certificate_hash,
        },
        "objective": {
            "sense": model.objective.sense,
            "computed": str(objective),
            "certificate_claim": str(exact_certificate.claimed_objective),
            "fixed": None if fixed_objective is None else str(fixed_objective),
            "pass": True,
        },
        "constraints": constraints,
        "blocks": blocks,
        "declared_input_hashes": declared_hashes,
        "attempt_artifact_sha256": artifact_hashes,
        "run_provenance": run_provenance,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one exactification testcase attempt"
    )
    parser.add_argument("case_root", type=Path)
    parser.add_argument("attempt_id")
    parser.add_argument(
        "--certificate",
        default="certificate.json",
        help="certificate path relative to the attempt directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate_attempt(
            arguments.case_root,
            arguments.attempt_id,
            certificate=arguments.certificate,
        )
    except HarnessError as error:
        print(
            json.dumps(
                {
                    "format": HARNESS_REPORT_FORMAT,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
