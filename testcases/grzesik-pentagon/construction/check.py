#!/usr/bin/env python3
"""Check the public Grzesik model and p/2p numerical provenance."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


CASE_ROOT = Path(__file__).resolve().parents[1]
INPUT = CASE_ROOT / "input"
REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY))

from verify import load_model  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    model = load_model(INPUT / "model.json")
    assert [(block.name, block.size) for block in model.blocks] == [
        ("U", 1),
        ("P", 8),
        ("Q", 6),
        ("R", 5),
    ]
    assert len(model.constraints) == 14
    assert model.objective.sense == "minimize"
    assert sha256(INPUT / "model.json") == "d8ec26f3cc9590612af0d121a868825896b4f646a79e292d4ed3998ee16321ae"
    assert sha256(INPUT / "discovery.dat-s") == "c4ca3642d4227676c15f88ebb0c9889c7e5b1bf8850be8e5300664e6ec68824d"

    manifest = load(INPUT / "manifest.json")
    assert manifest["source"]["solver"]["commit"] == "ca110db5ea1cc46e811b70dfea9cbb25db74448d"
    assert manifest["source"]["solver"]["binary_sha256"] == (
        "c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0"
    )
    assert [run["label"] for run in manifest["workflow"]["precision_evidence"]] == [
        "p",
        "2p",
    ]
    for relative, record in manifest["files"].items():
        assert sha256(INPUT / relative) == record["sha256"], relative

    p = load(INPUT / "numerical" / "p" / "approximate_solution.json")
    two_p = load(INPUT / "numerical" / "2p" / "approximate_solution.json")
    assert (p["claimed_precision_digits"], p["solver_internal_precision_bits"]) == (80, 512)
    assert (two_p["claimed_precision_digits"], two_p["solver_internal_precision_bits"]) == (160, 1024)
    assert (INPUT / "discovery.result").read_bytes() == (
        INPUT / "numerical" / "p" / "result.out"
    ).read_bytes()
    assert (INPUT / "approximate_solution.json").read_bytes() == (
        INPUT / "numerical" / "p" / "approximate_solution.json"
    ).read_bytes()

    stability = load(INPUT / "numerical" / "numerical_stability.json")
    assert stability["summary"]["stable_nullities"] is True
    assert stability["summary"]["stable_kernel_projectors"] is True
    assert [(block["nullity_p"], block["nullity_2p"]) for block in stability["blocks"]] == [
        (0, 0),
        (4, 4),
        (1, 1),
        (2, 2),
    ]
    assert float(stability["summary"]["worst_projector_distance_operator_norm"]) < 1.0e-8
    print("ok: Grzesik exact model and p/2p numerical provenance agree")


if __name__ == "__main__":
    main()
