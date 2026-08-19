#!/usr/bin/env python3
"""Exact affine rounding using modular sparse pivots and a FLINT square solve."""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

from flint import fmpq, fmpq_mat

sys.set_int_max_str_digits(0)


def frac(value) -> Fraction:
    if isinstance(value, Fraction):
        return value
    return Fraction(value)


def spell(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def modular_value(value: Fraction, prime: int) -> int:
    denominator = value.denominator % prime
    if denominator == 0:
        raise ZeroDivisionError(f"denominator divisible by modular prime {prime}")
    return (value.numerator % prime) * pow(denominator, prime - 2, prime) % prime


def select_pivots(rows: list[dict[int, Fraction]], prime: int) -> tuple[list[int], list[int]]:
    echelon: dict[int, dict[int, int]] = {}
    selected_rows: list[int] = []
    pivot_columns: list[int] = []
    for row_index, exact_row in enumerate(rows):
        row = {
            column: residue
            for column, value in exact_row.items()
            if (residue := modular_value(value, prime))
        }
        while row:
            pivot = min(row)
            prior = echelon.get(pivot)
            if prior is None:
                inverse = pow(row[pivot], prime - 2, prime)
                row = {
                    column: normalized
                    for column, value in row.items()
                    if (normalized := value * inverse % prime)
                }
                echelon[pivot] = row
                selected_rows.append(row_index)
                pivot_columns.append(pivot)
                break
            factor = row[pivot]
            for column, value in prior.items():
                updated = (row.get(column, 0) - factor * value) % prime
                if updated:
                    row[column] = updated
                else:
                    row.pop(column, None)
    return selected_rows, pivot_columns


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--approx", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--system-output", required=True, type=Path)
    parser.add_argument("--denominator-bits", required=True, type=int)
    args = parser.parse_args()

    model = json.loads(args.model.read_text())
    approx = json.loads(args.approx.read_text())
    config = json.loads(args.config.read_text())
    sizes = {block["name"]: block["size"] for block in model["blocks"]}
    coords = [
        (block["name"], i, j)
        for block in model["blocks"]
        for i in range(block["size"])
        for j in range(i, block["size"])
    ]
    coord_index = {coord: index for index, coord in enumerate(coords)}
    nvars = len(coords)
    equations: list[tuple[dict[int, Fraction], Fraction, dict]] = []

    def add_expression(expression: dict, target: Fraction, source: dict) -> None:
        row: dict[int, Fraction] = {}
        for term in expression["terms"]:
            column = coord_index[(term["block"], term["row"], term["col"])]
            row[column] = row.get(column, Fraction(0)) + frac(term["coefficient"])
            if row[column] == 0:
                del row[column]
        equations.append((row, target - frac(expression["constant"]), source))

    active = set(config.get("active_constraints", []))
    for constraint in model["constraints"]:
        if constraint["sense"] == "eq" or constraint["name"] in active:
            add_expression(
                constraint["expression"],
                Fraction(0),
                {
                    "kind": "original_equality"
                    if constraint["sense"] == "eq"
                    else "active_inequality",
                    "name": constraint["name"],
                },
            )

    fixed_objective = frac(config["fixed_objective"])
    add_expression(
        model["objective"]["expression"],
        fixed_objective,
        {"kind": "fixed_objective", "value": spell(fixed_objective)},
    )

    kernel_summary = {}
    for block_name, raw_basis in config.get("kernels", {}).items():
        size = sizes[block_name]
        basis = [[frac(value) for value in vector] for vector in raw_basis]
        before = len(equations)
        for vector_index, vector in enumerate(basis):
            if len(vector) != size:
                raise ValueError(f"wrong kernel vector length for {block_name}")
            for row_index in range(size):
                row: dict[int, Fraction] = {}
                for column_index, coefficient in enumerate(vector):
                    if coefficient == 0:
                        continue
                    i, j = sorted((row_index, column_index))
                    column = coord_index[(block_name, i, j)]
                    row[column] = row.get(column, Fraction(0)) + coefficient
                    if row[column] == 0:
                        del row[column]
                equations.append(
                    (
                        row,
                        Fraction(0),
                        {
                            "kind": "kernel_face",
                            "block": block_name,
                            "vector": vector_index,
                            "matrix_row": row_index,
                        },
                    )
                )
        kernel_summary[block_name] = {
            "kernel_dimension": len(basis),
            "equations_added": len(equations) - before,
            "equation_rank": size * len(basis) - len(basis) * (len(basis) - 1) // 2,
        }

    coefficient_rows = [row for row, _, _ in equations]
    primes = [1000000007, 1000000009]
    modular_results = []
    for prime in primes:
        selected, pivots = select_pivots(coefficient_rows, prime)
        modular_results.append((prime, selected, pivots))
        print(f"modular rank over F_{prime}: {len(pivots)}", flush=True)
    ranks = {len(pivots) for _, _, pivots in modular_results}
    if len(ranks) != 1:
        raise RuntimeError(f"modular ranks disagree: {sorted(ranks)}")
    prime, selected_rows, pivot_columns = modular_results[0]
    rank = len(pivot_columns)
    pivot_set = set(pivot_columns)
    free_columns = [column for column in range(nvars) if column not in pivot_set]

    approximate_blocks = {block["name"]: block["matrix"] for block in approx["blocks"]}
    approximate_coordinates = [
        Fraction(approximate_blocks[name][i][j]) for name, i, j in coords
    ]
    max_denominator = 1 << args.denominator_bits
    solution = [Fraction(0) for _ in range(nvars)]
    for column in free_columns:
        # A shared dyadic denominator prevents the least-common-denominator
        # explosion caused by independently chosen continued fractions across
        # more than a thousand free coordinates.
        scaled = approximate_coordinates[column] * max_denominator
        solution[column] = Fraction(round(scaled), max_denominator)

    print(f"assembling exact {rank}-by-{rank} FLINT subsystem", flush=True)
    flat_matrix = []
    flat_rhs = []
    for row_index in selected_rows:
        row, rhs, _ = equations[row_index]
        target = rhs
        for column, coefficient in row.items():
            if column not in pivot_set:
                target -= coefficient * solution[column]
        for column in pivot_columns:
            value = row.get(column, Fraction(0))
            flat_matrix.append(fmpq(value.numerator, value.denominator))
        flat_rhs.append(fmpq(target.numerator, target.denominator))
    square = fmpq_mat(rank, rank, flat_matrix)
    rhs_matrix = fmpq_mat(rank, 1, flat_rhs)
    print("solving exact FLINT subsystem", flush=True)
    pivot_solution = square.solve(rhs_matrix)
    for index, column in enumerate(pivot_columns):
        solution[column] = Fraction(str(pivot_solution[index, 0]))

    failed_rows = []
    for row_index, (row, rhs, source) in enumerate(equations):
        residual = sum((coefficient * solution[column] for column, coefficient in row.items()), Fraction(0)) - rhs
        if residual:
            failed_rows.append(
                {"row": row_index, "source": source, "residual": spell(residual)}
            )
            if len(failed_rows) >= 10:
                break
    if failed_rows:
        raise RuntimeError(f"exact equation verification failed: {failed_rows}")
    print("all enlarged affine equations verified exactly", flush=True)

    blocks = []
    for block in model["blocks"]:
        name = block["name"]
        size = block["size"]
        matrix = []
        for i in range(size):
            matrix_row = []
            for j in range(size):
                key = (name, i, j) if i <= j else (name, j, i)
                matrix_row.append(spell(solution[coord_index[key]]))
            matrix.append(matrix_row)
        blocks.append({"name": name, "matrix": matrix})
    candidate = {
        "format": "exact-block-sdp-certificate-v1",
        "claimed_objective": spell(fixed_objective),
        "blocks": blocks,
    }
    args.output.write_text(json.dumps(candidate, indent=2) + "\n")

    source_counts = {}
    for _, _, source in equations:
        source_counts[source["kind"]] = source_counts.get(source["kind"], 0) + 1
    system = {
        "format": "exactification-affine-system-v1",
        "backend": "two-prime-sparse-modular-pivots-plus-exact-flint-square-solve",
        "variable_count": nvars,
        "equation_count": len(equations),
        "exact_rank": rank,
        "free_variable_count": len(free_columns),
        "consistent": True,
        "all_equations_rechecked_exactly": True,
        "modular_ranks": {str(p): len(cols) for p, _, cols in modular_results},
        "selected_prime": prime,
        "denominator_bits": args.denominator_bits,
        "free_rounding": "nearest_shared_dyadic_denominator",
        "shared_free_denominator": str(max_denominator),
        "equation_sources": source_counts,
        "kernel_face_summary": kernel_summary,
        "pivot_variables": [list(coords[column]) for column in pivot_columns],
        "free_variables": [list(coords[column]) for column in free_columns],
    }
    args.system_output.write_text(json.dumps(system, indent=2) + "\n")


if __name__ == "__main__":
    main()
