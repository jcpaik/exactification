"""Build a deterministic, certificate-free exactification workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Iterable

from .testcase_harness import HarnessError, load_json_strict


INVENTORY_FORMAT = "exactification-blind-workspace-inventory-v1"
INVENTORY_NAME = "BLIND_WORKSPACE_INVENTORY.json"

# These are repository-runtime files, not directory globs.  Updating the
# trusted surface therefore requires an intentional code change and review.
TRUSTED_FILES = (
    "manual/EXACTIFICATION_WORKFLOW.md",
    "manual/TESTCASE_CONTRACT.md",
    "verify/FORMAT.md",
    "verify/__init__.py",
    "verify/__main__.py",
    "verify/exact_sdp.py",
    "validation/__init__.py",
    "validation/testcase_harness.py",
)
EXACTIFY_RUNTIME_FILES = (
    "exactify/affine_modular_solve.py",
    "exactify/affine_round.py",
    "exactify/build_affine_config.py",
    "exactify/make_discovery_artifacts.py",
    "exactify/make_run_records.py",
    "exactify/recover_projectors.py",
    "exactify/recover_relations.py",
)

_CASE_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PROHIBITED_PARTS = {
    ".git",
    "attempts",
    "construction",
    "constructions",
    "oracle",
    "oracles",
}
_CACHE_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
}
_CACHE_FILES = {".DS_Store"}
_CACHE_SUFFIXES = {".pyc", ".pyo"}
_PROHIBITED_INPUT_FILENAMES = {
    "certificate.json",
    "expected.json",
    "oracle.json",
}
_PROHIBITED_INPUT_TEXT = (
    "exact-block-sdp-certificate-v1",
    '"psd_trace"',
    "PAPER_MATRICES",
)
_PROHIBITED_RUNTIME_TEXT = (
    "oracle/",
    "oracles/",
    "PAPER_MATRICES",
    "retry-1",
)
_PROHIBITED_RUNTIME_PATTERNS = (
    (
        re.compile(r"testcases/[a-z0-9]+(?:-[a-z0-9]+)*"),
        "hardcoded testcase path",
    ),
    (
        re.compile(r"(?:attempt|retry)-[0-9]+(?:[A-Za-z0-9._-]*)"),
        "hardcoded attempt identifier",
    ),
)


class BuildError(Exception):
    """The requested blind workspace cannot be built safely."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise BuildError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _relative_spelling(path: Path) -> str:
    return path.as_posix()


def _check_relative_path(relative: Path, *, category: str) -> None:
    lowered = {part.lower() for part in relative.parts}
    prohibited = sorted(lowered & _PROHIBITED_PARTS)
    if prohibited:
        raise BuildError(
            f"{category}: prohibited path component(s) in {relative}: "
            + ", ".join(prohibited)
        )


def _is_cache_path(relative: Path) -> bool:
    return (
        any(part in _CACHE_PARTS for part in relative.parts)
        or relative.name in _CACHE_FILES
        or relative.suffix in _CACHE_SUFFIXES
    )


def _regular_file(path: Path, description: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise BuildError(f"{description}: cannot stat {path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise BuildError(f"{description}: symlinks are forbidden: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise BuildError(f"{description}: expected a regular file: {path}")


def _walk_public_input(input_directory: Path) -> list[Path]:
    try:
        root_metadata = input_directory.lstat()
    except OSError as error:
        raise BuildError(f"cannot stat public input {input_directory}: {error}") from error
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise BuildError(f"public input must be a real directory: {input_directory}")

    files: list[Path] = []
    for directory, directory_names, filenames in os.walk(
        input_directory, topdown=True, followlinks=False
    ):
        current = Path(directory)
        kept_directories: list[str] = []
        for name in sorted(directory_names):
            path = current / name
            relative = path.relative_to(input_directory)
            try:
                metadata = path.lstat()
            except OSError as error:
                raise BuildError(f"cannot stat public input path {path}: {error}") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise BuildError(f"public input symlink is forbidden: {path}")
            if _is_cache_path(relative):
                continue
            _check_relative_path(relative, category="public input")
            kept_directories.append(name)
        directory_names[:] = kept_directories

        for name in sorted(filenames):
            path = current / name
            relative = path.relative_to(input_directory)
            _regular_file(path, "public input")
            if _is_cache_path(relative):
                continue
            _check_relative_path(relative, category="public input")
            if relative.name.lower() in _PROHIBITED_INPUT_FILENAMES:
                raise BuildError(f"public input contains prohibited artifact {relative}")
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(input_directory).as_posix())


def _walk_json(value: Any, location: str) -> None:
    if isinstance(value, dict):
        if value.get("format") == "exact-block-sdp-certificate-v1":
            raise BuildError(f"certificate-format object leaked into {location}")
        for key, child in value.items():
            if key == "psd_trace":
                raise BuildError(f"PSD certificate trace leaked into {location}")
            _walk_json(child, location)
    elif isinstance(value, list):
        for child in value:
            _walk_json(child, location)


def _scan_case_input(path: Path) -> None:
    if path.suffix.lower() == ".json":
        try:
            _walk_json(load_json_strict(path), str(path))
        except HarnessError as error:
            raise BuildError(f"public input JSON is invalid: {error}") from error
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    except OSError as error:
        raise BuildError(f"cannot scan public input {path}: {error}") from error
    for marker in _PROHIBITED_INPUT_TEXT:
        if marker in text:
            raise BuildError(
                f"public input contains prohibited certificate marker {marker!r}: {path}"
            )


def _scan_runtime_tool(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BuildError(f"cannot scan runtime tool {path}: {error}") from error
    for marker in _PROHIBITED_RUNTIME_TEXT:
        if marker in text:
            raise BuildError(
                f"runtime exactify tool contains run-specific marker {marker!r}: {path}"
            )
    for pattern, description in _PROHIBITED_RUNTIME_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            raise BuildError(
                f"runtime exactify tool contains {description} {match.group(0)!r}: {path}"
            )


def _source_file(repository: Path, relative: str, category: str) -> Path:
    relative_path = Path(relative)
    _check_relative_path(relative_path, category=category)
    source = repository / relative_path
    _regular_file(source, category)
    return source


def _copy_file(
    repository: Path,
    destination: Path,
    source: Path,
    destination_relative: Path,
    category: str,
) -> dict[str, Any]:
    _check_relative_path(destination_relative, category=category)
    target = destination / destination_relative
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(source, target)
    except OSError as error:
        raise BuildError(f"cannot copy {source} to {target}: {error}") from error
    source_hash = _sha256(source)
    target_hash = _sha256(target)
    if target_hash != source_hash:
        raise BuildError(f"copy hash mismatch for {destination_relative}")
    try:
        source_relative = source.relative_to(repository)
        size = source.stat().st_size
    except (OSError, ValueError) as error:
        raise BuildError(f"cannot inventory {source}: {error}") from error
    return {
        "path": _relative_spelling(destination_relative),
        "source": _relative_spelling(source_relative),
        "category": category,
        "size": size,
        "sha256": source_hash,
    }


def _normalize_case_ids(case_ids: Iterable[str]) -> list[str]:
    result = list(case_ids)
    if not result:
        raise BuildError("at least one testcase ID is required")
    if len(result) != len(set(result)):
        raise BuildError("testcase IDs must be unique")
    for case_id in result:
        if not isinstance(case_id, str) or _CASE_ID_RE.fullmatch(case_id) is None:
            raise BuildError(f"unsafe testcase ID {case_id!r}")
    return sorted(result)


def build_blind_workspace(
    repository: str | Path,
    destination: str | Path,
    case_ids: Iterable[str],
) -> dict[str, Any]:
    """Copy the explicit blind allowlist into a new, nonexisting directory."""

    try:
        repository_path = Path(repository).resolve(strict=True)
    except OSError as error:
        raise BuildError(f"cannot resolve repository {repository!r}: {error}") from error
    if not repository_path.is_dir():
        raise BuildError(f"repository is not a directory: {repository_path}")
    selected_cases = _normalize_case_ids(case_ids)

    destination_path = Path(destination).absolute()
    if destination_path.exists() or destination_path.is_symlink():
        raise BuildError(
            f"destination already exists; refusing to overwrite: {destination_path}"
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination_path.mkdir()
    except OSError as error:
        raise BuildError(f"cannot create destination {destination_path}: {error}") from error

    created = True
    try:
        entries: list[dict[str, Any]] = []
        for relative in TRUSTED_FILES:
            source = _source_file(repository_path, relative, "trusted runtime")
            entries.append(
                _copy_file(
                    repository_path,
                    destination_path,
                    source,
                    Path(relative),
                    "trusted_runtime",
                )
            )
        for relative in EXACTIFY_RUNTIME_FILES:
            source = _source_file(repository_path, relative, "exactify runtime")
            _scan_runtime_tool(source)
            entries.append(
                _copy_file(
                    repository_path,
                    destination_path,
                    source,
                    Path(relative),
                    "exactify_runtime",
                )
            )

        testcases_root = repository_path / "testcases"
        try:
            testcases_metadata = testcases_root.lstat()
        except OSError as error:
            raise BuildError(f"cannot stat testcase directory {testcases_root}: {error}") from error
        if stat.S_ISLNK(testcases_metadata.st_mode) or not stat.S_ISDIR(
            testcases_metadata.st_mode
        ):
            raise BuildError(
                "testcases directory must be a real directory, not a symlink: "
                f"{testcases_root}"
            )

        for case_id in selected_cases:
            case_root = testcases_root / case_id
            input_directory = case_root / "input"
            try:
                case_metadata = case_root.lstat()
            except OSError as error:
                raise BuildError(f"unknown testcase {case_id!r}: {error}") from error
            if stat.S_ISLNK(case_metadata.st_mode) or not stat.S_ISDIR(
                case_metadata.st_mode
            ):
                raise BuildError(
                    f"testcase root must be a real directory, not a symlink: {case_root}"
                )
            if not input_directory.is_dir():
                raise BuildError(f"unknown or incomplete testcase {case_id!r}")
            for source in _walk_public_input(input_directory):
                _scan_case_input(source)
                input_relative = source.relative_to(input_directory)
                destination_relative = (
                    Path("testcases") / case_id / "input" / input_relative
                )
                entries.append(
                    _copy_file(
                        repository_path,
                        destination_path,
                        source,
                        destination_relative,
                        "case_input",
                    )
                )

        entries.sort(key=lambda entry: entry["path"])
        paths = [entry["path"] for entry in entries]
        if len(paths) != len(set(paths)):
            raise BuildError("allowlist produced duplicate destination paths")
        inventory = {
            "format": INVENTORY_FORMAT,
            "case_ids": selected_cases,
            "files": entries,
        }
        inventory_bytes = (
            json.dumps(inventory, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        inventory_path = destination_path / INVENTORY_NAME
        inventory_path.write_bytes(inventory_bytes)

        # A final destination-side path scan guards against future copy-rule
        # changes accidentally broadening the snapshot.
        actual_files = sorted(
            path.relative_to(destination_path).as_posix()
            for path in destination_path.rglob("*")
            if path.is_file()
        )
        expected_files = sorted(paths + [INVENTORY_NAME])
        if actual_files != expected_files:
            raise BuildError(
                "destination coverage differs from the explicit allowlist: "
                f"expected {expected_files}, found {actual_files}"
            )

        created = False
        return {
            "format": INVENTORY_FORMAT,
            "status": "built",
            "case_ids": selected_cases,
            "file_count": len(entries),
            "inventory": INVENTORY_NAME,
            "inventory_sha256": _sha256_bytes(inventory_bytes),
            "files": entries,
        }
    finally:
        if created and destination_path.exists():
            shutil.rmtree(destination_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic certificate-free blind workspace"
    )
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--case", action="append", required=True, dest="case_ids")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = build_blind_workspace(
            arguments.repository, arguments.destination, arguments.case_ids
        )
    except BuildError as error:
        print(
            json.dumps(
                {"format": INVENTORY_FORMAT, "status": "failed", "error": str(error)},
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
