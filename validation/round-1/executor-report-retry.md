# Blind exactification executor report — retry-1

> **Historical scope note:** This report records the successful Round 1 retry
> exactly as executed. All three exact SDP certificate results remain valid.
> A later fixture audit reclassified `rotated-rational-kernel` as a transparent
> control because its public projector equality exposes the supporting face; it
> is not the stronger held-out numerical-subspace test now required by the
> [acceptance protocol](../ACCEPTANCE.md). The replacement
> `obfuscated-rational-kernel` fixture subsequently passed the isolated Round 2
> run. See the [Round 1 operational record](OPERATIONAL.md) and
> [Round 2 executor report](../round-2/executor-report-round-2.md).

## Scope and read allowlist

This run stayed inside
`/Users/jcpaik/Documents/research/exactification/validation/round-1/blind-workspace`.
The read allowlist was:

- `manual/TESTCASE_CONTRACT.md`;
- `manual/EXACTIFICATION_WORKFLOW.md`;
- `verify/FORMAT.md` and execution of the copied `verify` package;
- the public `input/` directory of the current testcase, opened in the required
  order: `rotated-rational-kernel`, `grzesik-pentagon`, then
  `dlm-three-point-10`; and
- files created during this retry under `exactify/` and each
  `attempts/retry-1/` directory.

No oracle, previous attempt, published exact matrix, target matrix, parent or
sibling directory, Git history, internet source, or separate fallback
certificate/strategy was inspected. Repository commit and dirty-worktree
fields in `run.json` are therefore explicitly null with a blind-restriction
note.

## Exact outcomes

| Case | Blocks | Constraints | Exact objective | Exact ranks | Certificate SHA-256 | Result |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `rotated-rational-kernel` | 1 | 2 | `0` | `X=3` | `fe2825989f522281facb57e5619938074cb8765fbf19c46c531d2529e677db1e` | `EXACT_SDP_CERTIFICATE` |
| `grzesik-pentagon` | 4 | 14 | `24/625` | `U=1, P=4, Q=5, R=3` | `5a8b7c17b8d1689fa1b716e288a7abc7e1e13b686fc6b6699d5989b36575ab94` | `EXACT_SDP_CERTIFICATE` |
| `dlm-three-point-10` | 31 | 130 | `10` | all 31 ranks recorded in `verification.json` | `f65c289dae39dfdd51dc9bd62402fa50051deaf3483abc961c279dfcada940e6` | `EXACT_SDP_CERTIFICATE` |

All three final checks were rerun after metadata generation. Each exited zero
with JSON status `verified`. Every attempt contains `run.json`,
`objective-candidates.json`, `spectra.json`, `kernels.json`, `candidate.json`,
`certificate.json`, `verifier-output.json`, `verification.json`, and
`proof.md`. Additional discovery and failure diagnostics are retained where
applicable.

## Construction summaries

### Rotated rational kernel

The first affine form is exactly `trace(A X)` for a rational rank-three
orthogonal projector `A`. The numerical matrix confirms nullity three without
selecting individual eigenvectors. The closed-form candidate
`X=(7/3)(I-A)` is rational PSD of rank three, annihilates `A`, and has trace
seven.

### Grzesik pentagon

The public 512-bit point gives nullities `P=4`, `Q=1`, and `R=2` with clear
positive spectral gaps. Basis-invariant kernel projectors rationalize exactly
at denominator bounds at most 100. Constraints 01–05, 09–12, and 14 track the
solver noise and were imposed as active; constraints 06, 07, 08, and 13 have
strict numerical margins. The resulting exact face has a PSD rational point
after 80-bit affine rounding.

### DLM three-point bound

Nullities were classified for all 31 blocks. Rational projectors recovered all
but `triple_sos.pi1.s_0`; that 23-by-23 block was recovered by twenty
independent row relations at denominator bound `10^8`, exact rank 20, relation
height `110341440`, and maximum normalized residual about `7.37e-37`.

The enlarged system has 689 rows over 1,641 upper-triangular coordinates.
Sparse elimination over both `F_1000000007` and `F_1000000009` independently
gave rank 601. A 601-by-601 subsystem was solved exactly with FLINT. The 1,040
free coordinates used one shared dyadic denominator `2^100`, and all 689 rows
were rechecked over the rationals before PSD trace emission.

## Principal commands

Full argument arrays and exit codes are retained in each `run.json`. The final
proof commands were:

```sh
python3 -m verify emit-traces testcases/rotated-rational-kernel/input/model.json testcases/rotated-rational-kernel/attempts/retry-1/candidate.json -o testcases/rotated-rational-kernel/attempts/retry-1/certificate.json
python3 -m verify check testcases/rotated-rational-kernel/input/model.json testcases/rotated-rational-kernel/attempts/retry-1/certificate.json --json

python3 exactify/affine_round.py --model testcases/grzesik-pentagon/input/model.json --approx testcases/grzesik-pentagon/input/approximate_solution.json --config testcases/grzesik-pentagon/attempts/retry-1/discovery-config.json --output testcases/grzesik-pentagon/attempts/retry-1/candidate.json --system-output testcases/grzesik-pentagon/attempts/retry-1/affine-system.json --denominator-bits 80
python3 -m verify emit-traces testcases/grzesik-pentagon/input/model.json testcases/grzesik-pentagon/attempts/retry-1/candidate.json -o testcases/grzesik-pentagon/attempts/retry-1/certificate.json
python3 -m verify check testcases/grzesik-pentagon/input/model.json testcases/grzesik-pentagon/attempts/retry-1/certificate.json --json

python3 exactify/recover_projectors.py --approx testcases/dlm-three-point-10/input/approximate_solution.json --nullities testcases/dlm-three-point-10/attempts/retry-1/nullities.json --output testcases/dlm-three-point-10/attempts/retry-1/kernel-recovery.json --decimal-precision 90 --maximum-denominator-power 18
python3 exactify/recover_relations.py --approx testcases/dlm-three-point-10/input/approximate_solution.json --block triple_sos.pi1.s_0 --nullity 3 --output testcases/dlm-three-point-10/attempts/retry-1/kernel-relations-pi1-s0.json --decimal-precision 90 --maximum-denominator-power 12 --accept-residual 1e-30
python3 exactify/affine_modular_solve.py --model testcases/dlm-three-point-10/input/model.json --approx testcases/dlm-three-point-10/input/approximate_solution.json --config testcases/dlm-three-point-10/attempts/retry-1/discovery-config.json --output testcases/dlm-three-point-10/attempts/retry-1/candidate.json --system-output testcases/dlm-three-point-10/attempts/retry-1/affine-system.json --denominator-bits 100
python3 -m verify emit-traces testcases/dlm-three-point-10/input/model.json testcases/dlm-three-point-10/attempts/retry-1/candidate.json -o testcases/dlm-three-point-10/attempts/retry-1/certificate.json
python3 -m verify check testcases/dlm-three-point-10/input/model.json testcases/dlm-three-point-10/attempts/retry-1/certificate.json --json
```

## DLM operational failures and recovery

Both material stalls are preserved in
`testcases/dlm-three-point-10/attempts/retry-1/operational-failures.json`.

1. The initial backend spent about 480 seconds recomputing per-block face ranks
   on global 1,641-column dense matrices and never reached global elimination.
   It was interrupted with exit 130 before writing a candidate. The redundant
   ranks were replaced by the exact codimension formula
   `n*k-k*(k-1)/2`.
2. The row-cleared integer DomainMatrix backend reached the real 689-by-1,641
   system, then spent about 360 seconds in SymPy's Python sparse
   fraction-free `sdm_rref_den` loop without completing pivots. It was
   interrupted with exit 130 before output. The replacement used two-prime
   sparse pivot selection and an exact reduced FLINT solve.

A later non-mathematical development diagnostic is also retained: independently
chosen continued-fraction denominators produced a 13 MB candidate with
roughly 27,000-digit values, exceeding Python's default integer-string parser
guard. It is preserved as `candidate-large-denominators.json`. Reusing a
single `2^100` denominator reduced the successful candidate to about 230 KB
with maximum rational spelling length 110, without changing the kernel branch
or exact affine validity.

## Ambiguities and limitations

- Each fixture exposed one normalized numerical run. Independent `p`/`2p`
  validation could not be performed from the allowlisted data; this is stated
  in every `spectra.json`. Complete exact checking, rather than numerical
  stability alone, is the success gate.
- The Grzesik active-set split is numerically unambiguous in the supplied run,
  but no second solver start was public. All original inequalities were still
  checked in their original directions by the exact verifier.
- The DLM manifest names a theorem result, but this blind workspace supplies no
  separately invoked theorem adapter or reverse witness. The supported status
  is therefore `EXACT_SDP_CERTIFICATE`, not `RIGOROUS_PROBLEM_BOUND` or
  `SHARP_OR_OPTIMAL`.
- `run.json` cannot contain its own SHA-256 without a self-reference. Each run
  hashes every other consumed/generated file and records this exception.

## Manual feedback

1. The required `run.json` Git commit/dirty fields conflict with a validation
   instruction forbidding Git-history inspection. The contract should define
   an explicit `not_inspected_blind_policy` value.
2. The workflow strongly prefers two numerical precision runs, while the
   testcase contract requires only one `approximate_solution`. A normative
   single-run fallback should be stated for sealed fixtures.
3. `kernels.json` provenance examples list `numerical_lll`,
   `complementary_slackness`, and `mixed`, but basis-invariant rational
   projector reconstruction is a natural direct implementation of the same
   subspace principle. It should receive a declared provenance label.
4. For large sparse systems, a full symbolic RREF can be substantially more
   expensive than modular selection of an exact nonsingular subsystem. The
   manual should explicitly bless the pattern used here: ranks over two large
   primes, exact rational square solve, then exact replay of every original
   row.
5. Independently rationalizing many free coordinates can cause an avoidable
   least-common-denominator explosion. Recommend a shared dyadic denominator
   as the first large-face rounding strategy.
6. The verifier's JSON aggregates constraint coverage, whereas Gate B asks for
   each identifier and exact residual/sign. Exposing optional per-constraint
   detail would make the checker report match the manual more directly.
7. Python 3.11+ limits integer-string conversion by default. Either document
   this operational boundary or parse canonical rationals without relying on
   that global interpreter limit; exact certificates can otherwise fail before
   mathematics is checked.
