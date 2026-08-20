# Exactifying Singular Flag-Algebra SDPs

The central lesson from the existing literature is that one should not expect
every coordinate returned by an SDP solver to be rational. Even with rational
input data and a rational optimum, an optimizer can be non-unique, irrational,
or badly conditioned. An interior-point solver may select a different point of
the optimal face from the convenient rational point ultimately used in the
proof.

Successful methods therefore do not exactify the raw coordinates independently.
They first identify the optimal face, reduce to its relative interior, and only
then rationalize or algebraize a well-conditioned reduced solution.

## Early flag-algebra proofs

The two original pentagon papers largely bypass the algorithmic reconstruction
question in their presentation:

- [Grzesik](https://arxiv.org/abs/1102.0962) gives explicit rational matrices
  \(P,Q,R\), evaluates the fourteen graph coefficients rationally, and proves
  positive semidefiniteness from exact characteristic polynomials.
- [Hatami, Hladký, Král', Norine, and Razborov](https://arxiv.org/abs/1102.1634)
  use symmetry-adapted blocks and present exact matrices.

These matrices should be understood as convenient exact points on the optimal
face, not necessarily entrywise rationalizations of the point preferred by a
particular numerical solver.

## Strict-feasibility rounding

[Peyrl and Parrilo](https://www.mit.edu/~parrilo/pubs/files/PeyrlParrilo-ComputingSumOfSquaresDecompositionsWithRationalCoefficients.pdf)
give the basic numerical-symbolic method for a positive-definite Gram matrix:

1. approximate the numerical matrix rationally using continued fractions or
   LLL;
2. project the approximation exactly onto the rational affine constraint space;
3. use the smallest-eigenvalue margin to ensure that rounding and projection do
   not leave the PSD cone; and
4. verify the final rational matrix exactly, for example with a characteristic
   polynomial or an \(LDL^{\mathsf T}\) decomposition.

Schematically,

\[
Q_{\mathrm{num}}
\longrightarrow \widetilde Q\in\mathbb Q^{n\times n}
\longrightarrow \Pi_{\{Ax=b\}}(\widetilde Q)
\longrightarrow \text{exact PSD verification}.
\]

If \(Q_{\mathrm{num}}\succeq\varepsilon I\) and the combined rounding and
projection error is smaller than \(\varepsilon\), the final matrix remains PSD.
This argument requires strict feasibility. A singular matrix must first be
reduced to a smaller face on which the corresponding reduced matrix is positive
definite.

## Flagmatic's sharp-bound workflow

Flagmatic systematizes facial reduction for sharp flag-algebra bounds. Its
construction-assisted workflow is:

1. supply or recover the candidate exact bound;
2. identify the sharp admissible graphs;
3. use the extremal construction and complementary slackness to obtain forced
   zero eigenvectors;
4. factor every singular block as

   \[
   Q=R Q'R^{\mathsf T},
   \]

   with exact \(R\) and positive-definite \(Q'\);
5. rationalize \(Q'\) while imposing the sharp-graph equations exactly;
6. reconstruct \(Q\); and
7. verify every coefficient and PSD condition in exact arithmetic.

The purpose of the factorization is to replace a boundary point \(Q\) by an
interior point \(Q'\) of the minimal face. Positive-definite \(Q'\) is stable
under sufficiently small rational perturbations.

The [Flagmatic User's Guide](https://lidicky.name/flagmatic/UsersGuide.pdf)
demonstrates this workflow on the pentagon problem itself. It uses the balanced
\(C_5\) construction to construct zero eigenvectors, factors the Gram blocks,
imposes the exact bound \(24/625\), rationalizes the reduced positive-definite
blocks, and verifies the result. The reported kernel dimensions include
\(4,1,2\), matching Grzesik's blocks:

\[
\operatorname{nullity}(P)=4,\qquad
\operatorname{nullity}(Q)=1,\qquad
\operatorname{nullity}(R)=2.
\]

[Falgas-Ravry and Vaughan](https://arxiv.org/abs/1110.1623) distribute exact
machine-readable Flagmatic certificates and a checker, making the exact
certificate—not the floating-point solution—the proof artifact.

For a non-sharp result, Flagmatic also supports a simpler alternative: round a
strictly feasible factorization and accept a nearby, slightly weaker rational
bound. This proves a rigorous upper bound but does not recover an exact optimum.

## Recovering a kernel subspace with LLL

Construction-derived kernels are not always available. A more general method is
given by [Dostert, de Laat, and Moustrou](https://doi.org/10.1137/20M1351692):

1. fix the conjectured exact objective and turn optimization into feasibility;
2. solve at high precision to obtain an approximate relative-interior point of
   the optimal face;
3. collect the eigenvectors associated with near-zero eigenvalues in a matrix
   \(N\);
4. use LLL to find integer equations defining the column space of \(N\);
5. compute the kernel basis exactly over \(\mathbb Q\);
6. add \(Xv=0\) to the affine system for every recovered kernel vector \(v\);
7. solve the enlarged affine system exactly, rationalizing only its free
   variables; and
8. verify all linear constraints and PSD blocks exactly.

The important insight is that numerical zero-eigenvectors should not themselves
be rounded. In an eigenspace of dimension greater than one, the numerical solver
may return arbitrary real rotations of a rational basis. The invariant object is
the kernel subspace. Integer relations defining that subspace can be stable even
when its particular numerical basis is not.

PSLQ can serve a similar role for small relation searches, but it should be
applied to stable linear relations or subspace invariants rather than blindly to
each Gram-matrix entry.

## A detailed flag-algebra projection example

[Gilboa, Glebov, Hefetz, Linial, and Morgenstern](https://arxiv.org/abs/1908.06480)
give a transparent manual example:

1. determine the common kernel of all sharp certificates;
2. project the SDP onto its orthogonal complement;
3. impose exact equations from the sharp graphs;
4. round free coordinates in the projected problem;
5. solve the dependent coordinates exactly; and
6. pull the certificate back to the original flag space.

Some coordinates in their exact certificate lie in
\(\mathbb Q(\sqrt2,\sqrt3)\), illustrating that the correct target field need
not be \(\mathbb Q\).

## When rational certificates do not exist

Rational SDP input does not guarantee a rational feasible or optimal point.
[Kolmogorov, Naldi, and Zapata](https://arxiv.org/abs/2405.13625) address
degenerate feasibility problems without assuming a rational solution. Their
method uses maximum-rank information to construct polynomial equations with an
isolated real solution, which can then be handled by symbolic or numerical
algebraic geometry.

A general exactifier should therefore support two endpoints:

- rational certificates obtained after facial reduction; and
- algebraic certificates over an explicitly represented number field.

## Recommended workflow for the Grzesik testbed

Our current SDPA-GMP run recovers \(u=24/625\) but returns different Gram
matrices from Grzesik's rational certificate. The literature suggests the
following next experiment:

1. Fix \(u=24/625\) and solve a feasibility problem instead of optimizing \(u\)
   again.
2. Determine the exact sharp-graph equations. When pretending that the
   extremal construction is unknown, infer candidates from numerical primal
   support and validate them across precisions; when the construction is
   available, derive them directly from it.
3. Recover the kernel subspaces of \(P,Q,R\), expecting nullities \(4,1,2\).
4. Construct exact complementary bases

   \[
   R_P\in\mathbb Q^{8\times4},\qquad
   R_Q\in\mathbb Q^{6\times5},\qquad
   R_R\in\mathbb Q^{5\times3}.
   \]

5. Substitute

   \[
   P=R_P P'R_P^{\mathsf T},\qquad
   Q=R_Q Q'R_Q^{\mathsf T},\qquad
   R=R_R R'R_R^{\mathsf T},
   \]

   where the reduced blocks should be positive definite.
6. Rationalize only the free reduced coordinates, then project them onto all
   exact coefficient equations.
7. Verify the fourteen graph inequalities, the exact objective, and all PSD
   conditions independently with exact arithmetic.

For a problem with a known matching construction, the Flagmatic method gives
the cleanest kernels. For an unknown problem, the LLL subspace-recovery method
of Dostert--de Laat--Moustrou is the stronger template.

## Design principle

The exactification pipeline should be understood as

\[
\text{numerical optimum}
\longrightarrow
\text{candidate exact objective}
\longrightarrow
\text{optimal-face and kernel reconstruction}
\longrightarrow
\text{reduced strictly feasible problem}
\longrightarrow
\text{rational or algebraic reconstruction}
\longrightarrow
\text{exact verification}.
\]

Continued fractions are only one local tool near the end of this process. The
structural step is discovering the face on which exact rounding is safe.
