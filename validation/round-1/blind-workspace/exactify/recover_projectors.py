#!/usr/bin/env python3
"""Recover basis-invariant rational kernel projectors from numerical blocks."""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


def primitive_integer_vector(vector: sp.Matrix) -> list[int]:
    denominators = [int(value.q) for value in vector]
    common = math.lcm(*denominators) if denominators else 1
    entries = [int(value * common) for value in vector]
    divisor = math.gcd(*entries) if entries else 1
    if divisor:
        entries = [value // abs(divisor) for value in entries]
    for value in entries:
        if value:
            if value < 0:
                entries = [-entry for entry in entries]
            break
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approx", required=True, type=Path)
    parser.add_argument("--nullities", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decimal-precision", type=int, default=90)
    parser.add_argument("--maximum-denominator-power", type=int, default=18)
    args = parser.parse_args()

    mp.mp.dps = args.decimal_precision
    approx = json.loads(args.approx.read_text())
    nullities = json.loads(args.nullities.read_text())["nullities"]
    blocks = {block["name"]: block["matrix"] for block in approx["blocks"]}
    result: dict = {
        "format": "exactification-kernel-projector-recovery-v1",
        "source": str(args.approx),
        "working_decimal_precision": args.decimal_precision,
        "method": "basis_invariant_numerical_projector_then_exact_rational_reconstruction",
        "blocks": {},
    }

    for name, nullity in nullities.items():
        raw_matrix = blocks[name]
        size = len(raw_matrix)
        numerical_matrix = mp.matrix([[mp.mpf(value) for value in row] for row in raw_matrix])
        eigenvalues, eigenvectors = mp.eigsy(numerical_matrix)
        scale = max(mp.mpf(1), max(abs(value) for value in eigenvalues))
        normalized = [abs(value) / scale for value in eigenvalues]
        entry: dict = {
            "size": size,
            "candidate_nullity": nullity,
            "normalized_absolute_eigenvalues": [mp.nstr(value, 30) for value in normalized],
        }
        if nullity == 0:
            entry.update({"status": "full_rank", "kernel_basis_columns": [], "relation_matrix": []})
            result["blocks"][name] = entry
            continue
        if nullity == size:
            exact_projector = sp.eye(size)
            denominator_bound = 1
            max_error = max(
                abs((mp.mpf(1) if i == j else mp.mpf(0)) - (mp.mpf(1) if i == j else mp.mpf(0)))
                for i in range(size)
                for j in range(size)
            )
        else:
            numerical_kernel = eigenvectors[:, :nullity]
            numerical_projector = numerical_kernel * numerical_kernel.T
            exact_projector = None
            denominator_bound = None
            max_error = None
            for power in range(1, args.maximum_denominator_power + 1):
                bound = 10**power
                rows = []
                for i in range(size):
                    row = []
                    for j in range(size):
                        value = (numerical_projector[i, j] + numerical_projector[j, i]) / 2
                        rational = Fraction(mp.nstr(value, args.decimal_precision - 10)).limit_denominator(bound)
                        row.append(sp.Rational(rational.numerator, rational.denominator))
                    rows.append(row)
                candidate = sp.Matrix(rows)
                if candidate * candidate == candidate and candidate.rank() == nullity:
                    exact_projector = candidate
                    denominator_bound = bound
                    max_error = max(
                        abs(
                            numerical_projector[i, j]
                            - mp.mpf(int(candidate[i, j].p)) / mp.mpf(int(candidate[i, j].q))
                        )
                        for i in range(size)
                        for j in range(size)
                    )
                    break
            if exact_projector is None:
                entry.update({"status": "no_exact_projector_within_ladder"})
                result["blocks"][name] = entry
                continue

        kernel_basis = [primitive_integer_vector(vector) for vector in exact_projector.columnspace()]
        relation_basis = [primitive_integer_vector(vector) for vector in exact_projector.nullspace()]
        entry.update(
            {
                "status": "recovered",
                "denominator_bound": str(denominator_bound),
                "maximum_projector_entry_residual": mp.nstr(max_error, 30),
                "exact_projector_rank": int(exact_projector.rank()),
                "exact_projector": [
                    [str(exact_projector[i, j]) for j in range(size)] for i in range(size)
                ],
                "kernel_basis_columns": kernel_basis,
                "relation_matrix": relation_basis,
                "relation_exact_rank": len(relation_basis),
                "relation_height": max(
                    (abs(value) for row in relation_basis for value in row), default=0
                ),
            }
        )
        result["blocks"][name] = entry

    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
