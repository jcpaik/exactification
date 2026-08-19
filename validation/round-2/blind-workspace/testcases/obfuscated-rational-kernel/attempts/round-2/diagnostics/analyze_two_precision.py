#!/usr/bin/env python3
"""Validate a numerically recovered graph chart against two independent runs."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


def rat(value: str | int) -> sp.Rational:
    return sp.Rational(value)


def mp_rat(value: str | int) -> mp.mpf:
    q = Fraction(value)
    return mp.mpf(q.numerator) / q.denominator


def spell(value: sp.Rational) -> str:
    return str(value)


def opnorm(matrix: mp.matrix) -> mp.mpf:
    if not matrix.rows or not matrix.cols:
        return mp.mpf(0)
    _, singular, _ = mp.svd(matrix)
    return max(abs(singular[index]) for index in range(len(singular)))


def smallest_singular(matrix: mp.matrix) -> mp.mpf:
    _, singular, _ = mp.svd(matrix)
    return min(abs(singular[index]) for index in range(len(singular)))


def extract(matrix: mp.matrix, rows: list[int], columns: list[int]) -> mp.matrix:
    return mp.matrix([[matrix[row, column] for column in columns] for row in rows])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--p", required=True, type=Path)
    parser.add_argument("--two-p", required=True, type=Path)
    parser.add_argument("--relations-p", required=True, type=Path)
    parser.add_argument("--relations-two-p", required=True, type=Path)
    parser.add_argument("--spectra-output", required=True, type=Path)
    parser.add_argument("--kernels-output", required=True, type=Path)
    parser.add_argument("--decimal-precision", type=int, default=100)
    args = parser.parse_args()

    mp.mp.dps = args.decimal_precision
    model = json.loads(args.model.read_text())
    relation_documents = {
        "p": json.loads(args.relations_p.read_text()),
        "2p": json.loads(args.relations_two_p.read_text()),
    }
    if any(document.get("status") != "recovered" for document in relation_documents.values()):
        raise RuntimeError("both numerical relation recoveries must succeed")
    relation_p = sp.Matrix(relation_documents["p"]["relation_matrix"])
    relation_two_p = sp.Matrix(relation_documents["2p"]["relation_matrix"])
    if relation_p.rref()[0] != relation_two_p.rref()[0]:
        raise RuntimeError("the p and 2p relation row spaces differ")

    selected = relation_documents["2p"]
    block_name = selected["block"]
    nullity = int(selected["candidate_nullity"])
    relation = relation_two_p
    basis_columns = selected["kernel_basis_columns"]
    exact_basis = sp.Matrix.hstack(*[sp.Matrix(column) for column in basis_columns])
    if relation * exact_basis != sp.zeros(relation.rows, exact_basis.cols):
        raise RuntimeError("relation matrix does not annihilate exact kernel basis")
    if relation.rank() != relation.cols - nullity or exact_basis.rank() != nullity:
        raise RuntimeError("exact relation/kernel ranks are inconsistent")

    q_indices = list(selected["pivot_rows"])
    p_indices = [index for index in range(relation.cols) if index not in q_indices]
    q_minor = exact_basis.extract(q_indices, range(nullity))
    exact_graph = exact_basis * q_minor.inv()
    if exact_graph.extract(q_indices, range(nullity)) != sp.eye(nullity):
        raise RuntimeError("graph chart normalization failed")
    exact_graph_coordinates = exact_graph.extract(p_indices, range(nullity))

    approximate_documents = {
        "p": json.loads(args.p.read_text()),
        "2p": json.loads(args.two_p.read_text()),
    }
    sources = {"p": str(args.p), "2p": str(args.two_p)}
    model_sizes = {block["name"]: block["size"] for block in model["blocks"]}
    spectra_runs = []
    validations = []

    for label in ("p", "2p"):
        approximate = approximate_documents[label]
        approximate_blocks = {
            block["name"]: mp.matrix([[mp.mpf(value) for value in row] for row in block["matrix"]])
            for block in approximate["blocks"]
        }
        spectra_blocks = {}
        selected_matrix = None
        selected_kernel = None
        selected_positive = None
        selected_eigenvalues = None
        selected_scale = None
        for name, size in model_sizes.items():
            matrix = approximate_blocks[name]
            eigenvalues, eigenvectors = mp.eigsy(matrix)
            scale = max(mp.mpf(1), max(abs(value) for value in eigenvalues))
            normalized = [abs(value) / scale for value in eigenvalues]
            candidate_nullity = nullity if name == block_name else 0
            positive_first = normalized[candidate_nullity] if candidate_nullity < size else None
            zero_last = normalized[candidate_nullity - 1] if candidate_nullity else None
            gap = positive_first / zero_last if zero_last and positive_first else None
            spectra_blocks[name] = {
                "eigenvalues": [mp.nstr(value, 55) for value in eigenvalues],
                "normalization_scale": mp.nstr(scale, 55),
                "normalized_absolute_eigenvalues": [mp.nstr(value, 45) for value in normalized],
                "candidate_nullity": candidate_nullity,
                "largest_structural_zero_normalized": None if zero_last is None else mp.nstr(zero_last, 45),
                "smallest_positive_normalized": None if positive_first is None else mp.nstr(positive_first, 45),
                "nullity_boundary_gap_ratio": None if gap is None else mp.nstr(gap, 35),
            }
            if name == block_name:
                selected_matrix = matrix
                selected_kernel = eigenvectors[:, :nullity]
                selected_positive = eigenvectors[:, nullity:]
                selected_eigenvalues = eigenvalues
                selected_scale = scale

        expression_values = {}
        equality_residuals = []
        for constraint in model["constraints"]:
            expression = constraint["expression"]
            value = mp_rat(expression["constant"])
            for term in expression["terms"]:
                value += mp_rat(term["coefficient"]) * approximate_blocks[term["block"]][term["row"], term["col"]]
            expression_values[constraint["name"]] = mp.nstr(value, 50)
            if constraint["sense"] == "eq":
                equality_residuals.append(abs(value))

        objective_expression = model["objective"]["expression"]
        objective = mp_rat(objective_expression["constant"])
        for term in objective_expression["terms"]:
            objective += mp_rat(term["coefficient"]) * approximate_blocks[term["block"]][term["row"], term["col"]]
        precision_field = "claimed_precision_bits" if "claimed_precision_bits" in approximate else "claimed_precision_digits"
        spectra_runs.append({
            "label": label,
            "source": sources[label],
            precision_field: approximate[precision_field],
            "claimed_objective": approximate["claimed_objective"],
            "recomputed_objective": mp.nstr(objective, 55),
            "maximum_absolute_equality_residual": mp.nstr(max(equality_residuals, default=mp.mpf(0)), 45),
            "affine_expression_values": expression_values,
            "blocks": spectra_blocks,
        })

        assert selected_matrix is not None and selected_kernel is not None
        assert selected_positive is not None and selected_eigenvalues is not None and selected_scale is not None
        numerical_relation = mp.matrix([[mp.mpf(int(relation[i, j])) for j in range(relation.cols)] for i in range(relation.rows)])
        numerical_basis = mp.matrix([[mp.mpf(int(exact_basis[i, j])) for j in range(nullity)] for i in range(exact_basis.rows)])
        numerical_graph_exact = mp.matrix([
            [mp.mpf(int(exact_graph[i, j].p)) / int(exact_graph[i, j].q) for j in range(nullity)]
            for i in range(exact_graph.rows)
        ])
        exact_q, _ = mp.qr(numerical_basis)
        exact_q = exact_q[:, :nullity]
        cross = exact_q.T * selected_kernel
        sigma_min_cross = smallest_singular(cross)
        principal_sine = mp.sqrt(max(mp.mpf(0), 1 - sigma_min_cross * sigma_min_cross))

        relation_residual = opnorm(numerical_relation * selected_kernel) / (
            opnorm(numerical_relation) * max(mp.mpf(1), opnorm(selected_kernel))
        )
        block_kernel_residual = opnorm(selected_matrix * numerical_graph_exact) / (
            opnorm(selected_matrix) * max(mp.mpf(1), opnorm(numerical_graph_exact))
        )
        kernel_q_minor = extract(selected_kernel, q_indices, list(range(nullity)))
        numerical_graph = selected_kernel * (kernel_q_minor ** -1)
        graph_error = max(
            abs(numerical_graph[i, j] - numerical_graph_exact[i, j])
            for i in range(numerical_graph.rows)
            for j in range(numerical_graph.cols)
        )
        positive_minor = extract(selected_positive, p_indices, list(range(selected_positive.cols)))
        positive_sigma_min = smallest_singular(positive_minor)
        positive_condition = opnorm(positive_minor) / positive_sigma_min
        block_minor = extract(selected_matrix, p_indices, p_indices)
        block_sigma_min = smallest_singular(block_minor)
        block_condition = opnorm(block_minor) / block_sigma_min
        normalized_zeros = [abs(selected_eigenvalues[index]) / selected_scale for index in range(nullity)]
        validations.append({
            "label": label,
            "source": sources[label],
            "maximum_normalized_relation_residual_rowwise": relation_documents[label]["maximum_normalized_relation_residual"],
            "normalized_relation_residual_operator": mp.nstr(relation_residual, 45),
            "normalized_block_kernel_residual_operator": mp.nstr(block_kernel_residual, 45),
            "largest_principal_angle_sine": mp.nstr(principal_sine, 45),
            "maximum_graph_coordinate_absolute_error": mp.nstr(graph_error, 45),
            "largest_structural_zero_normalized": mp.nstr(max(normalized_zeros), 45),
            "smallest_positive_normalized": mp.nstr(abs(selected_eigenvalues[nullity]) / selected_scale, 45),
            "positive_space_coordinate_minor": {
                "indices": p_indices,
                "smallest_singular_value": mp.nstr(positive_sigma_min, 40),
                "condition_estimate_2": mp.nstr(positive_condition, 40),
            },
            "block_positive_minor": {
                "indices": p_indices,
                "smallest_singular_value": mp.nstr(block_sigma_min, 40),
                "condition_estimate_2": mp.nstr(block_condition, 40),
            },
        })

    def improvement(field: str) -> str:
        first = mp.mpf(validations[0][field])
        second = mp.mpf(validations[1][field])
        return "infinite" if second == 0 else mp.nstr(first / second, 30)

    spectra = {
        "format": "exactification-spectra-v1",
        "precision_runs": spectra_runs,
        "nullity_branch": {
            "block": block_name,
            "selected_nullity": nullity,
            "basis": "independent symmetric eigendecomposition of each public matrix",
            "decision": "three values at the printed noise floor followed by a stable positive cluster",
        },
        "limitation": "Both solvers used higher internal precision, but SDPA-GMP printed each matrix to 40 decimal digits; diagnostics are therefore bounded by the independent printed outputs.",
    }
    kernels = {
        "format": "exactification-kernels-v1",
        "method": "basis-invariant numerical graph-coordinate recovery",
        "blocks": {
            block_name: {
                "candidate_nullity": nullity,
                "precision_runs_used": [sources["p"], sources["2p"]],
                "status": "recovered",
                "recovery_method": "numerical_graph_chart",
                "provenance": "numerical_graph_chart",
                "independent_recoveries_have_equal_exact_row_space": True,
                "relation_matrix": [[int(relation[i, j]) for j in range(relation.cols)] for i in range(relation.rows)],
                "relation_exact_rank": int(relation.rank()),
                "relation_height": max(abs(int(value)) for value in relation),
                "exact_kernel_basis_columns": basis_columns,
                "exact_kernel_rank": int(exact_basis.rank()),
                "exact_relation_times_kernel_zero": True,
                "graph_chart": {
                    "kernel_coordinate_indices_Q": q_indices,
                    "positive_coordinate_indices_P": p_indices,
                    "selection_rule": "maximum-volume kernel-coordinate minor; complementary positive-space minor validated at both precisions",
                    "exact_graph_basis_columns": [[spell(exact_graph[i, j]) for i in range(exact_graph.rows)] for j in range(nullity)],
                    "exact_graph_coordinates_G_rows_P": [[spell(exact_graph_coordinates[i, j]) for j in range(nullity)] for i in range(exact_graph_coordinates.rows)],
                    "exact_Q_minor_is_identity": True,
                },
                "validation": validations,
                "residual_improvement_factors_p_over_2p": {
                    "maximum_rowwise_relation": improvement("maximum_normalized_relation_residual_rowwise"),
                    "relation": improvement("normalized_relation_residual_operator"),
                    "block_kernel": improvement("normalized_block_kernel_residual_operator"),
                    "principal_angle_sine": improvement("largest_principal_angle_sine"),
                    "graph_coordinate_error": improvement("maximum_graph_coordinate_absolute_error"),
                },
                "relation_height_ladder": relation_documents["2p"]["ladder"],
                "face_equations_added": exact_basis.rows * nullity,
                "face_equation_rank": exact_basis.rows * nullity - nullity * (nullity - 1) // 2,
            }
        },
    }
    args.spectra_output.write_text(json.dumps(spectra, indent=2) + "\n")
    args.kernels_output.write_text(json.dumps(kernels, indent=2) + "\n")


if __name__ == "__main__":
    main()
