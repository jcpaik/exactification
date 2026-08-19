# Exact certificate: obfuscated-rational-kernel

The two independent public SDPA-GMP solutions both have a three-dimensional
numerical kernel. Graph-coordinate recovery at each precision selected kernel
coordinates `[0, 7, 9]` and independently returned the same exact rank-seven
integer relation space, of height 168929. The maximum normalized relation
residual improved from `1.34293315221926829239025406257e-41` at `p` to
`7.46711776994743728943165364846e-42` at `2p`. The full p/2p spectra,
principal-angle checks, pivot conditioning, exact relations, and exact kernel
basis are recorded in `spectra.json` and `kernels.json`.

The recovered kernel equations and the manifest's scalar fixed objective were
added to the original eight generic equalities. The exact affine system has 55
symmetric-entry variables, exact rank 35, and 20 free coordinates. Shared
64-bit dyadic rounding followed by an exact reduced solve satisfies all 40
enlarged equations, including all original equations, on exact replay.

The trusted trace emitter accepted the resulting rank-seven block. The fresh
command

```sh
python3 -B -m verify check testcases/obfuscated-rational-kernel/input/model.json testcases/obfuscated-rational-kernel/attempts/round-2/certificate.json --json
```

checked one PSD block and all nine model constraints, returned exit zero, and
computed the exact objective `2224093617954365/48084958827`. The supported
workflow status is `EXACT_SDP_CERTIFICATE`. No construction, oracle, prior
attempt, exact target matrix, or public face projector was used.
