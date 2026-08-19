#!/usr/bin/env python3
"""Generate and inspect Grzesik's SDP for pentagons in triangle-free graphs."""

from __future__ import annotations

import argparse
import itertools
import re
from decimal import Decimal
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "grzesik.dat-s"

MatrixEntry = tuple[str, int, int]
Expression = tuple[dict[MatrixEntry, int], int]


def expression(*terms: tuple[str, int, int, int], constant: int = 0) -> Expression:
    coefficients: dict[MatrixEntry, int] = {}
    for matrix, row, column, coefficient in terms:
        key = (matrix, min(row, column), max(row, column))
        coefficients[key] = coefficients.get(key, 0) + coefficient
    return coefficients, constant


# The fourteen entries inside the maximum in Theorem 2, before its factor 1/120.
EXPRESSIONS: tuple[Expression, ...] = (
    expression(("p", 1, 1, 120)),
    expression(("p", 1, 1, 12), ("p", 1, 2, 24), ("p", 1, 3, 24),
               ("p", 1, 5, 24), ("q", 1, 1, 12)),
    expression(("p", 1, 2, 8), ("p", 1, 3, 8), ("p", 1, 4, 8),
               ("p", 1, 5, 8), ("p", 1, 6, 8), ("p", 1, 7, 8),
               ("p", 2, 2, 4), ("p", 3, 3, 4), ("p", 5, 5, 4),
               ("q", 1, 2, 8), ("q", 1, 3, 8), ("r", 1, 1, 4)),
    expression(("p", 1, 4, 12), ("p", 1, 6, 12), ("p", 1, 7, 12),
               ("p", 1, 8, 12), ("q", 2, 2, 6), ("q", 3, 3, 6),
               ("r", 1, 3, 12)),
    expression(("p", 1, 8, 48), ("r", 3, 3, 24)),
    expression(("p", 2, 3, 16), ("p", 2, 5, 16), ("p", 3, 5, 16),
               ("q", 1, 1, 8), ("q", 1, 4, 16)),
    expression(("p", 2, 7, 8), ("p", 3, 6, 8), ("p", 4, 5, 8),
               ("q", 1, 4, 8), ("q", 2, 4, 8), ("q", 3, 4, 8),
               ("q", 4, 4, 4), ("r", 1, 1, 4)),
    expression(("p", 2, 3, 4), ("p", 2, 4, 4), ("p", 2, 5, 4),
               ("p", 2, 6, 4), ("p", 3, 4, 4), ("p", 3, 5, 4),
               ("p", 3, 7, 4), ("p", 5, 6, 4), ("p", 5, 7, 4),
               ("q", 1, 2, 4), ("q", 1, 3, 4), ("q", 1, 5, 4),
               ("q", 1, 6, 4), ("q", 2, 3, 4), ("r", 1, 2, 4),
               ("r", 1, 4, 4)),
    expression(("p", 2, 7, 4), ("p", 2, 8, 4), ("p", 3, 6, 4),
               ("p", 3, 8, 4), ("p", 4, 5, 4), ("p", 5, 8, 4),
               ("q", 1, 5, 4), ("q", 1, 6, 4), ("q", 2, 5, 4),
               ("q", 3, 6, 4), ("r", 1, 3, 4), ("r", 2, 2, 2),
               ("r", 2, 3, 4), ("r", 3, 4, 4), ("r", 4, 4, 2)),
    expression(("p", 4, 4, 8), ("p", 6, 6, 8), ("p", 7, 7, 8),
               ("q", 2, 3, 16), ("r", 1, 5, 16)),
    expression(("p", 4, 8, 4), ("p", 6, 8, 4), ("p", 7, 8, 4),
               ("q", 2, 6, 4), ("q", 3, 5, 4), ("q", 5, 5, 2),
               ("q", 6, 6, 2), ("r", 1, 5, 4), ("r", 2, 3, 4),
               ("r", 2, 5, 4), ("r", 3, 4, 4), ("r", 3, 5, 4),
               ("r", 4, 5, 4)),
    expression(("p", 8, 8, 12), ("r", 3, 5, 24), ("r", 5, 5, 12)),
    expression(("p", 4, 6, 4), ("p", 4, 7, 4), ("p", 6, 7, 4),
               ("q", 2, 4, 4), ("q", 2, 6, 4), ("q", 3, 4, 4),
               ("q", 3, 5, 4), ("q", 4, 5, 4), ("q", 4, 6, 4),
               ("r", 1, 2, 4), ("r", 1, 4, 4), ("r", 2, 4, 4)),
    expression(("q", 5, 6, 20), ("r", 2, 4, 20), constant=120),
)

BLOCKS = {"p": (2, 8), "q": (3, 6), "r": (4, 5)}


def variables() -> list[str | MatrixEntry]:
    result: list[str | MatrixEntry] = ["u"]
    for matrix, (_, size) in BLOCKS.items():
        result.extend((matrix, row, column)
                      for row in range(1, size + 1)
                      for column in range(row, size + 1))
    return result


def generate(path: Path) -> None:
    """Write min u subject to 120u - expression_i >= 0 and P,Q,R PSD."""
    names = variables()
    indices = {name: index for index, name in enumerate(names, start=1)}
    lines = [
        '"Grzesik C5/K3 SDP: objective u; 14 scalar slacks; P(8), Q(6), R(5)"',
        f"{len(names)} = mDIM",
        "4 = nBLOCK",
        "-14 8 6 5 = bLOCKsTRUCT",
        " ".join("1" if name == "u" else "0" for name in names),
    ]

    # F_0: only the C5 case has the constant 120.
    for row, (_, constant) in enumerate(EXPRESSIONS, start=1):
        if constant:
            lines.append(f"0 1 {row} {row} {constant}")

    # Each diagonal entry in the first (LP) block is the corresponding slack.
    u_index = indices["u"]
    for row, (coefficients, _) in enumerate(EXPRESSIONS, start=1):
        lines.append(f"{u_index} 1 {row} {row} 120")
        for key, coefficient in sorted(coefficients.items()):
            lines.append(f"{indices[key]} 1 {row} {row} {-coefficient}")

    # The remaining blocks are exactly the three Gram matrices.
    for matrix, (block, size) in BLOCKS.items():
        for row in range(1, size + 1):
            for column in range(row, size + 1):
                lines.append(f"{indices[(matrix, row, column)]} {block} {row} {column} 1")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(f"wrote {path} ({len(names)} variables, 4 blocks, 14 inequalities)")


PAPER_MATRICES = {
    "p": (625, (
        (24, -36, -36, 24, -36, 24, 24, -36),
        (-36, 277, 97, -79, 97, -79, -259, 54),
        (-36, 97, 277, -79, 97, -259, -79, 54),
        (24, -79, -79, 247, -259, 67, 67, -36),
        (-36, 97, 97, -259, 277, -79, -79, 54),
        (24, -79, -259, 67, -79, 247, 67, -36),
        (24, -259, -79, 67, -79, 67, 247, -36),
        (-36, 54, 54, -36, 54, -36, -36, 54),
    )),
    "q": (2500, (
        (1728, -1551, -1551, -1308, 687, 687),
        (-1551, 2336, 742, 908, 2557, -4084),
        (-1551, 742, 2336, 908, -4084, 2557),
        (-1308, 908, 908, 1728, -254, -254),
        (687, 2557, -4084, -254, 15264, -14424),
        (687, -4084, 2557, -254, -14424, 15264),
    )),
    "r": (625, (
        (1512, 568, -380, 568, -376),
        (568, 475, -191, 0, -93),
        (-380, -191, 192, -191, -2),
        (568, 0, -191, 475, -93),
        (-376, -93, -2, -93, 190),
    )),
}


def bareiss_determinant(matrix: list[list[int]]) -> int:
    """Fraction-free determinant; sufficient for the small principal minors here."""
    size = len(matrix)
    if size == 0:
        return 1
    work = [row[:] for row in matrix]
    sign = 1
    denominator = 1
    for pivot_index in range(size - 1):
        if work[pivot_index][pivot_index] == 0:
            swap = next((row for row in range(pivot_index + 1, size)
                         if work[row][pivot_index] != 0), None)
            if swap is None:
                return 0
            work[pivot_index], work[swap] = work[swap], work[pivot_index]
            sign = -sign
        pivot = work[pivot_index][pivot_index]
        for row in range(pivot_index + 1, size):
            for column in range(pivot_index + 1, size):
                numerator = (work[row][column] * pivot
                             - work[row][pivot_index] * work[pivot_index][column])
                work[row][column] = numerator // denominator
        denominator = pivot
    return sign * work[-1][-1]


def verify_paper_certificate() -> None:
    for name, (_, matrix) in PAPER_MATRICES.items():
        for order in range(1, len(matrix) + 1):
            for subset in itertools.combinations(range(len(matrix)), order):
                minor = [[matrix[row][column] for column in subset] for row in subset]
                determinant = bareiss_determinant(minor)
                if determinant < 0:
                    raise AssertionError(f"{name.upper()} has a negative principal minor {subset}")
        print(f"{name.upper()}: PSD (all principal minors are nonnegative)")

    values: list[Fraction] = []
    for coefficients, constant in EXPRESSIONS:
        value = Fraction(constant)
        for (name, row, column), coefficient in coefficients.items():
            denominator, matrix = PAPER_MATRICES[name]
            value += coefficient * Fraction(matrix[row - 1][column - 1], denominator)
        values.append(value / 120)

    target = Fraction(24, 625)
    print("case coefficients:", " ".join(str(value) for value in values))
    print("maximum:", max(values))
    if max(values) != target:
        raise AssertionError(f"expected {target}, got {max(values)}")


OBJECTIVE_PATTERN = re.compile(
    r"objVal(Primal|Dual)\s*=\s*([+-]?[0-9.]+(?:[Ee][+-]?[0-9]+)?)"
)
XVEC_PATTERN = re.compile(
    r"xVec\s*=\s*\{\s*([+-]?[0-9.]+(?:[Ee][+-]?[0-9]+)?)",
    re.DOTALL,
)


def recover(result: Path, max_denominator: int) -> None:
    text = result.read_text(encoding="utf-8")
    xvec_match = XVEC_PATTERN.search(text)
    if xvec_match:
        literal = xvec_match.group(1)
        approximation = Fraction(Decimal(literal))
        candidate = approximation.limit_denominator(max_denominator)
        error = abs(approximation - candidate)
        print(f"xVec[1] (u): {literal}")
        print(f"  recovered: {candidate}")
        print(f"  absolute error: {float(error):.3e}")

    matches = OBJECTIVE_PATTERN.findall(text)
    if not matches:
        raise SystemExit(f"no SDPA objective values found in {result}")
    for side, literal in matches[-2:]:
        approximation = Fraction(Decimal(literal))
        candidate = approximation.limit_denominator(max_denominator)
        error = abs(approximation - candidate)
        print(f"{side.lower()}: {literal}")
        print(f"  recovered: {candidate}")
        print(f"  absolute error: {float(error):.3e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate", help="write the SDPA sparse input")
    generate_parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_DATA)
    subparsers.add_parser("verify-paper", help="verify Grzesik's rational certificate exactly")
    recover_parser = subparsers.add_parser("recover", help="rationalize a solver objective")
    recover_parser.add_argument("result", type=Path)
    recover_parser.add_argument("--max-denominator", type=int, default=10_000)
    arguments = parser.parse_args()

    if arguments.command == "generate":
        generate(arguments.path)
    elif arguments.command == "verify-paper":
        verify_paper_certificate()
    else:
        recover(arguments.result, arguments.max_denominator)


if __name__ == "__main__":
    main()
