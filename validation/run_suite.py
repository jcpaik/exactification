"""Run the complete exactification acceptance suite from strict JSON config."""

from __future__ import annotations

import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .testcase_harness import HarnessError, load_json_strict


SUITE_FORMAT = "exactification-suite-v1"
SUMMARY_FORMAT = "exactification-suite-report-v1"
SUCCESS_STATUSES = {
    "EXACT_SDP_CERTIFICATE",
    "RIGOROUS_PROBLEM_BOUND",
    "SHARP_OR_OPTIMAL",
}

_CASE_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_ATTEMPT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_COMMAND_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_RATIONAL_RE = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class SuiteError(Exception):
    """The suite configuration or expected coverage is invalid."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SuiteError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _object(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SuiteError(f"{location}: expected an object")
    return value


def _array(value: Any, location: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SuiteError(f"{location}: expected an array")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise SuiteError(f"{location}: expected a nonempty string")
    return value


def _integer(value: Any, location: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SuiteError(f"{location}: expected an integer >= {minimum}")
    return value


def _fields(
    value: Mapping[str, Any],
    location: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - allowed)
    if missing:
        raise SuiteError(f"{location}: missing field(s): {', '.join(missing)}")
    if unknown:
        raise SuiteError(f"{location}: unknown field(s): {', '.join(unknown)}")


def _canonical_rational(value: Any, location: str) -> Fraction:
    if not isinstance(value, str) or _RATIONAL_RE.fullmatch(value) is None:
        raise SuiteError(f"{location}: expected a canonical rational string")
    result = Fraction(value)
    if str(result) != value:
        raise SuiteError(
            f"{location}: rational must be reduced and canonical; use {str(result)!r}"
        )
    return result


def _safe_working_directory(repository: Path, spelling: Any, location: str) -> Path:
    value = _string(spelling, location)
    if "\\" in value:
        raise SuiteError(f"{location}: paths must use '/' separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise SuiteError(f"{location}: expected a safe repository-relative path")
    candidate = repository.joinpath(*path.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repository)
    except (OSError, ValueError) as error:
        raise SuiteError(f"{location}: path escapes or does not exist: {value!r}") from error
    if not resolved.is_dir():
        raise SuiteError(f"{location}: expected a directory")
    return resolved


def _command_spec(raw: Any, location: str) -> dict[str, Any]:
    value = _object(raw, location)
    _fields(
        value,
        location,
        required={"id", "command", "cwd", "expected_exit_code"},
        optional={"timeout_seconds"},
    )
    command_id = _string(value["id"], f"{location}.id")
    if _COMMAND_ID_RE.fullmatch(command_id) is None:
        raise SuiteError(f"{location}.id: expected a safe command identifier")
    command = list(_array(value["command"], f"{location}.command"))
    if not command:
        raise SuiteError(f"{location}.command: command must not be empty")
    for position, argument in enumerate(command):
        _string(argument, f"{location}.command[{position}]")
    if command[0] != "{python}":
        raise SuiteError(f"{location}.command[0]: expected '{{python}}'")
    return {
        "id": command_id,
        "command": command,
        "cwd": _string(value["cwd"], f"{location}.cwd"),
        "expected_exit_code": _integer(
            value["expected_exit_code"], f"{location}.expected_exit_code"
        ),
        "timeout_seconds": _integer(
            value.get("timeout_seconds", 300),
            f"{location}.timeout_seconds",
            minimum=1,
        ),
    }


def _attempt_spec(raw: Any, location: str) -> dict[str, Any]:
    value = _object(raw, location)
    _fields(
        value,
        location,
        required={
            "case_id",
            "case_root",
            "attempt_id",
            "expected_target",
            "expected_status",
            "expected_blocks",
            "expected_constraints",
        },
    )
    case_id = _string(value["case_id"], f"{location}.case_id")
    if _CASE_ID_RE.fullmatch(case_id) is None:
        raise SuiteError(f"{location}.case_id: expected a lowercase hyphenated slug")
    case_root = _string(value["case_root"], f"{location}.case_root")
    if "\\" in case_root:
        raise SuiteError(f"{location}.case_root: paths must use '/' separators")
    case_root_path = PurePosixPath(case_root)
    if (
        case_root_path.is_absolute()
        or ".." in case_root_path.parts
        or case_root_path.name != case_id
    ):
        raise SuiteError(
            f"{location}.case_root: expected a safe repository-relative path ending in {case_id!r}"
        )
    attempt_id = _string(value["attempt_id"], f"{location}.attempt_id")
    if _ATTEMPT_ID_RE.fullmatch(attempt_id) is None or attempt_id in {".", ".."}:
        raise SuiteError(f"{location}.attempt_id: expected a safe identifier")
    target_raw = value["expected_target"]
    if target_raw is None:
        raise SuiteError(
            f"{location}.expected_target: fixed_objective:null discovery cases are "
            "outside the fixed-target v1 suite"
        )
    target = _canonical_rational(target_raw, f"{location}.expected_target")
    status = _string(value["expected_status"], f"{location}.expected_status")
    if status not in SUCCESS_STATUSES:
        raise SuiteError(f"{location}.expected_status: unsupported successful status")
    return {
        "case_id": case_id,
        "case_root": case_root,
        "attempt_id": attempt_id,
        "expected_target": target,
        "expected_status": status,
        "expected_blocks": _integer(
            value["expected_blocks"], f"{location}.expected_blocks", minimum=1
        ),
        "expected_constraints": _integer(
            value["expected_constraints"],
            f"{location}.expected_constraints",
        ),
    }


def _load_config(path: Path) -> dict[str, Any]:
    try:
        raw = load_json_strict(path)
    except HarnessError as error:
        raise SuiteError(str(error)) from error
    config = _object(raw, "suite")
    _fields(
        config,
        "suite",
        required={
            "format",
            "suite_id",
            "expected_case_ids",
            "unit_tests",
            "preflights",
            "attempts",
        },
    )
    if config["format"] != SUITE_FORMAT:
        raise SuiteError(f"suite.format: expected {SUITE_FORMAT!r}")
    suite_id = _string(config["suite_id"], "suite.suite_id")
    if _COMMAND_ID_RE.fullmatch(suite_id) is None:
        raise SuiteError("suite.suite_id: expected a safe identifier")

    expected_cases = list(_array(config["expected_case_ids"], "suite.expected_case_ids"))
    if not expected_cases:
        raise SuiteError("suite.expected_case_ids: at least one case is required")
    for position, case_id in enumerate(expected_cases):
        case_id = _string(case_id, f"suite.expected_case_ids[{position}]")
        if _CASE_ID_RE.fullmatch(case_id) is None:
            raise SuiteError(
                f"suite.expected_case_ids[{position}]: expected a lowercase slug"
            )
    if len(expected_cases) != len(set(expected_cases)):
        raise SuiteError("suite.expected_case_ids: duplicate case ID")

    unit_tests = _command_spec(config["unit_tests"], "suite.unit_tests")
    preflights = [
        _command_spec(item, f"suite.preflights[{position}]")
        for position, item in enumerate(
            _array(config["preflights"], "suite.preflights")
        )
    ]
    command_ids = [unit_tests["id"]] + [item["id"] for item in preflights]
    if len(command_ids) != len(set(command_ids)):
        raise SuiteError("suite: unit/preflight command IDs must be unique")

    attempts = [
        _attempt_spec(item, f"suite.attempts[{position}]")
        for position, item in enumerate(_array(config["attempts"], "suite.attempts"))
    ]
    attempt_keys = [
        (item["case_root"], item["attempt_id"]) for item in attempts
    ]
    if len(attempt_keys) != len(set(attempt_keys)):
        raise SuiteError("suite.attempts: duplicate case/attempt pair")
    covered_cases = {item["case_id"] for item in attempts}
    expected_set = set(expected_cases)
    if covered_cases != expected_set:
        missing = sorted(expected_set - covered_cases)
        extra = sorted(covered_cases - expected_set)
        raise SuiteError(
            "suite attempt coverage mismatch; "
            f"missing={missing}, extra={extra}"
        )
    return {
        "format": SUITE_FORMAT,
        "suite_id": suite_id,
        "expected_case_ids": expected_cases,
        "unit_tests": unit_tests,
        "preflights": preflights,
        "attempts": attempts,
    }


def _expand_command(arguments: Sequence[str], repository: Path) -> list[str]:
    expanded: list[str] = []
    for argument in arguments:
        if argument == "{python}":
            expanded.append(sys.executable)
        elif argument == "{repository}":
            expanded.append(str(repository))
        elif "{python}" in argument or "{repository}" in argument:
            raise SuiteError("command placeholders must occupy a complete argument")
        else:
            expanded.append(argument)
    return expanded


def _runtime_environment() -> tuple[dict[str, str], str]:
    environment = dict(os.environ)
    runtime_root = str(Path(__file__).resolve().parents[1])
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        runtime_root if not existing else runtime_root + os.pathsep + existing
    )
    return environment, runtime_root


def _run_command(
    *,
    command_id: str,
    kind: str,
    arguments: Sequence[str],
    cwd: Path,
    expected_exit_code: int,
    timeout_seconds: int,
) -> tuple[dict[str, Any], bytes, bytes]:
    environment, runtime_root = _runtime_environment()
    argv_bytes = json.dumps(list(arguments), separators=(",", ":")).encode("utf-8")
    timed_out = False
    try:
        result = subprocess.run(
            list(arguments),
            cwd=cwd,
            env=environment,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        exit_code: int | None = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = None
        timed_out = True
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    passed = exit_code == expected_exit_code and not timed_out
    command_report: dict[str, Any] = {
        "id": command_id,
        "kind": kind,
        "argv": list(arguments),
        "argv_sha256": _sha256_bytes(argv_bytes),
        "cwd": str(cwd),
        "pythonpath_runtime_root": runtime_root,
        "expected_exit_code": expected_exit_code,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_sha256": _sha256_bytes(stdout),
        "stderr_sha256": _sha256_bytes(stderr),
        "pass": passed,
    }
    if not passed:
        command_report["stdout_tail"] = stdout.decode("utf-8", errors="replace")[-2000:]
        command_report["stderr_tail"] = stderr.decode("utf-8", errors="replace")[-2000:]
    return command_report, stdout, stderr


def _parse_json_output(data: bytes, location: str) -> Mapping[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SuiteError(f"{location}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SuiteError(f"{location}: nonstandard JSON value {value!r}")

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique,
            parse_float=Decimal,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SuiteError(f"{location}: invalid JSON output: {error}") from error
    return _object(value, location)


def _check_attempt_report(
    report: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[bool, list[str], dict[str, Any]]:
    failures: list[str] = []
    case_id = expected["case_id"]
    case_root = expected["case_root"]
    attempt_id = expected["attempt_id"]
    if report.get("case_id") != case_id:
        failures.append("case_id mismatch")
    if report.get("attempt_id") != attempt_id:
        failures.append("attempt_id mismatch")
    if report.get("status") != expected["expected_status"]:
        failures.append("status mismatch")
    if report.get("required_status") != expected["expected_status"]:
        failures.append("required status mismatch")

    objective = report.get("objective")
    if not isinstance(objective, dict):
        failures.append("missing objective report")
        actual_fixed = actual_computed = None
    else:
        actual_fixed = objective.get("fixed")
        actual_computed = objective.get("computed")
        expected_target = expected["expected_target"]
        expected_spelling = None if expected_target is None else str(expected_target)
        if actual_fixed != expected_spelling:
            failures.append("fixed target mismatch")
        if expected_target is not None and actual_computed != expected_spelling:
            failures.append("computed target mismatch")

    model = report.get("model")
    if not isinstance(model, dict):
        failures.append("missing model coverage")
        blocks_checked = constraints_checked = None
        model_hash = None
    else:
        blocks_checked = model.get("blocks_checked")
        constraints_checked = model.get("constraints_checked")
        model_hash = model.get("sha256")
        if blocks_checked != expected["expected_blocks"]:
            failures.append("block coverage mismatch")
        if constraints_checked != expected["expected_constraints"]:
            failures.append("constraint coverage mismatch")
        if not isinstance(model_hash, str) or _SHA256_RE.fullmatch(model_hash) is None:
            failures.append("missing or invalid model hash")

    blocks = report.get("blocks")
    if not isinstance(blocks, list) or len(blocks) != expected["expected_blocks"]:
        failures.append("block report length mismatch")
    elif len({item.get("name") for item in blocks if isinstance(item, dict)}) != len(blocks):
        failures.append("duplicate block report name")
    constraints = report.get("constraints")
    if (
        not isinstance(constraints, list)
        or len(constraints) != expected["expected_constraints"]
    ):
        failures.append("constraint report length mismatch")
    elif len(
        {item.get("name") for item in constraints if isinstance(item, dict)}
    ) != len(constraints):
        failures.append("duplicate constraint report name")

    certificate = report.get("certificate")
    certificate_hash = certificate.get("sha256") if isinstance(certificate, dict) else None
    if (
        not isinstance(certificate_hash, str)
        or _SHA256_RE.fullmatch(certificate_hash) is None
    ):
        failures.append("missing or invalid certificate hash")
    summary = {
        "case_id": case_id,
        "case_root": case_root,
        "attempt_id": attempt_id,
        "expected_target": (
            None
            if expected["expected_target"] is None
            else str(expected["expected_target"])
        ),
        "actual_target": actual_computed,
        "expected_status": expected["expected_status"],
        "actual_status": report.get("status"),
        "expected_blocks": expected["expected_blocks"],
        "actual_blocks": blocks_checked,
        "expected_constraints": expected["expected_constraints"],
        "actual_constraints": constraints_checked,
        "model_sha256": model_hash,
        "certificate_sha256": certificate_hash,
        "failures": failures,
        "pass": not failures,
    }
    return not failures, failures, summary


def run_suite(
    repository: str | Path,
    config_path: str | Path,
) -> dict[str, Any]:
    """Run configured subprocess checks and return a machine-readable summary."""

    try:
        repository_path = Path(repository).resolve(strict=True)
        config = Path(config_path).resolve(strict=True)
    except OSError as error:
        raise SuiteError(f"cannot resolve suite input: {error}") from error
    if not repository_path.is_dir() or not config.is_file():
        raise SuiteError("repository must be a directory and config must be a file")
    parsed = _load_config(config)

    commands: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    all_passed = True

    command_specs = [("unit_tests", parsed["unit_tests"])] + [
        ("preflight", item) for item in parsed["preflights"]
    ]
    for kind, spec in command_specs:
        cwd = _safe_working_directory(
            repository_path, spec["cwd"], f"command {spec['id']}.cwd"
        )
        arguments = _expand_command(spec["command"], repository_path)
        command_report, _, _ = _run_command(
            command_id=spec["id"],
            kind=kind,
            arguments=arguments,
            cwd=cwd,
            expected_exit_code=spec["expected_exit_code"],
            timeout_seconds=spec["timeout_seconds"],
        )
        commands.append(command_report)
        all_passed = all_passed and command_report["pass"]

    for expected in parsed["attempts"]:
        case_id = expected["case_id"]
        case_root = expected["case_root"]
        attempt_id = expected["attempt_id"]
        _safe_working_directory(
            repository_path, case_root, f"attempt {case_id}/{attempt_id}.case_root"
        )
        arguments = [
            sys.executable,
            "-m",
            "validation.testcase_harness",
            case_root,
            attempt_id,
        ]
        command_report, stdout, _ = _run_command(
            command_id=f"attempt-{case_id}-{attempt_id}",
            kind="attempt",
            arguments=arguments,
            cwd=repository_path,
            expected_exit_code=0,
            timeout_seconds=300,
        )
        commands.append(command_report)
        if not command_report["pass"]:
            attempts.append(
                {
                    "case_id": case_id,
                    "case_root": case_root,
                    "attempt_id": attempt_id,
                    "failures": ["manifest-aware harness process failed"],
                    "harness_stdout_sha256": command_report["stdout_sha256"],
                    "pass": False,
                }
            )
            all_passed = False
            continue
        try:
            harness_report = _parse_json_output(
                stdout, f"attempt {case_id}/{attempt_id}"
            )
            attempt_passed, _, attempt_summary = _check_attempt_report(
                harness_report, expected
            )
        except SuiteError as error:
            attempt_passed = False
            attempt_summary = {
                "case_id": case_id,
                "case_root": case_root,
                "attempt_id": attempt_id,
                "failures": [str(error)],
                "pass": False,
            }
        attempt_summary["harness_stdout_sha256"] = command_report["stdout_sha256"]
        attempts.append(attempt_summary)
        all_passed = all_passed and attempt_passed

    reported_cases = {item["case_id"] for item in attempts if "case_id" in item}
    expected_cases = set(parsed["expected_case_ids"])
    coverage = {
        "expected_case_ids": sorted(expected_cases),
        "reported_case_ids": sorted(reported_cases),
        "missing_case_ids": sorted(expected_cases - reported_cases),
        "extra_case_ids": sorted(reported_cases - expected_cases),
    }
    if coverage["missing_case_ids"] or coverage["extra_case_ids"]:
        all_passed = False

    return {
        "format": SUMMARY_FORMAT,
        "suite_id": parsed["suite_id"],
        "status": "passed" if all_passed else "failed",
        "config": {
            "path": str(config),
            "sha256": _sha256_file(config),
        },
        "coverage": coverage,
        "commands": commands,
        "attempts": attempts,
    }


def _parser() -> argparse.ArgumentParser:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run the complete exactification acceptance suite"
    )
    parser.add_argument("--repository", type=Path, default=repository)
    parser.add_argument(
        "--config",
        type=Path,
        default=repository / "validation" / "suite.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = run_suite(arguments.repository, arguments.config)
    except SuiteError as error:
        report = {
            "format": SUMMARY_FORMAT,
            "status": "failed",
            "error": str(error),
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
