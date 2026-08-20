# Exactification tools

These commands implement the reconstruction side of the workflow in
[`manual/EXACTIFICATION_WORKFLOW.md`](../manual/EXACTIFICATION_WORKFLOW.md).
They are **discovery tools**, not part of the trusted proof checker. Their
output becomes a proof only after `python -m verify check` and the
manifest-aware testcase harness both pass.

## Environment

The round-1 validation used Python 3.14 with the versions pinned in
[`requirements.txt`](requirements.txt). Create an isolated environment and
install them with:

```sh
python3 -m pip install -r exactify/requirements.txt
```

`affine_modular_solve.py` uses FLINT for the reduced exact solve. The other
recovery commands use SymPy and mpmath; `make_run_records.py` also records the
NumPy version for provenance.

## Commands

- `make_discovery_artifacts.py` classifies numerical spectra and candidate
  nullities.
- `recover_projectors.py` reconstructs basis-invariant rational kernel
  projectors when their entries have manageable height.
- `recover_relations.py` reconstructs a kernel as graph-coordinate row
  relations, avoiding the arbitrary rotation of numerical eigenvectors.
- `build_affine_config.py` combines recovered kernel data and the fixed
  objective into an affine-reconstruction configuration.
- `affine_round.py` is the small-system exact affine rounder.
- `affine_modular_solve.py` uses two-prime sparse pivot selection, a reduced
  exact FLINT solve, shared-denominator free-coordinate rounding, and a full
  exact replay of every enlarged affine equation. Prefer it for large faces.
- `make_run_records.py` creates the immutable attempt metadata required by the
  testcase contract.

The concrete argument arrays used for Grzesik and DLM are preserved in the
frozen round-1 blind workspace and in
[`validation/round-1/executor-report-retry.md`](../validation/round-1/executor-report-retry.md).

## Creating `run.json`

`make_run_records.py` creates metadata for one existing blind attempt. It does
not discover testcases, read Git state, or contain suite-specific paths.

```sh
python3 exactify/make_run_records.py \
  --case-root /absolute/path/to/testcases/example-case \
  --attempt-id attempt-1 \
  --commands-json attempts/attempt-1/commands.json \
  --discovery-json attempts/attempt-1/discovery.json \
  --started-utc 2026-08-19T10:00:00Z \
  --ended-utc 2026-08-19T10:30:00Z
```

Relative metadata paths are interpreted from `--case-root`. Absolute metadata
paths are accepted only when they resolve inside that case root. The case must
already contain:

```text
<case-root>/
├── input/
│   └── manifest.json       # contains a nonempty string id
└── attempts/
    └── <attempt-id>/
```

The command writes `attempts/<attempt-id>/run.json`. It refuses to overwrite an
existing record unless `--replace` is passed, so historical records are
unchanged by default.

### Command-log input

`--commands-json` accepts an array, or an object whose only field is
`commands`. Every entry has this schema:

```json
{
  "argv": ["python3", "-m", "verify", "check", "model.json", "certificate.json", "--json"],
  "exit_code": 0,
  "purpose": "fresh exact certificate check",
  "note": "optional note"
}
```

`argv` is a nonempty string array. `exit_code` is an integer, and `purpose` is
a nonempty string. Unknown fields are rejected.

### Discovery input

`--discovery-json` is an object with these required fields:

```json
{
  "seeds": [],
  "precision_ladder": {"public_decimal_digits": [100]},
  "relation_height_ladder": [8, 16, 32],
  "denominator_ladder": [64, 96, 128],
  "objective_branches": [
    {"value": "0", "source": "fixed", "status": "accepted"}
  ],
  "nullity_branches": {"X": [3]},
  "public_matching_construction_used": false,
  "notes": "optional note"
}
```

`denominator_ladder_bits` is accepted as an input alias for
`denominator_ladder`; output always uses the generic field name.

### Hash and safety behavior

- All regular files below `input/` are hashed as portable paths beginning with
  `input/`.
- All regular files below the selected attempt are hashed as paths beginning
  with `attempts/<attempt-id>/`.
- `run.json` is excluded from generated hashes to avoid a self-reference.
- The command/discovery files receive explicit hashes even if they are outside
  the attempt directory.
- `..` traversal, unsafe attempt IDs, paths resolving outside the case root,
  symlink escapes, directory symlinks in hashed trees, duplicate JSON keys,
  and writes through a `run.json` symlink are rejected.
- Git fields are recorded as `not_inspected_blind_policy`; the utility never
  invokes Git.

Output JSON uses UTF-8, LF endings, sorted keys, deterministic path ordering,
and explicit timestamps supplied by the caller. Re-running with identical
inputs, timestamps, platform, and installed-tool metadata produces identical
bytes. Tool versions are queried through Python's standard package metadata
API. `sympy`, `mpmath`, `numpy`, and `python-flint` are optional: unavailable
tools are recorded as `not_available` and are never imported.

## Trust boundary

These scripts may use floating-point eigensolvers, heuristic denominator
ladders, modular rank guesses, and third-party exact-linear-algebra libraries.
None of those results is trusted. The final certificate must independently
pass:

```sh
python3 -m verify check MODEL CERTIFICATE --json
python3 -m validation.testcase_harness TESTCASE ATTEMPT_ID
```

The first command checks the exact model, objective claim, and PSD traces. The
second binds that result to the testcase manifest, including its declared
target and artifact hashes.
