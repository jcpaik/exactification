# Blind input: DLM three-point bound 10

This fixture is the rational three-point SDP used in Theorem 4.3 of Dostert,
de Laat, and Moustrou for spherical codes in dimension `n = 4`, relaxation
degree `d = N = 6`, and `cos(theta) = 1/6`. The original minimization
objective `M` is retained in `model.json`, and the discovery problem adds the
equality `M = 10`.

This is an exactification **input**, not a proof. It contains a fresh
high-precision numerical solution but no published exact Gram matrices,
kernel relations, or serialized solution.

## Files

- `model.json`: exact rational model in `exact-block-sdp-model-v1`; its
  symmetric-entry coefficients are not rounded.
- `discovery.dat-s`: 120-decimal SDPA sparse projection of the fixed-objective
  feasibility problem. SDPA trace-inner-product factors are applied only in
  this projection.
- `sdpa-gmp.params`: 300-bit, `1e-40` discovery settings.
- `discovery.result`: raw output from a fresh SDPA-GMP solve.
- `approximate_solution.json`: the 31 numerical PSD `yMat` blocks extracted
  from that solve.
- `manifest.json`: source hashes, parameters, structure, serialization
  settings, artifact hashes, and the blind-input policy.

The ancillary construction is identified by the hashes of `ThreePoint.jl`,
`SemidefiniteProgramming.jl`, and `proofs.jl` in the manifest. The associated
arXiv source archive is [arXiv:2001.00256](https://arxiv.org/abs/2001.00256),
and the published article is available at
[doi:10.1137/20M1351692](https://doi.org/10.1137/20M1351692).

## Source-derived structure

The port reproduces these independently checked invariants:

- invariant-basis sizes: `23, 16, 11, 7, 4, 2, 1`;
- filtered two-dimensional representation rows: `27, 18, 11, 6`;
- 31 PSD blocks and 1,641 upper-triangular scalar coordinates;
- 116 symmetric triple-polynomial equations, 13 single-polynomial
  equations, and one objective equality;
- 24,462 nonzero affine matrix coefficients.

The checked numerical solution has objective 10 and maximum equality
residual below `1e-30` after parsing the printed 40-digit matrices. Run:

```console
python3 tools/dlm/check_three_point.py
```

Regeneration and solver commands are documented in
`tools/dlm/README.md`.
