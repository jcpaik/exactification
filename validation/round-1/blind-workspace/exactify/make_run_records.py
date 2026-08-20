#!/usr/bin/env python3
"""Create one portable, safety-checked exactification ``run.json`` record."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


FORMAT = "exactification-run-v1"
GIT_NOT_INSPECTED = "not_inspected_blind_policy"
ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OPTIONAL_TOOL_DISTRIBUTIONS = {
    "mpmath": "mpmath",
    "numpy": "numpy",
    "python_flint": "python-flint",
    "sympy": "sympy",
}
DISCOVERY_REQUIRED = {
    "nullity_branches",
    "objective_branches",
    "precision_ladder",
    "public_matching_construction_used",
    "relation_height_ladder",
    "seeds",
}
DISCOVERY_ALLOWED = DISCOVERY_REQUIRED | {
    "denominator_ladder",
    "denominator_ladder_bits",
    "notes",
}


class RunRecordError(ValueError):
    """A user-controlled input violates the run-record contract."""


@dataclass(frozen=True)
class Settings:
    case_root: Path
    attempt_id: str
    commands_json: Path
    discovery_json: Path
    started_utc: str
    ended_utc: str
    replace: bool = False


@dataclass(frozen=True)
class Layout:
    case_root: Path
    input_dir: Path
    attempt_dir: Path
    commands_json: Path
    discovery_json: Path
    run_json: Path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    settings = parse_settings(parser, argv)
    try:
        output = generate_run_record(settings)
    except (OSError, RunRecordError) as error:
        parser.error(str(error))
    print(f"wrote {output}")
    return 0


def generate_run_record(
    settings: Settings,
    *,
    version_lookup: Callable[[str], str] | None = None,
) -> Path:
    """Validate inputs, compose canonical metadata, and write one run record."""
    layout = resolve_layout(settings)
    protect_output(layout.run_json, replace=settings.replace)

    manifest = load_json_object(layout.input_dir / "manifest.json", "public manifest")
    case_id = require_nonempty_string(manifest.get("id"), "manifest.id")
    commands = validate_commands(load_json(layout.commands_json, "commands JSON"))
    discovery = validate_discovery(load_json(layout.discovery_json, "discovery JSON"))
    started = parse_utc(settings.started_utc, "--started-utc")
    ended = parse_utc(settings.ended_utc, "--ended-utc")
    if ended < started:
        raise RunRecordError("--ended-utc must not precede --started-utc")

    record = build_record(
        case_id=case_id,
        settings=settings,
        layout=layout,
        commands=commands,
        discovery=discovery,
        started_utc=canonical_utc(started),
        ended_utc=canonical_utc(ended),
        version_lookup=version_lookup,
    )
    write_canonical_json(layout.run_json, record, replace=settings.replace)
    return layout.run_json


def build_record(
    *,
    case_id: str,
    settings: Settings,
    layout: Layout,
    commands: list[dict],
    discovery: dict,
    started_utc: str,
    ended_utc: str,
    version_lookup: Callable[[str], str] | None,
) -> dict:
    consumed = hash_tree(layout.input_dir, Path("input"))
    generated = hash_tree(
        layout.attempt_dir,
        Path("attempts") / settings.attempt_id,
        excluded={layout.run_json.resolve(strict=False)},
    )
    record = {
        "format": FORMAT,
        "case_id": case_id,
        "attempt_id": settings.attempt_id,
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "repository": {
            "commit": GIT_NOT_INSPECTED,
            "dirty_worktree": GIT_NOT_INSPECTED,
        },
        "platform": collect_platform(),
        "tool_versions": collect_tool_versions(version_lookup),
        "commands": commands,
        "consumed_file_sha256": consumed,
        "generated_file_sha256": generated,
        "metadata_input_sha256": {
            "commands_json": sha256(layout.commands_json),
            "discovery_json": sha256(layout.discovery_json),
        },
        "hash_note": "run.json is excluded from generated_file_sha256 to avoid a self-reference.",
    }
    record.update(discovery)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", required=True, type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument(
        "--commands-json",
        required=True,
        type=Path,
        help="JSON command log; relative paths are resolved from --case-root",
    )
    parser.add_argument(
        "--discovery-json",
        required=True,
        type=Path,
        help="JSON discovery metadata; relative paths are resolved from --case-root",
    )
    parser.add_argument("--started-utc", required=True, help="RFC 3339 UTC timestamp ending in Z")
    parser.add_argument("--ended-utc", required=True, help="RFC 3339 UTC timestamp ending in Z")
    parser.add_argument("--replace", action="store_true", help="replace an existing run.json")
    return parser


def parse_settings(parser: argparse.ArgumentParser, argv: Sequence[str] | None) -> Settings:
    args = parser.parse_args(argv)
    return Settings(
        case_root=args.case_root,
        attempt_id=args.attempt_id,
        commands_json=args.commands_json,
        discovery_json=args.discovery_json,
        started_utc=args.started_utc,
        ended_utc=args.ended_utc,
        replace=args.replace,
    )


def resolve_layout(settings: Settings) -> Layout:
    reject_traversal(settings.case_root, "--case-root")
    if not ATTEMPT_ID.fullmatch(settings.attempt_id) or settings.attempt_id in {".", ".."}:
        raise RunRecordError("--attempt-id must be one safe path component")

    case_root = resolve_directory(settings.case_root, "--case-root")
    input_dir = resolve_confined_directory(case_root / "input", case_root, "public input directory")
    attempts_dir = resolve_confined_directory(case_root / "attempts", case_root, "attempts directory")
    attempt_dir = resolve_confined_directory(
        attempts_dir / settings.attempt_id,
        attempts_dir,
        "attempt directory",
    )
    commands_json = resolve_metadata_file(settings.commands_json, case_root, "--commands-json")
    discovery_json = resolve_metadata_file(settings.discovery_json, case_root, "--discovery-json")
    return Layout(
        case_root=case_root,
        input_dir=input_dir,
        attempt_dir=attempt_dir,
        commands_json=commands_json,
        discovery_json=discovery_json,
        run_json=attempt_dir / "run.json",
    )


def resolve_metadata_file(raw_path: Path, case_root: Path, label: str) -> Path:
    reject_traversal(raw_path, label)
    candidate = raw_path if raw_path.is_absolute() else case_root / raw_path
    resolved = candidate.resolve(strict=True)
    require_within(resolved, case_root, label)
    if not resolved.is_file():
        raise RunRecordError(f"{label} is not a regular file: {raw_path}")
    return resolved


def resolve_directory(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RunRecordError(f"{label} is not a directory: {path}")
    return resolved


def resolve_confined_directory(path: Path, parent: Path, label: str) -> Path:
    resolved = resolve_directory(path, label)
    require_within(resolved, parent, label)
    return resolved


def reject_traversal(path: Path, label: str) -> None:
    if ".." in path.parts:
        raise RunRecordError(f"{label} must not contain '..' traversal")


def require_within(path: Path, parent: Path, label: str) -> None:
    if not path.is_relative_to(parent):
        raise RunRecordError(f"{label} escapes the allowed root: {path}")


def protect_output(path: Path, *, replace: bool) -> None:
    if path.is_symlink():
        raise RunRecordError(f"refusing to write through run.json symlink: {path}")
    if path.exists() and not replace:
        raise RunRecordError(f"run.json already exists; pass --replace to overwrite: {path}")
    if path.exists() and not path.is_file():
        raise RunRecordError(f"run.json path is not a regular file: {path}")


def load_json(path: Path, label: str):
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream, object_pairs_hook=unique_object)
    except json.JSONDecodeError as error:
        raise RunRecordError(f"invalid {label} at {path}: {error}") from error


def load_json_object(path: Path, label: str) -> dict:
    resolved = path.resolve(strict=True)
    require_within(resolved, path.parent.resolve(strict=True), label)
    value = load_json(resolved, label)
    if not isinstance(value, dict):
        raise RunRecordError(f"{label} must be a JSON object")
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise RunRecordError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def validate_commands(value) -> list[dict]:
    if isinstance(value, dict):
        if set(value) != {"commands"}:
            raise RunRecordError("commands JSON object must contain only the 'commands' field")
        value = value["commands"]
    if not isinstance(value, list):
        raise RunRecordError("commands JSON must be an array or {'commands': [...]} object")

    commands = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RunRecordError(f"commands[{index}] must be an object")
        unknown = set(item) - {"argv", "exit_code", "purpose", "note"}
        missing = {"argv", "exit_code", "purpose"} - set(item)
        if unknown or missing:
            raise RunRecordError(
                f"commands[{index}] has missing {sorted(missing)} or unknown {sorted(unknown)} fields"
            )
        argv = item["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
            raise RunRecordError(f"commands[{index}].argv must be a nonempty string array")
        if isinstance(item["exit_code"], bool) or not isinstance(item["exit_code"], int):
            raise RunRecordError(f"commands[{index}].exit_code must be an integer")
        require_nonempty_string(item["purpose"], f"commands[{index}].purpose")
        if "note" in item and not isinstance(item["note"], str):
            raise RunRecordError(f"commands[{index}].note must be a string")
        commands.append(item)
    return commands


def validate_discovery(value) -> dict:
    if not isinstance(value, dict):
        raise RunRecordError("discovery JSON must be an object")
    unknown = set(value) - DISCOVERY_ALLOWED
    missing = DISCOVERY_REQUIRED - set(value)
    denominator_fields = {"denominator_ladder", "denominator_ladder_bits"} & set(value)
    if unknown or missing or len(denominator_fields) != 1:
        raise RunRecordError(
            "discovery JSON requires the documented fields, exactly one denominator ladder, "
            f"and no unknown fields (missing={sorted(missing)}, unknown={sorted(unknown)})"
        )
    if not isinstance(value["seeds"], list):
        raise RunRecordError("discovery.seeds must be an array")
    if not isinstance(value["objective_branches"], list):
        raise RunRecordError("discovery.objective_branches must be an array")
    if not isinstance(value["public_matching_construction_used"], bool):
        raise RunRecordError("discovery.public_matching_construction_used must be boolean")
    if "notes" in value and not isinstance(value["notes"], str):
        raise RunRecordError("discovery.notes must be a string")

    result = dict(value)
    denominator_key = denominator_fields.pop()
    result["denominator_ladder"] = result.pop(denominator_key)
    return result


def require_nonempty_string(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunRecordError(f"{label} must be a nonempty string")
    return value


def parse_utc(value: str, label: str) -> dt.datetime:
    if not value.endswith("Z"):
        raise RunRecordError(f"{label} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise RunRecordError(f"invalid {label}: {value}") from error
    if parsed.utcoffset() != dt.timedelta(0):
        raise RunRecordError(f"{label} must use UTC")
    return parsed


def canonical_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def collect_platform() -> dict[str, str]:
    return {
        "machine": platform.machine(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "release": platform.release(),
        "system": platform.system(),
    }


def collect_tool_versions(
    version_lookup: Callable[[str], str] | None = None,
) -> dict[str, str]:
    lookup = version_lookup or metadata.version
    versions = {}
    for name, distribution in sorted(OPTIONAL_TOOL_DISTRIBUTIONS.items()):
        try:
            versions[name] = lookup(distribution)
        except metadata.PackageNotFoundError:
            versions[name] = "not_available"
    return versions


def hash_tree(base: Path, prefix: Path, *, excluded: set[Path] | None = None) -> dict[str, str]:
    base = base.resolve(strict=True)
    excluded = excluded or set()
    result = {}
    for path in sorted(base.rglob("*"), key=lambda item: item.relative_to(base).as_posix()):
        if path.is_symlink():
            target = path.resolve(strict=True)
            require_within(target, base, "hashed symlink")
            if target.is_dir():
                raise RunRecordError(f"directory symlinks are not supported in hashed trees: {path}")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        require_within(resolved, base, "hashed file")
        if resolved in excluded:
            continue
        logical_path = (prefix / path.relative_to(base)).as_posix()
        result[logical_path] = sha256(resolved)
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_canonical_json(path: Path, value: dict, *, replace: bool) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
        return

    descriptor, temporary_name = tempfile.mkstemp(prefix=".run.json.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
