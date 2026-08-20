# DLM three-point SDP port

This directory contains a small, dependency-free port of the rational SDP
construction used for Theorem 4.3 of:

Maria Dostert, David de Laat, and Philippe Moustrou, *Exact Semidefinite
Programming Bounds for Packing Problems*, SIAM Journal on Optimization 31
(2021), [doi:10.1137/20M1351692](https://doi.org/10.1137/20M1351692).

The port is deliberately one-way. It translates the ancillary Julia
construction into a blind numerical test input; it does not deserialize or
copy the authors' exact solution.

## Tools

- `generate_three_point.py` ports `Q`, `Y`, `Sbar`, `threepointsdp`, the
  affine block builder, and sparse SDPA serialization. Polynomial and SDP
  construction arithmetic uses Python `Fraction` throughout.
- `parse_sdpa_solution.py` extracts SDPA-GMP's `yMat` blocks. These are the
  PSD variables selected as `finalY` by the ancillary Julia parser.
- `check_three_point.py` independently checks the source-derived block
  structure, the repository's exact model schema, every entry in the decimal
  SDPA projection, manifest hashes, and numerical feasibility.

Run from the repository root:

```console
python3 tools/dlm/generate_three_point.py
python3 tools/dlm/check_three_point.py
```

To reproduce both numerical solves, replace `SDPA_GMP` below with the path to
the executable. The `p` run uses 300 internal bits and prints 40 digits; the
`2p` run uses 600 bits and prints 80 digits.

```console
SDPA_GMP -ds testcases/dlm-three-point-10/input/discovery.dat-s \
  -o testcases/dlm-three-point-10/input/numerical/p/result.out \
  -p testcases/dlm-three-point-10/input/numerical/p/params.sdpa
python3 tools/dlm/parse_sdpa_solution.py \
  testcases/dlm-three-point-10/input/numerical/p/result.out \
  testcases/dlm-three-point-10/input/model.json \
  testcases/dlm-three-point-10/input/numerical/p/approximate_solution.json
SDPA_GMP -ds testcases/dlm-three-point-10/input/discovery.dat-s \
  -o testcases/dlm-three-point-10/input/numerical/2p/result.out \
  -p testcases/dlm-three-point-10/input/numerical/2p/params.sdpa
python3 tools/dlm/parse_sdpa_solution.py \
  testcases/dlm-three-point-10/input/numerical/2p/result.out \
  testcases/dlm-three-point-10/input/model.json \
  testcases/dlm-three-point-10/input/numerical/2p/approximate_solution.json
python3 tools/check_numerical_stability.py \
  testcases/dlm-three-point-10/input
python3 tools/dlm/generate_three_point.py
python3 tools/dlm/check_three_point.py
```

The second generator invocation refreshes hashes for the solver result and
parsed approximation without changing either file.
