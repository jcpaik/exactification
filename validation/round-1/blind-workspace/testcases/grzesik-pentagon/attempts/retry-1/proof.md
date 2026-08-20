# Exact certificate: grzesik-pentagon

The public 512-bit optimizer identifies nullities four, one, and two in the
`P`, `Q`, and `R` blocks.  Basis-invariant numerical kernel projectors recover
exact rational subspaces.  The ten inequalities whose slacks track the solver
noise were imposed as active equalities; cases 06, 07, 08, and 13 retained
strict positive margins.  Kernel equations `X V = 0`, the fixed objective
`24/625`, and those active equations form a consistent exact affine system.

Free coordinates were rounded with an 80-bit denominator ladder and pivots
were obtained by exact back-substitution.  The trusted trace emitter accepted
every block.  The independent command

```sh
python3 -m verify check testcases/grzesik-pentagon/input/model.json testcases/grzesik-pentagon/attempts/retry-1/certificate.json --json
```

returned exit zero after checking four blocks and all fourteen constraints;
the exact objective is `24/625` and the ranks are `U=1`, `P=4`, `Q=5`, and
`R=3`.  The supported workflow status is `EXACT_SDP_CERTIFICATE`.
