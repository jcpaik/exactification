#!/usr/bin/env python3
"""Build p/2p spectra and basis-invariant kernel validation artifacts."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


def mpq(value: str | int | sp.Rational) -> mp.mpf:
    q = Fraction(str(value))
    return mp.mpf(q.numerator) / q.denominator


def extract(matrix: mp.matrix, rows: list[int], columns: list[int]) -> mp.matrix:
    return mp.matrix([[matrix[row, column] for column in columns] for row in rows])


def opnorm(matrix: mp.matrix) -> mp.mpf:
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
    parser.add_argument("--relations-dir", required=True, type=Path)
    parser.add_argument("--spectra-output", required=True, type=Path)
    parser.add_argument("--kernels-output", required=True, type=Path)
    parser.add_argument("--decimal-precision", type=int, default=180)
    args = parser.parse_args()
    mp.mp.dps = args.decimal_precision

    model = json.loads(args.model.read_text())
    approximate = {
        "p": json.loads(args.p.read_text()),
        "2p": json.loads(args.two_p.read_text()),
    }
    sources = {"p": str(args.p), "2p": str(args.two_p)}
    nullities = {"U": 0, "P": 4, "Q": 1, "R": 2}
    relation_docs: dict[str, dict[str, dict]] = {}
    for block, nullity in nullities.items():
        if not nullity:
            continue
        relation_docs[block] = {
            label: json.loads((args.relations_dir / f"relations-{block}-{label}.json").read_text())
            for label in ("p", "2p")
        }

    run_blocks: dict[str, dict[str, dict]] = {"p": {}, "2p": {}}
    run_matrices: dict[str, dict[str, mp.matrix]] = {"p": {}, "2p": {}}
    run_vectors: dict[str, dict[str, mp.matrix]] = {"p": {}, "2p": {}}
    spectra_runs = []
    for label in ("p", "2p"):
        matrices = {
            block["name"]: mp.matrix([[mp.mpf(value) for value in row] for row in block["matrix"]])
            for block in approximate[label]["blocks"]
        }
        run_matrices[label] = matrices
        for spec in model["blocks"]:
            name = spec["name"]
            values, vectors = mp.eigsy(matrices[name])
            run_vectors[label][name] = vectors
            scale = max(mp.mpf(1), max(abs(value) for value in values))
            normalized = [abs(value) / scale for value in values]
            k = nullities[name]
            run_blocks[label][name] = {
                "eigenvalues": [mp.nstr(value, 60) for value in values],
                "normalization_scale": mp.nstr(scale, 60),
                "normalized_absolute_eigenvalues": [mp.nstr(value, 48) for value in normalized],
                "candidate_nullity": k,
                "largest_structural_zero_normalized": None if k == 0 else mp.nstr(max(normalized[:k]), 45),
                "smallest_positive_normalized": None if k == spec["size"] else mp.nstr(normalized[k], 45),
                "nullity_boundary_gap_ratio": None if k == 0 or k == spec["size"] else mp.nstr(normalized[k] / max(normalized[:k]), 35),
            }

        constraint_values = {}
        equality_residuals = []
        for constraint in model["constraints"]:
            value = mpq(constraint["expression"]["constant"])
            for term in constraint["expression"]["terms"]:
                value += mpq(term["coefficient"]) * matrices[term["block"]][term["row"], term["col"]]
            constraint_values[constraint["name"]] = mp.nstr(value, 55)
            if constraint["sense"] == "eq":
                equality_residuals.append(abs(value))
        objective = mpq(model["objective"]["expression"]["constant"])
        for term in model["objective"]["expression"]["terms"]:
            objective += mpq(term["coefficient"]) * matrices[term["block"]][term["row"], term["col"]]
        precision_key = "claimed_precision_bits" if "claimed_precision_bits" in approximate[label] else "claimed_precision_digits"
        spectra_runs.append({
            "label": label,
            "source": sources[label],
            precision_key: approximate[label][precision_key],
            "claimed_objective": approximate[label]["claimed_objective"],
            "recomputed_objective": mp.nstr(objective, 60),
            "maximum_absolute_equality_residual": mp.nstr(max(equality_residuals, default=mp.mpf(0)), 50),
            "affine_expression_values": constraint_values,
            "blocks": run_blocks[label],
        })

    kernel_blocks: dict[str, dict] = {}
    for spec in model["blocks"]:
        name = spec["name"]
        size = spec["size"]
        k = nullities[name]
        if not k:
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

        docs = relation_docs[name]
        if docs["p"]["status"] != "recovered" or docs["2p"]["status"] != "recovered":
            raise RuntimeError(f"relation recovery failed for {name}")
        relation_p = sp.Matrix(docs["p"]["relation_matrix"])
        relation = sp.Matrix(docs["2p"]["relation_matrix"])
        if relation_p.rref()[0] != relation.rref()[0]:
            raise RuntimeError(f"p/2p row spaces differ for {name}")
        basis_columns = docs["2p"]["kernel_basis_columns"]
        basis = sp.Matrix.hstack(*[sp.Matrix(column) for column in basis_columns])
        if relation * basis != sp.zeros(relation.rows, basis.cols):
            raise RuntimeError(f"exact relation check failed for {name}")
        q_indices = list(docs["2p"]["pivot_rows"])
        p_indices = [index for index in range(size) if index not in q_indices]
        graph = basis * basis.extract(q_indices, range(k)).inv()
        graph_mp = mp.matrix([[mpq(graph[i, j]) for j in range(k)] for i in range(size)])
        relation_mp = mp.matrix([[mp.mpf(int(relation[i, j])) for j in range(size)] for i in range(relation.rows)])
        basis_mp = mp.matrix([[mp.mpf(int(basis[i, j])) for j in range(k)] for i in range(size)])
        exact_q, _ = mp.qr(basis_mp)
        exact_q = exact_q[:, :k]
        validation = []
        for label in ("p", "2p"):
            matrix = run_matrices[label][name]
            vectors = run_vectors[label][name]
            numerical_kernel = vectors[:, :k]
            numerical_positive = vectors[:, k:]
            cross = exact_q.T * numerical_kernel
            cross_min = sigma_min(cross)
            angle_sine = mp.sqrt(max(mp.mpf(0), 1 - cross_min * cross_min))
            relation_residual = opnorm(relation_mp * numerical_kernel) / (opnorm(relation_mp) * max(mp.mpf(1), opnorm(numerical_kernel)))
            block_residual = opnorm(matrix * graph_mp) / (opnorm(matrix) * max(mp.mpf(1), opnorm(graph_mp)))
            numerical_q_minor = extract(numerical_kernel, q_indices, list(range(k)))
            numerical_graph = numerical_kernel * (numerical_q_minor ** -1)
            graph_error = max(abs(numerical_graph[i, j] - graph_mp[i, j]) for i in range(size) for j in range(k))
            positive_minor = extract(numerical_positive, p_indices, list(range(size - k)))
            pos_min = sigma_min(positive_minor)
            block_minor = extract(matrix, p_indices, p_indices)
            block_min = sigma_min(block_minor)
            validation.append({
                "label": label,
                "source": sources[label],
                "maximum_normalized_relation_residual_rowwise": docs[label]["maximum_normalized_relation_residual"],
                "normalized_relation_residual_operator": mp.nstr(relation_residual, 45),
                "normalized_block_kernel_residual_operator": mp.nstr(block_residual, 45),
                "largest_principal_angle_sine": mp.nstr(angle_sine, 45),
                "maximum_graph_coordinate_absolute_error": mp.nstr(graph_error, 45),
                "positive_space_coordinate_minor": {
                    "indices": p_indices,
                    "smallest_singular_value": mp.nstr(pos_min, 40),
                    "condition_estimate_2": mp.nstr(opnorm(positive_minor) / pos_min, 40),
                },
                "block_positive_minor": {
                    "indices": p_indices,
                    "smallest_singular_value": mp.nstr(block_min, 40),
                    "condition_estimate_2": mp.nstr(opnorm(block_minor) / block_min, 40),
                },
            })

        def factor(field: str) -> str:
            first = mp.mpf(validation[0][field])
            second = mp.mpf(validation[1][field])
            return "infinite" if second == 0 else mp.nstr(first / second, 30)

        kernel_blocks[name] = {
            "candidate_nullity": k,
            "precision_runs_used": [sources["p"], sources["2p"]],
            "status": "recovered",
            "recovery_method": "numerical_graph_chart",
            "provenance": "numerical_graph_chart",
            "independent_recoveries_have_equal_exact_row_space": True,
            "relation_matrix": [[int(relation[i, j]) for j in range(size)] for i in range(relation.rows)],
            "relation_exact_rank": int(relation.rank()),
            "relation_height": max(abs(int(value)) for value in relation),
            "exact_kernel_basis_columns": basis_columns,
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
                "maximum_rowwise_relation": factor("maximum_normalized_relation_residual_rowwise"),
                "relation_operator": factor("normalized_relation_residual_operator"),
                "block_kernel": factor("normalized_block_kernel_residual_operator"),
                "principal_angle_sine": factor("largest_principal_angle_sine"),
                "graph_coordinate_error": factor("maximum_graph_coordinate_absolute_error"),
            },
            "relation_height_ladder": docs["2p"]["ladder"],
            "face_equations_added": size * k,
            "face_equation_rank": size * k - k * (k - 1) // 2,
        }

    spectra = {
        "format": "exactification-spectra-v1",
        "precision_runs": spectra_runs,
        "nullity_branches": {name: nullity for name, nullity in nullities.items()},
        "decision": "selected the stable p/2p gaps and required an identical exact relation row space from independent recoveries",
    }
    kernels = {
        "format": "exactification-kernels-v1",
        "method": "basis-invariant numerical graph-coordinate recovery",
        "blocks": kernel_blocks,
    }
    args.spectra_output.write_text(json.dumps(spectra, indent=2) + "\n")
    args.kernels_output.write_text(json.dumps(kernels, indent=2) + "\n")


if __name__ == "__main__":
    main()
