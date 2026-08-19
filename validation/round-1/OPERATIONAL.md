# Round 1 operational record

## Initial executor run

The first context-isolated executor was started with no inherited conversation
and the allowlisted `blind-workspace/` snapshot. It reported that it had read
the manuals and verifier, passed preflight for `rotated-rational-kernel`, and
derived from the public model that the face coefficient was an exact rank-3
rational projector. It reported no mathematical blocker.

The executor did not persist any attempt artifact after two bounded runs and an
explicit request to checkpoint the first case. It was therefore interrupted.
This is classified as an operational execution failure, not a failed exact
verification and not evidence against the workflow's mathematics. The blind
input snapshot was left unchanged for the fresh retry.

## Retry outcome

The fresh `retry-1` execution completed all three cases in the same frozen
blind workspace. The independent exact verifier accepted complete certificates
for:

| Case | Exact objective | Result |
| --- | ---: | --- |
| `rotated-rational-kernel` | `0` | `EXACT_SDP_CERTIFICATE` |
| `grzesik-pentagon` | `24/625` | `EXACT_SDP_CERTIFICATE` |
| `dlm-three-point-10` | `10` | `EXACT_SDP_CERTIFICATE` |

The detailed construction methods, hashes, commands, recovered operational
failures, and limitations are preserved in the
[`retry-1` executor report](executor-report-retry.md). These successes are exact
SDP certificate results; the DLM run did not claim a separately checked theorem
adapter or sharpness witness.

## Fixture interpretation after Round 1

The rotated result remains mathematically valid, but the fixture is now treated
as a transparent control. Its public equation is the trace against an exact
rational PSD projector, so PSD exposes the supporting face without requiring
genuine recovery of a hidden numerical subspace. It is not counted as the
held-out case under the strengthened
[acceptance criteria](../ACCEPTANCE.md#required-cases).

The stronger
[`obfuscated-rational-kernel`](../../testcases/obfuscated-rational-kernel/input/)
fixture supplies independent p/2p runs and keeps its construction, supporting
identity, exact kernel/projector, and oracle certificate outside blind input.
The isolated Round 2 run subsequently recovered its exact SDP certificate and
fresh certificates for Grzesik and DLM. See the
[Round 2 executor report](../round-2/executor-report-round-2.md) and
[combined-suite record](../round-2/SUITE.md).
