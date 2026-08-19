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
- `sdpa-gmp.params`, `discovery.result`, and `approximate_solution.json`: the
  legacy names for the `p` baseline.
- `numerical/p/` and `numerical/2p/`: separately named parameter, raw result,
  and normalized approximation files for both precision levels.
- `numerical/numerical_stability.json`: per-block spectra, numerical
  nullities, and kernel-projector comparisons.
- `manifest.json`: source hashes, parameters, structure, serialization
  settings, artifact hashes, and the blind-input policy.

Every public file in this directory tree except the self-referential manifest
is SHA-256 hashed by that manifest.

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
python3 tools/check_numerical_stability.py testcases/dlm-three-point-10/input
```

Regeneration and solver commands are documented in
`tools/dlm/README.md`.

## `p` / `2p` evidence

Both runs use exactly the same `discovery.dat-s` bytes:

| Run | Internal arithmetic | Printed matrix digits | Status | Runtime |
| --- | ---: | ---: | --- | ---: |
| `p` | 300 bits | 40 | `pdFEAS` | 78.094 s |
| `2p` | 600 bits | 80 | `pdFEAS` | 123.426 s |

The normalized approximations distinguish printed digits from the solver's
larger internal bit precision. The runs use
[nakatamaho/sdpa-gmp](https://github.com/nakatamaho/sdpa-gmp) commit
`ca110db5ea1cc46e811b70dfea9cbb25db74448d`; the binary SHA-256 is
`c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0`.

At relative eigenvalue threshold `1e-12`, all 31 blocks have the same
numerical nullity at `p` and `2p`. The worst operator-norm distance between
corresponding numerical kernel projectors is `7.39674990e-11`, for
`triple_sos.pi3.s_0`, below the declared `1e-8` check tolerance. This is
evidence for a stable face hypothesis, not an exact kernel oracle.
