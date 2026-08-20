#!/usr/bin/env python3
"""Self-check the blind DLM three-point test case and its SDPA projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from verify import load_model


EXPECTED_MUVT_SIZES = [23, 16, 11, 7, 4, 2, 1]
EXPECTED_PI3_ROWS = [27, 18, 11, 6]
EXPECTED_BLOCK_SIZES = [
    1, 1, 1, 1, 1, 1, 1,
    7, 6, 5, 4, 3, 2, 1,
    7, 6,
    23, 16, 16, 11, 7, 7, 4, 4, 2, 1, 27, 18, 18, 11, 6,
]
EXPECTED_VARIABLES = 1641
EXPECTED_TRIPLE_CONSTRAINTS = 116
EXPECTED_SINGLE_DEGREE = 12
EXPECTED_EQUALITIES = 130
EXPECTED_NONZEROS = 24462


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def invariant_basis_count(max_degree: int) -> int:
    return sum(
        1
        for l in range(max_degree + 1)
        for k in range((max_degree - l) // 2 + 1)
        for _ in range((max_degree - l - 2 * k) // 3 + 1)
    )


def filtered_pi3_count(max_degree: int, degree_limit: int) -> int:
    count = 0
    for l in range(max_degree + 1):
        for k in range((max_degree - l) // 2 + 1):
            for m in range((max_degree - l - 2 * k) // 3 + 1):
                basis_degree = l + 2 * k + 3 * m
                # Diagonal degrees of the two entries of Pi_3 are 2 and 4.
                count += 2 * basis_degree + 2 <= degree_limit
                count += 2 * basis_degree + 4 <= degree_limit
    return count


def as_decimal(value: str) -> Decimal:
    rational = Fraction(value)
    return Decimal(rational.numerator) / Decimal(rational.denominator)


def check_structure(directory: Path) -> tuple[dict, dict]:
    model_path = directory / "model.json"
    parsed_model = load_model(model_path)
    raw_model = json.loads(model_path.read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    derived_muvt = [invariant_basis_count(6 - shift) for shift in range(7)]
    assert derived_muvt == EXPECTED_MUVT_SIZES
    derived_pi3 = [
        filtered_pi3_count(5, 12),
        filtered_pi3_count(4, 10),
        filtered_pi3_count(3, 8),
        filtered_pi3_count(2, 6),
    ]
    assert derived_pi3 == EXPECTED_PI3_ROWS

    block_sizes = [block.size for block in parsed_model.blocks]
    assert block_sizes == EXPECTED_BLOCK_SIZES
    assert len(set(block.name for block in parsed_model.blocks)) == len(parsed_model.blocks)
    assert sum(size * (size + 1) // 2 for size in block_sizes) == EXPECTED_VARIABLES
    assert len(parsed_model.constraints) == EXPECTED_EQUALITIES
    assert all(constraint.sense == "eq" for constraint in parsed_model.constraints)
    assert parsed_model.objective.sense == "minimize"

    triple = [c for c in raw_model["constraints"] if c["name"].startswith("triple.")]
    single = [c for c in raw_model["constraints"] if c["name"].startswith("single.")]
    assert len(triple) == EXPECTED_TRIPLE_CONSTRAINTS
    assert len(single) == EXPECTED_SINGLE_DEGREE + 1
    fixed = raw_model["constraints"][-1]
    assert fixed["name"] == "fixed_objective"
    assert fixed["expression"]["terms"] == raw_model["objective"]["expression"]["terms"]
    assert Fraction(fixed["expression"]["constant"]) == (
        Fraction(raw_model["objective"]["expression"]["constant"]) - 10
    )

    nonzeros = sum(len(c["expression"]["terms"]) for c in raw_model["constraints"])
    assert nonzeros == EXPECTED_NONZEROS
    source_logic = manifest["structure"]
    assert source_logic["muvt_basis_sizes"] == derived_muvt
    assert source_logic["filtered_pi3_row_sizes"] == derived_pi3
    assert source_logic["block_sizes"] == EXPECTED_BLOCK_SIZES
    assert source_logic["scalar_upper_triangle_variables"] == EXPECTED_VARIABLES
    assert source_logic["equality_constraints"] == EXPECTED_EQUALITIES
    assert source_logic["constraint_matrix_nonzeros"] == EXPECTED_NONZEROS
    assert manifest["blind_input_policy"]["published_certificate_included"] is False
    assert manifest["blind_input_policy"]["published_serialized_solution_read"] is False
    return raw_model, manifest


def check_sdpa_projection(directory: Path, model: dict) -> None:
    lines = (directory / "discovery.dat-s").read_text(encoding="ascii").splitlines()
    constraints = model["constraints"]
    blocks = model["blocks"]
    assert int(lines[0]) == len(constraints)
    assert int(lines[1]) == len(blocks)
    assert [int(value) for value in lines[2].split()] == EXPECTED_BLOCK_SIZES
    rhs = [Decimal(value) for value in lines[3].split()]
    assert len(rhs) == len(constraints)

    with localcontext() as context:
        context.prec = 180
        for actual, constraint in zip(rhs, constraints):
            expected = -as_decimal(constraint["expression"]["constant"])
            assert abs(actual - expected) <= Decimal("1e-118") * max(Decimal(1), abs(expected))

        block_index = {block["name"]: i for i, block in enumerate(blocks, start=1)}
        expected_entries = []
        for constraint_index, constraint in enumerate(constraints, start=1):
            for term in constraint["expression"]["terms"]:
                coefficient = Fraction(term["coefficient"])
                if term["row"] != term["col"]:
                    coefficient /= 2
                expected_entries.append(
                    (
                        constraint_index,
                        block_index[term["block"]],
                        term["row"] + 1,
                        term["col"] + 1,
                        coefficient,
                    )
                )
        assert len(lines) - 4 == len(expected_entries) == EXPECTED_NONZEROS
        for line, expected in zip(lines[4:], expected_entries):
            fields = line.split()
            assert tuple(map(int, fields[:4])) == expected[:4]
            actual = Decimal(fields[4])
            wanted = as_decimal(str(expected[4]))
            assert abs(actual - wanted) <= Decimal("1e-118") * max(Decimal(1), abs(wanted))


def cholesky_with_relative_jitter(matrix: list[list[float]], relative_jitter: float = 1e-10) -> None:
    size = len(matrix)
    scale = max(1.0, max(abs(value) for row in matrix for value in row))
    jitter = relative_jitter * scale
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            value = matrix[row][column] + (jitter if row == column else 0.0)
            value -= sum(lower[row][k] * lower[column][k] for k in range(column))
            if row == column:
                if value <= 0:
                    raise AssertionError("approximate block is not PSD within relative jitter")
                lower[row][column] = math.sqrt(value)
            else:
                lower[row][column] = value / lower[column][column]


def check_approximate_solution(directory: Path, model: dict) -> None:
    solution = json.loads((directory / "approximate_solution.json").read_text(encoding="utf-8"))
    assert solution["format"] == "approximate-block-sdp-solution-v1"
    assert solution["claimed_objective"] == "10"
    assert solution["claimed_precision_digits"] == 40
    assert solution["solver_internal_precision_bits"] == 300
    assert [block["name"] for block in solution["blocks"]] == [
        block["name"] for block in model["blocks"]
    ]
    matrices: dict[str, list[list[Decimal]]] = {}
    for spec, block in zip(model["blocks"], solution["blocks"]):
        size = spec["size"]
        matrix = block["matrix"]
        assert len(matrix) == size and all(len(row) == size for row in matrix)
        assert all(matrix[i][j] == matrix[j][i] for i in range(size) for j in range(size))
        numeric = [[Decimal(value) for value in row] for row in matrix]
        matrices[block["name"]] = numeric
        cholesky_with_relative_jitter([[float(value) for value in row] for row in numeric])

    def evaluate(expression: dict) -> Decimal:
        value = as_decimal(expression["constant"])
        for term in expression["terms"]:
            value += (
                as_decimal(term["coefficient"])
                * matrices[term["block"]][term["row"]][term["col"]]
            )
        return value

    with localcontext() as context:
        context.prec = 100
        residuals = [abs(evaluate(c["expression"])) for c in model["constraints"]]
        assert max(residuals) < Decimal("1e-30")
        assert abs(evaluate(model["objective"]["expression"]) - Decimal(10)) < Decimal("1e-30")


def check_numerical_provenance(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["solver"]["commit"] == (
        "ca110db5ea1cc46e811b70dfea9cbb25db74448d"
    )
    assert manifest["source"]["solver"]["binary_sha256"] == (
        "c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0"
    )
    assert [run["label"] for run in manifest["workflow"]["precision_evidence"]] == [
        "p",
        "2p",
    ]
    p_directory = directory / "numerical" / "p"
    two_p_directory = directory / "numerical" / "2p"
    p = json.loads((p_directory / "approximate_solution.json").read_text(encoding="utf-8"))
    two_p = json.loads(
        (two_p_directory / "approximate_solution.json").read_text(encoding="utf-8")
    )
    assert (p["claimed_precision_digits"], p["solver_internal_precision_bits"]) == (40, 300)
    assert (two_p["claimed_precision_digits"], two_p["solver_internal_precision_bits"]) == (80, 600)
    assert (directory / "discovery.result").read_bytes() == (p_directory / "result.out").read_bytes()
    assert (directory / "approximate_solution.json").read_bytes() == (
        p_directory / "approximate_solution.json"
    ).read_bytes()
    stability = json.loads(
        (directory / "numerical" / "numerical_stability.json").read_text(encoding="utf-8")
    )
    assert stability["summary"]["stable_nullities"] is True
    assert stability["summary"]["stable_kernel_projectors"] is True
    assert len(stability["blocks"]) == 31
    assert all(block["nullity_p"] == block["nullity_2p"] for block in stability["blocks"])
    assert float(stability["summary"]["worst_projector_distance_operator_norm"]) < 1.0e-8


def check_hashes(directory: Path, manifest: dict) -> None:
    for name, record in manifest["files"].items():
        assert sha256(directory / name) == record["sha256"], name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        default=Path("testcases/dlm-three-point-10/input"),
    )
    args = parser.parse_args()
    model, manifest = check_structure(args.directory)
    check_sdpa_projection(args.directory, model)
    check_approximate_solution(args.directory, model)
    check_numerical_provenance(args.directory)
    check_hashes(args.directory, manifest)
    print(
        "ok: source-derived structure, exact model schema, SDPA projection, "
        "and numerical feasibility all agree"
    )


if __name__ == "__main__":
    main()
