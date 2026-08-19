# Blind input: obfuscated rational kernel

This synthetic exact block SDP has a rational rank-deficient optimal face and
a nonunique relative interior. The public affine rows and objective are dense,
generic rational functionals. No single equality is a kernel equation, a
projector trace, or another direct description of the supporting face.

The exact fixed objective is public. Recovering the face requires finding a
nontrivial combination of that fixed-objective equation with the generic
affine equalities, then recovering the rational nullspace from numerical
subspace evidence.

Two complete, independent SDPA-GMP feasibility runs are supplied:

- `numerical/p/`: 256-bit internal precision;
- `numerical/2p/`: 512-bit internal precision.

Each directory contains the exact `.dat-s` file passed to the solver, the
parameter file, unedited raw solver result, normalized approximation, and a
run record with the exact argument array. Every artifact is hashed in the
manifest.

SDPA-GMP prints 40 decimal digits for matrix entries, so both normalized files
honestly declare 40 printed digits rather than their larger internal working
precision. The runs use differently ordered and scaled but exactly equivalent
constraint projections. Compare kernel *subspaces* through principal angles;
individual eigensolver basis vectors may be arbitrarily rotated.

Construction data, the exact supporting combination, the exact kernel and
projector, and the rational oracle certificate are deliberately outside this
public directory and are not mounted in a blind run.
