#!/usr/bin/env python3
"""Generate the obfuscated rational-kernel exactification testcase.

All face-defining data stay under ``construction/``.  Public input contains
only a rational block-SDP model and two independently solved decimal points.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Sequence

import sympy as sp


CASE_ROOT = Path(__file__).resolve().parents[1]
INPUT = CASE_ROOT / "input"
CONSTRUCTION = CASE_ROOT / "construction"
REPOSITORY = CASE_ROOT.parents[1]
NUMERICAL = INPUT / "numerical"
SEED = 20260819
BLOCK_NAME = "moment_matrix"
SIZE = 10
RANK = 7
NULLITY = SIZE - RANK
PUBLIC_EQUALITIES = 8
PRINTED_DIGITS = 40
SOLVER_REPOSITORY = "https://github.com/nakatamaho/sdpa-gmp.git"
SOLVER_COMMIT = "ca110db5ea1cc46e811b70dfea9cbb25db74448d"
SOLVER_BINARY_SHA256 = "c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0"
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def qstr(value: sp.Rational | Fraction | int) -> str:
    if isinstance(value, sp.Rational):
        value = Fraction(int(value.p), int(value.q))
    elif isinstance(value, int):
        value = Fraction(value)
    if not isinstance(value, Fraction):
        raise TypeError(type(value))
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def fraction(value: sp.Rational | Fraction | int) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    return Fraction(int(value.p), int(value.q))


def decimal_string(value: Fraction, digits: int) -> str:
    """Round an exact rational to a deterministic scientific decimal."""
    if not value:
        return "0"
    sign = "-" if value < 0 else ""
    value = abs(value)
    numerator, denominator = value.numerator, value.denominator
    exponent = len(str(numerator)) - len(str(denominator))
    if exponent >= 0:
        while Fraction(numerator, denominator) < 10**exponent:
            exponent -= 1
        while Fraction(numerator, denominator) >= 10 ** (exponent + 1):
            exponent += 1
    else:
        while Fraction(numerator, denominator) < Fraction(1, 10 ** (-exponent)):
            exponent -= 1
        while Fraction(numerator, denominator) >= Fraction(1, 10 ** (-exponent - 1)):
            exponent += 1
    scale_power = digits - 1 - exponent
    scaled = value * (10**scale_power if scale_power >= 0 else Fraction(1, 10 ** (-scale_power)))
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    if 2 * remainder >= scaled.denominator:
        quotient += 1
    if len(str(quotient)) > digits:
        quotient //= 10
        exponent += 1
    text = str(quotient).rjust(digits, "0")
    return f"{sign}{text[0]}.{text[1:]}e{exponent:+d}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def dense_symmetric(rng: random.Random, size: int, bound: int) -> sp.Matrix:
    choices = [value for value in range(-bound, bound + 1) if value]
    matrix = sp.zeros(size)
    for row in range(size):
        for column in range(row, size):
            value = rng.choice(choices)
            matrix[row, column] = matrix[column, row] = value
    return matrix


def has_indefinite_principal_pair(matrix: sp.Matrix) -> bool:
    for row in range(matrix.rows):
        for column in range(row + 1, matrix.cols):
            determinant = matrix[row, row] * matrix[column, column] - matrix[row, column] ** 2
            if determinant < 0:
                return True
    return False


def upper_vector(matrix: sp.Matrix) -> sp.Matrix:
    return sp.Matrix([matrix[row, column] for row in range(matrix.rows) for column in range(row, matrix.cols)])


def trace_product(left: sp.Matrix, right: sp.Matrix) -> sp.Rational:
    return sp.Rational(sum(left[row, column] * right[row, column] for row in range(left.rows) for column in range(left.cols)))


def expression(matrix: sp.Matrix, constant: sp.Rational) -> dict[str, object]:
    terms: list[dict[str, object]] = []
    for row in range(matrix.rows):
        for column in range(row, matrix.cols):
            coefficient = matrix[row, column] if row == column else 2 * matrix[row, column]
            if coefficient:
                terms.append(
                    {
                        "block": BLOCK_NAME,
                        "row": row,
                        "col": column,
                        "coefficient": qstr(coefficient),
                    }
                )
    return {"constant": qstr(constant), "terms": terms}


def matrix_strings(matrix: sp.Matrix) -> list[list[str]]:
    return [[qstr(matrix[row, column]) for column in range(matrix.cols)] for row in range(matrix.rows)]


def make_hidden_instance() -> dict[str, object]:
    rng = random.Random(SEED)
    skew = sp.zeros(SIZE)
    nonzero_small = (-3, -2, -1, 1, 2, 3)
    for row in range(SIZE):
        for column in range(row + 1, SIZE):
            value = rng.choice(nonzero_small)
            skew[row, column] = value
            skew[column, row] = -value
    identity = sp.eye(SIZE)
    orthogonal = (identity - skew) * (identity + skew).inv()
    if orthogonal.T * orthogonal != identity:
        raise AssertionError("rational Cayley transform lost orthogonality")
    complement = orthogonal[:, :RANK]
    kernel = orthogonal[:, RANK:]
    projector = kernel * kernel.T
    if projector * projector != projector or projector.T != projector:
        raise AssertionError("hidden projector is not an exact orthogonal projector")

    face_metric = sp.diag(1, 2, 3, 5, 7, 11, 13)
    certificate_matrix = complement * face_metric * complement.T
    if certificate_matrix * kernel != sp.zeros(SIZE, NULLITY):
        raise AssertionError("certificate does not have the intended kernel")

    base = [sp.eye(SIZE)]
    base.extend(dense_symmetric(rng, SIZE, 6) for _ in range(PUBLIC_EQUALITIES - 1))
    for _ in range(10_000):
        mixing = sp.Matrix(
            PUBLIC_EQUALITIES,
            PUBLIC_EQUALITIES,
            lambda _r, _c: rng.choice((-4, -3, -2, -1, 1, 2, 3, 4)),
        )
        if mixing.det() == 0:
            continue
        public = [sum((mixing[row, col] * base[col] for col in range(PUBLIC_EQUALITIES)), sp.zeros(SIZE)) for row in range(PUBLIC_EQUALITIES)]
        if all(has_indefinite_principal_pair(matrix) for matrix in public):
            break
    else:
        raise RuntimeError("failed to construct dense indefinite public equalities")

    rhs = [trace_product(matrix, certificate_matrix) for matrix in public]
    multipliers = [sp.Rational(value) for value in (2, -3, 5, -7, 11, -13, 17, -19)]
    objective_matrix = projector - sum(
        (coefficient * matrix for coefficient, matrix in zip(multipliers, public)),
        sp.zeros(SIZE),
    )
    target = -sum((coefficient * value for coefficient, value in zip(multipliers, rhs)), sp.Rational(0))
    if objective_matrix + sum(
        (coefficient * matrix for coefficient, matrix in zip(multipliers, public)),
        sp.zeros(SIZE),
    ) != projector:
        raise AssertionError("supporting identity was not constructed exactly")
    if trace_product(objective_matrix, certificate_matrix) != target:
        raise AssertionError("certificate objective mismatch")
    if not has_indefinite_principal_pair(objective_matrix):
        raise AssertionError("objective accidentally exposes a semidefinite row")
    spanning = sp.Matrix.hstack(upper_vector(projector), *(upper_vector(matrix) for matrix in public))
    if spanning.rank() != PUBLIC_EQUALITIES + 1:
        raise AssertionError("supporting identity is not uniquely represented")

    constraints = []
    for index, (matrix, value) in enumerate(zip(public, rhs)):
        constraints.append(
            {
                "name": f"moment_{index:02d}",
                "sense": "eq",
                "expression": expression(matrix, -value),
            }
        )
    constraints.append(
        {
            "name": "fixed_objective",
            "sense": "eq",
            "expression": expression(objective_matrix, -target),
        }
    )
    model = {
        "format": "exact-block-sdp-model-v1",
        "blocks": [{"name": BLOCK_NAME, "size": SIZE}],
        "constraints": constraints,
        "objective": {"sense": "minimize", "expression": expression(objective_matrix, sp.Rational(0))},
    }
    return {
        "model": model,
        "orthogonal": orthogonal,
        "complement": complement,
        "kernel": kernel,
        "projector": projector,
        "certificate_matrix": certificate_matrix,
        "public_matrices": public,
        "rhs": rhs,
        "multipliers": multipliers,
        "objective_matrix": objective_matrix,
        "target": target,
        "mixing": mixing,
    }


def schur_trace(matrix: sp.Matrix) -> dict[str, object]:
    active = list(range(matrix.rows))
    current = [[fraction(matrix[row, column]) for column in range(matrix.cols)] for row in range(matrix.rows)]
    steps: list[dict[str, object]] = []
    while active:
        positive = [index for index in active if current[index][index] > 0]
        if positive:
            pivot_index = max(positive, key=lambda index: current[index][index])
            pivot = current[pivot_index][pivot_index]
            remaining = [index for index in active if index != pivot_index]
            for row_position, row in enumerate(remaining):
                for column in remaining[row_position:]:
                    value = current[row][column] - current[row][pivot_index] * current[pivot_index][column] / pivot
                    current[row][column] = current[column][row] = value
        else:
            pivot_index = active[0]
            pivot = current[pivot_index][pivot_index]
            if pivot != 0 or any(current[pivot_index][column] for column in active):
                raise AssertionError("construction certificate is not PSD")
            remaining = active[1:]
        steps.append({"index": pivot_index, "pivot": qstr(pivot)})
        active = remaining
    return {"algorithm": "symmetric-schur-v1", "steps": steps}


def write_oracle(hidden: dict[str, object]) -> None:
    certificate_matrix = hidden["certificate_matrix"]
    target = hidden["target"]
    certificate = {
        "format": "exact-block-sdp-certificate-v1",
        "claimed_objective": qstr(target),
        "blocks": [
            {
                "name": BLOCK_NAME,
                "matrix": matrix_strings(certificate_matrix),
                "psd_trace": schur_trace(certificate_matrix),
            }
        ],
    }
    write_json(CONSTRUCTION / "oracle_certificate.json", certificate)
    oracle = {
        "format": "obfuscated-rational-kernel-oracle-v1",
        "seed": SEED,
        "expected_rank": RANK,
        "expected_nullity": NULLITY,
        "kernel_basis": matrix_strings(hidden["kernel"]),
        "complement_basis": matrix_strings(hidden["complement"]),
        "kernel_projector": matrix_strings(hidden["projector"]),
        "support_multipliers": [qstr(value) for value in hidden["multipliers"]],
        "public_mixing": matrix_strings(hidden["mixing"]),
        "fixed_target": qstr(target),
        "certificate": "oracle_certificate.json",
    }
    write_json(CONSTRUCTION / "oracle.json", oracle)


def write_sdpa_sparse(
    path: Path,
    model: dict[str, object],
    digits: int,
    order: Sequence[int],
    scales: Sequence[int],
) -> None:
    constraints = model["constraints"]
    if sorted(order) != list(range(len(constraints))) or len(scales) != len(order):
        raise ValueError("invalid equivalent SDPA row transformation")
    transformed = [(constraints[index], Fraction(scales[position])) for position, index in enumerate(order)]
    lines = [
        str(len(transformed)),
        "1",
        str(SIZE),
        " ".join(
            decimal_string(-Fraction(constraint["expression"]["constant"]) * scale, digits)
            for constraint, scale in transformed
        ),
    ]
    for constraint_index, (constraint, scale) in enumerate(transformed, start=1):
        for item in constraint["expression"]["terms"]:
            coefficient = Fraction(item["coefficient"]) * scale
            if item["row"] != item["col"]:
                coefficient /= 2
            lines.append(
                f"{constraint_index} 1 {item['row'] + 1} {item['col'] + 1} {decimal_string(coefficient, digits)}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_parameters(path: Path, precision_bits: int, epsilon: str) -> None:
    path.write_text(
        "\n".join(
            (
                "2000 unsigned int maxIteration;",
                f"{epsilon} double 0.0 < epsilonStar;",
                "1e3 double 0.0 < lambdaStar;",
                "2.0 double 1.0 < omegaStar;",
                "-1e8 double lowerBound;",
                "1e8 double upperBound;",
                "0.1 double 0.0 <= betaStar < 1.0;",
                "0.3 double 0.0 <= betaBar < 1.0, betaStar <= betaBar;",
                "0.9 double 0.0 < gammaStar < 1.0;",
                f"{epsilon} double 0.0 < epsilonDash;",
                f"{precision_bits} precision;",
            )
        )
        + "\n",
        encoding="ascii",
    )


class BraceParser:
    def __init__(self, text: str):
        self.tokens = re.findall(r"\{|\}|,|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text)
        self.position = 0

    def parse(self):
        if self.position >= len(self.tokens) or self.tokens[self.position] != "{":
            raise ValueError(f"expected '{{' at token {self.position}")
        self.position += 1
        values = []
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token == "}":
                self.position += 1
                return values
            if token == ",":
                self.position += 1
                continue
            if token == "{":
                values.append(self.parse())
            elif NUMBER.fullmatch(token):
                values.append(token[1:] if token.startswith("+") else token)
                self.position += 1
            else:
                raise ValueError(f"unexpected token {token!r}")
        raise ValueError("unterminated brace list")


def parse_ymat(result: Path) -> list[list[str]]:
    text = result.read_text(encoding="utf-8")
    try:
        payload = text.split("yMat =", 1)[1].split("    main loop time", 1)[0]
    except IndexError as error:
        raise ValueError(f"{result} has no complete yMat section") from error
    blocks = BraceParser(payload).parse()
    if len(blocks) != 1:
        raise ValueError(f"expected one yMat block, found {len(blocks)}")
    matrix = blocks[0]
    if len(matrix) != SIZE or any(not isinstance(row, list) or len(row) != SIZE for row in matrix):
        raise ValueError("solver yMat has the wrong shape")
    return matrix


def evaluate_objective(matrix: list[list[str]], objective: dict[str, object], digits: int) -> str:
    value = Fraction(objective["constant"])
    for item in objective["terms"]:
        value += Fraction(item["coefficient"]) * Fraction(matrix[item["row"]][item["col"]])
    return decimal_string(value, digits)


def result_field(text: str, pattern: str, field: str) -> str:
    matches = re.findall(pattern, text, re.MULTILINE)
    if not matches:
        raise ValueError(f"solver result has no {field}")
    return matches[-1].strip()


def result_summary(result: Path) -> dict[str, object]:
    text = result.read_text(encoding="utf-8")
    return {
        "status": result_field(text, r"^phase\.value\s*=\s*(\S+)", "phase status"),
        "iterations": int(result_field(text, r"^\s*Iteration\s*=\s*(\d+)", "iteration count")),
        "runtime_seconds": result_field(
            text,
            r"^\s*total time\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
            "runtime",
        ),
        "primal_feasibility_error": result_field(
            text,
            r"^p\.feas\.error\s*=\s*(\S+)",
            "primal feasibility error",
        ),
        "dual_feasibility_error": result_field(
            text,
            r"^d\.feas\.error\s*=\s*(\S+)",
            "dual feasibility error",
        ),
    }


def solve_run(
    solver: Path,
    model: dict[str, object],
    run_id: str,
    precision_bits: int,
    epsilon: str,
    coefficient_digits: int,
    order: Sequence[int],
    scales: Sequence[int],
    rerun: bool,
) -> dict[str, object]:
    run_dir = NUMERICAL / run_id
    data = run_dir / "problem.dat-s"
    params = run_dir / "sdpa-gmp.params"
    result = run_dir / "result.txt"
    approximate_path = run_dir / "approximate_solution.json"
    record_path = run_dir / "run.json"
    write_sdpa_sparse(data, model, coefficient_digits, order, scales)
    write_parameters(params, precision_bits, epsilon)
    command = [
        str(solver),
        "-ds",
        data.relative_to(REPOSITORY).as_posix(),
        "-o",
        result.relative_to(REPOSITORY).as_posix(),
        "-p",
        params.relative_to(REPOSITORY).as_posix(),
    ]
    if rerun or not result.is_file() or not record_path.is_file():
        completed = subprocess.run(
            command,
            cwd=REPOSITORY,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                f"SDPA-GMP run {run_id} failed with exit {completed.returncode}\n{completed.stdout}"
            )
    matrix = parse_ymat(result)
    approximate = {
        "format": "approximate-block-sdp-solution-v1",
        "numeric_type": "decimal",
        "claimed_precision_digits": PRINTED_DIGITS,
        "claimed_objective": evaluate_objective(matrix, model["objective"]["expression"], PRINTED_DIGITS),
        "blocks": [{"name": BLOCK_NAME, "matrix": matrix}],
    }
    write_json(approximate_path, approximate)
    summary = result_summary(result)
    artifacts = {
        "sdpa_sparse": {
            "path": data.relative_to(INPUT).as_posix(),
            "sha256": sha256(data),
        },
        "parameters": {
            "path": params.relative_to(INPUT).as_posix(),
            "sha256": sha256(params),
        },
        "raw_result": {
            "path": result.relative_to(INPUT).as_posix(),
            "sha256": sha256(result),
        },
        "approximate_solution": {
            "path": approximate_path.relative_to(INPUT).as_posix(),
            "sha256": sha256(approximate_path),
        },
    }
    record = {
        "format": "sdpa-gmp-run-record-v1",
        "id": run_id,
        "solver": {
            "name": "SDPA-GMP",
            "repository": SOLVER_REPOSITORY,
            "commit": SOLVER_COMMIT,
            "binary_sha256": SOLVER_BINARY_SHA256,
        },
        "arguments": command,
        **summary,
        "solver_precision_bits": precision_bits,
        "printed_decimal_digits": PRINTED_DIGITS,
        "coefficient_decimal_digits": coefficient_digits,
        "epsilon": epsilon,
        "equivalent_row_order": list(order),
        "equivalent_row_scales": list(scales),
        "artifacts": artifacts,
    }
    if rerun or not record_path.is_file():
        write_json(record_path, record)
    else:
        preserved = json.loads(record_path.read_text(encoding="utf-8"))
        immutable_fields = {
            key: record[key]
            for key in (
                "format",
                "id",
                "solver",
                "solver_precision_bits",
                "printed_decimal_digits",
                "coefficient_decimal_digits",
                "epsilon",
                "equivalent_row_order",
                "equivalent_row_scales",
                "artifacts",
            )
        }
        if any(preserved.get(key) != value for key, value in immutable_fields.items()):
            raise RuntimeError(f"preserved run record {run_id} no longer matches regenerated artifacts; use --rerun")
        record = preserved
    return {
        "id": run_id,
        "approximate_solution": artifacts["approximate_solution"]["path"],
        "run_record": {
            "path": record_path.relative_to(INPUT).as_posix(),
            "sha256": sha256(record_path),
        },
        **{key: record[key] for key in (
            "solver_precision_bits",
            "printed_decimal_digits",
            "coefficient_decimal_digits",
            "epsilon",
            "equivalent_row_order",
            "equivalent_row_scales",
            "arguments",
            "status",
            "iterations",
            "runtime_seconds",
            "primal_feasibility_error",
            "dual_feasibility_error",
        )},
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--solver",
        type=Path,
        default=Path("/private/tmp/sdpa-gmp-exactification/sdpa_gmp"),
        help="SDPA-GMP executable",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="replace preserved raw run records by executing SDPA-GMP again",
    )
    args = parser.parse_args()
    solver = args.solver.resolve()
    if not solver.is_file():
        raise FileNotFoundError(args.solver)
    if sha256(solver) != SOLVER_BINARY_SHA256:
        raise RuntimeError(f"solver binary hash mismatch: {solver}")
    INPUT.mkdir(parents=True, exist_ok=True)
    NUMERICAL.mkdir(parents=True, exist_ok=True)

    hidden = make_hidden_instance()
    model = hidden["model"]
    write_json(INPUT / "model.json", model)
    write_oracle(hidden)

    count = len(model["constraints"])
    runs = [
        solve_run(
            solver,
            model,
            "p",
            256,
            "1e-35",
            90,
            list(range(count)),
            [1] * count,
            args.rerun,
        ),
        solve_run(
            solver,
            model,
            "2p",
            512,
            "1e-60",
            170,
            [8, 3, 0, 6, 1, 7, 4, 2, 5],
            [2, 3, 5, 7, 11, 13, 17, 19, 23],
            args.rerun,
        ),
    ]
    target = qstr(hidden["target"])
    manifest = {
        "format": "exactification-testcase-v1",
        "id": "obfuscated-rational-kernel",
        "title": "Obfuscated supporting face with a rational kernel",
        "field": "Q",
        "model": "model.json",
        "approximate_solution": "numerical/2p/approximate_solution.json",
        "fixed_objective": target,
        "solution_side": "affine_psd_blocks",
        "source": {
            "solver": {
                "name": "SDPA-GMP",
                "repository": SOLVER_REPOSITORY,
                "commit": SOLVER_COMMIT,
                "binary_sha256": SOLVER_BINARY_SHA256,
            }
        },
        "structure": {
            "block_count": 1,
            "block_sizes": [SIZE],
            "scalar_upper_triangle_variables": SIZE * (SIZE + 1) // 2,
            "equality_constraints": len(model["constraints"]),
        },
        "workflow": {
            "primary_run": "2p",
            "additional_approximate_solutions": ["numerical/p/approximate_solution.json"],
            "numerical_runs": runs,
        },
        "serialization": {
            "exact": "model.json uses canonical numerator/denominator strings over Q",
            "solver_matrix_printed_decimal_digits": PRINTED_DIGITS,
            "note": "Internal solver precision exceeds the 40 digits printed by SDPA-GMP; approximate files claim only printed digits.",
        },
        "files": {
            "model.json": {"sha256": sha256(INPUT / "model.json")},
            **{
                artifact["path"]: {"sha256": artifact["sha256"]}
                for run in runs
                for artifact in run["artifacts"].values()
            },
            **{run["run_record"]["path"]: {"sha256": run["run_record"]["sha256"]} for run in runs},
        },
        "blind_input_policy": {
            "exact_certificate_included": False,
            "exact_kernel_included": False,
            "exact_projector_included": False,
            "construction_mounted": False,
            "previous_attempts_mounted": False,
            "note": "Construction-only generator, supporting identity, and oracle certificate are excluded from blind input.",
        },
        "leakage_policy": {
            "single_model_row_may_expose_supporting_projector": False,
            "supporting_face_requires_fixed_objective_and_generic_equalities": True,
            "construction_self_check_present": True,
        },
        "features": [
            "rational_coefficients",
            "rank_deficient",
            "rational_kernel_subspace",
            "obfuscated_supporting_face",
            "two_precision_runs",
            "independently_scaled_solver_projections",
            "nonunique_relative_interior",
        ],
    }
    write_json(INPUT / "manifest.json", manifest)
    print(f"generated {CASE_ROOT}")
    for run in runs:
        print(
            f"{run['id']}: precision={run['solver_precision_bits']} bits "
            f"status={run['status']} runtime={run['runtime_seconds']}s "
            f"approx_sha256={run['artifacts']['approximate_solution']['sha256']}"
        )


if __name__ == "__main__":
    main()
