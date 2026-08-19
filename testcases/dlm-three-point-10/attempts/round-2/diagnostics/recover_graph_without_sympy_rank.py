#!/usr/bin/env python3
"""Recover a graph chart while certifying rank from its explicit pivot form."""

from __future__ import annotations

import argparse
import itertools
import json
import math
from fractions import Fraction
from pathlib import Path

import mpmath as mp


def primitive(values: list[int]) -> list[int]:
    divisor = math.gcd(*values)
    if divisor:
        values = [value // abs(divisor) for value in values]
    for value in values:
        if value:
            return [-entry for entry in values] if value < 0 else values
    return values


def spell(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approx", required=True, type=Path)
    parser.add_argument("--block", required=True)
    parser.add_argument("--nullity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decimal-precision", required=True, type=int)
    parser.add_argument("--maximum-denominator-power", type=int, default=8)
    parser.add_argument("--accept-residual", default="1e-18")
    args = parser.parse_args()
    mp.mp.dps = args.decimal_precision

    approximate = json.loads(args.approx.read_text())
    raw = next(block["matrix"] for block in approximate["blocks"] if block["name"] == args.block)
    matrix = mp.matrix([[mp.mpf(value) for value in row] for row in raw])
    _, vectors = mp.eigsy(matrix)
    size = len(raw)
    kernel = vectors[:, : args.nullity]
    q_indices = max(
        itertools.combinations(range(size), args.nullity),
        key=lambda rows: abs(mp.det(mp.matrix([[kernel[row, column] for column in range(args.nullity)] for row in rows]))),
    )
    q_minor = mp.matrix([[kernel[row, column] for column in range(args.nullity)] for row in q_indices])
    p_indices = [row for row in range(size) if row not in q_indices]
    numerical_coefficients = {
        row: mp.lu_solve(q_minor.T, mp.matrix([[kernel[row, column]] for column in range(args.nullity)]))
        for row in p_indices
    }

    selected = None
    ladder = []
    threshold = mp.mpf(args.accept_residual)
    for power in range(1, args.maximum_denominator_power + 1):
        bound = 10**power
        graph_rows: dict[int, list[Fraction]] = {}
        relation_rows: list[list[int]] = []
        maximum_residual = mp.mpf(0)
        for row in p_indices:
            coefficients = [
                Fraction(mp.nstr(numerical_coefficients[row][index], args.decimal_precision - 10)).limit_denominator(bound)
                for index in range(args.nullity)
            ]
            graph_rows[row] = coefficients
            common = math.lcm(*[coefficient.denominator for coefficient in coefficients])
            relation = [0] * size
            relation[row] = common
            for index, q_row in enumerate(q_indices):
                coefficient = coefficients[index]
                relation[q_row] -= coefficient.numerator * (common // coefficient.denominator)
            relation = primitive(relation)
            relation_rows.append(relation)
            product = [sum(mp.mpf(relation[index]) * kernel[index, column] for index in range(size)) for column in range(args.nullity)]
            numerator = mp.sqrt(sum(value * value for value in product))
            denominator = mp.sqrt(sum(mp.mpf(value) ** 2 for value in relation))
            maximum_residual = max(maximum_residual, numerator / denominator)
        height = max(abs(value) for relation in relation_rows for value in relation)
        ladder.append({
            "denominator_bound": str(bound),
            "maximum_normalized_relation_residual": mp.nstr(maximum_residual, 35),
            "relation_height": height,
        })
        if maximum_residual < threshold:
            selected = (bound, graph_rows, relation_rows, maximum_residual, height)
            break

    if selected is None:
        output = {
            "format": "exactification-row-relation-recovery-v1",
            "block": args.block,
            "candidate_nullity": args.nullity,
            "status": "no_relation_basis_within_ladder",
            "pivot_rows": list(q_indices),
            "ladder": ladder,
        }
    else:
        bound, graph_rows, relation_rows, maximum_residual, height = selected
        basis_columns: list[list[str]] = []
        for column in range(args.nullity):
            vector = [Fraction(0) for _ in range(size)]
            vector[q_indices[column]] = Fraction(1)
            for row in p_indices:
                vector[row] = graph_rows[row][column]
            basis_columns.append([spell(value) for value in vector])
        # Each relation row has a distinct non-Q pivot coordinate, so these
        # size-k rows are exactly independent without a dense row reduction.
        for relation, row in zip(relation_rows, p_indices):
            if relation[row] == 0 or any(relation[other] != 0 for other in p_indices if other != row):
                raise RuntimeError("relation matrix lost explicit graph-pivot form")
        # Check the relation/basis product exactly using Fraction arithmetic.
        for relation in relation_rows:
            for column in range(args.nullity):
                if sum((Fraction(relation[index]) * Fraction(basis_columns[column][index]) for index in range(size)), Fraction(0)):
                    raise RuntimeError("exact relation times graph basis is nonzero")
        output = {
            "format": "exactification-row-relation-recovery-v1",
            "block": args.block,
            "candidate_nullity": args.nullity,
            "status": "recovered",
            "method": "numerical_graph_chart_explicit_pivot_rank",
            "pivot_rows": list(q_indices),
            "denominator_bound": str(bound),
            "relation_matrix": relation_rows,
            "relation_exact_rank": size - args.nullity,
            "rank_certificate": "distinct non-Q pivot coordinate in every relation row",
            "relation_height": height,
            "maximum_normalized_relation_residual": mp.nstr(maximum_residual, 35),
            "kernel_basis_columns": basis_columns,
            "exact_relation_times_kernel_zero": True,
            "ladder": ladder,
        }
    args.output.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
