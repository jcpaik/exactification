# First SDPA-GMP Run

The 512-bit run in [`grzesik-512.result`](grzesik-512.result) successfully
recovers Grzesik's objective coefficient:

| Quantity | Value |
| --- | --- |
| SDPA-GMP status | `pdOPT` |
| Iterations | 67 |
| Reported correct digits | 49.4 |
| Primal-dual gap | \(1.4324459500879372\times10^{-51}\) |
| Numerical \(u\) | \(0.0384000\ldots0000783954\ldots\) |
| Recovered \(u\) | \(24/625\) |
| Reconstruction error | \(7.84\times10^{-52}\) |

Provenance:

| Artifact | Value |
| --- | --- |
| SDPA-GMP source | commit `ca110db5ea1cc46e811b70dfea9cbb25db74448d` |
| Platform | macOS, arm64 |
| Arithmetic precision | 512 bits |
| Input SHA-256 | `c4ca3642d4227676c15f88ebb0c9889c7e5b1bf8850be8e5300664e6ec68824d` |
| Result SHA-256 | `770371d603f88b298a59fadd3f3ab7dc8df826f7eedd00a12e561a357dc8632d` |

The published rational certificate was then checked independently. Its
fourteen normalized coefficients are

```text
24/625 24/625 24/625 24/625 24/625 24/625 322/9375
471/12500 24/625 24/625 24/625 24/625 -63/3125 24/625
```

Their maximum is exactly \(24/625\), and every principal minor of each of the
three rational Gram matrices is nonnegative.

## Exactification lesson

The optimal Gram matrices are not unique. SDPA-GMP found the correct objective
but not Grzesik's particular matrices. For example, the solver returned
\(p_{12}\approx-0.0898296790591\), whereas Grzesik chose
\(p_{12}=-36/625=-0.0576\). Several inequality slacks also differ from those of
the published certificate.

Consequently, entrywise rational reconstruction of an arbitrary optimizer is
not a viable general strategy here. The next exactification pass should:

1. recover the objective first;
2. detect approximate Gram-matrix kernels and the active inequality face;
3. solve the resulting affine/KKT constraints for a convenient rational point
   on the optimal face, using symmetry where available; and
4. verify the resulting coefficient inequalities and PSD conditions exactly.

This is a useful feature of the testbed: it separates easy recovery of the
sharp bound from the harder problem of selecting and exactifying a proof
certificate.
