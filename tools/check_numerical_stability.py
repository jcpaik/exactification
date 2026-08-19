#!/usr/bin/env python3
"""Compare p/2p SDP runs without asserting an exact kernel oracle.

The diagnostic uses a declared relative eigenvalue threshold and compares
orthogonal projectors onto the resulting numerical nullspaces.  It is evidence
for a stable face hypothesis, not an exact proof of rank or kernel equations.
"""

from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import numpy as np


RELATIVE_EIGENVALUE_THRESHOLD = 1.0e-12
PROJECTOR_DISTANCE_TOLERANCE = 1.0e-8
APPROXIMATE_PSD_TOLERANCE = 1.0e-10


def fraction_decimal(value: str) -> Decimal:
    rational = Fraction(value)
    return Decimal(rational.numerator) / Decimal(rational.denominator)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def result_field(text: str, field: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(field)}\s*=\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def matrices(solution: dict) -> dict[str, list[list[Decimal]]]:
    return {
        block["name"]: [[Decimal(entry) for entry in row] for row in block["matrix"]]
        for block in solution["blocks"]
    }


def evaluate(expression: dict, block_matrices: dict[str, list[list[Decimal]]]) -> Decimal:
    value = fraction_decimal(expression["constant"])
    for term in expression["terms"]:
        value += (
            fraction_decimal(term["coefficient"])
            * block_matrices[term["block"]][term["row"]][term["col"]]
        )
    return value


def decimal_scientific(value: Decimal) -> str:
    return "0.00000000E+00" if value == 0 else f"{value:.8E}"


def check_feasibility(model: dict, solution: dict, fixed_objective: str) -> dict[str, str]:
    block_matrices = matrices(solution)
    printed_digits = solution["claimed_precision_digits"]
    tolerance = Decimal(10) ** (-(printed_digits // 2))
    equality_residuals: list[Decimal] = []
    inequality_violations: list[Decimal] = []
    with localcontext() as context:
        context.prec = max(100, printed_digits + 30)
        for constraint in model["constraints"]:
            value = evaluate(constraint["expression"], block_matrices)
            if constraint["sense"] == "eq":
                equality_residuals.append(abs(value))
            elif constraint["sense"] == "ge":
                inequality_violations.append(max(Decimal(0), -value))
            else:
                inequality_violations.append(max(Decimal(0), value))
        objective = evaluate(model["objective"]["expression"], block_matrices)
        objective_error = abs(objective - fraction_decimal(fixed_objective))
    max_equality = max(equality_residuals, default=Decimal(0))
    max_violation = max(inequality_violations, default=Decimal(0))
    if max_equality > tolerance:
        raise AssertionError(f"equality residual {max_equality} exceeds {tolerance}")
    if max_violation > tolerance:
        raise AssertionError(f"inequality violation {max_violation} exceeds {tolerance}")
    if objective_error > tolerance:
        raise AssertionError(f"objective error {objective_error} exceeds {tolerance}")
    return {
        "check_tolerance": str(tolerance),
        "max_equality_residual": decimal_scientific(max_equality),
        "max_inequality_violation": decimal_scientific(max_violation),
        "objective_error_to_fixed_target": decimal_scientific(objective_error),
    }


def spectral_data(block: dict) -> tuple[np.ndarray, np.ndarray, float]:
    matrix = np.array(block["matrix"], dtype=float)
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    if float(np.min(eigenvalues)) < -APPROXIMATE_PSD_TOLERANCE * scale:
        raise AssertionError(f"{block['name']}: not approximately PSD")
    return eigenvalues, eigenvectors, scale


def normalized_spectrum_summary(eigenvalues: np.ndarray, scale: float, nullity: int) -> tuple[str, str | None]:
    normalized = np.abs(eigenvalues) / scale
    max_null = float(np.max(normalized[:nullity])) if nullity else 0.0
    min_positive = float(np.min(normalized[nullity:])) if nullity < len(normalized) else None
    return f"{max_null:.8E}", None if min_positive is None else f"{min_positive:.8E}"


def compare_blocks(p_solution: dict, two_p_solution: dict) -> tuple[list[dict], float, str | None]:
    p_blocks = p_solution["blocks"]
    two_p_blocks = two_p_solution["blocks"]
    if [block["name"] for block in p_blocks] != [block["name"] for block in two_p_blocks]:
        raise AssertionError("p and 2p block orders differ")

    records = []
    worst_distance = 0.0
    worst_block = None
    for p_block, two_p_block in zip(p_blocks, two_p_blocks):
        p_values, p_vectors, p_scale = spectral_data(p_block)
        two_p_values, two_p_vectors, two_p_scale = spectral_data(two_p_block)
        p_nullity = int(np.sum(np.abs(p_values) <= RELATIVE_EIGENVALUE_THRESHOLD * p_scale))
        two_p_nullity = int(
            np.sum(np.abs(two_p_values) <= RELATIVE_EIGENVALUE_THRESHOLD * two_p_scale)
        )
        if p_nullity != two_p_nullity:
            raise AssertionError(
                f"{p_block['name']}: nullity changed {p_nullity} -> {two_p_nullity}"
            )
        projector_distance = None
        if p_nullity:
            p_kernel = p_vectors[:, :p_nullity]
            two_p_kernel = two_p_vectors[:, :two_p_nullity]
            p_projector = p_kernel @ p_kernel.T
            two_p_projector = two_p_kernel @ two_p_kernel.T
            distance = float(np.linalg.norm(p_projector - two_p_projector, ord=2))
            if distance > PROJECTOR_DISTANCE_TOLERANCE:
                raise AssertionError(
                    f"{p_block['name']}: projector distance {distance} exceeds tolerance"
                )
            projector_distance = f"{distance:.8E}"
            if distance > worst_distance:
                worst_distance = distance
                worst_block = p_block["name"]
        p_max_null, p_min_positive = normalized_spectrum_summary(
            p_values, p_scale, p_nullity
        )
        two_p_max_null, two_p_min_positive = normalized_spectrum_summary(
            two_p_values, two_p_scale, two_p_nullity
        )
        records.append(
            {
                "block": p_block["name"],
                "size": len(p_block["matrix"]),
                "nullity_p": p_nullity,
                "nullity_2p": two_p_nullity,
                "projector_distance_operator_norm": projector_distance,
                "p_max_relative_null_eigenvalue": p_max_null,
                "p_min_relative_positive_eigenvalue": p_min_positive,
                "2p_max_relative_null_eigenvalue": two_p_max_null,
                "2p_min_relative_positive_eigenvalue": two_p_min_positive,
            }
        )
    return records, worst_distance, worst_block


def run_record(directory: Path, solution: dict, feasibility: dict) -> dict:
    result_text = (directory / "result.out").read_text(encoding="utf-8")
    return {
        "solver_internal_precision_bits": solution["solver_internal_precision_bits"],
        "printed_digits": solution["claimed_precision_digits"],
        "phase": result_field(result_text, "phase.value"),
        "iterations": int(result_field(result_text, "Iteration")),
        "primal_feasibility_error_reported": result_field(result_text, "p.feas.error"),
        "dual_feasibility_error_reported": result_field(result_text, "d.feas.error"),
        "runtime_seconds_reported": result_field(result_text, "total time"),
        **feasibility,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_directory", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="defaults to INPUT/numerical/numerical_stability.json",
    )
    args = parser.parse_args()
    output = args.output or args.input_directory / "numerical" / "numerical_stability.json"

    model = load(args.input_directory / "model.json")
    manifest = load(args.input_directory / "manifest.json")
    p_dir = args.input_directory / "numerical" / "p"
    two_p_dir = args.input_directory / "numerical" / "2p"
    p_solution = load(p_dir / "approximate_solution.json")
    two_p_solution = load(two_p_dir / "approximate_solution.json")
    if two_p_solution["solver_internal_precision_bits"] != 2 * p_solution["solver_internal_precision_bits"]:
        raise AssertionError("2p internal precision is not twice p")
    if two_p_solution["claimed_precision_digits"] != 2 * p_solution["claimed_precision_digits"]:
        raise AssertionError("2p printed digits are not twice p")

    p_feasibility = check_feasibility(model, p_solution, manifest["fixed_objective"])
    two_p_feasibility = check_feasibility(model, two_p_solution, manifest["fixed_objective"])
    blocks, worst_distance, worst_block = compare_blocks(p_solution, two_p_solution)
    report = {
        "format": "numerical-face-stability-v1",
        "method": {
            "relative_eigenvalue_threshold": f"{RELATIVE_EIGENVALUE_THRESHOLD:.1E}",
            "projector_distance_tolerance": f"{PROJECTOR_DISTANCE_TOLERANCE:.1E}",
            "approximate_psd_tolerance": f"{APPROXIMATE_PSD_TOLERANCE:.1E}",
            "eigensolver": f"numpy.linalg.eigh ({np.__version__})",
            "warning": "This is numerical face evidence, not an exact rank or kernel oracle.",
        },
        "runs": {
            "p": run_record(p_dir, p_solution, p_feasibility),
            "2p": run_record(two_p_dir, two_p_solution, two_p_feasibility),
        },
        "summary": {
            "stable_nullities": True,
            "stable_kernel_projectors": True,
            "worst_projector_distance_operator_norm": f"{worst_distance:.8E}",
            "worst_projector_block": worst_block,
        },
        "blocks": blocks,
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(
        f"ok: {len(blocks)} stable block nullities; worst projector distance "
        f"{worst_distance:.3e} ({worst_block})"
    )


if __name__ == "__main__":
    main()
