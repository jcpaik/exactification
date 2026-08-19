#!/usr/bin/env python3
"""Create spectra.json and kernels.json from public input and blind discovery."""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


def primitive_vector(vector: sp.Matrix) -> list[int]:
    common = math.lcm(*[int(value.q) for value in vector]) if len(vector) else 1
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


def mp_fraction(value: str) -> mp.mpf:
    rational = Fraction(value)
    return mp.mpf(rational.numerator) / rational.denominator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--approx", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--spectra-output", required=True, type=Path)
    parser.add_argument("--kernels-output", required=True, type=Path)
    parser.add_argument("--decimal-precision", type=int, default=80)
    args = parser.parse_args()

    mp.mp.dps = args.decimal_precision
    model = json.loads(args.model.read_text())
    approx = json.loads(args.approx.read_text())
    config = json.loads(args.config.read_text())
    approximate_blocks = {
        block["name"]: mp.matrix([[mp.mpf(value) for value in row] for row in block["matrix"]])
        for block in approx["blocks"]
    }
    raw_kernels = config.get("kernels", {})

    spectra_blocks = {}
    kernel_blocks = {}
    for block in model["blocks"]:
        name = block["name"]
        size = block["size"]
        matrix = approximate_blocks[name]
        eigenvalues, eigenvectors = mp.eigsy(matrix)
        scale = max(mp.mpf(1), max(abs(value) for value in eigenvalues))
        basis = raw_kernels.get(name, [])
        nullity = len(basis)
        spectra_blocks[name] = {
            "eigenvalues": [mp.nstr(value, 50) for value in eigenvalues],
            "normalization_scale": mp.nstr(scale, 50),
            "normalized_absolute_eigenvalues": [mp.nstr(abs(value) / scale, 35) for value in eigenvalues],
            "candidate_nullity": nullity,
        }

        if not basis:
            kernel_blocks[name] = {
                "candidate_nullity": 0,
                "precision_runs_used": ["input/approximate_solution.json"],
                "status": "full_rank_no_kernel_recovery_required",
                "provenance": "mixed",
                "relation_matrix": None,
                "relation_exact_rank": None,
                "exact_kernel_basis_columns": [],
                "relation_height": None,
                "normalized_relation_residual_max": None,
                "subspace_projection_residual_frobenius": None,
                "face_equations_added": 0,
                "face_equation_rank": 0,
            }
            continue

        exact_columns = [sp.Matrix([sp.Rational(value) for value in vector]) for vector in basis]
        exact_basis = sp.Matrix.hstack(*exact_columns)
        relation_vectors = exact_basis.T.nullspace()
        relations = [primitive_vector(vector) for vector in relation_vectors]
        relation_matrix = sp.Matrix(relations)
        numerical_kernel = eigenvectors[:, :nullity]
        maximum_relation_residual = mp.mpf(0)
        for relation in relations:
            product = [
                sum(mp.mpf(relation[row]) * numerical_kernel[row, column] for row in range(size))
                for column in range(nullity)
            ]
            numerator = mp.sqrt(sum(value * value for value in product))
            denominator = mp.sqrt(sum(mp.mpf(value) ** 2 for value in relation)) * max(
                mp.mpf(1), mp.norm(numerical_kernel)
            )
            maximum_relation_residual = max(maximum_relation_residual, numerator / denominator)

        embedded = mp.matrix([[mp.mpf(int(exact_basis[i, j])) for j in range(nullity)] for i in range(size)])
        exact_q, _ = mp.qr(embedded)
        exact_q = exact_q[:, :nullity]
        projection_error = (mp.eye(size) - numerical_kernel * numerical_kernel.T) * exact_q
        projection_residual = mp.sqrt(
            sum(
                projection_error[i, j] ** 2
                for i in range(projection_error.rows)
                for j in range(projection_error.cols)
            )
        )
        face_rank = size * nullity - nullity * (nullity - 1) // 2
        kernel_blocks[name] = {
            "candidate_nullity": nullity,
            "precision_runs_used": ["input/approximate_solution.json"],
            "status": "recovered",
            "provenance": "mixed",
            "relation_matrix": relations,
            "relation_exact_rank": int(relation_matrix.rank()),
            "exact_kernel_basis_columns": basis,
            "relation_height": max((abs(value) for row in relations for value in row), default=0),
            "normalized_relation_residual_max": mp.nstr(maximum_relation_residual, 35),
            "subspace_projection_residual_frobenius": mp.nstr(projection_residual, 35),
            "face_equations_added": size * nullity,
            "face_equation_rank": face_rank,
        }

    residuals = {}
    equality_absolute_residuals = []
    for constraint in model["constraints"]:
        expression = constraint["expression"]
        value = mp_fraction(expression["constant"])
        for term in expression["terms"]:
            value += mp_fraction(term["coefficient"]) * approximate_blocks[term["block"]][
                term["row"], term["col"]
            ]
        residuals[constraint["name"]] = mp.nstr(value, 40)
        if constraint["sense"] == "eq":
            equality_absolute_residuals.append(abs(value))

    objective_expression = model["objective"]["expression"]
    objective = mp_fraction(objective_expression["constant"])
    for term in objective_expression["terms"]:
        objective += mp_fraction(term["coefficient"]) * approximate_blocks[term["block"]][
            term["row"], term["col"]
        ]

    precision_key = (
        "claimed_precision_bits" if "claimed_precision_bits" in approx else "claimed_precision_digits"
    )
    spectra = {
        "format": "exactification-spectra-v1",
        "precision_runs": [
            {
                "source": "input/approximate_solution.json",
                precision_key: approx[precision_key],
                "claimed_objective": approx["claimed_objective"],
                "recomputed_objective": mp.nstr(objective, 45),
                "maximum_absolute_equality_residual": mp.nstr(
                    max(equality_absolute_residuals, default=mp.mpf(0)), 40
                ),
                "affine_expression_values": residuals,
                "blocks": spectra_blocks,
            }
        ],
        "limitation": "The blind input supplied one normalized numerical run; exact certificate verification is the proof gate.",
    }
    kernels = {
        "format": "exactification-kernels-v1",
        "method": "basis-invariant numerical projector rational reconstruction, with row-relation recovery where required",
        "blocks": kernel_blocks,
    }
    args.spectra_output.write_text(json.dumps(spectra, indent=2) + "\n")
    args.kernels_output.write_text(json.dumps(kernels, indent=2) + "\n")


if __name__ == "__main__":
    main()
