# Exact block-SDP certificate format, version 1

This directory contains a small checker for rational block-SDP certificates.  The
checker has two inputs: a **model**, which states the affine problem, and a
**certificate**, which assigns an exact symmetric matrix to every PSD block.

The checker proves exactly the following facts:

1. every supplied block is positive semidefinite over the rationals;
2. every stated affine equality or inequality holds; and
3. the affine objective at the supplied point equals the claimed value.

This is a feasibility-and-value certificate.  It is an optimality certificate
only when the model itself encodes the relevant bound proof (for example, a
flag-algebra identity), or when separately checked primal/dual models establish
matching bounds.

## Rational and structural conventions

- Every rational scalar is a JSON **string** in canonical reduced form: `"0"`,
  `"-7"`, or `"13/25"`.  JSON floating-point numbers, decimals, `"-0"`,
  `"2/4"`, and `"3/1"` are rejected.
- Dimensions, row indices, column indices, and trace indices are nonnegative
  JSON integers.  Booleans are not integers.
- Objects reject unknown fields, duplicate JSON keys, missing fields, duplicate
  names, and duplicate affine coordinates.
- Matrix indices are zero-based.
- A certificate stores each symmetric matrix in full.  Symmetry is checked
  exactly.

## Model

```json
{
  "format": "exact-block-sdp-model-v1",
  "blocks": [
    {"name": "X", "size": 2}
  ],
  "constraints": [
    {
      "name": "normalization",
      "sense": "eq",
      "expression": {
        "constant": "-1",
        "terms": [
          {"block": "X", "row": 0, "col": 0, "coefficient": "1"}
        ]
      }
    }
  ],
  "objective": {
    "sense": "maximize",
    "expression": {
      "constant": "0",
      "terms": [
        {"block": "X", "row": 0, "col": 1, "coefficient": "2"}
      ]
    }
  }
}
```

Block sizes must be positive.  The allowed constraint senses are:

- `"eq"`: expression = 0;
- `"ge"`: expression >= 0;
- `"le"`: expression <= 0.

The objective sense is `"maximize"` or `"minimize"`.  It records the intended
optimization direction; the checker evaluates the same affine expression in
either case.

### Entry-coefficient convention

Each affine term must use a canonical upper-triangular coordinate,
`0 <= row <= col < block size`.  Its coefficient multiplies that displayed
matrix entry **once**:

```text
constant + sum(coefficient * X[row,col]).
```

There is no implicit factor of two.  Consequently, to encode
`trace(A X)` for symmetric `A` and `X`, use coefficient `A[i,i]` on a diagonal
entry and coefficient `2*A[i,j]` on an off-diagonal entry with `i < j`.

## Certificate

```json
{
  "format": "exact-block-sdp-certificate-v1",
  "claimed_objective": "1",
  "blocks": [
    {
      "name": "X",
      "matrix": [
        ["1", "1"],
        ["1", "1"]
      ],
      "psd_trace": {
        "algorithm": "symmetric-schur-v1",
        "steps": [
          {"index": 0, "pivot": "1"},
          {"index": 1, "pivot": "0"}
        ]
      }
    }
  ]
}
```

The certificate must assign exactly one matrix to each model block and no other
blocks.

### PSD trace semantics

The trace is an exact replay log for symmetric Schur-complement elimination.
Initially the active matrix is the supplied matrix and active indices are the
original matrix indices.  For each step:

1. `index` must be active, and `pivot` must equal its current diagonal entry.
2. If the pivot is positive, delete its row and column after replacing the
   remaining active matrix by

   ```text
   S[i,j] <- S[i,j] - S[i,k] * S[k,j] / pivot.
   ```

3. If the pivot is zero, its entire active row must be zero, then its row and
   column are deleted without changing the remainder.
4. A negative pivot is rejected.

Every original index must occur exactly once.  Thus a successful trace proves
PSD, including singular PSD matrices.  The number of positive pivots is the
exact rank.  The trace need not use the natural index order, although the bundled
emitter does so deterministically.

## Command line

Check an existing certificate:

```sh
python -m verify check model.json certificate.json
```

Add deterministic exact PSD traces to a candidate certificate whose block
objects contain `name` and `matrix` (an existing `psd_trace` is replaced):

```sh
python -m verify emit-traces model.json candidate.json -o certificate.json
python -m verify check model.json certificate.json
```

Use `--json` with `check` for a machine-readable success report.  Exit status is
zero on success, one when an exact mathematical check fails, and two for malformed
input, I/O errors, or command-line misuse.
