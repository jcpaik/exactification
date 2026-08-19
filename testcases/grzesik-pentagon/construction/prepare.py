#!/usr/bin/env python3
"""Build the blind Grzesik testcase from the committed discovery artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


CASE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = Path(__file__).resolve().parents[3]
PROBLEM = REPOSITORY / "problems" / "pentagons-triangle-free"
INPUT = CASE_ROOT / "input"

sys.path.insert(0, str(PROBLEM))
import grzesik_sdp as grzesik  # noqa: E402
from parse_sdpa_solution import parse_solution  # noqa: E402


def expression(constant: int = 0, terms: list[dict[str, object]] | None = None) -> dict:
    return {"constant": str(constant), "terms": terms or []}


def term(block: str, row: int, column: int, coefficient: int) -> dict:
    return {
        "block": block,
        "row": row,
        "col": column,
        "coefficient": str(coefficient),
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def main() -> None:
    INPUT.mkdir(parents=True, exist_ok=True)

    constraints = []
    for index, (coefficients, constant) in enumerate(grzesik.EXPRESSIONS, start=1):
        terms = [term("U", 0, 0, 120)]
        for (block, row, column), coefficient in sorted(coefficients.items()):
            terms.append(term(block.upper(), row - 1, column - 1, -coefficient))
        constraints.append(
            {
                "name": f"five_vertex_case_{index:02d}",
                "sense": "ge",
                "expression": expression(-constant, terms),
            }
        )

    model = {
        "format": "exact-block-sdp-model-v1",
        "blocks": [
            {"name": "U", "size": 1},
            {"name": "P", "size": 8},
            {"name": "Q", "size": 6},
            {"name": "R", "size": 5},
        ],
        "constraints": constraints,
        "objective": {
            "sense": "minimize",
            "expression": expression(0, [term("U", 0, 0, 1)]),
        },
    }
    (INPUT / "model.json").write_text(
        json.dumps(model, indent=2) + "\n", encoding="ascii"
    )

    source_result = PROBLEM / "results" / "grzesik-512.result"
    source_data = PROBLEM / "data" / "grzesik.dat-s"
    source_params = PROBLEM / "data" / "grzesik-512.param"
    shutil.copyfile(source_data, INPUT / "discovery.dat-s")
    shutil.copyfile(source_result, INPUT / "discovery.result")
    parse_solution(
        INPUT / "discovery.result",
        INPUT / "model.json",
        INPUT / "approximate_solution.json",
    )

    p_directory = INPUT / "numerical" / "p"
    p_directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_params, p_directory / "params.sdpa")
    shutil.copyfile(source_result, p_directory / "result.out")
    parse_solution(
        p_directory / "result.out",
        INPUT / "model.json",
        p_directory / "approximate_solution.json",
    )

    two_p_directory = INPUT / "numerical" / "2p"
    if (two_p_directory / "result.out").exists():
        parse_solution(
            two_p_directory / "result.out",
            INPUT / "model.json",
            two_p_directory / "approximate_solution.json",
        )

    manifest = {
        "format": "exactification-testcase-v1",
        "id": "grzesik-pentagon",
        "title": "Pentagons in triangle-free graphs (Grzesik basis)",
        "field": "Q",
        "model": "model.json",
        "approximate_solution": "approximate_solution.json",
        "fixed_objective": "24/625",
        "solution_side": "affine_psd_blocks",
        "source": {
            "paper": "https://arxiv.org/abs/1102.0962",
            "solver": {
                "name": "SDPA-GMP",
                "repository": "https://github.com/nakatamaho/sdpa-gmp.git",
                "commit": "ca110db5ea1cc46e811b70dfea9cbb25db74448d",
                "binary_sha256": "c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0",
            },
        },
        "numerical_runs": {
            "p": {
                "solver_internal_precision_bits": 512,
                "printed_digits": 80,
                "parameters": "numerical/p/params.sdpa",
                "result": "numerical/p/result.out",
                "approximate_solution": "numerical/p/approximate_solution.json",
                **solver_summary(p_directory / "result.out"),
            },
            "2p": {
                "solver_internal_precision_bits": 1024,
                "printed_digits": 160,
                "parameters": "numerical/2p/params.sdpa",
                "result": "numerical/2p/result.out",
                "approximate_solution": "numerical/2p/approximate_solution.json",
                **solver_summary(two_p_directory / "result.out"),
            },
            "stability_report": "numerical/numerical_stability.json",
        },
        "workflow": {
            "additional_approximate_solutions": [
                "numerical/2p/approximate_solution.json"
            ],
            "precision_evidence": [
                {
                    "label": "p",
                    "path": "numerical/p/approximate_solution.json",
                    "claimed_precision_digits": 80,
                    "solver_internal_precision_bits": 512,
                    "producer_run_id": "sdpa-gmp-p",
                    "command": [
                        "sdpa_gmp", "-ds",
                        "problems/pentagons-triangle-free/data/grzesik.dat-s", "-o",
                        "problems/pentagons-triangle-free/results/grzesik-512.result",
                        "-p", "problems/pentagons-triangle-free/data/grzesik-512.param"
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
                    "claimed_precision_digits": 160,
                    "solver_internal_precision_bits": 1024,
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
                "sha256": sha256(INPUT / "numerical" / "numerical_stability.json"),
            },
        },
        "blind_input_policy": {
            "exact_certificate_included": False,
            "published_certificate_included": False,
            "oracle_paths_mounted": False,
            "exact_kernel_oracle_included": False,
            "note": "The numerical optimizer differs entrywise from Grzesik's published matrices; p/2p ranks are diagnostics only.",
        },
    }
    manifest["files"] = {
        str(path.relative_to(INPUT)): {"sha256": sha256(path)}
        for path in sorted(INPUT.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    (INPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii"
    )


if __name__ == "__main__":
    main()
