# Blind exactification executor report — round-2

## Blind preflight

Execution was confined to this blind workspace. `BLIND_WORKSPACE_INVENTORY.json` listed 55 files, and the initial check found exactly 55 files outside the inventory itself: no missing or extra paths, no size or SHA-256 mismatch, and no construction-, oracle-, attempt-, or certificate-named leaked path. The workflow manual, testcase contract, and verifier format were read in full before exactification. No repository Git data, parent/sibling validation directory, construction, oracle, prior attempt, published certificate, target matrix, or expected kernel was inspected.

## Exact results

| Case | Exact objective | Exact ranks | Generic exact verifier | Manifest-aware harness | Certificate SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `obfuscated-rational-kernel` | `2224093617954365/48084958827` | `moment_matrix=7` | zero exit; 1 block, 9 constraints | zero exit; `EXACT_SDP_CERTIFICATE` | `945f086744c3428413a607efa07943f52c152a54126952a0d0561d5399dc75b9` |
| `grzesik-pentagon` | `24/625` | `U=1, P=4, Q=5, R=3` | zero exit; 4 blocks, 14 constraints | zero exit; `EXACT_SDP_CERTIFICATE` | `a0fbf43ad114dfea0cd4c943ce050c13c1d6f36adf2baab8c3929a93c7585a71` |
| `dlm-three-point-10` | `10` | grouped below | zero exit; 31 blocks, 130 constraints | zero exit; `EXACT_SDP_CERTIFICATE` | `3bbf0fd32abc4f55012db3d0cb8f5997d9af95988b3d60a3dd0e0d30b7a6f40c` |

The exact DLM ranks, grouped without omission, are:

- rank 0: `bound_scalar.B`, `gegenbauer_scalar.a_3` through `a_6`, `three_point_kernel.F_6`;
- rank 1: `gegenbauer_scalar.a_1`, `gegenbauer_scalar.a_2`, `three_point_kernel.F_5`, `triple_sos.pi2.s_3`;
- rank 2: `three_point_kernel.F_4`, `triple_sos.pi2.gram_determinant`, `triple_sos.pi2.s_2`;
- rank 3: `three_point_kernel.F_3`;
- rank 4: `three_point_kernel.F_2`, `triple_sos.pi2.s_1`;
- rank 5: `single_interval_sos.q_0`, `single_interval_sos.q_1`;
- rank 6: `three_point_kernel.F_0`, `three_point_kernel.F_1`, `triple_sos.pi3.s_3`;
- rank 7: `triple_sos.pi1.s_3`, `triple_sos.pi2.s_0`;
- rank 8: `triple_sos.pi1.gram_determinant`;
- rank 9: `triple_sos.pi3.gram_determinant`;
- rank 10: `triple_sos.pi1.s_2`, `triple_sos.pi3.s_2`;
- rank 14: `triple_sos.pi1.s_1`;
- rank 16: `triple_sos.pi3.s_1`;
- rank 20: `triple_sos.pi1.s_0`;
- rank 25: `triple_sos.pi3.s_0`.

## Held-out obfuscated rational kernel

The single 10×10 block had three values at the independent files' 40-digit printed noise floor and a stable normalized positive cluster beginning near `0.218462`, producing nullity 3. Basis-invariant graph recovery selected kernel coordinate indices `Q=[0,7,9]` and positive indices `P=[1,2,3,4,5,6,8]`. Both runs independently returned the same rank-7 integer relation space and exact rank-3 kernel basis, with relation height `168929`.

The maximum rowwise normalized relation residual improved from `1.3429331522192683e-41` at p to `7.467117769947437e-42` at 2p. The normalized block-kernel residual improved from `6.895115667532859e-42` to `4.914706971682532e-42`; principal-angle sine improved from `1.727401824088716e-41` to `1.417689934831748e-41`; and maximum graph-coordinate error improved from `2.328243616554070e-41` to `1.019839316048717e-41`. The positive-space coordinate minor had condition estimate about `1.590` at both precisions, and the corresponding block minor about `8.385`.

No exact model row or target matrix was used to discover this face. Provenance is `numerical_graph_chart`. The recovered face added 30 raw `XV=0` rows of exact rank 27. With the nine-dimensional original/objective row space, the complete affine system had exact rank 35, 20 free coordinates, and one row-space overlap. A shared `2^64` grid and exact FLINT backsolve produced a rank-7 PSD block at the manifest target. One diagnostic helper indexing error was retained in `operational-failures.json`; correcting matrix extraction did not change the mathematical branch.

## Grzesik pentagon

The p/2p spectra selected nullities `U=0`, `P=4`, `Q=1`, and `R=2`. Independent graph recoveries returned identical exact relation spaces, with relation heights `3`, `1`, and `2`. Across the singular blocks, rowwise relation, block-kernel, graph-coordinate, and principal-angle diagnostics improved by roughly 38 decimal orders from the 80-digit p file to the 160-digit 2p file. The selected block-positive minor condition estimates were approximately `56.1` for `P`, `139.8` for `Q`, and `112.2` for `R`, stable at both precisions.

The first kernel-face reconstruction omitted active scalar inequalities. Exact trace emission rejected it because `five_vertex_case_03` equalled `-3419/22282920707136844948184236032000`, violating `ge`. Both numerical runs classified ten constraints (`01`–`05`, `09`–`12`, and `14`) as active: their slacks decreased from about `1e-49` at p to `1e-99` at 2p. Adding those exact scalar face rows was the only mathematical branch change.

The final system had 73 variables, 59 raw rows, exact rank 51, and 22 free variables. Kernel face codimension was 41, active-plus-objective rank 11, and their row-space overlap 1. A shared `2^96` grid passed all raw rows, all 14 original inequalities, and all PSD traces, yielding exact ranks `U=1, P=4, Q=5, R=3`. The rejected active-set branch and nonzero emitter event were retained. A later direct script-path harness invocation encountered an import-context `ModuleNotFoundError`; packaging uses module/workspace import context and records that operational event separately.

## DLM three-point bound 10

All 31 blocks had stable p/2p nullities. Twenty-two were singular: six scalar-zero blocks and sixteen non-scalar blocks recovered by graph-coordinate relations. Every non-scalar p/2p pair produced the same exact kernel basis; full relation ranks therefore identify the same annihilator row space. Maximum rowwise relation residuals improved by approximately 39–51 decimal orders from p to 2p, and `kernels.json` records operator residuals, principal angles, graph errors, and pivot conditioning for every singular block.

The largest fallback branch, `triple_sos.pi3.s_0`, has nullity 2, exact relation rank 25, and height `4348080`. The attempt's p/2p rowwise residuals improve from `1.2760243720669974e-36` to `2.505655325430203e-76`, with identical exact graph bases. A separate public-input-only replay after execution independently corroborated the same `P/Q` chart, exact identities `M[:,P]=I_25`, `V[Q]=I_2`, and `MV=0`; it measured relation residual `1.424e-36 -> 2.784e-76` and principal-angle sine `2.516e-36 -> 4.398e-76` in 5.31 seconds. That replay remained in `/private/tmp` and was not a consumed attempt artifact.

The complete DLM face contributed 558 raw kernel rows with theoretical codimension 486. Together with the original/fixed-objective rows, the exact system contained 1641 variables and 689 raw rows. Both primes gave rank 601; the exact FLINT solve certified rank 601 and left 1040 free coordinates. The original-plus-objective rank was 130, with face overlap 15. A shared `2^160` grid produced maximum candidate numerator/denominator sizes of 241/242 bits, passed exact substitution into all 689 rows, and emitted complete PSD traces for all 31 blocks.

Four DLM operational events are retained. A sandbox process-list diagnostic exited nonzero, and a premature output existence check also exited nonzero. More materially, both generic `pi3.s_0` recoveries found numerical graph relations but spent about 774 seconds in dense SymPy exact rank; they were interrupted with `SIGINT`/exit 130. The fallback preserved the same nullity and graph chart, certified relation rank from the explicit distinct non-Q pivot coordinates, checked `MV=0` using exact fractions, and completed both p/2p runs without changing the mathematical branch.

## Principal commands

The recovery template used independently for each p/2p non-scalar block was:

```text
python3 exactify/recover_relations.py --approx <p-or-2p.json> --block <name> --nullity <k> --output <relation.json> --decimal-precision <dps> --maximum-denominator-power <power> --accept-residual <threshold>
```

The exact configuration and affine reconstruction used the supplied generic tools:

```text
python3 exactify/build_affine_config.py --fixed-objective <target> --projectors <scalar-or-empty.json> --relation-override <relation.json> ... --output <affine-config.json>
python3 exactify/affine_modular_solve.py --model <model.json> --approx <2p.json> --config <affine-config.json> --output <candidate.json> --system-output <affine-system.json> --denominator-bits <bits>
```

Every final candidate was traced and checked in fresh processes:

```text
python3 -m verify emit-traces <model.json> <candidate.json> -o <certificate.json>
python3 -m verify check <model.json> <certificate.json> --json
python3 -m validation.testcase_harness testcases/<case-id> round-2
```

`run.json` is generated last from explicit `commands.json` and `discovery.json` with:

```text
python3 exactify/make_run_records.py --case-root testcases/<case-id> --attempt-id round-2 --commands-json attempts/round-2/commands.json --discovery-json attempts/round-2/discovery.json --started-utc <start> --ended-utc <end>
```

## Artifact locations

- Held-out attempt: `testcases/obfuscated-rational-kernel/attempts/round-2/`
- Grzesik attempt: `testcases/grzesik-pentagon/attempts/round-2/`
- DLM attempt: `testcases/dlm-three-point-10/attempts/round-2/`

Each directory contains the required discovery evidence (`objective-candidates.json`, `spectra.json`, `kernels.json`), exact affine record (`affine-system.json`), exact point and trace certificate (`candidate.json`, `certificate.json`), verifier reports, proof narrative, operational events when applicable, and final provenance record. Fresh manifest-aware harness checks exited zero for all three attempts and returned `EXACT_SDP_CERTIFICATE`. Exact certificate verification is independent of all numerical discovery files.
