"""Validation harness for reusable exactification testcases."""

from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = [
    "BuildError",
    "HarnessError",
    "SuiteError",
    "build_blind_workspace",
    "load_json_strict",
    "run_suite",
    "validate_attempt",
]


def __getattr__(name: str) -> Any:
    """Load public harness symbols lazily so ``python -m`` stays warning-free."""

    if name in {"HarnessError", "load_json_strict", "validate_attempt"}:
        return getattr(import_module(".testcase_harness", __name__), name)
    if name in {"BuildError", "build_blind_workspace"}:
        return getattr(import_module(".build_blind_workspace", __name__), name)
    if name in {"SuiteError", "run_suite"}:
        return getattr(import_module(".run_suite", __name__), name)
    raise AttributeError(name)
