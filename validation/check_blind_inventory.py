#!/usr/bin/env python3
"""Verify the immutable seal and permitted outputs of a blind workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from .testcase_harness import HarnessError, load_json_strict


FORMAT = "exactification-blind-workspace-inventory-v1"
INVENTORY = "BLIND_WORKSPACE_INVENTORY.json"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CASE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PROHIBITED = {".git", "construction", "constructions", "oracle", "oracles", "attempts"}


class InventoryError(Exception):
    """The workspace no longer matches its sealed inventory."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InventoryError(f"{location}: expected an object")
    return value


def _safe_relative(value: Any, location: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InventoryError(f"{location}: expected a nonempty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise InventoryError(f"{location}: unsafe relative path {value!r}")
    if path.as_posix() != value:
        raise InventoryError(f"{location}: path is not canonical: {value!r}")
    return path


def _metadata(path: Path, location: str):
    try:
        metadata = path.lstat()
    except OSError as error:
        raise InventoryError(f"{location}: cannot stat {path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise InventoryError(f"{location}: symlinks are forbidden: {path}")
    return metadata


def _allowed_generated(path: PurePosixPath, case_ids: set[str]) -> bool:
    if path == PurePosixPath("executor-report-round-2.md"):
        return True
    parts = path.parts
    return (
        len(parts) >= 3
        and parts[0] == "testcases"
        and parts[1] in case_ids
        and parts[2] == "attempts"
        and not any(
            part.lower() == ".git"
            or "oracle" in part.lower()
            or "construction" in part.lower()
            for part in parts[3:]
        )
    )


def check_blind_inventory(
    workspace: str | Path,
    *,
    allow_generated_attempts: bool = False,
) -> dict[str, Any]:
    root = Path(workspace).absolute()
    metadata = _metadata(root, "workspace")
    if not stat.S_ISDIR(metadata.st_mode):
        raise InventoryError(f"workspace is not a directory: {root}")
    inventory_path = root / INVENTORY
    inventory_metadata = _metadata(inventory_path, "inventory")
    if not stat.S_ISREG(inventory_metadata.st_mode):
        raise InventoryError("inventory is not a regular file")
    try:
        raw = load_json_strict(inventory_path)
    except HarnessError as error:
        raise InventoryError(str(error)) from error
    document = _object(raw, "inventory")
    if set(document) != {"format", "case_ids", "files"}:
        raise InventoryError("inventory: expected exactly format, case_ids, and files")
    if document["format"] != FORMAT:
        raise InventoryError(f"inventory.format: expected {FORMAT!r}")

    raw_cases = document["case_ids"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise InventoryError("inventory.case_ids: expected a nonempty array")
    case_ids: list[str] = []
    for position, value in enumerate(raw_cases):
        if not isinstance(value, str) or _CASE.fullmatch(value) is None:
            raise InventoryError(f"inventory.case_ids[{position}]: invalid case ID")
        case_ids.append(value)
    if len(case_ids) != len(set(case_ids)) or case_ids != sorted(case_ids):
        raise InventoryError("inventory.case_ids must be unique and sorted")

    raw_files = document["files"]
    if not isinstance(raw_files, list):
        raise InventoryError("inventory.files: expected an array")
    listed: dict[PurePosixPath, dict[str, Any]] = {}
    for position, raw_entry in enumerate(raw_files):
        entry = _object(raw_entry, f"inventory.files[{position}]")
        required = {"path", "source", "category", "size", "sha256"}
        if set(entry) != required:
            raise InventoryError(f"inventory.files[{position}]: wrong fields")
        relative = _safe_relative(entry["path"], f"inventory.files[{position}].path")
        if relative in listed:
            raise InventoryError(f"inventory.files: duplicate path {relative}")
        if set(part.lower() for part in relative.parts) & _PROHIBITED:
            raise InventoryError(f"inventory contains prohibited path {relative}")
        if not isinstance(entry["source"], str) or not entry["source"]:
            raise InventoryError(f"inventory.files[{position}].source: expected string")
        if not isinstance(entry["category"], str) or not entry["category"]:
            raise InventoryError(f"inventory.files[{position}].category: expected string")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise InventoryError(f"inventory.files[{position}].size: expected nonnegative integer")
        if not isinstance(entry["sha256"], str) or _SHA.fullmatch(entry["sha256"]) is None:
            raise InventoryError(f"inventory.files[{position}].sha256: invalid digest")
        listed[relative] = entry
    if list(listed) != sorted(listed, key=lambda item: item.as_posix()):
        raise InventoryError("inventory.files must be sorted by path")

    original_directories: set[PurePosixPath] = {PurePosixPath(".")}
    for relative, entry in listed.items():
        current = relative.parent
        while current != PurePosixPath("."):
            original_directories.add(current)
            current = current.parent
        path = root.joinpath(*relative.parts)
        file_metadata = _metadata(path, f"inventoried file {relative}")
        if not stat.S_ISREG(file_metadata.st_mode):
            raise InventoryError(f"inventoried path is not a regular file: {relative}")
        if file_metadata.st_size != entry["size"]:
            raise InventoryError(f"inventoried size mismatch: {relative}")
        if _sha256(path) != entry["sha256"]:
            raise InventoryError(f"inventoried hash mismatch: {relative}")

    generated_files: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        path_metadata = _metadata(path, f"workspace path {relative}")
        if relative in listed or relative in original_directories or relative == PurePosixPath(INVENTORY):
            continue
        if allow_generated_attempts and _allowed_generated(relative, set(case_ids)):
            if stat.S_ISREG(path_metadata.st_mode):
                generated_files.append(relative.as_posix())
            elif not stat.S_ISDIR(path_metadata.st_mode):
                raise InventoryError(f"generated path has unsupported type: {relative}")
            continue
        raise InventoryError(f"unexpected workspace path: {relative}")

    return {
        "format": "exactification-blind-workspace-check-v1",
        "status": "verified",
        "workspace": str(root),
        "inventory_sha256": _sha256(inventory_path),
        "case_ids": case_ids,
        "inventoried_files": len(listed),
        "generated_files": generated_files,
        "generated_file_count": len(generated_files),
        "allow_generated_attempts": allow_generated_attempts,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--allow-generated-attempts", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = check_blind_inventory(
            arguments.workspace,
            allow_generated_attempts=arguments.allow_generated_attempts,
        )
    except (InventoryError, OSError) as error:
        report = {
            "format": "exactification-blind-workspace-check-v1",
            "status": "failed",
            "error": str(error),
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
