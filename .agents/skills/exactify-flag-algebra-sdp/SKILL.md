---
name: exactify-flag-algebra-sdp
description: Exactify singular rational flag-algebra or block SDPs from high-precision numerical solutions into independently verified certificates. Use when recovering an exact objective, rational kernel face, PSD matrices, or an SDPA-GMP certificate, or when diagnosing an exactification attempt. Do not use to generate a flag-algebra model from only an informal graph problem or to claim theorem-level sharpness without checked adapters and witnesses.
---

# Exactify a flag-algebra SDP

Turn an exact rational block SDP and high-precision numerical evidence into a
manifest-bound certificate checked using exact arithmetic. Treat numerical
optimization, spectral analysis, LLL/PSLQ, and rational reconstruction only as
candidate discovery.

The central method is:

1. recover exact equations for the kernel subspace;
2. impose those equations on the original exact affine system;
3. round free coordinates on a shared rational grid;
4. backsolve the remaining coordinates exactly; and
5. check the complete result independently.

Never round raw solver coordinates, eigenvectors, or eigensolver projectors
entry by entry. Numerical kernel bases can be arbitrarily rotated even when the
underlying subspace is rational.

## Establish the task boundary

Start from the repository's [user-facing surface](../../../README.md#user-facing-surface-input-and-output):

- `input/manifest.json` describes the case, target, field, paths, and policy;
- `input/model.json` is an exact `exact-block-sdp-model-v1` model;
- numerical `p` and `2p` runs contain full decimal block matrices and
  provenance; and
- write only a new `attempts/<attempt-id>/` directory.

Do not infer a flag-algebra SDP from an informal extremal-graph statement in
this skill. If the exact model or its theorem mapping is missing, report the
missing adapter as a prerequisite.

The current trusted proof path is rational. Quadratic-field relation discovery
may be explored, but it remains `EXPLORATION_ONLY` until a versioned exact
number-field format and checker exist. Never serialize quadratic elements as
rational decimals.

Respect the case's blind-input policy. Do not inspect construction code,
oracle files, golden certificates, prior attempts, or published exact matrices
unless the task explicitly places them in scope. Never use an expected
certificate to choose objectives, kernels, pivots, grids, or entries.

## Read the authoritative material

Before changing an attempt, read these sources directly:

- [exact certificate format](../../../verify/FORMAT.md), completely;
- [testcase contract](../../../manual/TESTCASE_CONTRACT.md), Sections 1--8 and
  12--13; and
- the relevant phase of the [exactification workflow](../../../manual/EXACTIFICATION_WORKFLOW.md):
  Sections 1--4 for every run, Section 5 for objective discovery, Sections
  6--9 for reconstruction, and Sections 10--13 before assigning a status.

Use the supplied [exactification tools](../../../exactify/README.md) instead of
reimplementing their algorithms when they fit the case. Treat these tools as
untrusted discovery machinery; only the exact checker and manifest-aware
harness close the proof path.

## Run the workflow

### 1. Preflight the public input

Before running or trusting a solver:

- verify all manifest hashes;
- parse exact coefficients without binary floating point;
- check block dimensions, symmetry, unique names, coordinates, senses, and
  the off-diagonal coefficient convention from `verify/FORMAT.md`;
- recompute model and block counts;
- evaluate the numerical solution against the exact model at high precision;
- verify the objective direction and theorem mapping explicitly; and
- require a non-null canonical rational `fixed_objective` for a target-bound
  certificate.

Stop with `INPUT_INVALID` when the model, hashes, dimensions, provenance, or
mapping are inconsistent. Do not repair or reinterpret them silently.

### 2. Establish the objective and relative-interior face

If no exact objective is supplied, build rational candidates from independent
high-precision objective values using a denominator-height ladder. Require
candidate stability at higher precision before pursuing it.

For each candidate `tau`, add `objective(X) = tau` exactly and solve the
resulting feasibility problem near the relative interior, at `p` and `2p` and
preferably from independent starts. Preserve all raw outputs and parameters.
Do not add a positive-definite perturbation to a block expected to be
structurally singular.

An exact feasible point at `tau` proves the bound direction declared by the
model and theorem adapter; it does not by itself prove optimality.

### 3. Classify stable nullities

For every block and precision:

- normalize the spectrum by the block scale;
- compare structural-small values with the residual/noise floor;
- identify a stable gap before the positive cluster;
- retain ambiguous neighboring nullities as explicit branches; and
- record p/2p spectra, gaps, residual scales, and branch decisions.

Do not use a universal eigenvalue cutoff. A spectral gap is discovery evidence,
not a PSD proof.

### 4. Recover the exact kernel subspace

Use DLM integer relations first. For a numerical kernel basis `N` of an
`n`-dimensional block with nullity `k`, recover `n-k` independent primitive
integer rows `M` satisfying `M N ~= 0`. Canonicalize `M`, compute an exact
rational basis `V` of `null(M)`, and require exact ranks
`rank(M) = n-k`, `rank(V) = k`, and `M V = 0`.

When simultaneous relations are unstable or expensive, use the graph-chart
fallback:

1. choose a well-conditioned positive-space coordinate set `P` by
   rank-revealing pivoting;
2. let `Q` be its complement;
3. compute `G = -A[P,P]^-1 A[P,Q]` independently at p and 2p;
4. recover the same exact rational `G` from both runs; and
5. form `V[Q,:] = I`, `V[P,:] = G`, `M[:,P] = I`, and `M[:,Q] = -G`.

Record the pivot set, conditioning, relation heights, exact row-space hashes,
normalized relation and block-kernel residuals, and largest principal angles at
both precisions. Higher-precision errors must follow the lower noise floor
rather than plateau. Require the final exact candidate to satisfy `X V = 0`
exactly.

### 5. Reconstruct inside the exact affine space

Add the original affine equations, fixed-objective equality, recovered
`X_i V_i = 0` equations, and explicitly branched active inequalities. Preserve
the full enlarged system and every row's origin.

For large systems, select pivots modulo at least two primes, certify the chosen
exact minor, solve the reduced exact subsystem, round all free coordinates on
one shared denominator grid, and backsolve pivot coordinates exactly. Recheck
every original and face row exactly after substitution.

If the exact affine residual is nonzero, more solver digits cannot fix it.
Change one item at a time: denominator grid, pivot choice, active-set branch,
kernel branch, objective candidate, field, or numerical precision.

### 6. Emit and check the exact certificate

From the repository root, run fresh processes:

```sh
python3 -m verify emit-traces \
  testcases/<case-id>/input/model.json \
  testcases/<case-id>/attempts/<attempt-id>/candidate.json \
  -o testcases/<case-id>/attempts/<attempt-id>/certificate.json

python3 -m verify check \
  testcases/<case-id>/input/model.json \
  testcases/<case-id>/attempts/<attempt-id>/certificate.json \
  --json

python3 -m validation.testcase_harness \
  testcases/<case-id> <attempt-id>
```

The generic checker proves exact affine feasibility, the certificate's claimed
objective, and rational PSD through replayable Schur complements. The harness
additionally binds that objective to the manifest target, compares candidate
and certificate matrices, and checks artifact hashes and coverage. A generic
checker pass at a different feasible objective is not a testcase pass.

Never weaken the checker with numerical eigenvalues, a skipped block, a hidden
target, a certificate hash whitelist, or a known-good bypass.

### 7. Package the attempt

Produce the contract artifacts applicable to the branch:

- `objective-candidates.json`
- `spectra.json`
- `kernels.json`
- `affine-system.json` when face equations or affine reconstruction are used
- `candidate.json`
- `certificate.json`
- `verifier-output.json`
- `verification.json`
- `run.json`
- `proof.md`
- `operational-failures.json` whenever an operational event occurred

Record command argument arrays, exits, timestamps, versions, precision and
height ladders, branches, hashes of every consumed/generated file, and whether
a public matching construction was used. Record timeouts, signals, nonzero
backend exits, memory stops, manual interruptions, and missing expected
artifacts immediately, even when a later fallback succeeds.

## Assign status conservatively

Use only these statuses:

- `INPUT_INVALID`: public inputs or their mapping fail preflight.
- `EXPLORATION_ONLY`: numerical candidates exist, but no complete
  manifest-bound exact certificate passes; this includes a null target.
- `NO_CERTIFICATE_FOUND`: declared search limits were exhausted reproducibly.
- `EXACT_SDP_CERTIFICATE`: the rational verifier and target-binding harness
  pass every block, constraint, objective, artifact, and coverage check.
- `RIGOROUS_PROBLEM_BOUND`: the exact certificate and a separate exact theorem
  adapter prove the original problem bound.
- `SHARP_OR_OPTIMAL`: the preceding gates plus a matching exact witness or
  checked zero-gap argument pass.

Do not promote a status because the numerical solution agrees with a paper,
the certificate looks PSD numerically, or a relation has low height. In the
final report, state the exact objective, field, model/certificate hashes,
block/constraint coverage, exact ranks, final status, failed branches, and any
remaining theorem or witness dependency.
