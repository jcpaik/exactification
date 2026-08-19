# Pentagons in Triangle-Free Graphs

This directory is the first exactification testbed. The problem is to maximize
the asymptotic induced density of \(C_5\) among triangle-free graphs:

\[
\pi_{C_5}(K_3)=\frac{24}{625}.
\]

The extremal construction is the balanced blow-up of \(C_5\).

## Flag-algebra types in the two original proofs

Both independent proofs use the same three triangle-free types on three
vertices, up to a relabeling of \(P_3\):

| Type | Underlying graph | HHKNR labels | Grzesik labels |
| --- | --- | --- | --- |
| \(\sigma_0\) | \(\overline{K_3}\) | no edges | no edges |
| \(\sigma_1\) | \(K_2\sqcup K_1\) | edge \(12\) | edge \(12\) |
| \(\sigma_2\) | \(P_3\) | edges \(13,23\), center \(3\) | edges \(12,23\), center \(2\) |

In both calculations, two order-4 flags overlap in their three labeled
vertices, producing an unlabeled graph on
\(4+4-3=5\) vertices. The final identities are therefore expanded over the
14 isomorphism classes of triangle-free graphs on five vertices.

### HHKNR

Hatami, Hladký, Král', Norine, and Razborov use symmetry-adapted linear
combinations of the order-4 flags:

- a 2-dimensional \(+\) block for \(\sigma_0\);
- a 3-dimensional \(+\) block and a 2-dimensional \(-\) block for
  \(\sigma_1\);
- a 2-dimensional \(+\) block and an additional antisymmetric rank-one
  square for \(\sigma_2\).

The paper also defines the trivial type \(0\) and the fully labeled pentagon
type \(P\). The type \(P\) is used for the uniqueness and exact-extremal-
structure argument, not for the basic upper-bound calculation in Theorem 3.1.

Source: [On the Number of Pentagons in Triangle-Free Graphs](https://arxiv.org/abs/1102.1634).

### Grzesik

Grzesik uses the complete order-4 flag bases:

| Type | Number of flags | PSD block |
| --- | ---: | ---: |
| \(\sigma_0\) | 8 | \(P\in\mathbb S_+^8\) |
| \(\sigma_1\) | 6 | \(Q\in\mathbb S_+^6\) |
| \(\sigma_2\) | 5 | \(R\in\mathbb S_+^5\) |

With \(l=5\), each of the 14 triangle-free five-vertex graphs supplies one
affine upper-bound constraint. The SDP minimizes the largest of those
coefficients subject to \(P,Q,R\succeq0\). Grzesik reports explicit rational
matrices with optimum \(24/625\).

Source: [On the maximum number of five-cycles in a triangle-free graph](https://arxiv.org/abs/1102.0962).

## SDP encoding

[`grzesik_sdp.py`](grzesik_sdp.py) transcribes the fourteen expressions in
Theorem 2. It introduces the scalar \(u\), the upper-triangular entries of
\(P,Q,R\), and imposes

\[
120u-E_i(P,Q,R)\geq 0\qquad(1\leq i\leq14),
\]

where \(E_i\) is the corresponding expression inside Grzesik's maximum. In
SDPA standard form this is one 14-dimensional diagonal block and PSD blocks of
sizes \(8,6,5\). There are 73 scalar variables in total. All input coefficients
are integers.

Generate the sparse instance from the repository root:

```sh
python3 problems/pentagons-triangle-free/grzesik_sdp.py generate
```

This writes [`data/grzesik.dat-s`](data/grzesik.dat-s). The committed
[`data/grzesik-512.param`](data/grzesik-512.param) requests 512-bit arithmetic,
a \(10^{-50}\) stopping tolerance, and 80 displayed digits for solution data.

## SDPA-GMP reproduction

The first run used the native `sdpa_gmp` executable built from the official
[SDPA-GMP repository](https://github.com/nakatamaho/sdpa-gmp) at commit
[`ca110db5`](https://github.com/nakatamaho/sdpa-gmp/commit/ca110db5ea1cc46e811b70dfea9cbb25db74448d)
(version 7.1.3). On macOS/Clang the bundled SPOOLES 2.2 source needed three
build-only changes from `IVinit(nfront, NULL)` to `IVinit(nfront, 0)`, and the
C++ compilation needed `-std=c++11`. These changes were made only in the
temporary upstream build tree.

Run the generated instance with:

```sh
SDPA_GMP_BIN=/path/to/sdpa_gmp
"$SDPA_GMP_BIN" \
  -ds problems/pentagons-triangle-free/data/grzesik.dat-s \
  -o problems/pentagons-triangle-free/results/grzesik-512.result \
  -p problems/pentagons-triangle-free/data/grzesik-512.param

python3 problems/pentagons-triangle-free/grzesik_sdp.py recover \
  problems/pentagons-triangle-free/results/grzesik-512.result
```

The result was `pdOPT` after 67 iterations, with 49.4 reported correct digits
and primal-dual gap \(1.43\times10^{-51}\). The full-precision numerical
objective was

```text
0.0384000000000000000000000000000000000000000000000007839543469097845425146269765504
```

Continued-fraction reconstruction with denominator at most 10,000 returns
\(24/625\); its distance from the displayed iterate is
\(7.84\times10^{-52}\). This matches Grzesik's reported coefficient. The raw
output and detailed observations are in [`results/`](results/README.md).

## Exact cross-check

The same script contains Grzesik's published rational matrices only for an
independent post-solve check. It verifies PSD exactly by checking every
principal minor with fraction-free integer determinants, evaluates all
fourteen expressions over `Fraction`, and checks that their maximum is exactly
\(24/625\):

```sh
python3 problems/pentagons-triangle-free/grzesik_sdp.py verify-paper
```

The numerical solve does not use these matrices or an initial point derived
from them.

The next HHKNR symmetry-adapted experiment will test block reduction and the
relationship between a singular full-basis solution and positive-definite
reduced blocks.
