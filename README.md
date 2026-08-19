# Exactification of Flag Algebra Certificates

This repository develops a reproducible pipeline for solving extremal graph
theory problems with **flag algebras**, high-precision semidefinite programming
via **SDPA-GMP**, and exact certificate reconstruction.

The central goal is to turn a strong numerical SDP bound into a finite,
independently checkable exact proof. The project covers both classical benchmark
problems and open problems where the extremal construction or sharp bound is not
known in advance.

> **Project status:** active workflow validation. The isolated Round 1 retry
> produced exact SDP certificates for the transparent rotated control,
> Grzesik's pentagon SDP at `24/625`, and the DLM three-point SDP at `10`.
> After a fixture audit reclassified the rotated control, the isolated Round 2
> run recovered exact SDP certificates for the stronger held-out
> `obfuscated-rational-kernel` p/2p fixture, Grzesik, and DLM. The strengthened
> rational three-case validation requirement is complete. These are
> `EXACT_SDP_CERTIFICATE` results, not independent theorem-level certificates.
> See the [acceptance record](validation/ACCEPTANCE.md),
> [Round 2 executor report](validation/round-2/executor-report-round-2.md), and
> [combined-suite record](validation/round-2/SUITE.md).

## Research goals

- Express known and open extremal graph theory problems as flag algebra SDPs.
- Solve the resulting programs at arbitrary precision with SDPA-GMP.
- Detect the exact structure hidden in numerical solutions.
- Recover rational or algebraic data using established and new exactification
  methods, including rational reconstruction and PSLQ.
- Produce compact certificates that can be verified using exact arithmetic,
  without trusting the numerical optimizer.
- Systematize the full workflow so that experiments are reproducible and new
  problems require as little problem-specific machinery as possible.

## Intended workflow

```mermaid
flowchart LR
    A["Extremal graph problem"] --> B["Flag algebra model"]
    B --> C["Semidefinite program"]
    C --> D["SDPA-GMP high-precision solve"]
    D --> E["Numerical solution"]
    E --> F["Structure detection"]
    F --> G["Rational or algebraic reconstruction"]
    G --> H["Exact certificate"]
    H --> I["Independent exact verification"]
    I --> J["Rigorous bound or theorem"]
```

Numerical optimization is used for discovery. Mathematical validity comes from
the final exact certificate and checker.

## What exactification means here

An SDP solver generally returns approximations to the optimum, matrix entries,
and dual variables. These approximations may strongly suggest a sharp result,
but they are not by themselves a proof. Exactification aims to recover and
verify the underlying exact data, for example by:

1. identifying entries that are rational, algebraic, zero, or linearly
   dependent;
2. finding candidate relations with continued fractions, lattice methods,
   rational reconstruction, or PSLQ;
3. reconstructing exact positive-semidefinite matrices, kernels, and dual
   multipliers;
4. checking all flag algebra identities, feasibility conditions, and the final
   objective value using exact arithmetic; and
5. exporting enough provenance and verification data for an independent rerun.

The system should support certificates over the rationals whenever possible and
over explicit algebraic number fields when necessary.

## Certificate standard

A complete result should eventually contain:

- the extremal problem and normalization conventions;
- the generated types, flags, admissible graphs, and density identities;
- the exact claimed bound;
- exact primal or dual certificate data;
- an exact proof of positive semidefiniteness, such as an `LDL^T`, Gram, or
  sum-of-squares decomposition;
- the SDPA-GMP input, precision, parameters, and raw output used for discovery;
- the reconstruction method and its tolerances or search bounds; and
- a deterministic verification report.

The exact checker should have a small trusted surface and should not depend on
SDPA-GMP or floating-point arithmetic.

## Planned repository layout

```text
problems/        Problem specifications and extremal constructions
flags/           Flag, type, and admissible-graph generation
sdp/             SDP construction, serialization, and SDPA-GMP integration
exactify/        Structure detection and exact reconstruction algorithms
certificates/    Exact, machine-readable proof certificates
verify/          Minimal exact certificate checker
experiments/     Reproducible numerical runs and parameter studies
tests/           Unit, regression, and end-to-end tests
docs/            Mathematical conventions, formats, and research notes
```

This layout is provisional and will evolve with the implementation.

## Design principles

- **Separate discovery from proof.** Numerical output proposes a certificate;
  exact verification proves it.
- **Preserve precision and provenance.** Record solver settings and avoid
  accidental conversion through machine-precision floating point.
- **Prefer explicit artifacts.** SDP instances, solver output, reconstructed
  data, and verification results should be inspectable and versionable.
- **Keep verification independent.** The checker should be simpler than the
  generator and exactification pipeline.
- **Benchmark before generalizing.** Validate each stage on problems with known
  sharp answers before relying on it for open cases.
- **Make failure informative.** Reconstruction should report residuals,
  conditioning, rank ambiguity, and insufficient-precision evidence rather than
  silently guessing exact values.

## Roadmap

- [ ] Specify canonical formats for problems, SDP data, and exact certificates.
- [ ] Implement or integrate flag and admissible-graph generation.
- [ ] Add SDPA-GMP input generation, execution, and output parsing.
- [ ] Build precision-aware diagnostics for rank, kernels, and near-zero terms.
- [ ] Implement rational reconstruction and PSLQ-based relation discovery.
- [ ] Reconstruct exact PSD decompositions and dual certificates.
- [x] Build a deterministic exact-arithmetic verifier for rational v1
  certificates.
- [ ] Reproduce several classical flag algebra bounds end to end.
- [ ] Package complete, independently verifiable certificates for new results.

## Reproducibility policy

Committed results should distinguish three classes of artifact:

1. **Source inputs** — the problem specification and generation parameters.
2. **Discovery artifacts** — generated SDPs and high-precision solver output.
3. **Proof artifacts** — exact certificates and deterministic verification
   results.

Large generated files may eventually live outside Git, but every result should
include stable metadata and a documented way to regenerate or retrieve them.

## Workflow validation

The reusable cases live in [`testcases/`](testcases/README.md). They cover
Grzesik's flag-algebra SDP, the rational three-point SDP used in Theorem 4.3 of
Dostert--de Laat--Moustrou, the transparent rotated control used in Round 1,
and the stronger obfuscated rational-kernel fixture completed in Round 2. The
exact pass conditions and author/executor isolation protocol are in
[`validation/ACCEPTANCE.md`](validation/ACCEPTANCE.md).

The proof checker uses only Python's exact `Fraction` arithmetic. It verifies
every original affine condition, the exact objective, and every full PSD block
through a replayable exact Schur-complement trace. Numerical solutions and
kernel relations are deliberately outside its trusted input.

The validation layer also provides a deterministic certificate-free
[blind-workspace builder](validation/README.md#build-a-blind-workspace), a
manifest-aware [target-binding harness](validation/README.md#check-one-attempt),
and a fresh-process [suite runner](validation/README.md#run-the-complete-suite).
The combined suite verifies six immutable or promoted attempts: the Round 1
DLM, Grzesik, and rotated-control certificates and the Round 2 DLM, Grzesik,
and obfuscated-fixture certificates. It also checks the frozen Round 2 blind
workspace inventory before accepting the Round 2 results.

## Contributing

Contributions are welcome in graph generation, flag algebra modeling, arbitrary-
precision SDP integration, exact linear algebra, integer-relation algorithms,
certificate formats, and benchmark problems.

When adding a result, include the mathematical conventions, generation inputs,
solver precision and parameters, reconstruction procedure, exact certificate,
and a passing verification test. Avoid presenting a numerical residual alone as
a rigorous proof.

## Background

- **Flag algebras** provide a systematic calculus for deriving inequalities
  between substructure densities in large combinatorial objects.
- **Semidefinite programming** turns a finite flag algebra relaxation into a
  computational optimization problem.
- **SDPA-GMP** solves such programs using arbitrary-precision arithmetic, which
  can reveal exact structure that is obscured at ordinary floating-point
  precision.
- **PSLQ** and related integer-relation algorithms can recover candidate exact
  relations among high-precision numerical values.

These ingredients are complementary: flag algebras define the proof search
space, high-precision SDP exposes a candidate solution, exactification recovers
its symbolic structure, and exact verification closes the proof.

See [Exactifying Singular Flag-Algebra SDPs](docs/exactification-strategies.md)
for a survey of the rounding, kernel-recovery, facial-reduction, and algebraic
methods used in existing work. The operational version is the
[Agent Workflow for Exactifying Singular SDPs](manual/EXACTIFICATION_WORKFLOW.md).
