# Exactification validation commands

The validation layer keeps the generic v1 SDP verifier independent of testcase
policy.  `testcase_harness.py` binds a verifier pass to a testcase manifest,
its fixed objective, immutable input and run hashes, complete attempt artifacts,
and `verification.json.final_status`.

## Build a blind workspace

The destination must not exist:

```sh
python3 -m validation.build_blind_workspace /path/to/new-workspace \
  --case dlm-three-point-10 \
  --case grzesik-pentagon \
  --case rotated-rational-kernel \
  --case obfuscated-rational-kernel
```

The builder has a source-code allowlist.  It copies the workflow and contract,
the trusted verifier and testcase harness, generic exactification runtime tools,
and only the selected cases' public `input/` trees.  It never copies Git data,
construction directories, oracle material, caches, or prior attempts.  It
rejects symlinks and certificate-like public input, refuses to overwrite an
existing destination, and writes `BLIND_WORKSPACE_INVENTORY.json` with a sorted
SHA-256 inventory of every copied file.

For `obfuscated-rational-kernel`, this means the p/2p solver artifacts under
`input/` are copied, while `construction/generate.py`, the supporting identity,
the exact kernel/projector, and the oracle certificate are not. The frozen
Round 2 workspace used this policy. Building a workspace alone does not
constitute a pass; its inventory and the resulting attempts must also pass the
checks below.

## Check a frozen blind-workspace inventory

```sh
python3 -B -m validation.check_blind_inventory \
  validation/round-2/blind-workspace \
  --allow-generated-attempts
```

Without `--allow-generated-attempts`, the checker requires exact initial
coverage by the builder's inventory. The explicit post-run mode additionally
permits only the executor report and generated attempt trees for inventoried
case IDs; it still rejects unlisted source inputs, construction or oracle data,
symlinks, traversal paths, missing files, and size or hash changes.

For the completed Round 2 workspace, all 55 inventoried files verify, 93
generated files are admitted by that narrow policy, and the inventory SHA-256
is `c9a6277a0f1d334fc83d0d54c689c4e9a51cb1a1741c2cd0c00be52a4faba1c9`.

## Check one attempt

```sh
python3 -m validation.testcase_harness \
  validation/round-1/blind-workspace/testcases/grzesik-pentagon retry-1
```

Run-provenance paths are rooted at the workspace directory containing
`testcases/`.  Consequently, the same `testcases/<id>/...` hash keys work in a
repository checkout or a frozen blind workspace, while traversal and symlink
escapes are rejected.

## Run the complete suite

```sh
python3 -B -m validation.run_suite --config validation/suite.json
```

The default strict-JSON configuration is `validation/suite.json`.  The runner
starts fresh Python processes for unit tests, each optional preflight, and every
manifest-aware attempt check.  Its stdout is one JSON report containing the
exact command arrays, exit codes, stdout/stderr and argument hashes, config
hash, coverage, targets, statuses, model hashes, and certificate hashes.  A
configuration error or any child failure exits nonzero.

The Round 1 entries deliberately validate
`validation/round-1/blind-workspace/testcases/<id>`.  Those roots preserve the
exact public inputs consumed by the isolated retry and its immutable attempt
metadata.  The public inputs under top-level `testcases/` may evolve (for
example, by gaining stronger numerical provenance), so historical run hashes
must not be silently rebound to them.  The current DLM preflight still checks
the current top-level public input independently.

The Round 1 retry has exact certificates at objectives `0`, `24/625`, and `10`
for the rotated control, Grzesik, and DLM respectively. The rotated certificate
is a valid exact result, but the case is no longer counted as the held-out
numerical-subspace fixture because its public projector equality exposes the
face.

The combined configuration also verifies the promoted Round 2 DLM, Grzesik,
and obfuscated-fixture attempts under top-level `testcases/`. Thus the suite
covers six attempts, all four expected case IDs, the unit tests, the DLM and
obfuscated-fixture preflights, and the frozen Round 2 inventory preflight. The
three Round 2 certificates have exact objectives `10`, `24/625`, and
`2224093617954365/48084958827`, respectively. The complete hashes and status
scope are recorded in [`round-2/SUITE.md`](round-2/SUITE.md).

The v1 suite is deliberately fixed-target and rational: every
`expected_target` must be a non-null canonical rational string. A
`fixed_objective: null` discovery case remains exploration and needs a
separately versioned target-binding rule before it can enter this success
suite.
