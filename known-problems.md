# Known Exact Problems for Flag-Algebra Benchmarks

This is a working list of extremal problems whose optimum is known exactly and
which can be expressed as flag-algebra semidefinite programs. They are ordered
roughly by their value as benchmarks for the numerical-to-exact pipeline, not by
historical importance.

Unless stated otherwise, all densities below are asymptotic. For a graph $H$,
its induced density means the probability that a uniformly random
$|V(H)|$-set induces $H$. Graph edge density is normalized by
$\binom{n}{2}$, and 3-graph edge density by $\binom{n}{3}$.

## Small rational sanity checks

1. **Mantel's theorem.** Maximize edge density subject to $K_3$-freeness.
   The exact optimum is

   $$
   \pi(K_3)=\frac12,
   $$

   attained by balanced complete bipartite graphs. This should be the smallest
   end-to-end test of flag generation, SDP serialization, rational recovery,
   and exact PSD verification. Falgas-Ravry and Vaughan give an explicit flag-
   algebra derivation as a running example in
   [their treatment of the semidefinite method](https://arxiv.org/abs/1110.1623).

2. **Turán's theorem.** For fixed $r\ge 3$, maximize edge density subject to
   $K_r$-freeness. The exact optimum is

   $$
   \pi(K_r)=1-\frac{1}{r-1},
   $$

   attained by the balanced complete $(r-1)$-partite graph. The cases
   $r=4,5$ provide a controlled increase in the number of admissible graphs
   while keeping the answer and extremal construction elementary.

3. **Goodman's monochromatic-triangle problem.** Minimize
   $p(K_3)+p(\overline{K_3})$, equivalently the density of monochromatic
   triangles in a red/blue coloring of $K_n$. The exact asymptotic minimum is

   $$
   \frac14.
   $$

   Balanced complete bipartite graphs and half-density quasirandom graphs both
   attain the limiting value. Multiple non-isomorphic extremizers make this a
   useful early test for non-unique optimal faces.

4. **Directed-triangle inducibility.** Maximize the induced density of the
   directed 3-cycle among oriented graphs. The exact optimum is

   $$
   i(\vec C_3)=\frac14,
   $$

   attained asymptotically by regular tournaments. This is a small test that
   the framework can handle directed structures; see
   [Sperfeld](https://arxiv.org/abs/1111.4813).

## Recommended first nontrivial benchmarks

5. **Pentagons in triangle-free graphs — recommended first problem.** Maximize
   the $C_5$-density subject to $K_3$-freeness. The exact optimum is

   $$
   \frac{5!}{5^5}=\frac{24}{625},
   $$

   attained by the balanced blow-up of $C_5$. This was proved directly with
   flag algebras by
   [Hatami, Hladký, Král', Norine, and Razborov](https://arxiv.org/abs/1102.1634)
   and independently by [Grzesik](https://arxiv.org/abs/1102.0962). It is small
   enough to inspect, but nontrivial enough to exercise several flag types and
   a meaningful rational PSD certificate.

6. **Inducibility of $K_4^-$.** Here $K_4^-$ is $K_4$ with one edge
   removed. Maximize its induced density over all graphs. The exact optimum is

   $$
   i(K_4^-)=\frac{72}{125},
   $$

   attained by balanced complete 5-partite graphs. Hirst obtained the exact
   upper bound by flag-algebra SDP in
   [The Inducibility of Graphs on Four Vertices](https://arxiv.org/abs/1109.1592).

7. **Inducibility of the paw graph.** The paw is a triangle with one pendant
   edge. Its exact inducibility is

   $$
   i(H_{\mathrm{paw}})=\frac38.
   $$

   This is the second four-vertex case solved by Hirst with flag-algebra SDP in
   [the same paper](https://arxiv.org/abs/1109.1592). It is a useful companion
   to $K_4^-$: the objective size is identical, but the optimal face and
   extremal construction differ.

8. **Inducibility of $C_5$.** Maximize the induced $C_5$-density over all
   graphs. The exact optimum is

   $$
   i(C_5)=\frac{5!}{5^5-5}=\frac1{26},
   $$

   attained by the iterated balanced blow-up of $C_5$. The recursive
   extremizer makes this substantially different from the triangle-free
   pentagon problem. See
   [Balogh, Hu, Lidický, and Pfender](https://arxiv.org/abs/1411.4645).

## Problems with additional density constraints

9. **Minimum triangle density at edge density $2/3$.** Among graph sequences
   with edge density $2/3$, minimize triangle density. The exact minimum is

   $$
   p(K_3)=\frac29,
   $$

   attained by balanced complete tripartite graphs. This is a concrete point
   of Razborov's exact solution to the full edge/triangle-density problem in
   [On the Minimal Density of Triangles in Graphs](https://people.cs.uchicago.edu/~razborov/files/triangles.pdf).
   It tests affine side constraints and exact dual multipliers.

10. **Minimum $K_4$-density at edge density $3/4$.** Among graph sequences
    with edge density $3/4$, minimize $K_4$-density. The exact minimum is

    $$
    p(K_4)=\frac{4!}{4^4}=\frac{3}{32},
    $$

    attained by balanced complete 4-partite graphs. This is a concrete rational
    instance of [Reiher's Clique Density Theorem](https://arxiv.org/abs/1212.2454)
    and a natural step up from the constrained triangle problem.

## Colored-graph benchmarks

11. **Three-color Ramsey multiplicity of triangles.** Minimize the density of
    monochromatic triangles in a 3-edge-coloring of $K_n$. The exact
    asymptotic minimum is

    $$
    \frac1{25}.
    $$

    Extremal colorings are based on blow-ups of the triangle-free 2-coloring of
    $K_5$. See
    [Cummings, Král', Pfender, Sperfeld, Treglown, and Young](https://arxiv.org/abs/1206.1987).
    This tests colored flags and symmetry reduction.

12. **Four-color Ramsey multiplicity of triangles.** Minimize the density of
    monochromatic triangles in a 4-edge-coloring of $K_n$. The exact
    asymptotic minimum is

    $$
    \frac1{256}.
    $$

    Extremal colorings are based on blow-ups of the two Ramsey colorings of
    $K_{16}$. The proof uses a symmetry-aware flag-algebra formulation; see
    [Kiem, Pokutta, and Spiegel](https://arxiv.org/abs/2312.08049). This is a
    larger rational stress test after the three-color case works.

## Algebraic and recursive exact values

13. **Inducibility of the directed 2-edge out-star.** Maximize the induced
    density of the oriented graph with arcs $x\to y$ and $x\to z$, with no
    edge between $y$ and $z$. The exact optimum is

    $$
    i(\vec S_3)=2\sqrt3-3.
    $$

    An iterated blow-up construction is extremal. This is the most attractive
    early test for PSLQ or minimal-polynomial recovery because the optimum is
    quadratic irrational rather than rational. The result appears in the
    flag-algebra/SDP work of
    [Falgas-Ravry and Vaughan](https://arxiv.org/abs/1110.1623).

## 3-uniform hypergraph benchmarks

14. **Independent-neighborhood forbidden families.** Falgas-Ravry and Vaughan
    proved the following exact 3-graph Turán densities using Flagmatic:

    $$
    \begin{aligned}
    \pi(K_4^-,C_5,F_{3,2})&=\frac{12}{49},\\
    \pi(K_4^-,F_{3,2})&=\frac5{18},\\
    \pi(J_4,F_{3,2})=\pi(J_5,F_{3,2})&=\frac38.
    \end{aligned}
    $$

    Here $K_4^-$ is the 3-graph with three of the four possible triples on
    four vertices, $F_{3,2}=\{abc,ade,bde,cde\}$, and $J_t$ consists of a
    center $x$, $t$ other vertices, and every triple containing $x$ and
    two of those vertices. The paper supplies computation scripts and
    certificate-related ancillary files, making these especially useful for
    comparison with a new exactifier:
    [On applications of Razborov's flag algebra calculus to extremal 3-graph theory](https://arxiv.org/abs/1110.1623).

15. **Induced-forbidden 3-graph densities.** The same Flagmatic work proves

    $$
    \pi(F_{3,2},\text{ induced }K_4^-)=\frac38
    $$

    and

    $$
    \pi(K_5^{(3)},\text{ induced 5-vertex 3-graphs with exactly 8 edges})
    =\frac34.
    $$

    In each expression, the displayed configurations are forbidden. These test
    induced constraints in a 3-uniform setting. Definitions and machine
    artifacts are in
    [Falgas-Ravry and Vaughan](https://arxiv.org/abs/1110.1623).

16. **Fano-plane Turán density.** Maximize 3-edge density subject to containing
    no Fano plane. The exact optimum is

    $$
    \pi(\mathbb F)=\frac34,
    $$

    attained by the balanced complete bipartite 3-graph, consisting of all
    triples meeting both parts. The result was not originally discovered by a
    flag-algebra SDP, but it is a clean exact hypergraph benchmark with a known
    finite extremal structure; see
    [Bellmann and Reiher](https://arxiv.org/abs/1804.07673).

## Suggested benchmark progression

1. Mantel's theorem.
2. Pentagons in triangle-free graphs.
3. $K_4^-$ and paw inducibility.
4. Minimum triangle density at edge density $2/3$.
5. Induced $C_5$.
6. Directed out-star $i(\vec S_3)=2\sqrt3-3$.
7. Three-color monochromatic triangles.
8. The rational 3-graph families with published Flagmatic artifacts.

This progression isolates failures: rational reconstruction and PSD checking
come first, followed by affine constraints, recursive extremizers, algebraic
number recovery, colored structures, and finally 3-uniform hypergraphs.

## Deliberate exclusions

- The inducibility of $P_4$ is still open, so it is not a ground-truth
  exactification benchmark.
- The classical Turán density of the tetrahedron $K_4^{(3)}$ is still open;
  the conjectured value $5/9$ must not be treated as known.
- Numerical flag-algebra bounds without a matching construction or a rigorous
  exact proof are not included.
