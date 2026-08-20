#!/usr/bin/env python3
"""Audit the generated obfuscated rational-kernel fixture."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import sympy as sp


CASE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = CASE_ROOT.parents[1]
INPUT = CASE_ROOT / "input"
CONSTRUCTION = CASE_ROOT / "construction"
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
RATIONAL = re.compile(r"(?:0|-?[1-9]\d*)(?:/[1-9]\d*)?\Z")
SOLVER_REPOSITORY = "https://github.com/nakatamaho/sdpa-gmp.git"
SOLVER_COMMIT = "ca110db5ea1cc46e811b70dfea9cbb25db74448d"
SOLVER_BINARY_SHA256 = "c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0"


def strict_json(path: Path):
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AssertionError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact(value: str) -> Fraction:
    if not isinstance(value, str) or not RATIONAL.fullmatch(value):
        raise AssertionError(f"noncanonical rational spelling: {value!r}")
    parsed = Fraction(value)
    if str(parsed) != value:
        raise AssertionError(f"unreduced rational spelling: {value!r}")
    return parsed


def spq(value: str) -> sp.Rational:
    parsed = exact(value)
    return sp.Rational(parsed.numerator, parsed.denominator)


def mpq(value: str) -> mp.mpf:
    parsed = exact(value)
    return mp.mpf(parsed.numerator) / parsed.denominator


def expression_matrix(expression: dict, size: int) -> sp.Matrix:
    if set(expression) != {"constant", "terms"}:
        raise AssertionError("affine expression has unexpected fields")
    exact(expression["constant"])
    matrix = sp.zeros(size)
    seen = set()
    for item in expression["terms"]:
        if set(item) != {"block", "row", "col", "coefficient"}:
            raise AssertionError("affine term has unexpected fields")
        if item["block"] != "moment_matrix":
            raise AssertionError("unexpected block reference")
        row, column = item["row"], item["col"]
        if isinstance(row, bool) or isinstance(column, bool) or not (0 <= row <= column < size):
            raise AssertionError("noncanonical matrix coordinate")
        if (row, column) in seen:
            raise AssertionError("duplicate affine coordinate")
        seen.add((row, column))
        coefficient = spq(item["coefficient"])
        if row != column:
            coefficient /= 2
        matrix[row, column] = matrix[column, row] = coefficient
    return matrix


def matrix_from_strings(value: list[list[str]]) -> sp.Matrix:
    return sp.Matrix([[spq(item) for item in row] for row in value])


def upper_vector(matrix: sp.Matrix) -> sp.Matrix:
    return sp.Matrix([matrix[row, column] for row in range(matrix.rows) for column in range(row, matrix.cols)])


def proportional(left: sp.Matrix, right: sp.Matrix) -> bool:
    left_values = list(left)
    right_values = list(right)
    pivot = next((index for index, value in enumerate(right_values) if value), None)
    if pivot is None:
        raise AssertionError("zero hidden projector")
    ratio = left_values[pivot] / right_values[pivot]
    return ratio != 0 and all(a == ratio * b for a, b in zip(left_values, right_values))


def indefinite_witness(matrix: sp.Matrix) -> tuple[int, int] | None:
    for row in range(matrix.rows):
        for column in range(row + 1, matrix.cols):
            if matrix[row, row] * matrix[column, column] - matrix[row, column] ** 2 < 0:
                return row, column
    return None


def validate_model(model: dict) -> tuple[list[sp.Matrix], sp.Matrix]:
    if set(model) != {"format", "blocks", "constraints", "objective"}:
        raise AssertionError("model top-level fields are not v1-exact")
    if model["format"] != "exact-block-sdp-model-v1":
        raise AssertionError("wrong model format")
    if model["blocks"] != [{"name": "moment_matrix", "size": 10}]:
        raise AssertionError("unexpected block declaration")
    constraints = model["constraints"]
    if len(constraints) != 9 or constraints[-1]["name"] != "fixed_objective":
        raise AssertionError("expected eight generic rows and one fixed objective")
    names = set()
    matrices = []
    for constraint in constraints:
        if set(constraint) != {"name", "sense", "expression"} or constraint["sense"] != "eq":
            raise AssertionError("constraint is not a v1 equality")
        if constraint["name"] in names:
            raise AssertionError("duplicate constraint name")
        names.add(constraint["name"])
        matrix = expression_matrix(constraint["expression"], 10)
        if len(constraint["expression"]["terms"]) < 50:
            raise AssertionError(f"public row {constraint['name']} is not dense")
        matrices.append(matrix)
    objective = model["objective"]
    if set(objective) != {"sense", "expression"} or objective["sense"] != "minimize":
        raise AssertionError("unexpected objective")
    objective_matrix = expression_matrix(objective["expression"], 10)
    if objective_matrix != matrices[-1]:
        raise AssertionError("fixed-objective row differs from the objective")
    return matrices[:-1], objective_matrix


def validate_approximate(path: Path, model: dict) -> tuple[mp.matrix, list[mp.mpf], mp.matrix, mp.mpf]:
    value = strict_json(path)
    if set(value) != {"format", "numeric_type", "claimed_precision_digits", "claimed_objective", "blocks"}:
        raise AssertionError(f"unexpected approximate-solution fields in {path.name}")
    if value["format"] != "approximate-block-sdp-solution-v1" or value["numeric_type"] != "decimal":
        raise AssertionError(f"wrong approximate format in {path.name}")
    if value["claimed_precision_digits"] != 40 or not NUMBER.fullmatch(value["claimed_objective"]):
        raise AssertionError(f"dishonest printed precision metadata in {path.name}")
    if len(value["blocks"]) != 1 or value["blocks"][0]["name"] != "moment_matrix":
        raise AssertionError(f"wrong blocks in {path.name}")
    raw = value["blocks"][0]["matrix"]
    if len(raw) != 10 or any(len(row) != 10 for row in raw):
        raise AssertionError(f"wrong matrix shape in {path.name}")
    if any(not isinstance(item, str) or not NUMBER.fullmatch(item) for row in raw for item in row):
        raise AssertionError(f"nondecimal matrix entry in {path.name}")
    if any(raw[row][column] != raw[column][row] for row in range(10) for column in range(10)):
        raise AssertionError(f"printed matrix is not symmetric in {path.name}")
    matrix = mp.matrix([[mp.mpf(item) for item in row] for row in raw])

    residuals = []
    for constraint in model["constraints"]:
        expression = constraint["expression"]
        residual = mpq(expression["constant"])
        for item in expression["terms"]:
            residual += mpq(item["coefficient"]) * matrix[item["row"], item["col"]]
        residuals.append(abs(residual))
    if max(residuals) >= mp.mpf("1e-30"):
        raise AssertionError(f"affine residual too large in {path.name}: {max(residuals)}")

    eigenvalues, eigenvectors = mp.eigsy(matrix)
    spectrum = [eigenvalues[index] for index in range(10)]
    zero_scale = max(abs(value) for value in spectrum[:3])
    if zero_scale >= mp.mpf("1e-30") or spectrum[3] <= mp.mpf("1e-2"):
        raise AssertionError(f"unstable singular spectrum in {path.name}")
    return matrix, spectrum, eigenvectors[:, :3], max(residuals)


def signed_permutation_distance(rotation: mp.matrix) -> mp.mpf:
    best = mp.inf
    for permutation in itertools.permutations(range(rotation.rows)):
        for signs in itertools.product((-1, 1), repeat=rotation.rows):
            distance = mp.mpf(0)
            for row in range(rotation.rows):
                for column in range(rotation.cols):
                    target = signs[row] if column == permutation[row] else 0
                    distance += (rotation[row, column] - target) ** 2
            best = min(best, mp.sqrt(distance))
    return best


def main() -> None:
    mp.mp.dps = 100
    manifest = strict_json(INPUT / "manifest.json")
    model = strict_json(INPUT / "model.json")
    oracle = strict_json(CONSTRUCTION / "oracle.json")
    if manifest["format"] != "exactification-testcase-v1" or manifest["id"] != CASE_ROOT.name:
        raise AssertionError("manifest identity mismatch")
    if manifest["field"] != "Q" or manifest["solution_side"] != "affine_psd_blocks":
        raise AssertionError("manifest field/solution side mismatch")
    target = exact(manifest["fixed_objective"])
    if target != exact(oracle["fixed_target"]):
        raise AssertionError("public fixed target differs from construction target")
    if manifest.get("source", {}).get("solver") != {
        "name": "SDPA-GMP",
        "repository": SOLVER_REPOSITORY,
        "commit": SOLVER_COMMIT,
        "binary_sha256": SOLVER_BINARY_SHA256,
    }:
        raise AssertionError("solver source provenance mismatch")

    for name, metadata in manifest["files"].items():
        path = INPUT / name
        if not path.is_file() or sha256(path) != metadata["sha256"]:
            raise AssertionError(f"hash mismatch for {name}")
    runs = manifest["workflow"]["numerical_runs"]
    if [(run["id"], run["solver_precision_bits"], run["printed_decimal_digits"]) for run in runs] != [
        ("p", 256, 40),
        ("2p", 512, 40),
    ]:
        raise AssertionError("p/2p precision metadata mismatch")
    if manifest["approximate_solution"] != "numerical/2p/approximate_solution.json":
        raise AssertionError("2p run is not the primary approximate solution")
    if manifest["workflow"]["additional_approximate_solutions"] != [
        "numerical/p/approximate_solution.json"
    ]:
        raise AssertionError("p run is not routed as the additional approximation")
    for run in runs:
        record_path = INPUT / run["run_record"]["path"]
        if sha256(record_path) != run["run_record"]["sha256"]:
            raise AssertionError(f"run-record hash mismatch for {run['id']}")
        record = strict_json(record_path)
        if record["format"] != "sdpa-gmp-run-record-v1" or record["id"] != run["id"]:
            raise AssertionError(f"bad preserved run record for {run['id']}")
        if record["solver"] != manifest["source"]["solver"]:
            raise AssertionError(f"solver provenance mismatch in run {run['id']}")
        for field in (
            "arguments",
            "status",
            "iterations",
            "runtime_seconds",
            "primal_feasibility_error",
            "dual_feasibility_error",
            "solver_precision_bits",
            "printed_decimal_digits",
            "coefficient_decimal_digits",
            "epsilon",
            "equivalent_row_order",
            "equivalent_row_scales",
            "artifacts",
        ):
            if run[field] != record[field]:
                raise AssertionError(f"manifest/run-record mismatch for {run['id']} field {field}")
        arguments = record["arguments"]
        public_prefix = INPUT.relative_to(REPOSITORY).as_posix()
        expected_suffix = [
            "-ds",
            f"{public_prefix}/{record['artifacts']['sdpa_sparse']['path']}",
            "-o",
            f"{public_prefix}/{record['artifacts']['raw_result']['path']}",
            "-p",
            f"{public_prefix}/{record['artifacts']['parameters']['path']}",
        ]
        if not isinstance(arguments, list) or arguments[1:] != expected_suffix:
            raise AssertionError(f"inexact solver argument array for {run['id']}")
        solver_path = Path(arguments[0])
        if solver_path.is_file() and sha256(solver_path) != SOLVER_BINARY_SHA256:
            raise AssertionError(f"solver binary hash mismatch for {run['id']}")
        for artifact in record["artifacts"].values():
            artifact_path = INPUT / artifact["path"]
            if sha256(artifact_path) != artifact["sha256"]:
                raise AssertionError(f"artifact hash mismatch for {artifact['path']}")
            if manifest["files"].get(artifact["path"]) != {"sha256": artifact["sha256"]}:
                raise AssertionError(f"manifest omits artifact hash for {artifact['path']}")
        result = INPUT / record["artifacts"]["raw_result"]["path"]
        params = INPUT / record["artifacts"]["parameters"]["path"]
        result_text = result.read_text(encoding="utf-8")
        if f"phase.value = {record['status']}" not in result_text or record["status"] != "pdFEAS":
            raise AssertionError(f"solver did not reach pdFEAS for {run['id']}")
        if f"{run['solver_precision_bits']} precision;" not in params.read_text(encoding="ascii"):
            raise AssertionError(f"solver precision file mismatch for {run['id']}")

    public_rows, objective_matrix = validate_model(model)
    projector = matrix_from_strings(oracle["kernel_projector"])
    if projector.T != projector or projector * projector != projector or projector.rank() != 3:
        raise AssertionError("construction projector is invalid")
    for name, matrix in [(f"moment_{index:02d}", value) for index, value in enumerate(public_rows)] + [
        ("objective", objective_matrix)
    ]:
        if proportional(matrix, projector):
            raise AssertionError(f"public coefficient {name} proportionally reveals the projector")
        if indefinite_witness(matrix) is None:
            raise AssertionError(f"public coefficient {name} is not certifiably indefinite")

    multipliers = [spq(value) for value in oracle["support_multipliers"]]
    if any(value == 0 for value in multipliers):
        raise AssertionError("supporting combination omits a public equality")
    reconstructed = objective_matrix + sum(
        (coefficient * matrix for coefficient, matrix in zip(multipliers, public_rows)), sp.zeros(10)
    )
    if reconstructed != projector:
        raise AssertionError("supporting projector identity failed")
    columns = sp.Matrix.hstack(upper_vector(objective_matrix), *(upper_vector(matrix) for matrix in public_rows))
    if columns.rank() != 9:
        raise AssertionError("supporting representation is not unique")
    solution = columns.gauss_jordan_solve(upper_vector(projector))[0]
    expected = sp.Matrix([1, *multipliers])
    if solution != expected or any(value == 0 for value in solution):
        raise AssertionError("supporting face does not require every advertised row")
    constant = spq(model["constraints"][-1]["expression"]["constant"])
    for multiplier, constraint in zip(multipliers, model["constraints"][:-1]):
        constant += multiplier * spq(constraint["expression"]["constant"])
    if constant != 0:
        raise AssertionError("supporting affine constants do not cancel")

    verifier = subprocess.run(
        [
            sys.executable,
            "-m",
            "verify",
            "check",
            str(INPUT / "model.json"),
            str(CONSTRUCTION / "oracle_certificate.json"),
            "--json",
        ],
        cwd=REPOSITORY,
        check=False,
        capture_output=True,
        text=True,
    )
    if verifier.returncode:
        raise AssertionError(f"oracle certificate failed verifier: {verifier.stderr or verifier.stdout}")
    verifier_report = json.loads(verifier.stdout)
    if verifier_report.get("status") != "verified" or verifier_report.get("objective") != str(target):
        raise AssertionError("unexpected oracle verifier report")

    p_matrix, p_spectrum, p_kernel, p_residual = validate_approximate(
        INPUT / runs[0]["approximate_solution"], model
    )
    q_matrix, q_spectrum, q_kernel, q_residual = validate_approximate(
        INPUT / runs[1]["approximate_solution"], model
    )
    if mp.norm(p_matrix - q_matrix, p="inf") <= mp.mpf("1e-15"):
        raise AssertionError("independent numerical runs are effectively identical")
    for index in range(3, 10):
        relative = abs(p_spectrum[index] - q_spectrum[index]) / max(1, abs(q_spectrum[index]))
        if relative >= mp.mpf("1e-9"):
            raise AssertionError(f"positive spectrum is unstable at index {index}")
    cosines = mp.svd(p_kernel.T * q_kernel, compute_uv=False)
    minimum_cosine = min(cosines[index] for index in range(3))
    principal_sine = mp.sqrt(max(mp.mpf(0), 1 - minimum_cosine**2))
    if principal_sine >= mp.mpf("1e-30"):
        raise AssertionError(f"kernel principal angle is unstable: sine={principal_sine}")
    basis_rotation = p_kernel.T * q_kernel
    permutation_distance = signed_permutation_distance(basis_rotation)
    if permutation_distance <= mp.mpf("0.1"):
        raise AssertionError("p/2p eigensolver kernels did not exhibit a nontrivial basis rotation")

    public_names = {
        path.relative_to(INPUT).as_posix()
        for path in INPUT.rglob("*")
        if path.is_file()
    }
    expected_public = {"README.md", "manifest.json", *manifest["files"]}
    if public_names != expected_public:
        raise AssertionError(f"unexpected or unhashed public files: {sorted(public_names ^ expected_public)}")

    print("ok: exact model and construction-only rational certificate verified")
    print("ok: all nine public coefficient matrices are dense, indefinite, and not proportional to the projector")
    print("ok: unique supporting identity uses objective plus all eight generic equalities")
    print("ok: complete p/2p solver bundles, source commit, argument arrays, and manifest hashes verified")
    print(
        "ok: p/2p nullity=3, max affine residuals="
        f"{mp.nstr(p_residual, 6)}/{mp.nstr(q_residual, 6)}, "
        f"principal-angle sine={mp.nstr(principal_sine, 6)}, "
        f"signed-permutation basis distance={mp.nstr(permutation_distance, 6)}"
    )
    print(
        "ok: positive spectra p/2p="
        + ",".join(mp.nstr(value, 8) for value in p_spectrum[3:])
        + " / "
        + ",".join(mp.nstr(value, 8) for value in q_spectrum[3:])
    )


if __name__ == "__main__":
    main()
