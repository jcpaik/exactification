#!/usr/bin/env python3
"""Assemble affine-rounding configuration from persisted kernel discoveries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixed-objective", required=True)
    parser.add_argument("--projectors", required=True, type=Path)
    parser.add_argument("--relation-override", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    recovered = json.loads(args.projectors.read_text())["blocks"]
    for override_path in args.relation_override:
        override = json.loads(override_path.read_text())
        recovered[override["block"]] = override

    kernels = {}
    failures = []
    for block, entry in recovered.items():
        nullity = entry.get("candidate_nullity", 0)
        if not nullity:
            continue
        if entry.get("status") != "recovered":
            failures.append(block)
            continue
        kernels[block] = entry["kernel_basis_columns"]
    if failures:
        raise RuntimeError(f"unrecovered kernel blocks: {failures}")

    output = {
        "fixed_objective": args.fixed_objective,
        "active_constraints": [],
        "kernels": kernels,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
