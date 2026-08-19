# Blind input: rotated rational kernel

This transparent control feasibility SDP has a rational optimal face but an
irrational relative-interior numerical point. Its three-dimensional numerical
nullspace is represented by an arbitrary orthonormal eigenbasis; individual
eigenvectors are not the object to rationalize.

Construct any rational certificate satisfying the exact model. No target Gram
matrix is included.

This case produced an exact certificate in the Round 1 retry, but it is not an
adequate held-out numerical-subspace test. The public model writes an exact
rational PSD projector directly into the equality `trace(A X) = 0`; together
with `X` being PSD, that equality reveals the supporting face. The case is
retained as a transparent positive control. The stronger held-out fixture is
[`obfuscated-rational-kernel`](../../obfuscated-rational-kernel/input/), whose
construction and oracle data are excluded from blind input. Its Round 2 run is
complete with an exact SDP certificate; see the
[Round 2 executor report](../../../validation/round-2/executor-report-round-2.md).
