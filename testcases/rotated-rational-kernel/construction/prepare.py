#!/usr/bin/env python3
"""Construct a blind singular SDP with an irrational numerical optimizer."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


CASE_ROOT = Path(__file__).resolve().parents[1]
INPUT = CASE_ROOT / "input"


def rational(value: sp.Rational) -> str:
    number = Fraction(int(value.p), int(value.q))
    return str(number.numerator) if number.denominator == 1 else f"{number.numerator}/{number.denominator}"


def term(row: int, column: int, coefficient: str) -> dict:
    return {"block": "X", "row": row, "col": column, "coefficient": coefficient}


def main() -> None:
    INPUT.mkdir(parents=True, exist_ok=True)

    skew = sp.Matrix(
        [
            [0, 1, 0, 1, 0, 0],
            [-1, 0, 2, 0, 1, 0],
            [0, -2, 0, 1, 0, 1],
            [-1, 0, -1, 0, 2, 0],
            [0, -1, 0, -2, 0, 1],
            [0, 0, -1, 0, -1, 0],
        ]
    )
    identity = sp.eye(6)
    orthogonal = (identity - skew) * (identity + skew).inv()
    if orthogonal.T * orthogonal != identity:
        raise AssertionError("Cayley transform is not exactly orthogonal")

    complement = orthogonal[:, :3]
    kernel = orthogonal[:, 3:]
    kernel_projector = kernel * kernel.T
    if kernel_projector * kernel_projector != kernel_projector:
        raise AssertionError("kernel projector is not exactly idempotent")

    face_terms = []
    for row in range(6):
        for column in range(row, 6):
            coefficient = kernel_projector[row, column]
            if row != column:
                coefficient *= 2
            if coefficient:
                face_terms.append(term(row, column, rational(coefficient)))

    model = {
        "format": "exact-block-sdp-model-v1",
        "blocks": [{"name": "X", "size": 6}],
        "constraints": [
            {
                "name": "unit_trace_face",
                "sense": "eq",
                "expression": {"constant": "0", "terms": face_terms},
            },
            {
                "name": "trace_seven",
                "sense": "eq",
                "expression": {
                    "constant": "-7",
                    "terms": [term(index, index, "1") for index in range(6)],
                },
            },
        ],
        "objective": {
            "sense": "minimize",
            "expression": {"constant": "0", "terms": []},
        },
    }
    (INPUT / "model.json").write_text(json.dumps(model, indent=2) + "\n", encoding="ascii")

    mp.mp.dps = 110
    s2, s3, s5, s7 = (mp.sqrt(value) for value in (2, 3, 5, 7))
    interior = mp.matrix(
        [
            [1 + s2 / 10, s3 / 20, -s5 / 30],
            [s3 / 20, 2 - s2 / 10, s7 / 40],
            [-s5 / 30, s7 / 40, 4],
        ]
    )
    numeric_complement = mp.matrix(
        [[mp.mpf(int(value.p)) / int(value.q) for value in row] for row in complement.tolist()]
    )
    numeric_matrix = numeric_complement * interior * numeric_complement.T
    approximate = {
        "format": "approximate-block-sdp-solution-v1",
        "numeric_type": "decimal",
        "claimed_precision_digits": 100,
        "claimed_objective": "0",
        "blocks": [
            {
                "name": "X",
                "matrix": [
                    [mp.nstr(numeric_matrix[row, column], 102) for column in range(6)]
                    for row in range(6)
                ],
            }
        ],
    }
    (INPUT / "approximate_solution.json").write_text(
        json.dumps(approximate, indent=2) + "\n", encoding="ascii"
    )

    manifest = {
        "format": "exactification-testcase-v1",
        "id": "rotated-rational-kernel",
        "title": "Held-out rational face with an irrational relative-interior point",
        "field": "Q",
        "model": "model.json",
        "approximate_solution": "approximate_solution.json",
        "fixed_objective": "0",
        "solution_side": "affine_psd_blocks",
        "blind_input_policy": {"exact_certificate_included": False},
        "features": [
            "rank_deficient",
            "kernel_dimension_3",
            "rational_kernel_subspace",
            "irrational_numerical_entries",
            "nonunique_relative_interior",
        ],
    }
    (INPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()
