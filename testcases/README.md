# Exactification testcases

These cases exercise the workflow in
[`../manual/EXACTIFICATION_WORKFLOW.md`](../manual/EXACTIFICATION_WORKFLOW.md).
Their public `input/` directories contain exact SDP models and numerical
discovery data, but no published or golden exact Gram matrices.

| Case | Role | Main failure mode tested | Fixed objective | Validation state |
| --- | --- | --- | ---: | --- |
| [`grzesik-pentagon`](grzesik-pentagon/input/) | Grzesik's flag-algebra SDP, fresh SDPA-GMP run | Nonunique optimizer; singular blocks of several nullities | `24/625` | Round 1 and Round 2 exact certificates |
| [`dlm-three-point-10`](dlm-three-point-10/input/) | DLM Theorem 4.3, regenerated from the official ancillary formulas | Large multiblock singular SOS SDP | `10` | Round 1 and Round 2 exact certificates |
| [`rotated-rational-kernel`](rotated-rational-kernel/input/) | Transparent synthetic control | Irrational numerical point and arbitrary eigenbasis for a rational kernel subspace | `0` | Round 1 exact certificate; not an adequate held-out fixture |
| [`obfuscated-rational-kernel`](obfuscated-rational-kernel/input/) | Stronger held-out synthetic fixture | Dense generic affine rows; rational face recovery from independent p/2p numerical subspaces | `2224093617954365/48084958827` | Round 2 exact certificate |

The Round 1 retry produced exact certificates for its three cases. The rotated
control remains useful as a positive recovery test, but its public equality is
the trace against an exact rational PSD projector; PSD therefore exposes the
supporting face directly. It does not satisfy the current
[held-out face criteria](../manual/TESTCASE_CONTRACT.md#held-out-face-criteria).

The obfuscated fixture replaces that role for Round 2. Its public input contains
two independent SDPA-GMP runs at p and 2p, while its construction data,
supporting identity, exact kernel/projector, and oracle certificate remain
outside `input/` and are excluded by the deterministic blind-workspace builder.
The context-isolated Round 2 executor recovered its rational face and exact
certificate from those public inputs. Fresh manifest-aware harness checks also
accepted the Round 2 Grzesik and DLM attempts. All three results have status
`EXACT_SDP_CERTIFICATE`; see the
[Round 2 executor report](../validation/round-2/executor-report-round-2.md) and
[combined-suite record](../validation/round-2/SUITE.md).

The authoritative model and certificate format is
[`../verify/FORMAT.md`](../verify/FORMAT.md). A completed attempt must pass, in
a fresh process,

```sh
python3 -m verify check \
  testcases/<case>/input/model.json \
  testcases/<case>/attempts/<attempt>/certificate.json \
  --json
```

The validation protocol and success criteria are in
[`../validation/ACCEPTANCE.md`](../validation/ACCEPTANCE.md). Numerical
agreement alone is never recorded as a passing testcase.
