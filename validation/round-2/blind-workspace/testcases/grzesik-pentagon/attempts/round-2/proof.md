# Grzesik pentagon exact SDP certificate — round-2

This blind attempt certifies an exact rational feasible point of the public `exact-block-sdp-model-v1` model with objective `24/625`. The certificate has exact ranks `U=1`, `P=4`, `Q=5`, and `R=3`.

The face was discovered independently from the public p and 2p numerical matrices. Stable nullities were `U=0`, `P=4`, `Q=1`, and `R=2`. Basis-invariant graph-coordinate recovery returned identical exact relation row spaces at both precisions, with relation heights 3, 1, and 2. The p-to-2p relation, block-kernel, and principal-angle residuals improve by about 38 decimal orders; pivot-minor condition estimates are recorded in `kernels.json`.

Ten scalar `ge` constraints were also classified active because their slacks decreased from about `1e-49` at p to `1e-99` at 2p. The first exact grid point omitted them and failed `five_vertex_case_03`; that nonzero emitter event and the unchanged-kernel recovery are retained in `operational-failures.json` and the failed candidate is retained under `diagnostics/`.

The final affine reconstruction used two modular primes, an exact 51-by-51 FLINT solve, a shared dyadic grid of 96 bits, and exact substitution into all 59 original/objective/active/kernel rows. The bundled emitter produced complete symmetric-Schur traces for all four blocks.

Fresh generic verification command:

```text
python3 -m verify check testcases/grzesik-pentagon/input/model.json testcases/grzesik-pentagon/attempts/round-2/certificate.json --json
```

It exits zero with objective `24/625`, 14 constraints checked, four blocks checked, and the ranks above. The manifest-aware acceptance command is:

```text
python3 validation/testcase_harness.py testcases/grzesik-pentagon round-2
```

This is an `EXACT_SDP_CERTIFICATE`; no sharpness or matching-witness claim is made.
