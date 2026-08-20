#!/usr/bin/env python3
"""Round a numerical block SDP inside an exact, kernel-reduced affine face.

The kernel bases and active inequalities are discovery inputs.  This program
never reads a certificate or oracle.  Its output still has to pass the
independent verifier.
"""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path

import sympy as sp


def frac(value: str | int | Fraction | sp.Rational) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, sp.Rational):
        return Fraction(int(value.p), int(value.q))
    return Fraction(value)


def spell(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


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

    block_sizes = {block["name"]: block["size"] for block in model["blocks"]}
    coords = [
        (block["name"], i, j)
        for block in model["blocks"]
        for i in range(block["size"])
        for j in range(i, block["size"])
    ]
    coord_index = {coord: index for index, coord in enumerate(coords)}
    nvars = len(coords)
    equations: list[tuple[list[Fraction], Fraction, dict]] = []

    def add_expression(expression: dict, rhs_value: Fraction, source: dict) -> None:
        row = [Fraction(0) for _ in range(nvars)]
        for term in expression["terms"]:
            key = (term["block"], term["row"], term["col"])
            row[coord_index[key]] += frac(term["coefficient"])
        # constant + linear = rhs_value
        rhs = rhs_value - frac(expression["constant"])
        equations.append((row, rhs, source))

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

    kernel_summary: dict[str, dict] = {}
    for block_name, raw_basis in config.get("kernels", {}).items():
        size = block_sizes[block_name]
        basis = [[frac(entry) for entry in vector] for vector in raw_basis]
        if any(len(vector) != size for vector in basis):
            raise ValueError(f"wrong kernel vector length for {block_name}")
        before = len(equations)
        face_rows: list[list[Fraction]] = []
        for vector_index, vector in enumerate(basis):
            for row_index in range(size):
                row = [Fraction(0) for _ in range(nvars)]
                for column_index, coefficient in enumerate(vector):
                    i, j = sorted((row_index, column_index))
                    row[coord_index[(block_name, i, j)]] += coefficient
                face_rows.append(row)
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
        # For k independent kernel columns, X V = 0 cuts out the symmetric
        # matrices supported on an (n-k)-dimensional complement.  Its exact
        # codimension is nk-k(k-1)/2.  Computing this rank on a global
        # nvars-wide dense matrix is prohibitively wasteful for large models.
        face_rank = size * len(basis) - len(basis) * (len(basis) - 1) // 2
        kernel_summary[block_name] = {
            "kernel_dimension": len(basis),
            "equations_added": len(equations) - before,
            "equation_rank": face_rank,
        }

    # Clear denominators independently in each row.  SymPy then sends the
    # integer matrix through fraction-free DomainMatrix/FLINT reduction.
    integer_rows = []
    for row, rhs, _ in equations:
        values = row + [rhs]
        common = math.lcm(*[value.denominator for value in values])
        integer_rows.append(
            [sp.Integer(value.numerator * (common // value.denominator)) for value in values]
        )
    augmented = sp.Matrix(integer_rows)
    print(
        f"reducing exact integer system: {augmented.rows} rows x {augmented.cols - 1} variables",
        flush=True,
    )
    reduced, pivots = augmented.rref()
    print(f"exact reduction complete: rank {len(pivots)}", flush=True)
    if nvars in pivots:
        raise RuntimeError("enlarged exact affine system is inconsistent")
    pivot_columns = list(pivots)
    free_columns = [index for index in range(nvars) if index not in pivot_columns]

    approx_matrices = {block["name"]: block["matrix"] for block in approx["blocks"]}
    approximate_coordinates = [
        Fraction(approx_matrices[name][i][j]) for name, i, j in coords
    ]
    max_denominator = 1 << args.denominator_bits
    solution = [Fraction(0) for _ in range(nvars)]
    for index in free_columns:
        solution[index] = approximate_coordinates[index].limit_denominator(max_denominator)
    for row_index, pivot_column in enumerate(pivot_columns):
        value = frac(reduced[row_index, nvars])
        for free_column in free_columns:
            value -= frac(reduced[row_index, free_column]) * solution[free_column]
        solution[pivot_column] = value

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

    sources_by_kind: dict[str, int] = {}
    for _, _, source in equations:
        sources_by_kind[source["kind"]] = sources_by_kind.get(source["kind"], 0) + 1
    system = {
        "format": "exactification-affine-system-v1",
        "variable_count": nvars,
        "equation_count": len(equations),
        "exact_rank": len(pivot_columns),
        "free_variable_count": len(free_columns),
        "consistent": True,
        "denominator_bits": args.denominator_bits,
        "maximum_free_denominator": str(max_denominator),
        "equation_sources": sources_by_kind,
        "kernel_face_summary": kernel_summary,
        "pivot_variables": [list(coords[index]) for index in pivot_columns],
        "free_variables": [list(coords[index]) for index in free_columns],
    }
    args.system_output.write_text(json.dumps(system, indent=2) + "\n")


if __name__ == "__main__":
    main()
