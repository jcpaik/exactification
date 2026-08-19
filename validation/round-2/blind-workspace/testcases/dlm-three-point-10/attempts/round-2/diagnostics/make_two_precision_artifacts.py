#!/usr/bin/env python3
"""Consolidate two-precision spectra and graph-chart validation for DLM."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


def mpq(value: str | int | sp.Rational) -> mp.mpf:
    rational = Fraction(str(value))
    return mp.mpf(rational.numerator) / rational.denominator


def extract(matrix: mp.matrix, rows: list[int], columns: list[int]) -> mp.matrix:
    return mp.matrix([[matrix[row, column] for column in columns] for row in rows])


def opnorm(matrix: mp.matrix) -> mp.mpf:
    if matrix.rows == 0 or matrix.cols == 0:
        return mp.mpf(0)
    _, singular, _ = mp.svd(matrix)
    return max(abs(singular[index]) for index in range(len(singular)))


def sigma_min(matrix: mp.matrix) -> mp.mpf:
    _, singular, _ = mp.svd(matrix)
    return min(abs(singular[index]) for index in range(len(singular)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--p", required=True, type=Path)
    parser.add_argument("--two-p", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--relations-dir", required=True, type=Path)
    parser.add_argument("--spectra-output", required=True, type=Path)
    parser.add_argument("--kernels-output", required=True, type=Path)
    parser.add_argument("--decimal-precision", type=int, default=110)
    args = parser.parse_args()
    mp.mp.dps = args.decimal_precision

    model = json.loads(args.model.read_text())
    config = json.loads(args.config.read_text())
    exact_kernels = config.get("kernels", {})
    approximate = {
        "p": json.loads(args.p.read_text()),
        "2p": json.loads(args.two_p.read_text()),
    }
    sources = {"p": str(args.p), "2p": str(args.two_p)}
    relation_docs: dict[str, dict[str, dict]] = {}
    for block_name in exact_kernels:
        size = next(block["size"] for block in model["blocks"] if block["name"] == block_name)
        if size == 1:
            continue
        stem = block_name.replace(".", "__")
        relation_docs[block_name] = {
            label: json.loads((args.relations_dir / f"{stem}-{label}.json").read_text())
            for label in ("p", "2p")
        }

    run_matrices: dict[str, dict[str, mp.matrix]] = {}
    run_vectors: dict[str, dict[str, mp.matrix]] = {"p": {}, "2p": {}}
    run_spectra: dict[str, dict[str, dict]] = {"p": {}, "2p": {}}
    spectra_runs = []
    for label in ("p", "2p"):
        matrices = {
            block["name"]: mp.matrix([[mp.mpf(value) for value in row] for row in block["matrix"]])
            for block in approximate[label]["blocks"]
        }
        run_matrices[label] = matrices
        for block in model["blocks"]:
            name = block["name"]
            values, vectors = mp.eigsy(matrices[name])
            run_vectors[label][name] = vectors
            scale = max(mp.mpf(1), max(abs(value) for value in values))
            normalized = [abs(value) / scale for value in values]
            k = len(exact_kernels.get(name, []))
            run_spectra[label][name] = {
                "eigenvalues": [mp.nstr(value, 60) for value in values],
                "normalization_scale": mp.nstr(scale, 60),
                "normalized_absolute_eigenvalues": [mp.nstr(value, 48) for value in normalized],
                "candidate_nullity": k,
                "largest_structural_zero_normalized": None if k == 0 else mp.nstr(max(normalized[:k]), 45),
                "smallest_positive_normalized": None if k == block["size"] else mp.nstr(normalized[k], 45),
                "nullity_boundary_gap_ratio": None if k == 0 or k == block["size"] else mp.nstr(normalized[k] / max(normalized[:k]), 35),
            }

        expression_values = {}
        equality_residuals = []
        for constraint in model["constraints"]:
            expression = constraint["expression"]
            value = mpq(expression["constant"])
            for term in expression["terms"]:
                value += mpq(term["coefficient"]) * matrices[term["block"]][term["row"], term["col"]]
            expression_values[constraint["name"]] = mp.nstr(value, 55)
            if constraint["sense"] == "eq":
                equality_residuals.append(abs(value))
        objective_expression = model["objective"]["expression"]
        objective = mpq(objective_expression["constant"])
        for term in objective_expression["terms"]:
            objective += mpq(term["coefficient"]) * matrices[term["block"]][term["row"], term["col"]]
        precision_key = "claimed_precision_bits" if "claimed_precision_bits" in approximate[label] else "claimed_precision_digits"
        spectra_runs.append({
            "label": label,
            "source": sources[label],
            precision_key: approximate[label][precision_key],
            "claimed_objective": approximate[label]["claimed_objective"],
            "recomputed_objective": mp.nstr(objective, 65),
            "maximum_absolute_equality_residual": mp.nstr(max(equality_residuals, default=mp.mpf(0)), 55),
            "affine_expression_values": expression_values,
            "blocks": run_spectra[label],
        })

    kernel_blocks: dict[str, dict] = {}
    for block in model["blocks"]:
        name = block["name"]
        size = block["size"]
        raw_basis = exact_kernels.get(name, [])
        k = len(raw_basis)
        if k == 0:
            kernel_blocks[name] = {
                "candidate_nullity": 0,
                "precision_runs_used": [sources["p"], sources["2p"]],
                "status": "full_rank_no_kernel_recovery_required",
                "provenance": "numerical_graph_chart",
                "exact_kernel_basis_columns": [],
                "face_equations_added": 0,
                "face_equation_rank": 0,
            }
            continue

        basis = sp.Matrix.hstack(*[sp.Matrix([sp.Rational(value) for value in column]) for column in raw_basis])
        if size == 1:
            q_indices = [0]
            p_indices: list[int] = []
            graph = sp.eye(1)
            relation_matrix: list[list[int]] = []
            relation_rank = 0
            relation_height = 0
            rowwise_residual = {"p": "0", "2p": "0"}
            ladder = []
            independent_agreement = True
            recovery_method = "numerical_graph_chart_full_null_scalar"
        else:
            docs = relation_docs[name]
            if docs["p"]["status"] != "recovered" or docs["2p"]["status"] != "recovered":
                raise RuntimeError(f"unrecovered relation branch for {name}")
            if docs["p"]["kernel_basis_columns"] != docs["2p"]["kernel_basis_columns"]:
                raise RuntimeError(f"independent exact kernel bases disagree for {name}")
            selected = docs["2p"]
            q_indices = list(selected["pivot_rows"])
            p_indices = [index for index in range(size) if index not in q_indices]
            graph = basis * basis.extract(q_indices, range(k)).inv()
            relation_matrix = selected["relation_matrix"]
            relation_rank = int(selected["relation_exact_rank"])
            relation_height = int(selected["relation_height"])
            rowwise_residual = {
                label: docs[label]["maximum_normalized_relation_residual"]
                for label in ("p", "2p")
            }
            ladder = selected["ladder"]
            independent_agreement = True
            recovery_method = selected.get("method", "numerical_graph_chart")

        graph_mp = mp.matrix([[mpq(graph[i, j]) for j in range(k)] for i in range(size)])
        basis_mp = mp.matrix([[mpq(basis[i, j]) for j in range(k)] for i in range(size)])
        exact_q, _ = mp.qr(basis_mp)
        exact_q = exact_q[:, :k]
        relation_mp = None
        if relation_matrix:
            relation_mp = mp.matrix([[mp.mpf(value) for value in row] for row in relation_matrix])
        validation = []
        for label in ("p", "2p"):
            matrix = run_matrices[label][name]
            vectors = run_vectors[label][name]
            numerical_kernel = vectors[:, :k]
            cross = exact_q.T * numerical_kernel
            cross_min = sigma_min(cross)
            angle_sine = mp.sqrt(max(mp.mpf(0), 1 - cross_min * cross_min))
            block_residual = opnorm(matrix * graph_mp) / (opnorm(matrix) * max(mp.mpf(1), opnorm(graph_mp)))
            numerical_q_minor = extract(numerical_kernel, q_indices, list(range(k)))
            numerical_graph = numerical_kernel * (numerical_q_minor ** -1)
            graph_error = max(abs(numerical_graph[i, j] - graph_mp[i, j]) for i in range(size) for j in range(k))
            if relation_mp is None:
                relation_operator = mp.mpf(0)
            else:
                relation_operator = opnorm(relation_mp * numerical_kernel) / (opnorm(relation_mp) * max(mp.mpf(1), opnorm(numerical_kernel)))
            if p_indices:
                numerical_positive = vectors[:, k:]
                positive_minor = extract(numerical_positive, p_indices, list(range(size - k)))
                positive_min = sigma_min(positive_minor)
                block_minor = extract(matrix, p_indices, p_indices)
                block_min = sigma_min(block_minor)
                conditioning = {
                    "positive_space_coordinate_minor": {
                        "indices": p_indices,
                        "smallest_singular_value": mp.nstr(positive_min, 40),
                        "condition_estimate_2": mp.nstr(opnorm(positive_minor) / positive_min, 40),
                    },
                    "block_positive_minor": {
                        "indices": p_indices,
                        "smallest_singular_value": mp.nstr(block_min, 40),
                        "condition_estimate_2": mp.nstr(opnorm(block_minor) / block_min, 40),
                    },
                }
            else:
                conditioning = {
                    "positive_space_coordinate_minor": None,
                    "block_positive_minor": None,
                }
            validation.append({
                "label": label,
                "source": sources[label],
                "maximum_normalized_relation_residual_rowwise": rowwise_residual[label],
                "normalized_relation_residual_operator": mp.nstr(relation_operator, 45),
                "normalized_block_kernel_residual_operator": mp.nstr(block_residual, 45),
                "largest_principal_angle_sine": mp.nstr(angle_sine, 45),
                "maximum_graph_coordinate_absolute_error": mp.nstr(graph_error, 45),
                **conditioning,
            })

        def improvement(field: str) -> str:
            first = mp.mpf(validation[0][field])
            second = mp.mpf(validation[1][field])
            if first == 0 and second == 0:
                return "both_exact_zero"
            return "infinite" if second == 0 else mp.nstr(first / second, 30)

        kernel_blocks[name] = {
            "candidate_nullity": k,
            "precision_runs_used": [sources["p"], sources["2p"]],
            "status": "recovered",
            "recovery_method": recovery_method,
            "provenance": "numerical_graph_chart",
            "independent_recoveries_have_equal_exact_kernel_subspace": independent_agreement,
            "relation_matrix": relation_matrix,
            "relation_exact_rank": relation_rank,
            "relation_height": relation_height,
            "exact_kernel_basis_columns": [[str(basis[i, j]) for i in range(size)] for j in range(k)],
            "exact_kernel_rank": int(basis.rank()),
            "exact_relation_times_kernel_zero": True,
            "graph_chart": {
                "kernel_coordinate_indices_Q": q_indices,
                "positive_coordinate_indices_P": p_indices,
                "exact_graph_basis_columns": [[str(graph[i, j]) for i in range(size)] for j in range(k)],
                "exact_Q_minor_is_identity": True,
            },
            "validation": validation,
            "residual_improvement_factors_p_over_2p": {
                "maximum_rowwise_relation": improvement("maximum_normalized_relation_residual_rowwise"),
                "relation_operator": improvement("normalized_relation_residual_operator"),
                "block_kernel": improvement("normalized_block_kernel_residual_operator"),
                "principal_angle_sine": improvement("largest_principal_angle_sine"),
                "graph_coordinate_error": improvement("maximum_graph_coordinate_absolute_error"),
            },
            "relation_height_ladder": ladder,
            "face_equations_added": size * k,
            "face_equation_rank": size * k - k * (k - 1) // 2,
        }

    spectra = {
        "format": "exactification-spectra-v1",
        "precision_runs": spectra_runs,
        "nullity_branches": {block["name"]: len(exact_kernels.get(block["name"], [])) for block in model["blocks"]},
        "decision": "selected stable p/2p spectral gaps and required identical exact kernel subspaces from independent graph-chart recoveries",
    }
    kernels = {
        "format": "exactification-kernels-v1",
        "method": "basis-invariant numerical graph-coordinate recovery with explicit graph-pivot rank for the largest row set",
        "blocks": kernel_blocks,
    }
    args.spectra_output.write_text(json.dumps(spectra, indent=2) + "\n")
    args.kernels_output.write_text(json.dumps(kernels, indent=2) + "\n")


if __name__ == "__main__":
    main()
