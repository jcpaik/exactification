# Exact certificate: rotated-rational-kernel

The public model has one rational PSD block `X`, two affine equalities, and the
identically zero objective.  The first equality is `trace(A X)=0`, with exact
`A` a rank-three orthogonal projector.  The candidate is
`X = (7/3)(I-A)`, so it is positive semidefinite of rank three, annihilates
`A`, and has trace seven.

The independent command

```sh
python3 -m verify check testcases/rotated-rational-kernel/input/model.json testcases/rotated-rational-kernel/attempts/retry-1/certificate.json --json
```

checked one complete block, both constraints, objective `0`, and every exact
Schur pivot.  Its exit status was zero.  The resulting workflow status is
`EXACT_SDP_CERTIFICATE`; no theorem-level optimality claim was declared.
