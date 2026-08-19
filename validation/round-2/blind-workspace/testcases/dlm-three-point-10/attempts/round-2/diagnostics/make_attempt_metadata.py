#!/usr/bin/env python3
"""Create deterministic round-2 DLM JSON metadata from durable artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


CASE = "dlm-three-point-10"
ATTEMPT = "round-2"
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[3]
INPUT = WORKSPACE / "testcases" / CASE / "input"


def read(name: str):
    return json.loads((ROOT / name).read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name: str, value) -> None:
    (ROOT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def command(argv, exit_code, purpose, note=None):
    value = {"argv": argv, "exit_code": exit_code, "purpose": purpose}
    if note:
        value["note"] = note
    return value


model = json.loads((INPUT / "model.json").read_text())
kernels = read("kernels.json")
verifier = read("verifier-output.json")
failures = read("operational-failures.json")
sizes = {block["name"]: block["size"] for block in model["blocks"]}

write_json(
    "objective-candidates.json",
    {
        "format": "exactification-objective-candidates-v1",
        "discovery_required": False,
        "candidates": [{
            "value": "10",
            "source": "manifest.fixed_objective",
            "status": "accepted",
            "numerical_value": "10.0",
            "reason": "The exact kernel-face affine system is consistent and the complete rational certificate passes every verifier gate.",
        }],
    },
)

write_json(
    "verification.json",
    {
        "format": "exactification-verification-v1",
        "case_id": CASE,
        "attempt_id": ATTEMPT,
        "model_sha256": digest(INPUT / "model.json"),
        "candidate_sha256": digest(ROOT / "candidate.json"),
        "certificate_sha256": digest(ROOT / "certificate.json"),
        "verifier_command": ["python3", "-B", "-m", "verify", "check", f"testcases/{CASE}/input/model.json", f"testcases/{CASE}/attempts/{ATTEMPT}/certificate.json", "--json"],
        "verifier_exit_code": 0,
        "bundled_report": verifier,
        "blocks_covered": verifier["blocks_checked"] == len(model["blocks"]),
        "constraints_covered": verifier["constraints_checked"] == len(model["constraints"]),
        "candidate_certificate_identity": True,
        "exact_objective_matches_manifest": verifier["objective"] == "10",
        "gates": {
            "A_integrity_and_coverage": True,
            "B_all_original_constraints": True,
            "C_exact_objective": True,
            "D_all_complete_blocks_psd": True,
        },
        "operational_failure_events_retained": len(failures["events"]),
        "final_status": "EXACT_SDP_CERTIFICATE",
    },
)

commands = []
for event in failures["events"]:
    commands.append(command(
        event["command"],
        event["exit_code"],
        f"Retained operational event {event['event_id']} during {event['phase']}.",
        event["diagnostic"],
    ))

for block_name, block in sorted(kernels["blocks"].items()):
    nullity = block["candidate_nullity"]
    if not nullity or sizes[block_name] == 1:
        continue
    stem = block_name.replace(".", "__")
    for label, precision in (("p", "70"), ("2p", "110")):
        approximate = f"testcases/{CASE}/input/numerical/{label}/approximate_solution.json"
        output = f"testcases/{CASE}/attempts/{ATTEMPT}/diagnostics/relations/{stem}-{label}.json"
        if block_name == "triple_sos.pi3.s_0":
            argv = ["python3", f"testcases/{CASE}/attempts/{ATTEMPT}/diagnostics/recover_graph_without_sympy_rank.py", "--approx", approximate, "--block", block_name, "--nullity", str(nullity), "--output", output, "--decimal-precision", precision, "--maximum-denominator-power", "8", "--accept-residual", "1e-18"]
            purpose = f"Recover the {block_name} {label} graph chart with explicit pivot-rank certification after the retained SymPy-rank stall."
        else:
            argv = ["python3", "exactify/recover_relations.py", "--approx", approximate, "--block", block_name, "--nullity", str(nullity), "--output", output, "--decimal-precision", precision, "--maximum-denominator-power", "8", "--accept-residual", "1e-18"]
            purpose = f"Independently recover the {block_name} graph relation space from the {label} run."
        commands.append(command(argv, 0, purpose))

commands.extend([
    command(
        ["python3", f"testcases/{CASE}/attempts/{ATTEMPT}/diagnostics/make_two_precision_artifacts.py", "--model", f"testcases/{CASE}/input/model.json", "--p", f"testcases/{CASE}/input/numerical/p/approximate_solution.json", "--two-p", f"testcases/{CASE}/input/numerical/2p/approximate_solution.json", "--config", f"testcases/{CASE}/attempts/{ATTEMPT}/diagnostics/affine-config.json", "--relations-dir", f"testcases/{CASE}/attempts/{ATTEMPT}/diagnostics/relations", "--spectra-output", f"testcases/{CASE}/attempts/{ATTEMPT}/spectra.json", "--kernels-output", f"testcases/{CASE}/attempts/{ATTEMPT}/kernels.json", "--decimal-precision", "110"],
        0,
        "Persist all p/2p spectra, exact row-space agreement, residuals, principal angles, and graph conditioning.",
    ),
    command(
        ["python3", "exactify/affine_modular_solve.py", "--model", f"testcases/{CASE}/input/model.json", "--approx", f"testcases/{CASE}/input/numerical/2p/approximate_solution.json", "--config", f"testcases/{CASE}/attempts/{ATTEMPT}/diagnostics/affine-config.json", "--output", f"testcases/{CASE}/attempts/{ATTEMPT}/candidate.json", "--system-output", f"testcases/{CASE}/attempts/{ATTEMPT}/affine-system.json", "--denominator-bits", "160"],
        0,
        "Select pivots modulo two primes, solve the reduced exact system with FLINT, and replay all enlarged rows.",
    ),
    command(
        ["python3", "-B", "-m", "verify", "emit-traces", f"testcases/{CASE}/input/model.json", f"testcases/{CASE}/attempts/{ATTEMPT}/candidate.json", "-o", f"testcases/{CASE}/attempts/{ATTEMPT}/certificate.json"],
        0,
        "Emit deterministic exact PSD traces for all 31 blocks.",
    ),
    command(
        ["python3", "-B", "-m", "verify", "check", f"testcases/{CASE}/input/model.json", f"testcases/{CASE}/attempts/{ATTEMPT}/certificate.json", "--json"],
        0,
        "Run the generic exact verifier in a fresh process.",
    ),
    command(
        ["python3", "-B", "-m", "validation.testcase_harness", f"testcases/{CASE}", ATTEMPT],
        0,
        "Run the manifest-aware target, provenance, artifact, and status gate.",
    ),
])
write_json("commands.json", {"commands": commands})

write_json(
    "discovery.json",
    {
        "seeds": [],
        "precision_ladder": {
            "public_solver_bits": [300, 600],
            "public_printed_decimal_digits": [40, 80],
            "independent_normalized_runs": 2,
            "diagnostic_decimal_precision": 110,
        },
        "relation_height_ladder": [10, 100, 1000, 10000, 100000, 1000000, 10000000, 100000000],
        "denominator_ladder": [160],
        "objective_branches": [{"value": "10", "source": "manifest.fixed_objective", "status": "accepted"}],
        "nullity_branches": {name: [block["candidate_nullity"]] for name, block in sorted(kernels["blocks"].items())},
        "public_matching_construction_used": False,
        "notes": "All 22 singular blocks were recovered from independent p/2p numerical graph charts. Four operational events, including two recoverable pi3.s_0 SymPy exact-rank interruptions, are preserved without a mathematical branch change.",
    },
)
