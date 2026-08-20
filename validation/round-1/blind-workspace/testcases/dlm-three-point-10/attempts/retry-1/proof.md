# Exact certificate: dlm-three-point-10

The public 40-digit transcription exhibits stable rational kernel faces in the
31-block DLM SDP.  Nullspaces were recovered through basis-invariant rational
projectors.  The one projector whose entry denominators exceeded the available
rational-reconstruction window (`triple_sos.pi1.s_0`) was recovered instead by
twenty independent DLM-style row relations; their maximum normalized residual
is approximately `7.37e-37`.

The original 130 equalities, objective `10`, and all equations `X V = 0`
produce 689 rows over 1,641 upper-triangular coordinates.  Sparse elimination
over two primes independently found rank 601.  A 601-by-601 subsystem was
solved over the rationals by FLINT, with 1,040 free coordinates rounded to a
shared denominator `2^100`; all 689 equations were then rechecked exactly.

The trusted emitter generated complete Schur traces, and the fresh command

```sh
python3 -m verify check testcases/dlm-three-point-10/input/model.json testcases/dlm-three-point-10/attempts/retry-1/certificate.json --json
```

returned exit zero after checking all 31 blocks and 130 constraints at exact
objective `10`.  The supported workflow status is `EXACT_SDP_CERTIFICATE`;
the theorem adapter and a separate sharpness witness were not run here.
