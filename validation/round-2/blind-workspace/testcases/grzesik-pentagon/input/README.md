# Blind input: Grzesik pentagon SDP

This folder contains only the exact SDP model, the SDPA-GMP discovery input and
output, and a language-neutral transcription of the numerical optimizer. It
does not contain Grzesik's published rational Gram matrices.

The fixed objective is `24/625`. The task is to construct any exact rational
certificate attaining that value; matching the paper's particular optimizer is
neither required nor expected.

Coordinates in `model.json` are zero-based. Each off-diagonal term multiplies
the displayed symmetric matrix entry once, as specified by
`exact-block-sdp-model-v1`.

## Numerical provenance

The `numerical/` directory records two independent runs of the same
`discovery.dat-s` bytes:

| Run | Internal arithmetic | Printed matrix digits | Status | Runtime |
| --- | ---: | ---: | --- | ---: |
| `p` | 512 bits | 80 | `pdOPT` | 1.216 s |
| `2p` | 1024 bits | 160 | `pdOPT` | 3.998 s |

The normalized JSON files therefore claim 80 and 160 available decimal
digits, respectively. The larger internal bit counts are recorded separately;
they are not mislabeled as reliable output digits.

Both runs used the local binary built from
[nakatamaho/sdpa-gmp](https://github.com/nakatamaho/sdpa-gmp) commit
`ca110db5ea1cc46e811b70dfea9cbb25db74448d`. Its SHA-256 is
`c17c133367fff473f1683ea3fd4131d295a73038229231a0c6a1b725b27fd3f0`.
Every public artifact except the self-referential manifest is hashed in
`manifest.json`.

At the declared relative eigenvalue threshold `1e-12`, the numerical
nullities are stable:

| Block | `p` nullity | `2p` nullity |
| --- | ---: | ---: |
| `U` | 0 | 0 |
| `P` | 4 | 4 |
| `Q` | 1 | 1 |
| `R` | 2 | 2 |

The largest operator-norm distance between corresponding numerical kernel
projectors is `4.96429243e-15`. These are numerical face diagnostics, not
exact rank claims or supplied kernel equations. Reproduce the check with:

```console
python3 tools/check_numerical_stability.py testcases/grzesik-pentagon/input
python3 testcases/grzesik-pentagon/construction/check.py
```
