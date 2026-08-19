# Agent Workflow for Exactifying Singular SDPs

This is an operational manual for a fresh agent. It assumes no conversation
history and no knowledge of a published certificate. Its job is to turn an
exact SDP model plus high-precision numerical evidence into a certificate that
an independent program can verify using exact arithmetic.

The core method is Sections 3.1--3.4 of Dostert, de Laat, and Moustrou (DLM),
[Exact semidefinite programming bounds for packing problems](https://doi.org/10.1137/20M1351692),
with the authors' [arXiv version](https://arxiv.org/abs/2001.00256) and
[ancillary Julia/Nemo source](https://arxiv.org/src/2001.00256) serving as the
primary implementation references. DLM's essential move is to recover exact
equations for the *kernel subspace*, impose those equations, and only then
round within the resulting affine space. Do not round numerical eigenvectors
or raw SDP coordinates independently.

## 1. What counts as evidence

Keep two phases visibly separate.

### Exploration

The following are heuristics and are never a proof:

- a solver status such as `pdOPT`;
- small primal/dual residuals or a small duality gap;
- a decimal that is close to a rational or quadratic number;
- a spectral gap or a guessed nullity;
- an LLL/PSLQ relation with a small numerical residual;
- a rationalized matrix whose floating-point eigenvalues look nonnegative; or
- agreement with a value reported in a paper.

These facts may generate a candidate. Label all such output
`EXPLORATION_ONLY` until every exact gate in Section 10 passes.

### Proof

The proof begins only after the exact model is reparsed independently. A proof
uses exact field arithmetic to establish:

1. every original affine equality and inequality;
2. the exact objective value;
3. positive semidefiniteness of every complete block; and
4. the declared connection between SDP feasibility and the mathematical claim.

The LLL relations and numerical solution need not be trusted by the verifier.
They are scaffolding used to find an exact object.

## 2. Supported problem and field

Normalize the problem to an exact block SDP

\[
  \operatorname{opt}_{X_1,\ldots,X_b}
  c_0+\sum_i\langle C_i,X_i\rangle
  \quad\text{subject to}\quad
  X_i\succeq0,
  \qquad
  e_j(X_1,\ldots,X_b)\ \mathrel{\bowtie_j}\ 0,
\]

where each \(X_i\) is symmetric, every \(e_j\) is affine, and
\(\bowtie_j\in\{=,\ge,\le\}\). Vectorize the upper-triangular block entries in
a canonical order when the workflow below writes the affine system as
\(Ax=b\). There is no separate, competing set of scalar variables: \(x\) is
just this vector of displayed block entries.

This repository's authoritative rational proof representation is
[`verify/FORMAT.md`](../verify/FORMAT.md): `exact-block-sdp-model-v1` and
`exact-block-sdp-certificate-v1`. Its affine coefficient on an off-diagonal
entry multiplies that displayed entry once; a trace inner product therefore
uses coefficient \(2A_{ij}\) for \(i<j\). Affine inequalities remain `ge` or
`le` constraints in that format. A source adapter may instead introduce a
nonnegative \(1\times1\) slack block, but it must check exact equivalence and
document the change.

The mathematical workflow supports these fields:

- \(K=\mathbb Q\); and
- \(K=\mathbb Q(\alpha)\), where \(\alpha^2=d\), \(d>1\) is a positive
  squarefree integer, and the selected real embedding is \(\alpha=+\sqrt d\).

The procedure can discover a certificate in either field, but it does **not**
prove that such a certificate must exist. Rational SDP data can have an
optimizer of higher algebraic degree, as DLM explicitly warns. If both paths
fail cleanly, report that fact; do not force a false rationalization.

The repository verifier format named above currently implements the rational
path only. A quadratic case is not proof-complete until a versioned quadratic
model/certificate format and exact checker implement the selected embedding
and algebraic sign decisions. Do not serialize quadratic elements into the
rational format.

## 3. Required inputs and preflight

Read `manual/TESTCASE_CONTRACT.md`, then locate the testcase manifest. Before
running a solver, require:

- an exact, losslessly parsed model over the declared field;
- a documented vectorization convention for symmetric blocks;
- an objective sense and a theorem-level interpretation of a feasible
  certificate;
- either high-precision solver output or a reproducible command to generate it;
- the selected real embedding for a quadratic field;
- a writable attempt directory separate from any oracle/golden certificate;
  and
- an exact verifier command, or enough information to implement one without
  consulting an expected certificate.

Run these preflight checks:

1. Verify every input hash recorded in the manifest.
2. Parse every integer/rational/quadratic coefficient exactly. Never parse an
   exact coefficient through binary floating point.
3. Check dimensions, block symmetry, variable indices, and unique constraint
   identifiers.
4. Recompute model counts: variables, equalities, PSD blocks, and scalar block
   dimensions.
5. Evaluate the supplied numerical vector in the exact model at high precision
   and compare the recomputed residuals with the solver log.
6. Check the sign convention by evaluating the objective directly. Do not infer
   whether it is an upper or lower bound from the word "primal" or "dual".

If any check fails, stop with `INPUT_INVALID`. A certificate for a mistranscribed
SDP proves nothing about the intended problem.

## 4. The outer loop

Use the following loop rather than a single rounding attempt.

```text
validate exact model and theorem mapping
obtain high-precision optimization runs at p and 2p
generate exact objective candidates (unless one is explicitly supplied)

for objective candidate tau, simplest/stablest first:
    add objective(x) = tau exactly
    solve the resulting feasibility problem near its relative interior
    repeat at two or more precisions and, if possible, from different starts

    generate stable candidate nullities for every block
    for a small set of nullity combinations, best evidence first:
        recover kernel subspaces by DLM integer relations
        if that route is unstable/expensive, try a well-conditioned graph chart
        add X_i V_i = 0 exactly
        select affine pivots modularly and certify the reduced exact subsystem
        round all free coordinates on one shared grid, then backsolve exactly
        run every exact verification gate
        for a target-bound testcase, run the manifest-aware harness

        if all gates pass:
            package the proof and stop
        diagnose the failed gate and adapt one variable at a time

if no candidate passes:
    increase precision and relation-height limits, or revise the field/objective
    record a reproducible failure rather than claiming a proof
```

The exact verifier—and, for a testcase, the target-binding harness—is the
termination condition. Numerical closeness is not.

## 5. Objective discovery without a target certificate

DLM fixes a known sharp objective and solves feasibility. When the exact scalar
is not supplied, add this exploratory stage.

### Rational candidate

From independent high-precision optimization runs with values \(t_p,t_{2p}\):

1. Require agreement to substantially more digits than any proposed
   denominator or coefficient height can explain.
2. Enumerate continued-fraction convergents and nearby semiconvergents of the
   more accurate value. Use a denominator-height ladder rather than one large
   bound.
3. Retain only candidates whose distance decreases appropriately when the
   precision increases.
4. For each retained \(\tau\in\mathbb Q\), add
   \(c_0+c^{\mathsf T}x=\tau\) exactly and solve feasibility.

### Quadratic candidate

For a declared candidate field \(\mathbb Q(\sqrt d)\), run an integer-relation
algorithm on

\[
  (1,\sqrt d,t_{2p}).
\]

A relation \(A+B\sqrt d+C t\approx0\), \(C\ne0\), proposes

\[
  \tau=-\frac{A+B\sqrt d}{C}.
\]

Primitive-normalize the relation, validate it on a separately computed
higher-precision value, and then test exact feasibility. Searching a relation
does not establish the field or the objective; the exact certificate does.

### What the objective certificate proves

An exact feasible point at \(\tau\) proves only what feasibility at \(\tau\)
means for the normalized SDP. For a generic minimization problem it shows
\(\operatorname{opt}\le\tau\); for a generic maximization problem it shows
\(\operatorname{opt}\ge\tau\). Many extremal-graph certificates are dual
feasible objects whose objective gives a combinatorial upper bound. Use the
manifest's theorem mapping, not a generic slogan.

Do not call \(\tau\) optimal or sharp without an exact matching witness, a
zero-gap exact primal/dual pair, or another rigorous argument.

## 6. Obtain a relative-interior fixed-objective solution

For each exact candidate \(\tau\), turn optimization into the feasibility
problem

\[
  Ex=f,\quad g_r(x)\mathrel{\bowtie_r}0,\quad
  c_0+c^{\mathsf T}x=\tau,\quad X_i\succeq0.
\]

This matters because an interior-point feasibility solve aims at the relative
interior of the fixed-objective feasible set. At such a point, each block has
the smallest kernel forced throughout that face. DLM used SDPA-GMP for this
purpose. Use arbitrary precision and retain the complete decimal output.

If the solver cannot directly seek the relative interior:

- average several feasible points in high precision;
- use small random auxiliary objectives while retaining the exact objective
  equality, then average their solutions; or
- after a tentative face is found, maximize a common eigenvalue margin on that
  face.

Never add \(X_i\succeq\varepsilon I\) to a block believed to be structurally
singular. DLM's strategy is to force structural small eigenvalues to exact zero,
not to perturb them positive.

### Precision ladder

Start at no less than a few hundred bits for a nontrivial singular SDP. Let
`p` denote working bits and double it when a classification or relation is
unstable. Set solver tolerances comfortably above unit roundoff but far below
the anticipated spectral gap. Save at least two runs, normally at `p` and
`2p`, and never overwrite the earlier run.

For scale-independent diagnostics, compute

\[
\rho_{\rm eq}=
\max_j\frac{|(Ex-f)_j|}
 {1+|f_j|+\|E_{j,:}\|_1\|x\|_\infty},
\]

\[
\rho_{\rm obj}=
\frac{|c_0+c^{\mathsf T}x-\tau|}
 {1+|\tau|+\|c\|_1\|x\|_\infty},
\qquad
\rho_{\rm psd}=
\max_i\frac{\max(0,-\lambda_{\min}(X_i))}
 {\max(1,\|X_i\|_2)}.
\]

Use

\[
  \eta=\max(\rho_{\rm eq},\rho_{\rm obj},\rho_{\rm psd},
             100n_{\max}2^{-p})
\]

only as an exploratory noise scale. It is not a certified eigenvalue-error
bound.

## 7. Adaptive kernel-subspace recovery

### 7.1 Choose candidate nullities

For each numerical block \(X_i^*\), compute an SVD or a symmetric eigendecomposition
at the same or greater precision. Sort normalized singular values

\[
  0\le s_1\le\cdots\le s_m,
  \qquad s_j=\sigma_j/\max(1,\|X_i^*\|_2).
\]

Do not use one universal cutoff. Instead:

1. Scan cutoffs on a geometric grid beginning near the run's noise scale
   \(\eta\) and ending well below the stable positive cluster.
2. Treat every nullity created by a large adjacent spectral gap as a candidate.
3. Compare runs at `p` and `2p`. Structural-zero values should move toward zero
   with the residual/noise floor, whereas positive values should stabilize.
4. Prefer a nullity that is stable across precisions and starts, leaves a clear
   positive cluster, and later yields low-height relations.
5. Keep ambiguous neighboring nullities as alternate branches. Do not silently
   discard them.

For a candidate nullity \(k\), put an orthonormal basis of the corresponding
numerical subspace in the columns of \(N\in\mathbb R^{m\times k}\).

### 7.2 Rational field, primary route: DLM integer relations

The columns returned by an eigensolver are generally arbitrary real rotations
of the true kernel. Rounding those columns is invalid. Search instead for
integer row vectors \(a\in\mathbb Z^m\) such that

\[
  a^{\mathsf T}N\approx0.
\]

Find \(m-k\) independent relations. This is the rational form of DLM Section
3.2.

```text
input: N (m by k), precision p, candidate nullity k
S := [1, ..., m]
relations := empty integer matrix

while rank_Q(relations) < m-k:
    use LLL/PSLQ to find a nonzero integer combination
        a_S of the row vectors N[S, :]
    lift a_S to a in Z^m and primitive-normalize it
    if a increases exact row rank and passes numerical validation:
        append a
        remove from S a pivot index where a is nonzero
    else:
        raise relation-height allowance or numerical precision
        if repeated attempts fail, reject this nullity branch

M := canonical row basis of relations (HNF or exact RREF)
require rank_Q(M) = m-k
V := exact basis of null_Q(M)
require number of columns of V = k
return M, V
```

DLM's ancillary implementation uses Nemo's `lindep`, removes a row involved in
each relation, canonicalizes relations, and then computes the rational
nullspace. LLL originates in Lenstra, Lenstra, and Lovasz,
[Factoring polynomials with rational coefficients](https://doi.org/10.1007/BF01457454).

Use this DLM route first. It searches directly for a low-height rational
annihilator of the subspace, does not depend on choosing a coordinate chart,
and remains appropriate when no well-conditioned coordinate minor is stable.
On a large block it can nevertheless become costly or unstable: a simultaneous
relation may have much greater height than a simple coordinate description,
and arbitrary numerical kernel bases can make repeated `lindep` calls
expensive. Those symptoms trigger the fallback below; they are not permission
to round eigenvectors.

### 7.3 Rational field fallback: a graph chart of the kernel

This fallback recovers the same subspace in coordinates that are invariant
under a change of numerical kernel basis. Let a block have size \(n\), candidate
nullity \(k\), and positive-space dimension \(r=n-k\). From an independently
computed eigendecomposition at precision `p`, form a basis
\(U_+\in\mathbb R^{n\times r}\) for the positive eigenspace. Use
rank-revealing QR with column pivoting on \(U_+^{\mathsf T}\), or pivoted
Cholesky on the block, to select \(r\) coordinate indices \(P\) for which
\(U_+[P,:]\) is well conditioned. Let \(Q\) be the complementary \(k\) indices.

For a numerical block \(A\), solve at high precision

\[
  G=-A[P,P]^{-1}A[P,Q].
\]

The graph-basis matrix \(V\in\mathbb R^{n\times k}\), defined by

\[
  V[Q,:]=I_k,\qquad V[P,:]=G,
\]

spans \(\ker A\) in exact arithmetic. Unlike the columns returned by an
eigensolver, \(G\) is fixed by the subspace and the chosen coordinate sets
\((P,Q)\); rotating the numerical kernel basis does not change it.

```text
input: numerical blocks A_p and A_2p, nullity k
r := n-k
choose P of size r by pivoted QR on the positive space of A_p
Q := complement(P)
require the same P minor to remain full rank and well conditioned at 2p
compute G_p  := -solve(A_p[P,P],  A_p[P,Q])
compute G_2p := -solve(A_2p[P,P], A_2p[P,Q])
recover one rational G from the agreeing leading digits of G_p and G_2p
V[Q,:] := I;  V[P,:] := G
M[:,P] := I; M[:,Q] := -G
require over Q: M*V = 0, rank(M)=r, rank(V)=k
validate M and V against both independently computed numerical subspaces
```

Select \(P\) by conditioning, not lexicographic convenience. Record the
estimated smallest singular value and condition number of the selected
positive-space minor at `p` and `2p`. If the minor becomes ill conditioned,
changes rank, or causes large reconstruction amplification, try the next
rank-revealing pivot set. If no pivot set is stable, raise precision or return
to the DLM relation route; a graph chart is then not reliable evidence.

Recover the entries of \(G\) with a height ladder (continued fractions, PSLQ,
or a common-denominator search) and require the *same exact matrix* at `p` and
`2p`. For the exact \(M,V\), check \(MV=0\) and both ranks over
\(\mathbb Q\). At each precision also record

\[
 \frac{\|M N_t\|_2}{\|M\|_2\max(1,\|N_t\|_2)},\qquad
 \frac{\|A_tV\|_2}{\|A_t\|_2\max(1,\|V\|_2)},\qquad
 \sin\theta_{\max}(\operatorname{col}V,\operatorname{col}N_t),
 \quad t\in\{p,2p\}.
\]

Here \(N_t\) is an independently computed numerical kernel basis and
\(\theta_{\max}\) is the largest principal angle. Set acceptance thresholds
from each run's residual/noise scale, positive spectral gap, and measured
linear-solve amplification. The `2p` residuals and angles must track the lower
noise floor rather than plateau; merely matching a fixed decimal cutoff is not
enough. Finally, the reconstructed certificate must satisfy \(X_iV=0\)
exactly. This fallback rationalizes a basis-invariant graph of the subspace,
not the arbitrary eigenvectors and not an entrywise-rounded projector.

Use DLM/LLL as the general primary route and the graph chart as an explicit
fallback when a stable positive-space pivot set exists and its graph
coordinates have substantially lower height. Run both when affordable: equal
exact row spaces are strong diagnostic evidence, but exact certificate
verification remains the proof.

### 7.4 Relation acceptance and adaptive height

For a proposed relation define the basis-invariant normalized residual

\[
  r(a,N)=\frac{\|a^{\mathsf T}N\|_2}
                 {\|a\|_2\max(1,\|N\|_2)}.
\]

Use a coefficient-height ladder, for example doubling the allowed relation
bits. Keep enough numerical precision that `p` exceeds several times the
relation-bit allowance plus a safety margin. Accept a relation for further
exploration only when:

- it raises the exact rank;
- its residual is close to the current subspace noise rather than merely small
  in absolute terms;
- the same exact relation has a substantially smaller residual on an
  independently computed higher-precision subspace; and
- the exact subspace \(\operatorname{col}(V)\), embedded numerically, has small
  principal angles to \(\operatorname{col}(N)\) at both precisions.

Low height is evidence, not a gate of truth. A high-height relation may be
correct, and a low-height relation may be accidental. Exact feasibility and
PSD checking decide.

### 7.5 Quadratic field: recover a field-valued subspace

Let \(K=\mathbb Q(\alpha)\), \(\alpha^2=d\). With the same numerical
kernel matrix \(N\), form

\[
  \widetilde N=\begin{pmatrix}N\\ \sqrt d\,N\end{pmatrix}.
\]

Use LLL to find integer relations \((\lambda,\mu)\in\mathbb Z^m\times
\mathbb Z^m\) satisfying

\[
  (\lambda+\sqrt d\,\mu)^{\mathsf T}N\approx0.
\]

For each relation add the two rational rows

\[
  (\lambda^{\mathsf T},d\mu^{\mathsf T}),\qquad
  (\mu^{\mathsf T},\lambda^{\mathsf T})

\]

to a doubled matrix \(H\). Continue until

\[
  \operatorname{rank}_{\mathbb Q}H=2(m-k).
\]

Then \(\ker_{\mathbb Q}H\) has dimension \(2k\). Interpret every doubled
vector \((u,v)\) as \(u+\alpha v\), and extract a \(K\)-basis \(V\) of
dimension \(k\). Validate its numerical span under the selected embedding.
This is DLM Section 3.4; do not treat the conjugate embedding as the numerical
one.

### 7.6 Recover active affine inequalities

The repository proof model permits affine `ge` and `le` constraints in addition
to the equality-only DLM normal form. Evaluate every inequality in its
nonnegative orientation and scale its slack by the coefficient norm. Across the
same precision ladder:

- a slack that stabilizes well above the numerical noise is inactive and needs
  no face equation;
- a slack that decreases with the solver residual is a candidate active
  constraint; and
- a slack in the gray region creates two branches rather than a silent choice.

For an active branch, add that affine expression equal to zero in the internal
exact system. For an inactive branch, preserve its numerical margin when
choosing free rationals. This is the scalar analogue of kernel facial
reduction. It remains exploratory until the original `ge` or `le` constraint is
checked exactly in its original direction.

## 8. Add the face equations

For every exact kernel-basis column \(v\) of block \(i\), add

\[
  X_iv=0.

\]

This means one scalar affine equality per row of the product, with exact
duplicate equations removed later. It is not a trace constraint and it is not
the single quadratic equation \(v^{\mathsf T}X_iv=0\).

In the quadratic case, write \(X_i=X_{i,0}+\alpha X_{i,1}\) and
\(v=u+\alpha w\). Split \(X_iv=0\) into rational equations

\[
  X_{i,0}u+dX_{i,1}w=0,
  \qquad
  X_{i,1}u+X_{i,0}w=0.

\]

Append these equations to the original equalities, the fixed-objective
equality, and every candidate active affine inequality from Section 7.6. Keep
inactive inequalities out of the equality system. Before appending the fixed
objective, check the exact augmented row space: if the same equation is already
an original model row, do not add it again; if its left side is implied with a
different right side, reject the branch as inconsistent.

### 8.1 Expected face codimension

For a symmetric \(n\times n\) block and a full-column-rank kernel basis
\(V\in K^{n\times k}\), the exact linear map \(X\mapsto XV\) has rank

\[
  c(n,k)=nk-\frac{k(k-1)}2.
\]

Thus \(nk\) raw scalar equations contain \(k(k-1)/2\) symmetry
dependencies. In the graph chart of Section 7.3, an independent set consists
of the \(rk\) equations in the \(P\)-rows and the \(k(k+1)/2\) upper-triangle
equations in the \(Q\)-rows, where \(r=n-k\). Use this formula to predict the
per-block face rank and catch indexing or nullity errors. It does *not* imply
that adding the face rows raises the combined model rank by that amount:
original equalities can already contain part of the face. Record both the
theoretical face codimension and the measured combined rank.

### 8.2 Scalable exact affine reconstruction

Do not repeatedly run dense rational rank or RREF on every growing collection
of \(X_iV_i=0\) rows. That approach scales badly and can spend most of a run in
fraction-free exact division before producing a candidate. Use this pipeline:

```text
1. Generate original, objective-if-new, active, and face rows once.
   Clear denominators and primitive-normalize each sparse integer row.
2. Use the graph-chart subset above when available; otherwise retain raw rows
   and stream them through modular independence tests.
3. Compute rank and pivot row/column candidates modulo at least two suitable
   machine-word primes. A lower rank can mark a bad prime; distinct pivot sets
   at the same rank are not themselves an error. Sample more primes until the
   maximum rank stabilizes, then retain a full-rank pivot-minor candidate.
4. Certify the selected pivot minor as nonsingular over Q with an exact
   backend. Using that minor, express every other augmented row as an exact
   combination of the selected rows and check the complete row. This batched
   reduced solve certifies the claimed rank and consistency without full RREF.
5. Choose the nonpivot coordinates as free variables. After placing them on
   the shared grid from Section 9, solve the pivot coordinates over Q with
   FLINT/fmpq or an equivalent exact modular/rational solver.
6. Substitute the result into every raw original, objective, active, and
   X_i*V_i row—not merely the selected rows—and require exact zero.
```

The modular stage proposes pivots; exact nonsingularity, exact row-span checks,
and full-row substitution are proof obligations. Also compare the rank of the
coefficient matrix with the augmented matrix, first modularly and then through
the reduced exact row-span solve, so an inconsistent branch is rejected before
rounding. DLM used a
Kannan--Bachem-style integer reduction; see the primary
[Kannan--Bachem paper](https://doi.org/10.1137/0208040). A scalable
implementation may instead use the official
[FLINT exact-arithmetic library](https://flintlib.org/) after modular pivot
selection, while preserving the same exact gates.

Required exploratory checks before rounding:

- the enlarged exact system is consistent;
- its theoretical face codimension, modular ranks/primes, certified exact
  pivot minor, combined rank, overlaps, and free-variable count are recorded;
- every added row is traceable to a block and kernel vector;
- the higher-precision numerical point has a small residual in the enlarged
  system; and
- an exact solution of the selected subsystem is rechecked against every raw
  row; and
- the exact face has at least one degree of freedom unless a unique solution is
  expected from the equations themselves.

Inconsistency rejects the relation/nullity/objective branch. Do not drop an
original equation to make the system consistent.

## 9. Exact affine rounding

### 9.1 Rational path

Use the certified pivot subsystem from Section 8 and preserve the original
variable order in metadata even if a permutation is used internally. Round all
free variables to one common grid *before* exact back-substitution. For decimal
digits \(d\), set \(D=10^d\) and

\[
  z_j(D)=\frac{\operatorname{round}(D z_j^*)}{D}
\]

for every free coordinate \(z_j\). A binary grid \(D=2^b\) is equally valid.
If coordinate scales differ greatly, first apply recorded rational scaling and
use one common \(D\) in the scaled coordinates. Do not independently call a
continued-fraction or `limit_denominator` heuristic on every free coordinate:
unrelated coprime denominators propagate through the pivot solve and cause
avoidable coefficient swell.

```text
identify exact pivot columns B and free columns F
estimate a starting common-grid exponent d from the face margin and solve gain
for d on an increasing ladder:
    z_F := round(10^d * z_F_star) / 10^d, componentwise
    solve A[:,B] z_B = b - A[:,F] z_F on the reduced exact subsystem
    substitute z into every raw affine and face row exactly
    rebuild every full symmetric block from z
    run the exact PSD trace emitter/checker on every block
    if all exact gates pass: retain candidate and stop
    otherwise record the exact first failure and refine or backtrack
```

The exact pivot solve can introduce factors from the determinant of its pivot
minor, so final denominators need not all divide \(D\). The common grid still
keeps the freely chosen coordinates coherent and usually limits growth. For a
zero-dimensional affine space, skip grid rounding and solve the unique point
exactly.

Here "variables" means the internal upper-triangular affine-coordinate vector.
The proof artifact does not serialize that vector separately: write the rebuilt
full symmetric exact matrices into the block objects required by
`exact-block-sdp-certificate-v1`.

Choose the initial grid adaptively. Estimate the smallest *positive* eigenvalue
on the recovered face by restricting each numerical block to an exact
complement of \(V_i\). Combine that exploratory margin with (i) the measured
gain of the reduced pivot solve and (ii) the map from coordinate perturbations
to block operator norm. Select \(d\) so the estimated perturbation is safely
below the positive margin, then increase digits in recorded steps. This
estimate only chooses a starting point; exact PSD decides.

Diagnose each failed grid point before increasing precision:

- a nonzero exact affine or \(X_iV_i\) residual indicates a pivot, solve, or
  reconstruction bug; extra digits cannot repair it;
- a negative exact Schur pivot that shrinks toward zero as \(d\) increases,
  while the restricted positive margin is stable, is evidence that the grid is
  too coarse;
- a negative pivot that stabilizes, grows, or moves between incompatible
  blocks as \(d\) increases points to a wrong face, objective, nullity, or
  ill-conditioned pivot set; and
- rapid numerator/denominator growth calls for better row scaling, a better
  pivot minor, or a better kernel chart before independently rationalizing
  coordinates.

Record \(D\), digit/bit level, maximum coefficient bit lengths, exact
full-row residual result, and the first failing PSD block, permutation step,
and exact pivot value for every attempt. Never erase a coarser failure after a
finer grid passes.

It is always valid to parse sufficiently long decimal coordinates on one common
decimal grid, although this may create huge denominators. Certificate size is
secondary to obtaining the first proof; simplify only after a proof exists and
rerun every exact gate after simplification.

### 9.2 Quadratic path

Write

\[
  A=A_0+\alpha A_1,\quad b=b_0+\alpha b_1,\quad x=u+\alpha v.

\]

Replace \(Ax=b\) by the doubled rational system

\[
  \begin{pmatrix}A_0&dA_1\\A_1&A_0\end{pmatrix}
  \begin{pmatrix}u\\v\end{pmatrix}
  =
  \begin{pmatrix}b_0\\b_1\end{pmatrix}.
\]

Only the embedded approximation \(x^*\) is known, so first choose a nearby
approximate decomposition. Following DLM, set \(u^*=y\) and
\(v^*=(x^*-y)/\sqrt d\), where \(y\) is a least-squares/high-precision solution
of

\[
  \begin{pmatrix}
    A_0-\sqrt d A_1\\
    \sqrt d A_1-A_0
  \end{pmatrix}y
  =
  \begin{pmatrix}
    b_0-\sqrt d A_1x^*\\
    \sqrt d b_1-A_0x^*
  \end{pmatrix}.
\]

Then place all free entries of \((u^*,v^*)\) on one shared rational grid and
perform exact back-substitution in the doubled system. Recombine
\(x=u+\alpha v\).

The split is not unique; any nearby split is acceptable if the final exact
certificate passes. If this least-squares system is ill-conditioned, compute a
minimum-norm solution with high-precision QR/SVD, rescale the affine equations,
or choose free variables directly in the doubled exact system.

## 10. Exact verification gates

Use a fresh process or independently implemented verifier. It must parse only
the exact model and the proposed certificate. It must not use numerical blocks,
the relation residual, the expected certificate, or cached pass/fail flags.

There are two verification layers. The generic command in `verify/` proves that
the submitted matrices satisfy the submitted model and that the certificate's
claimed objective equals the objective recomputed from those matrices. It does
not read `manifest.json`, so by itself it does not bind the result to the
testcase's requested target, required status, artifact hashes, or blind-run
provenance. After the generic verifier passes, testcase acceptance MUST run the
manifest-aware harness from the repository root:

```sh
python3 validation/testcase_harness.py testcases/<case-id> <attempt-id>
```

The harness must compare the computed and claimed objectives with the
manifest's non-null `fixed_objective`, match the candidate and certificate,
check required artifacts and hashes, and require
`verification.json.final_status` to equal the claim's required status. A
generic verifier pass without this target-binding harness is not a passing
testcase. A null target remains an objective-discovery exploration unless a
versioned manifest-aware harness supplies another exact post-blind target
binding.

All exact gates and the testcase-binding layer are mandatory.

### Gate A: integrity and coverage

- Recompute and match the exact model hash.
- Check the field, embedding, dimensions, variable order, and block count.
- Reject missing, extra, `NaN`, decimal, or noncanonical exact values.
- Match exactly one full symmetric certificate matrix to every model block and
  reject missing or extra blocks.

### Gate B: affine equations and scalar inequalities

- Evaluate every original equality exactly and require residual zero.
- Evaluate every objective-fixing equality that is actually present in the
  exact model and require residual zero.
- Verify scalar inequalities exactly, either directly or as \(1\times1\) PSD
  blocks.
- Report each constraint identifier and exact residual/sign; do not report only
  an aggregate norm.

Kernel equations are discovery constraints. They may also be checked and
reported, but they do not replace any original condition.

### Gate C: exact objective and direction

Recompute \(c_0+c^{\mathsf T}x\) exactly from the original objective and match
the claimed exact value. Then let the manifest-aware harness compare that exact
value with the testcase target and use the manifest's declared bound relation
to state the result. Reject a certificate with the right decimal but the wrong
exact value, and reject a feasible certificate at any objective other than the
bound target.

### Gate D: exact PSD for every block

For a rational certificate in this repository, use the exact symmetric-Schur
trace required by [`verify/FORMAT.md`](../verify/FORMAT.md). Starting from the
full exact symmetric matrix, replay every declared pivot exactly:

- a positive pivot permits the exact Schur-complement update;
- a zero pivot is permitted only when its complete active row is exactly zero;
- a negative pivot fails; and
- every original index must be eliminated exactly once.

Generate a deterministic trace with
`python -m verify emit-traces MODEL CANDIDATE -o CERTIFICATE`, then check it in
a fresh process with `python -m verify check MODEL CERTIFICATE --json`. The
checker reparses all rationals and does not trust numerical eigenvalues.

The rational format and checker impose no fixed numerator, denominator, or
decimal-digit ceiling: integer arithmetic is arbitrary length. Execution is
still bounded by available time and memory. A timeout, signal, or memory
exhaustion while parsing or checking a very large rational certificate is an
operational resource failure, not evidence that the matrix is non-PSD. Record
the applicable limits, elapsed time, peak memory when available, and maximum
integer bit length; then reduce coefficient swell or raise an explicitly
declared resource limit and rerun the complete exact check.

DLM's independent method uses characteristic polynomials. It is an acceptable
cross-check, and it supplies a natural quadratic-field gate. For a symmetric
\(m\times m\) block \(X\), compute exactly

\[
  p(t)=\det(tI-X),\qquad
  q(t)=(-1)^m p(-t)=\det(tI+X).

\]

Under the selected real embedding, \(p\) is real-rooted because \(X\) is real
symmetric. Then \(X\succeq0\) if and only if every coefficient of \(q\) is
nonnegative. Store \(q\), or a hash plus all coefficients, in the verification
report.

For \(\mathbb Q\), compare coefficients as exact rationals. For
\(\mathbb Q(\sqrt d)\), use an exact sign predicate under \(\sqrt d>0\). For
\(z=a+b\sqrt d\):

- equal signs of \(a\) and \(b\) are immediate;
- if \(a\) and \(b\) have opposite signs, compare \(a^2\) with \(d b^2\)
  exactly; and
- handle zero components separately.

Never decide an algebraic sign from a floating approximation. A future
quadratic verifier may replay the same Schur algorithm with exact signs in the
selected ordered embedding, or use the characteristic-polynomial criterion.
Exact \(LDL^{\mathsf T}\) with proven pivot signs or an exact positive-definite
restriction to the recovered face are acceptable additional witnesses, but the
checker must implement at least one complete exact PSD proof for every block.

### Gate E: theorem semantics

Check any exact coefficient identity, flag-algebra expansion, SOS identity, or
adapter invariant that connects the normalized SDP to the mathematical claim.
If the testcase supplies only an SDP and no checked theorem mapping, the status
can be at most `EXACT_SDP_CERTIFICATE`, not `RIGOROUS_PROBLEM_BOUND`.

### Gate F: sharpness or optimality, when claimed

Require one of:

- an exact matching construction/witness;
- exact feasible primal and dual certificates with zero gap; or
- another separately checked theorem proving the reverse inequality.

Without this gate, say "rigorous feasible certificate/bound," not "exact
optimum."

## 11. Failure diagnostics and next action

Change one cause at a time and preserve failed attempts.

| Symptom | Likely cause | Next action |
| --- | --- | --- |
| Objective candidates change with precision | Optimization not converged or value outside searched field/height | Increase precision; improve scaling; widen height gradually; do not fix a value yet |
| Fixed-objective feasibility is numerically inconsistent | Wrong objective candidate, sign convention, or model | Recheck objective transcription; reject candidate |
| No stable spectral gap | Insufficient precision, poor scaling, non-relative-interior point, or genuinely tiny positive eigenvalues | Double precision; rescale blocks; use multiple starts/averaging; retain adjacent nullities |
| LLL finds no relation | Wrong nullity, too little precision, coefficient height too small, or kernel not defined over field | Validate another nullity; increase precision before height; then try the declared quadratic path |
| LLL finds many unstable short relations | Precision too low or subspace misclassified | Validate on an independent higher-precision run; reject relations whose residual does not improve |
| Graph coordinates disagree at `p` and `2p` | Ill-conditioned coordinate minor, wrong nullity, or insufficient precision | Try the next rank-revealing positive-space pivot set; record both condition estimates; then return to DLM/LLL or raise precision |
| Relation rank is below \(m-k\) | Missing relations or wrong field | Raise precision/height; use complementary-slackness relations only as extra hints; do not invent rows |
| Exact kernel system is inconsistent | At least one relation/nullity/objective is false, or vectorization is wrong | Audit block indexing, then backtrack the newest relation or nullity branch |
| Modular ranks fail to stabilize or the selected exact minor is singular | Sampled primes divide relevant minors, the row stream changed, or the pivot candidate was unlucky | Retry independent primes and hash the exact row stream; certify the final pivot minor over \(\mathbb Q\) |
| Reduced exact solve passes selected rows but not all rows | Wrong pivot selection, inconsistent branch, or row-generation/back-substitution bug | Stop; compare augmented ranks and recheck every raw row. More rounding digits cannot fix this |
| Exact affine point satisfies equations but a tiny negative eigenvalue remains | Free-variable rounding is too coarse or the recovered face is incomplete | Increase denominator bits; inspect restricted positive margin; recover missing kernel equations |
| Negative eigenvalue persists under finer rounding | Wrong face, non-relative-interior numerical point, or no certificate in chosen field | Re-solve at higher precision; revise nullity/field/objective |
| Quadratic linear equations pass but PSD signs fail | Wrong real embedding or insufficient/wrong kernel | Check \(d\), embedding, and exact sign code; never use conjugate signs accidentally |
| Exact SDP passes but claimed theorem does not | Missing/incorrect adapter semantics | Downgrade status to `EXACT_SDP_CERTIFICATE`; repair theorem mapping separately |
| Exact elimination or verification exhausts time/memory | Dense formulation, coefficient swell, or an explicit resource limit | Record an operational failure; use modular pivots, a reduced FLINT solve, and a shared grid; a resource stop is not a PSD verdict |

### Record recoverable operational failures

Append every timeout, signal, nonzero backend exit, memory-limit event, manual
interruption, or failure to persist an expected artifact to
`operational-failures.json` immediately, even if a retry later succeeds. For
each event record the phase, backend and version, exact command argument array,
start/end or elapsed time, exit code or signal, declared resource limits, last
durable artifact, diagnostic, recovery action, and whether the recovery changed
the mathematical branch. A backend substitution that only changes the rank or
solve implementation normally sets `mathematical_branch_changed` to false; a
new objective, nullity, kernel, or field branch sets it to true.

Checkpoint hashes, precision evidence, recovered relations, modular primes and
pivots, and grid failures before starting another expensive phase. A recovered
operational event does not invalidate a later proof, but omitting it destroys
reproducibility. If resource limits end the run, report `NO_CERTIFICATE_FOUND`
only when those limits were declared in advance and the retained artifacts make
the stopping point reproducible; never reinterpret the event as mathematical
infeasibility.

Complementary slackness from a candidate construction may supply additional
kernel relations, but the blind workflow must not require a published matrix or
the expected kernel. Record whether each relation was data-derived,
construction-derived, or numerically discovered.

## 12. Proof artifacts

Write the following into the attempt directory defined by the testcase
contract:

- `run.json`: tool versions, commands, precision ladder, seeds, input hashes,
  timestamps, and exit codes;
- `objective-candidates.json`: every tested candidate and why it was accepted or
  rejected;
- `spectra.json`: scaled singular/eigenvalue clusters at every precision;
- `kernels.json`: exact relation matrices, exact kernel bases, ranks, and
  relation/principal-angle validation diagnostics from independent `p` and
  `2p` runs, including graph-chart pivots and conditioning when used;
- `affine-system.json`: face codimensions, row provenance, modular
  primes/ranks/pivots, certified exact pivot minor, shared-grid ladder, and
  full-row rechecks;
- `candidate.json`: full exact symmetric matrices in the candidate portion of
  the repository certificate format;
- `certificate.json`: the complete `exact-block-sdp-certificate-v1` object,
  including exact Schur PSD traces for every rational block;
- `verifier-output.json`: the unmodified JSON output of the generic exact
  verifier;
- `verification.json`: gate-by-gate exact results, exact objective, all block
  PSD witnesses, and the required `final_status` field;
- `operational-failures.json`: every recoverable or fatal operational event in
  the format required by the testcase contract; it is required when any such
  event occurred and may be omitted only when none occurred;
- `proof.md`: a short human-readable claim, model provenance, exact value,
  verification command, and sharpness witness if any; and
- immutable raw solver input/output or hashes pointing to them.

The exact certificate must be self-contained relative to the exact model. A
reader must be able to delete all floating-point files and still rerun the exact
verifier successfully.

## 13. Strict definition of success

Use exactly one of these statuses.

- `EXPLORATION_ONLY`: anything numerical, heuristic, or not independently
  verified.
- `INPUT_INVALID`: the exact testcase cannot be parsed or its provenance,
  dimensions, hashes, or theorem mapping fail preflight.
- `NO_CERTIFICATE_FOUND`: the search was reproducible but no candidate passed;
  this makes no mathematical nonexistence claim.
- `EXACT_SDP_CERTIFICATE`: Gates A--D pass in a fresh process for the complete
  original SDP.
- `RIGOROUS_PROBLEM_BOUND`: Gates A--E pass and the exact SDP certificate proves
  the declared bound for the original problem.
- `SHARP_OR_OPTIMAL`: Gates A--F pass, including an exact reverse witness or
  zero-gap argument.

The workflow succeeds for a testcase only at the level required by its
manifest. In addition to the gates associated with that level, the
manifest-aware harness must exit zero and
`verification.json.final_status` must equal `claim.required_status`. A generic
verifier pass at an unbound feasible objective is not success. Under the
current v1 harness, a successful proof testcase therefore has a non-null
manifest `fixed_objective`; a null value remains exploration until a versioned
exact target-binding rule is implemented. A test suite demonstrates the method
only when a fresh agent, denied the oracle certificate, produces the required
artifacts and the independent checker and harness pass them from a clean
environment.

## 14. Notes from the DLM ancillary implementation

The historical source is useful evidence about the intended algorithm, not a
portable threshold specification. Its `SemidefiniteProgramming.jl`:

- detects a small-singular-value cluster by SVD;
- calls Nemo `lindep` repeatedly on rows of the numerical kernel matrix;
- constructs an exact nullspace from the recovered integer relations;
- adds matrix-times-kernel-vector equations;
- clears denominators and uses integer row reduction before exact
  back-substitution; and
- verifies exact linear equations and PSD blocks through characteristic
  polynomials.

The archive uses fixed exploratory tolerances such as \(10^{-20}\) for one
singular-value cutoff and different residual thresholds in rational and
quadratic routines. Its examples use hundreds of digits of SDPA-GMP precision.
Do not cargo-cult those constants: scale the problem, compare independent
precision levels, use the adaptive rules above, and let exact verification be
the only proof gate. The archive's README pins Julia 1.1.1, Nemo 0.15.1, Hecke
0.6.6, AbstractAlgebra 0.7.1, and GenericSVD 0.2.2; a modern implementation may
use different exact-arithmetic libraries if it preserves the mathematical
gates.

Additional primary software references are the official
[SDPA-GMP repository](https://github.com/nakatamaho/sdpa-gmp) and the official
[Nemo repository](https://github.com/Nemocas/Nemo.jl).
