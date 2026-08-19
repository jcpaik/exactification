#!/usr/bin/env python3
"""Extract primal PSD blocks from an SDPA-GMP result as neutral JSON.

For the DLM builder the PSD decision matrices are SDPA's ``yMat`` blocks,
matching ``finalY`` in the ancillary ``SemidefiniteProgramming.jl`` parser.
The parser preserves the printed decimal strings; it performs no rounding.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


class BraceParser:
    def __init__(self, text: str):
        self.tokens = re.findall(
            r"\{|\}|,|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
            text,
        )
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


def result_field(text: str, field: str) -> str | None:
    match = re.search(rf"^{re.escape(field)}\s*=\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def printed_digits(text: str, field: str) -> int:
    value = result_field(text, field)
    if value is None:
        raise ValueError(f"result does not report {field}")
    match = re.search(r"\.(\d+)F", value)
    if match is None:
        raise ValueError(f"cannot infer printed digits from {field}={value!r}")
    return int(match.group(1))


def normalize_matrix(value, size: int) -> list[list[str]]:
    if size == 1 and len(value) == 1 and isinstance(value[0], str):
        return [[value[0]]]
    if len(value) != size or any(not isinstance(row, list) or len(row) != size for row in value):
        raise ValueError(f"solver block does not have expected shape {size}x{size}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    result_text = args.result.read_text(encoding="utf-8")
    model = json.loads(args.model.read_text(encoding="utf-8"))
    try:
        ymat_text = result_text.split("yMat =", 1)[1].split("    main loop time", 1)[0]
    except IndexError as error:
        raise ValueError("result does not contain a complete yMat section") from error
    parsed = BraceParser(ymat_text).parse()

    if len(parsed) != len(model["blocks"]):
        raise ValueError(
            f"solver emitted {len(parsed)} yMat blocks; model has {len(model['blocks'])}"
        )
    blocks = []
    for block, value in zip(model["blocks"], parsed):
        blocks.append(
            {
                "name": block["name"],
                "matrix": normalize_matrix(value, block["size"]),
            }
        )

    solution = {
        "format": "approximate-block-sdp-solution-v1",
        "numeric_type": "decimal",
        "claimed_precision_digits": printed_digits(result_text, "YPrint"),
        "solver_internal_precision_bits": int(result_field(result_text, "precision")),
        "claimed_objective": "10",
        "blocks": blocks,
    }
    args.output.write_text(json.dumps(solution, indent=2) + "\n", encoding="utf-8")
    print(f"extracted {len(blocks)} primal PSD blocks")


if __name__ == "__main__":
    main()
