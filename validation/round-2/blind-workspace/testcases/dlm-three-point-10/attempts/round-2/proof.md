# Exact certificate: dlm-three-point-10

The independent public `p` and `2p` SDPA-GMP solutions give stable nullities
for all 31 blocks, with total nullity 44 across 22 singular blocks. Numerical
graph-chart recovery produced the same exact rational kernel subspace at both
precisions for every singular block. The maximum recovered relation height is
110341440. Detailed spectra, residual improvements, principal angles, pivot
conditioning, exact relation matrices, and exact kernel bases are retained in
`spectra.json` and `kernels.json`.

The largest generic relation jobs exposed a performance issue in dense SymPy
exact rank for `triple_sos.pi3.s_0`. Both p/2p runs were interrupted after
about 774 seconds and retained as operational events. The same numerical graph
chart was then certified in explicit pivot form: distinct identity-pivot
coordinates prove relation rank 25, the two kernel pivot coordinates prove
kernel rank 2, and exact Fraction arithmetic proves `M V = 0`. This changed no
objective, nullity, field, or kernel branch. An independent public-only replay
recovered the same chart and relation height 4348080 in about 5.4 seconds.

The enlarged exact affine system has 1641 variables and 689 rows, with exact
and two-prime modular rank 601 and 1040 free variables. Shared denominator
`2^160`, a reduced FLINT solve, and full exact substitution satisfy every
enlarged row and every one of the 130 original equalities.

The trusted symmetric-Schur emitter accepted all 31 rational PSD blocks. The
fresh command

```sh
python3 -B -m verify check testcases/dlm-three-point-10/input/model.json testcases/dlm-three-point-10/attempts/round-2/certificate.json --json
```

returned exit zero with exact objective `10`, 31 checked blocks, and 130
checked constraints. The supported workflow status is
`EXACT_SDP_CERTIFICATE`. No construction, oracle, prior attempt, or exact
target matrix was used.
