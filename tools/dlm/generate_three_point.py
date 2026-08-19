#!/usr/bin/env python3
"""Generate the rational DLM Theorem 4.3 three-point SDP.

This is a dependency-free Python port of the SDP construction in the
ancillary ``ThreePoint.jl`` and the sparse SDPA serialization in
``SemidefiniteProgramming.jl`` accompanying

    Dostert, de Laat, and Moustrou,
    Exact Semidefinite Programming Bounds for Packing Problems,
    SIAM J. Optim. 31 (2021), https://doi.org/10.1137/20M1351692.

The port intentionally constructs only the *input* feasibility problem.  It
does not read, translate, or ship the authors' serialized exact solution.
All construction arithmetic is rational.  Decimal conversion happens only
when writing the convenience ``.dat-s`` file consumed by SDPA-GMP.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence


Exp = tuple[int, int, int]
ZERO_EXP: Exp = (0, 0, 0)


def q(value: int | Fraction) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(value)


def qstr(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def decimal_string(value: Fraction, digits: int) -> str:
    """Return a deterministic, sufficiently precise SDPA-GMP decimal."""
    if value.denominator == 1:
        return str(value.numerator)
    with localcontext() as context:
        context.prec = digits + 20
        result = Decimal(value.numerator) / Decimal(value.denominator)
        return format(result, f".{digits}E")


@dataclass
class Affine:
    """A sparse affine expression in the upper triangles of all PSD blocks."""

    constant: Fraction
    coefficients: dict[int, Fraction]

    @classmethod
    def scalar(cls, value: int | Fraction) -> "Affine":
        return cls(q(value), {})

    @classmethod
    def variable(cls, index: int) -> "Affine":
        return cls(Fraction(0), {index: Fraction(1)})

    def cleaned(self) -> "Affine":
        return Affine(
            self.constant,
            {index: value for index, value in self.coefficients.items() if value},
        )

    def __add__(self, other: int | Fraction | "Affine") -> "Affine":
        other = as_affine(other)
        coefficients = dict(self.coefficients)
        for index, value in other.coefficients.items():
            coefficients[index] = coefficients.get(index, Fraction(0)) + value
            if not coefficients[index]:
                del coefficients[index]
        return Affine(self.constant + other.constant, coefficients)

    __radd__ = __add__

    def __neg__(self) -> "Affine":
        return Affine(-self.constant, {i: -v for i, v in self.coefficients.items()})

    def __sub__(self, other: int | Fraction | "Affine") -> "Affine":
        return self + (-as_affine(other))

    def __rsub__(self, other: int | Fraction | "Affine") -> "Affine":
        return as_affine(other) - self

    def __mul__(self, other: int | Fraction | "Affine") -> "Affine":
        other = as_affine(other)
        if self.coefficients and other.coefficients:
            raise ValueError("the SDP construction attempted a nonlinear matrix product")
        if other.coefficients:
            return Affine(
                self.constant * other.constant,
                {i: self.constant * v for i, v in other.coefficients.items()},
            ).cleaned()
        return Affine(
            self.constant * other.constant,
            {i: other.constant * v for i, v in self.coefficients.items()},
        ).cleaned()

    __rmul__ = __mul__

    def is_zero(self) -> bool:
        return not self.constant and not self.coefficients


def as_affine(value: int | Fraction | Affine) -> Affine:
    return value if isinstance(value, Affine) else Affine.scalar(value)


class Poly:
    """Sparse polynomial in ``u,v,t`` with affine rational coefficients."""

    def __init__(self, terms: Mapping[Exp, Affine] | None = None):
        self.terms: dict[Exp, Affine] = {}
        for exponent, coefficient in (terms or {}).items():
            coefficient = as_affine(coefficient).cleaned()
            if not coefficient.is_zero():
                self.terms[exponent] = coefficient

    @classmethod
    def scalar(cls, value: int | Fraction | Affine) -> "Poly":
        value = as_affine(value)
        return cls({ZERO_EXP: value}) if not value.is_zero() else cls()

    @classmethod
    def monomial(
        cls, exponent: Exp, coefficient: int | Fraction | Affine = 1
    ) -> "Poly":
        return cls({exponent: as_affine(coefficient)})

    def coefficient(self, exponent: Exp) -> Affine:
        return self.terms.get(exponent, Affine.scalar(0))

    def __add__(self, other: int | Fraction | Affine | "Poly") -> "Poly":
        other = as_poly(other)
        terms = dict(self.terms)
        for exponent, coefficient in other.terms.items():
            combined = terms.get(exponent, Affine.scalar(0)) + coefficient
            if combined.is_zero():
                terms.pop(exponent, None)
            else:
                terms[exponent] = combined
        return Poly(terms)

    __radd__ = __add__

    def __neg__(self) -> "Poly":
        return Poly({exponent: -coefficient for exponent, coefficient in self.terms.items()})

    def __sub__(self, other: int | Fraction | Affine | "Poly") -> "Poly":
        return self + (-as_poly(other))

    def __rsub__(self, other: int | Fraction | Affine | "Poly") -> "Poly":
        return as_poly(other) - self

    def __mul__(self, other: int | Fraction | Affine | "Poly") -> "Poly":
        other = as_poly(other)
        terms: dict[Exp, Affine] = {}
        for left_exp, left_coeff in self.terms.items():
            for right_exp, right_coeff in other.terms.items():
                exponent = tuple(a + b for a, b in zip(left_exp, right_exp))
                coefficient = left_coeff * right_coeff
                combined = terms.get(exponent, Affine.scalar(0)) + coefficient
                if combined.is_zero():
                    terms.pop(exponent, None)
                else:
                    terms[exponent] = combined
        return Poly(terms)

    __rmul__ = __mul__

    def __pow__(self, exponent: int) -> "Poly":
        if exponent < 0:
            raise ValueError("negative polynomial powers are unsupported")
        result = Poly.scalar(1)
        factor = self
        power = exponent
        while power:
            if power & 1:
                result = result * factor
            factor = factor * factor
            power >>= 1
        return result

    def total_degree(self) -> int:
        return max((sum(exponent) for exponent in self.terms), default=-1)

    def specialize_diagonal(self) -> "Poly":
        """Apply ``(u,v,t) -> (u,u,1)``."""
        result = Poly()
        for (u_exp, v_exp, _), coefficient in self.terms.items():
            result += Poly.monomial((u_exp + v_exp, 0, 0), coefficient)
        return result

    def evaluate_one(self) -> Affine:
        return sum(self.terms.values(), Affine.scalar(0))


def as_poly(value: int | Fraction | Affine | Poly) -> Poly:
    return value if isinstance(value, Poly) else Poly.scalar(value)


U = Poly.monomial((1, 0, 0))
V = Poly.monomial((0, 1, 0))
T = Poly.monomial((0, 0, 1))


def gegenbauer_coefficients(k: int, n: int) -> list[Fraction]:
    """Coefficients of the normalized dimension-n Gegenbauer polynomial."""
    basis: list[list[Fraction]] = [[Fraction(1)]]
    if k == 0:
        return basis[0]
    basis.append([Fraction(0), Fraction(1)])
    for degree in range(2, k + 1):
        first = Fraction(2 * degree + n - 4, degree + n - 3)
        second = Fraction(degree - 1, degree + n - 3)
        previous = [Fraction(0)] + [first * c for c in basis[-1]]
        older = [second * c for c in basis[-2]]
        older.extend(Fraction(0) for _ in range(len(previous) - len(older)))
        basis.append([a - b for a, b in zip(previous, older)])
    return basis[-1]


def gegenbauer(k: int, n: int, variable: Poly) -> Poly:
    return sum(
        (coefficient * variable**degree
         for degree, coefficient in enumerate(gegenbauer_coefficients(k, n))),
        Poly(),
    )


def q_polynomial(n: int, k: int, u: Poly, v: Poly, t: Poly) -> Poly:
    result = Poly()
    uv_radial = (1 - u**2) * (1 - v**2)
    residual = t - u * v
    for degree, coefficient in enumerate(gegenbauer_coefficients(k, n)):
        if coefficient:
            result += (
                coefficient
                * uv_radial ** ((k - degree) // 2)
                * residual**degree
            )
    return result


def y_matrix(n: int, d: int, k: int, u: Poly, v: Poly, t: Poly) -> list[list[Poly]]:
    factor = q_polynomial(n - 1, k, u, v, t)
    size = d - k + 1
    return [
        [factor * u**i * v**j for j in range(size)]
        for i in range(size)
    ]


def matrix_sum(matrices: Sequence[list[list[Poly]]]) -> list[list[Poly]]:
    size = len(matrices[0])
    return [
        [sum((matrix[i][j] for matrix in matrices), Poly()) for j in range(size)]
        for i in range(size)
    ]


def sbar_matrix(n: int, d: int, k: int, u: Poly, v: Poly, t: Poly) -> list[list[Poly]]:
    permutations = (
        (u, v, t),
        (u, t, v),
        (v, u, t),
        (v, t, u),
        (t, u, v),
        (t, v, u),
    )
    return [
        [Fraction(1, 6) * entry for entry in row]
        for row in matrix_sum([y_matrix(n, d, k, *p) for p in permutations])
    ]


def quadform(matrix: list[list[Affine]], vector: Sequence[Poly]) -> Poly:
    result = Poly()
    for i in range(len(vector)):
        for j in range(i, len(vector)):
            result += (1 if i == j else 2) * vector[i] * vector[j] * matrix[i][j]
    return result


def trace_inner(matrix: list[list[Affine]], polynomial_matrix: list[list[Poly]]) -> Poly:
    result = Poly()
    for i in range(len(matrix)):
        for j in range(len(matrix)):
            result += polynomial_matrix[i][j] * matrix[i][j]
    return result


@dataclass(frozen=True)
class VariableLocation:
    block: int
    row: int
    column: int


@dataclass
class Block:
    index: int
    size: int
    role: str
    matrix: list[list[Affine]]


class SDPBuilder:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.variable_locations: dict[int, VariableLocation] = {}
        self.constraints: list[tuple[str, Affine]] = []
        self.objective = Affine.scalar(0)
        self._next_variable = 1

    def add_block(self, size: int, role: str) -> list[list[Affine]]:
        block_index = len(self.blocks) + 1
        matrix = [[Affine.scalar(0) for _ in range(size)] for _ in range(size)]
        for column in range(1, size + 1):
            for row in range(1, column + 1):
                index = self._next_variable
                self._next_variable += 1
                variable = Affine.variable(index)
                matrix[row - 1][column - 1] = variable
                matrix[column - 1][row - 1] = variable
                self.variable_locations[index] = VariableLocation(
                    block_index, row, column
                )
        self.blocks.append(Block(block_index, size, role, matrix))
        return matrix

    def add_constraint(self, name: str, expression: Affine) -> None:
        self.constraints.append((name, expression.cleaned()))

    @property
    def variable_count(self) -> int:
        return self._next_variable - 1


def invariant_basis(max_degree: int) -> list[Poly]:
    theta1 = U + V + T
    theta2 = U * V + U * T + V * T
    theta3 = U * V * T
    return [
        theta1**l * theta2**k * theta3**m
        for l in range(max_degree + 1)
        for k in range((max_degree - l) // 2 + 1)
        for m in range((max_degree - l - 2 * k) // 3 + 1)
    ]


def v_rows(basis: Sequence[Poly], degree_limit: int, v_matrix: Sequence[Sequence[Poly]]) -> list[tuple[Poly, int]]:
    rows: list[tuple[Poly, int]] = []
    for polynomial in basis:
        for component in range(2):
            diagonal = polynomial * polynomial * v_matrix[component][component]
            if diagonal.total_degree() <= degree_limit:
                rows.append((polynomial, component))
    return rows


def expanded_v_matrix(rows: Sequence[tuple[Poly, int]], v_matrix: Sequence[Sequence[Poly]]) -> list[list[Poly]]:
    return [
        [left_poly * right_poly * v_matrix[left_component][right_component]
         for right_poly, right_component in rows]
        for left_poly, left_component in rows
    ]


def assert_symmetric(polynomial: Poly) -> None:
    for exponent, coefficient in polynomial.terms.items():
        for permuted in set(itertools.permutations(exponent)):
            if polynomial.coefficient(permuted) != coefficient:
                raise AssertionError(
                    f"triple identity is not symmetric at {exponent}/{permuted}"
                )


def construct_three_point_sdp(
    n: int = 4,
    d: int = 6,
    costheta: Fraction = Fraction(1, 6),
    objective: Fraction = Fraction(10),
    truncation_degree: int | None = None,
) -> tuple[SDPBuilder, dict[str, object]]:
    """Construct the fixed-objective rational SDP from ``threepointsdp``."""
    N = d if truncation_degree is None else truncation_degree
    builder = SDPBuilder()

    bound_scalar = builder.add_block(1, "bound_scalar.B")
    a_blocks = [builder.add_block(1, f"gegenbauer_scalar.a_{k}") for k in range(1, d + 1)]
    f_blocks = [builder.add_block(d - k + 1, f"three_point_kernel.F_{k}") for k in range(d + 1)]
    single_sos = [
        builder.add_block(N + 1, "single_interval_sos.q_0"),
        builder.add_block(N, "single_interval_sos.q_1"),
    ]

    mu = [
        [U**k for k in range(N + 1)],
        [U**k for k in range(N)],
    ]
    muvt = [invariant_basis(N - shift) for shift in range(7)]

    theta1 = U + V + T
    theta2 = U * V + U * T + V * T
    theta3 = U * V * T
    pi2 = (
        theta1**2 * theta2**2
        - 4 * theta2**3
        - 4 * theta1**3 * theta3
        + 18 * theta1 * theta2 * theta3
        - 27 * theta3**2
    )
    representation_v = [
        [2 * theta1**2 - 6 * theta2, -theta1 * theta2 + 9 * theta3],
        [-theta1 * theta2 + 9 * theta3, 2 * theta2**2 - 6 * theta1 * theta3],
    ]

    filtered_rows = [
        v_rows(muvt[1], 2 * N, representation_v),
        v_rows(muvt[2], 2 * N - 2, representation_v),
        v_rows(muvt[3], 2 * N - 4, representation_v),
        v_rows(muvt[4], 2 * N - 6, representation_v),
    ]
    expanded_v = [expanded_v_matrix(rows, representation_v) for rows in filtered_rows]

    invariant_blocks: list[object] = [
        builder.add_block(len(muvt[0]), "triple_sos.pi1.s_0"),
        [
            builder.add_block(len(muvt[1]), "triple_sos.pi1.s_1"),
            builder.add_block(len(muvt[1]), "triple_sos.pi1.gram_determinant"),
        ],
        builder.add_block(len(muvt[2]), "triple_sos.pi1.s_2"),
        [
            builder.add_block(len(muvt[3]), "triple_sos.pi1.s_3"),
            builder.add_block(len(muvt[3]), "triple_sos.pi2.s_0"),
        ],
        [
            builder.add_block(len(muvt[4]), "triple_sos.pi2.s_1"),
            builder.add_block(len(muvt[4]), "triple_sos.pi2.gram_determinant"),
        ],
        builder.add_block(len(muvt[5]), "triple_sos.pi2.s_2"),
        builder.add_block(len(muvt[6]), "triple_sos.pi2.s_3"),
        builder.add_block(len(filtered_rows[0]), "triple_sos.pi3.s_0"),
        [
            builder.add_block(len(filtered_rows[1]), "triple_sos.pi3.s_1"),
            builder.add_block(len(filtered_rows[1]), "triple_sos.pi3.gram_determinant"),
        ],
        builder.add_block(len(filtered_rows[2]), "triple_sos.pi3.s_2"),
        builder.add_block(len(filtered_rows[3]), "triple_sos.pi3.s_3"),
    ]

    f_polynomial = sum(
        (
            trace_inner(
                f_blocks[k],
                sbar_matrix(n, d, k, U, V, T),
            )
            for k in range(d + 1)
        ),
        Poly(),
    )

    single_constraint = 3 * f_polynomial.specialize_diagonal()
    for k in range(1, d + 1):
        single_constraint += gegenbauer(k, n, U) * a_blocks[k - 1][0][0]
    single_constraint += 1 + quadform(single_sos[0], mu[0])
    single_constraint += (U + 1) * (costheta - U) * quadform(single_sos[1], mu[1])

    pu = (U + 1) * (costheta - U)
    pv = (V + 1) * (costheta - V)
    pt = (T + 1) * (costheta - T)
    gram_determinant = 1 + 2 * U * V * T - U**2 - V**2 - T**2

    # The indexing below mirrors suvt[1], ..., suvt[11] in ThreePoint.jl.
    triple_constraint = f_polynomial
    triple_constraint += quadform(invariant_blocks[0], muvt[0])
    triple_constraint += pi2 * quadform(invariant_blocks[3][1], muvt[3])
    triple_constraint += trace_inner(invariant_blocks[7], expanded_v[0])

    triple_constraint += (pu + pv + pt) * (
        quadform(invariant_blocks[1][0], muvt[1])
        + pi2 * quadform(invariant_blocks[4][0], muvt[4])
        + trace_inner(invariant_blocks[8][0], expanded_v[1])
    )
    triple_constraint += (pu * pv + pu * pt + pv * pt) * (
        quadform(invariant_blocks[2], muvt[2])
        + pi2 * quadform(invariant_blocks[5], muvt[5])
        + trace_inner(invariant_blocks[9], expanded_v[2])
    )
    triple_constraint += pu * pv * pt * (
        quadform(invariant_blocks[3][0], muvt[3])
        + pi2 * quadform(invariant_blocks[6], muvt[6])
        + trace_inner(invariant_blocks[10], expanded_v[3])
    )
    triple_constraint += gram_determinant * (
        quadform(invariant_blocks[1][1], muvt[1])
        + pi2 * quadform(invariant_blocks[4][1], muvt[4])
        + trace_inner(invariant_blocks[8][1], expanded_v[1])
    )

    assert_symmetric(triple_constraint)
    representative_exponents = sorted(
        (
            exponent
            for exponent in triple_constraint.terms
            if exponent[0] <= exponent[1] <= exponent[2]
        ),
        key=lambda exponent: (sum(exponent), exponent),
    )
    for exponent in representative_exponents:
        builder.add_constraint(
            f"triple.coefficient.u{exponent[0]}v{exponent[1]}t{exponent[2]}",
            triple_constraint.coefficient(exponent),
        )

    if any(v_exp or t_exp for _, v_exp, t_exp in single_constraint.terms):
        raise AssertionError("single constraint did not specialize to one variable")
    single_degree = single_constraint.total_degree()
    for degree in range(single_degree + 1):
        builder.add_constraint(
            f"single.coefficient.u{degree}",
            single_constraint.coefficient((degree, 0, 0)),
        )

    objective_expression = Affine.scalar(1)
    objective_expression += bound_scalar[0][0]
    objective_expression += sum((block[0][0] for block in a_blocks), Affine.scalar(0))
    objective_expression += trace_inner(
        f_blocks[0], sbar_matrix(n, d, 0, Poly.scalar(1), Poly.scalar(1), Poly.scalar(1))
    ).evaluate_one()
    builder.objective = objective_expression
    builder.add_constraint("fixed_objective", objective_expression - objective)

    metadata: dict[str, object] = {
        "parameters": {
            "n": n,
            "d": d,
            "N": N,
            "cos_theta": qstr(costheta),
            "fixed_objective": qstr(objective),
        },
        "source_logic": {
            "muvt_basis_sizes": [len(basis) for basis in muvt],
            "filtered_pi3_row_sizes": [len(rows) for rows in filtered_rows],
            "triple_representative_coefficients": len(representative_exponents),
            "single_polynomial_degree": single_degree,
        },
    }
    return builder, metadata


def exact_model(builder: SDPBuilder, metadata: Mapping[str, object]) -> dict[str, object]:
    def expression_object(expression: Affine) -> dict[str, object]:
        terms = []
        for variable_index, coefficient in sorted(expression.coefficients.items()):
            location = builder.variable_locations[variable_index]
            terms.append(
                {
                    "block": builder.blocks[location.block - 1].role,
                    "row": location.row - 1,
                    "col": location.column - 1,
                    "coefficient": qstr(coefficient),
                }
            )
        return {"constant": qstr(expression.constant), "terms": terms}

    constraints = []
    for name, expression in builder.constraints:
        constraints.append(
            {
                "name": name,
                "sense": "eq",
                "expression": expression_object(expression),
            }
        )

    return {
        "format": "exact-block-sdp-model-v1",
        "blocks": [
            {"name": block.role, "size": block.size}
            for block in builder.blocks
        ],
        "constraints": constraints,
        "objective": {
            "sense": "minimize",
            "expression": expression_object(builder.objective),
        },
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_sdpa_sparse(path: Path, model: Mapping[str, object], digits: int) -> None:
    constraints = model["constraints"]
    blocks = model["blocks"]
    lines = [
        str(len(constraints)),
        str(len(blocks)),
        " ".join(str(block["size"]) for block in blocks),
        " ".join(
            decimal_string(-Fraction(constraint["expression"]["constant"]), digits)
            for constraint in constraints
        ),
    ]
    block_indices = {block["name"]: index for index, block in enumerate(blocks, start=1)}
    for constraint_index, constraint in enumerate(constraints, start=1):
        for term in constraint["expression"]["terms"]:
            coefficient = Fraction(term["coefficient"])
            if term["row"] != term["col"]:
                coefficient /= 2
            lines.append(
                " ".join(
                    (
                        str(constraint_index),
                        str(block_indices[term["block"]]),
                        str(term["row"] + 1),
                        str(term["col"] + 1),
                        decimal_string(coefficient, digits),
                    )
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solver_summary(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")

    def field(name: str) -> str:
        match = re.search(rf"^\s*{re.escape(name)}\s*=\s*(.*?)\s*$", text, re.MULTILINE)
        if match is None:
            raise ValueError(f"{path} does not report {name}")
        return match.group(1)

    return {
        "phase": field("phase.value"),
        "iterations": int(field("Iteration")),
        "runtime_seconds_reported": field("total time"),
        "primal_feasibility_error_reported": field("p.feas.error"),
        "dual_feasibility_error_reported": field("d.feas.error"),
    }


def write_solver_parameters(path: Path, precision: int, epsilon: str) -> None:
    path.write_text(
        "\n".join(
            (
                "10000 unsigned int maxIteration;",
                f"{epsilon} double 0.0 < epsilonStar;",
                "1e4 double 0.0 < lambdaStar;",
                "2.0 double 1.0 < omegaStar;",
                "-1e5 double lowerBound;",
                "1e5 double upperBound;",
                "0.1 double 0.0 <= betaStar < 1.0;",
                "0.3 double 0.0 <= betaBar < 1.0, betaStar <= betaBar;",
                "0.9 double 0.0 < gammaStar < 1.0;",
                f"{epsilon} double 0.0 < epsilonDash;",
                f"{precision} precision;",
            )
        )
        + "\n",
        encoding="ascii",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("testcases/dlm-three-point-10/input"),
    )
    parser.add_argument("--decimal-digits", type=int, default=120)
    parser.add_argument("--solver-precision", type=int, default=300)
    parser.add_argument("--solver-epsilon", default="1e-40")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    builder, metadata = construct_three_point_sdp()
    model = exact_model(builder, metadata)

    model_path = args.output_dir / "model.json"
    sdpa_path = args.output_dir / "discovery.dat-s"
    parameter_path = args.output_dir / "sdpa-gmp.params"
    write_json(model_path, model)
    write_sdpa_sparse(sdpa_path, model, args.decimal_digits)
    write_solver_parameters(parameter_path, args.solver_precision, args.solver_epsilon)
    numerical_p_parameters = args.output_dir / "numerical" / "p" / "params.sdpa"
    if numerical_p_parameters.parent.is_dir():
        # The p result was produced with the legacy parameter file and SDPA-GMP's
        # default 40-digit print formats. Preserve those exact parameter bytes.
        write_solver_parameters(
            numerical_p_parameters, args.solver_precision, args.solver_epsilon
        )

    constraints = model["constraints"]
    nonzeros = sum(len(constraint["expression"]["terms"]) for constraint in constraints)
    manifest = {
        "format": "exactification-testcase-v1",
        "id": "dlm-three-point-10",
        "title": "DLM rational three-point bound for the (4,10,1/6) spherical code",
        "field": "Q",
        "model": "model.json",
        "approximate_solution": "approximate_solution.json",
        "fixed_objective": "10",
        "solution_side": "affine_psd_blocks",
        "source": {
            "paper_title": "Exact Semidefinite Programming Bounds for Packing Problems",
            "paper_authors": ["Maria Dostert", "David de Laat", "Philippe Moustrou"],
            "paper_doi": "10.1137/20M1351692",
            "result": "Theorem 4.3",
            "arxiv_id": "2001.00256",
            "ancillary_archive_sha256": "e3c76dae3f726b1b8acf98455899ca1cce23ab573cb86ec950e6e1bf38d0402f",
            "source_file_sha256": {
                "ThreePoint.jl": "2c4327789a62767ec4b28d22ee6ffc060200d5c45424d2f0e1ba9b0c5805a485",
                "SemidefiniteProgramming.jl": "d9fafc434c03e2247ce5199114b8b59a21b969f3def85fe5b3cb9bb2e1c903ba",
                "proofs.jl": "dae2712d8011207c1fef6c986cf1bbb1e44d982baab4271d2cb5fbd7f6527f1f",
            },
            "solver": {
                "name": "SDPA-GMP",
                "repository": "https://github.com/nakatamaho/sdpa-gmp.git",
                "commit": "ca110db5ea1cc46e811b70dfea9cbb25db74448d",
                "binary_sha256": "c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0",
            },
        },
        "parameters": metadata["parameters"],
        "structure": {
            **metadata["source_logic"],
            "block_count": len(model["blocks"]),
            "block_sizes": [block["size"] for block in model["blocks"]],
            "scalar_upper_triangle_variables": builder.variable_count,
            "equality_constraints": len(constraints),
            "constraint_matrix_nonzeros": nonzeros,
        },
        "serialization": {
            "exact": "model.json uses numerator/denominator strings over Q",
            "sdpa_sparse_decimal_digits": args.decimal_digits,
            "legacy_p_solver_precision_bits": args.solver_precision,
            "legacy_p_solver_epsilon": args.solver_epsilon,
        },
        "numerical_runs": {
            "p": {
                "solver_internal_precision_bits": 300,
                "printed_digits": 40,
                "parameters": "numerical/p/params.sdpa",
                "result": "numerical/p/result.out",
                "approximate_solution": "numerical/p/approximate_solution.json",
            },
            "2p": {
                "solver_internal_precision_bits": 600,
                "printed_digits": 80,
                "parameters": "numerical/2p/params.sdpa",
                "result": "numerical/2p/result.out",
                "approximate_solution": "numerical/2p/approximate_solution.json",
            },
            "stability_report": "numerical/numerical_stability.json",
        },
        "blind_input_policy": {
            "exact_certificate_included": False,
            "published_certificate_included": False,
            "published_serialized_solution_read": False,
            "oracle_paths_mounted": False,
            "exact_kernel_oracle_included": False,
            "note": "Only the ancillary SDP construction was ported; exact Gram matrices and published kernel relations are excluded, and p/2p ranks are diagnostics only.",
        },
        "features": [
            "rational_coefficients",
            "rank_deficient_sharp_solution",
            "large_multiblock_sos_model",
            "fixed_objective_feasibility_discovery",
        ],
    }
    p_directory = args.output_dir / "numerical" / "p"
    two_p_directory = args.output_dir / "numerical" / "2p"
    stability_path = args.output_dir / "numerical" / "numerical_stability.json"
    for label, directory in (("p", p_directory), ("2p", two_p_directory)):
        result_path = directory / "result.out"
        if result_path.is_file():
            manifest["numerical_runs"][label].update(solver_summary(result_path))
    numerical_files = [
        p_directory / "params.sdpa",
        p_directory / "result.out",
        p_directory / "approximate_solution.json",
        two_p_directory / "params.sdpa",
        two_p_directory / "result.out",
        two_p_directory / "approximate_solution.json",
        stability_path,
    ]
    if all(path.is_file() for path in numerical_files):
        manifest["workflow"] = {
            "additional_approximate_solutions": [
                "numerical/2p/approximate_solution.json"
            ],
            "precision_evidence": [
                {
                    "label": "p",
                    "path": "numerical/p/approximate_solution.json",
                    "claimed_precision_digits": 40,
                    "solver_internal_precision_bits": 300,
                    "producer_run_id": "sdpa-gmp-p",
                    "command": [
                        "sdpa_gmp", "-ds", "discovery.dat-s", "-o",
                        "discovery.result", "-p", "sdpa-gmp.params"
                    ],
                    "parameters_sha256": sha256(p_directory / "params.sdpa"),
                    "result_sha256": sha256(p_directory / "result.out"),
                    "approximate_solution_sha256": sha256(
                        p_directory / "approximate_solution.json"
                    ),
                },
                {
                    "label": "2p",
                    "path": "numerical/2p/approximate_solution.json",
                    "claimed_precision_digits": 80,
                    "solver_internal_precision_bits": 600,
                    "producer_run_id": "sdpa-gmp-2p",
                    "command": [
                        "sdpa_gmp", "-ds", "discovery.dat-s", "-o",
                        "numerical/2p/result.out", "-p", "numerical/2p/params.sdpa"
                    ],
                    "parameters_sha256": sha256(two_p_directory / "params.sdpa"),
                    "result_sha256": sha256(two_p_directory / "result.out"),
                    "approximate_solution_sha256": sha256(
                        two_p_directory / "approximate_solution.json"
                    ),
                },
            ],
            "numerical_stability": {
                "path": "numerical/numerical_stability.json",
                "sha256": sha256(stability_path),
            },
        }
    manifest["files"] = {
        str(path.relative_to(args.output_dir)): {"sha256": sha256(path)}
        for path in sorted(args.output_dir.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    write_json(args.output_dir / "manifest.json", manifest)

    print(
        f"generated {len(model['blocks'])} blocks, "
        f"{builder.variable_count} scalar coordinates, "
        f"{len(constraints)} equalities, and {nonzeros} matrix nonzeros"
    )


if __name__ == "__main__":
    main()
