#!/usr/bin/env python3
"""Recover exact row relations for a numerical kernel subspace.

This is the row-relation form of the DLM kernel recovery step.  It never
rationalizes individual eigenvectors.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


def primitive(entries: list[int]) -> list[int]:
    divisor = math.gcd(*entries)
    if divisor:
        entries = [value // abs(divisor) for value in entries]
    for value in entries:
        if value:
            if value < 0:
                entries = [-entry for entry in entries]
            break
    return entries


def primitive_vector(vector: sp.Matrix) -> list[int]:
    common = math.lcm(*[int(value.q) for value in vector])
    return primitive([int(value * common) for value in vector])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approx", required=True, type=Path)
    parser.add_argument("--block", required=True)
    parser.add_argument("--nullity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decimal-precision", type=int, default=90)
    parser.add_argument("--maximum-denominator-power", type=int, default=18)
    parser.add_argument("--accept-residual", default="1e-30")
    args = parser.parse_args()

    mp.mp.dps = args.decimal_precision
    approx = json.loads(args.approx.read_text())
    raw = next(block["matrix"] for block in approx["blocks"] if block["name"] == args.block)
    matrix = mp.matrix([[mp.mpf(value) for value in row] for row in raw])
    eigenvalues, eigenvectors = mp.eigsy(matrix)
    size = len(raw)
    kernel = eigenvectors[:, : args.nullity]

    pivot_rows = max(
        itertools.combinations(range(size), args.nullity),
        key=lambda rows: abs(
            mp.det(mp.matrix([[kernel[row, column] for column in range(args.nullity)] for row in rows]))
        ),
    )
    pivot_matrix = mp.matrix(
        [[kernel[row, column] for column in range(args.nullity)] for row in pivot_rows]
    )
    coefficients = {
        row: mp.lu_solve(
            pivot_matrix.T,
            mp.matrix([[kernel[row, column]] for column in range(args.nullity)]),
        )
        for row in range(size)
        if row not in pivot_rows
    }

    selected = None
    ladder = []
    threshold = mp.mpf(args.accept_residual)
    for power in range(1, args.maximum_denominator_power + 1):
        bound = 10**power
        relation_rows = []
        maximum_residual = mp.mpf(0)
        for row, numerical_coefficients in coefficients.items():
            rationals = [
                Fraction(mp.nstr(numerical_coefficients[index], args.decimal_precision - 10)).limit_denominator(bound)
                for index in range(args.nullity)
            ]
            common = math.lcm(*[value.denominator for value in rationals])
            relation = [0 for _ in range(size)]
            relation[row] = common
            for index, pivot_row in enumerate(pivot_rows):
                value = rationals[index]
                relation[pivot_row] -= value.numerator * (common // value.denominator)
            relation = primitive(relation)
            relation_rows.append(relation)

            product = [
                sum(mp.mpf(relation[index]) * kernel[index, column] for index in range(size))
                for column in range(args.nullity)
            ]
            numerator = mp.sqrt(sum(value * value for value in product))
            denominator = mp.sqrt(sum(mp.mpf(value) ** 2 for value in relation))
            maximum_residual = max(maximum_residual, numerator / denominator)
        height = max(abs(value) for relation in relation_rows for value in relation)
        ladder.append(
            {
                "denominator_bound": str(bound),
                "maximum_normalized_relation_residual": mp.nstr(maximum_residual, 30),
                "relation_height": height,
            }
        )
        if maximum_residual < threshold:
            selected = (bound, relation_rows, maximum_residual, height)
            break

    if selected is None:
        output = {
            "format": "exactification-row-relation-recovery-v1",
            "block": args.block,
            "candidate_nullity": args.nullity,
            "status": "no_relation_basis_within_ladder",
            "pivot_rows": list(pivot_rows),
            "ladder": ladder,
        }
    else:
        bound, relation_rows, maximum_residual, height = selected
        relation_matrix = sp.Matrix(relation_rows)
        basis = [primitive_vector(vector) for vector in relation_matrix.nullspace()]
        output = {
            "format": "exactification-row-relation-recovery-v1",
            "block": args.block,
            "candidate_nullity": args.nullity,
            "status": "recovered",
            "pivot_rows": list(pivot_rows),
            "denominator_bound": str(bound),
            "relation_matrix": relation_rows,
            "relation_exact_rank": int(relation_matrix.rank()),
            "relation_height": height,
            "maximum_normalized_relation_residual": mp.nstr(maximum_residual, 30),
            "kernel_basis_columns": basis,
            "ladder": ladder,
        }
    args.output.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
