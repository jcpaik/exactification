# Workflow validation protocol

The exactification workflow is considered validated only after an executor agent
that did not inherit the workflow-author conversation completes the following
loop.

## Current validation state

The context-isolated Round 1 retry produced exact SDP certificates for all
three inputs it received:

- `rotated-rational-kernel` at objective `0`;
- `grzesik-pentagon` at objective `24/625`; and
- `dlm-three-point-10` at objective `10`.

Those exact results remain valid and are recorded in the
[retry report](round-1/executor-report-retry.md). They establish certificate
recovery for the transparent rotated control and the two benchmark SDPs.

A later fixture audit found that `rotated-rational-kernel` did not meet the
current held-out criterion: its public model contains the exact rational PSD
projector whose zero trace exposes the supporting face. It is now classified as
a transparent control, not as the required held-out numerical-subspace test.
The stronger [`obfuscated-rational-kernel`](../testcases/obfuscated-rational-kernel/input/)
fixture supplies independent p/2p numerical runs while excluding its
construction, supporting identity, kernel/projector, and oracle certificate
from blind input. The context-isolated Round 2 executor recovered exact SDP
certificates for that fixture, Grzesik, and DLM. Fresh manifest-aware harnesses
accepted all three, so the strengthened rational three-case validation
requirement is complete.

| Round 2 case | Exact objective | Certificate SHA-256 | Result |
| --- | ---: | --- | --- |
| `obfuscated-rational-kernel` | `2224093617954365/48084958827` | `945f086744c3428413a607efa07943f52c152a54126952a0d0561d5399dc75b9` | `EXACT_SDP_CERTIFICATE` |
| `grzesik-pentagon` | `24/625` | `a0fbf43ad114dfea0cd4c943ce050c13c1d6f36adf2baab8c3929a93c7585a71` | `EXACT_SDP_CERTIFICATE` |
| `dlm-three-point-10` | `10` | `3bbf0fd32abc4f55012db3d0cb8f5997d9af95988b3d60a3dd0e0d30b7a6f40c` | `EXACT_SDP_CERTIFICATE` |

The detailed discovery and recovery record is the
[Round 2 executor report](round-2/executor-report-round-2.md). These statuses
certify the exact rational SDP models under the repository verifier and
manifest policy; they do not by themselves assert a separately checked
theorem adapter or extremal sharpness witness.

## Isolation

1. The author agent writes the workflow and testcase contract.
2. Test inputs contain the rational SDP model, one or more high-precision
   approximate solutions, numerical provenance, and the fixed objective. They
   do not contain a published exact Gram matrix or exactified certificate.
3. The executor agent starts without conversation history and is instructed to
   read only the workflow, testcase contract, verifier format, and testcase
   inputs before producing its candidates.
4. The executor records every input it used and every command needed to
   reproduce its output.

This is an operational isolation test, not a cryptographic sandbox. The
validation report must disclose the allowlist and any violation of it.

## Required cases

- `grzesik-pentagon`: a flag-algebra SDP whose sharp value is rational but whose
  numerical optimizer is not the published rational optimizer. This tests
  optimal-face and rational-kernel recovery rather than entrywise rounding.
- `dlm-three-point-10`: the rational, fixed-objective three-point SDP used for
  Theorem 4.3 of Dostert, de Laat, and Moustrou. This tests the paper's block-SDP
  kernel-recovery procedure on a primary-source instance.
- At least one held-out singular rational SDP not used to design the workflow.
  Its numerical kernel basis must not itself consist of obviously rational
  vectors, and its public input must not expose a projector-equivalent face
  equation. This tests recovery of a rational subspace rather than rounding
  individual eigenvectors. `obfuscated-rational-kernel` is the designated
  Round 2 fixture; the transparent rotated control does not fulfill this item.

A quadratic-field case is a required documented workflow branch and a desired
extended regression test, but it does not replace the three rational cases
above.

## Proof gates for every case

For a case to pass, an independent exact-arithmetic verifier must establish all
of the following from the rational model and candidate certificate:

1. every required block is present, symmetric, and has the declared size;
2. every affine equality holds exactly;
3. every affine inequality has the correct exact sign;
4. the objective equals the fixed claimed value exactly;
5. every semidefinite block is positive semidefinite by an exact argument; and
6. the verifier exits successfully without consulting floating-point data or an
   SDP solver.

Numerical residuals, plausible continued fractions, approximate eigenvalues,
or agreement with a paper are discovery evidence only and cannot satisfy a
proof gate.

For a target-bound repository testcase, the generic verifier is followed by
the manifest-aware harness, which binds the computed and claimed objectives to
the manifest target and checks the required artifacts and final status. The
deterministic builder, target-aware harness, and fresh-process suite runner are
documented in [`README.md`](README.md). The combined suite replays the three
immutable Round 1 attempts and checks the three promoted Round 2 attempts, with
exact target, status, artifact, and coverage checks for every entry.

## Loop completion

After the first execution attempt, the author receives only the executor's
failure report, ambiguities, and suggested clarifications. If any required case
fails, the author revises the workflow and a newly isolated executor reruns the
failed cases. The loop ends only when all required cases pass and the repository
contains:

- the versioned workflow and testcase contract;
- reusable input folders for all cases;
- exact candidate certificates;
- the independent verifier and its unit tests;
- executor and verifier reports for each round; and
- one command that reruns the complete exact verification suite.

The completed loop is rerun by

```sh
python3 -B -m validation.run_suite --config validation/suite.json
```

The six-attempt outcome, inventory digest, and exact certificate hashes are
recorded in [`round-2/SUITE.md`](round-2/SUITE.md).
