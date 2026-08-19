#!/usr/bin/env python3
"""Normalize a Grzesik SDPA-GMP result without rational reconstruction."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


NUMBER = re.compile(r"[+-](?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)")


def result_field(text: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}\s*=\s*(.*?)\s*$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"result does not report {field}")
    return match.group(1)


def printed_digits(text: str) -> int:
    value = result_field(text, "xPrint")
    match = re.search(r"\.(\d+)F", value)
    if match is None:
        raise ValueError(f"cannot infer printed digits from xPrint={value!r}")
    return int(match.group(1))


def matrix_from_upper(values: list[str], size: int) -> tuple[list[list[str]], list[str]]:
    matrix = [["0" for _ in range(size)] for _ in range(size)]
    cursor = 0
    for row in range(size):
        for column in range(row, size):
            matrix[row][column] = matrix[column][row] = values[cursor]
            cursor += 1
    return matrix, values[cursor:]


def parse_solution(result: Path, model_path: Path, output: Path) -> dict:
    result_text = result.read_text(encoding="utf-8")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    try:
        vector_text = result_text.split("xVec =", 1)[1].split("xMat =", 1)[0]
    except IndexError as error:
        raise ValueError("result does not contain a complete xVec section") from error
    values = [value[1:] if value.startswith("+") else value for value in NUMBER.findall(vector_text)]
    expected = sum(block["size"] * (block["size"] + 1) // 2 for block in model["blocks"])
    if len(values) != expected:
        raise ValueError(f"expected {expected} xVec entries, found {len(values)}")

    blocks = []
    remaining = values
    for block in model["blocks"]:
        matrix, remaining = matrix_from_upper(remaining, block["size"])
        blocks.append({"name": block["name"], "matrix": matrix})
    if remaining:
        raise AssertionError("unconsumed xVec entries")

    solution = {
        "format": "approximate-block-sdp-solution-v1",
        "numeric_type": "decimal",
        "claimed_precision_digits": printed_digits(result_text),
        "solver_internal_precision_bits": int(result_field(result_text, "precision")),
        "claimed_objective": values[0],
        "blocks": blocks,
    }
    output.write_text(json.dumps(solution, indent=2) + "\n", encoding="ascii")
    return solution


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    solution = parse_solution(args.result, args.model, args.output)
    print(
        f"extracted {len(solution['blocks'])} blocks at {solution['claimed_precision_digits']} printed "
        f"digits from a {solution['solver_internal_precision_bits']}-bit run"
    )


if __name__ == "__main__":
    main()
