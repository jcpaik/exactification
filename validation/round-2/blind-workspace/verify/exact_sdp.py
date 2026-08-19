"""Trusted core for exact rational block-SDP certificate checking.

All mathematical arithmetic in this module uses :class:`fractions.Fraction`.
It contains no numerical optimizer and deliberately rejects JSON floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
from math import gcd
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


MODEL_FORMAT = "exact-block-sdp-model-v1"
CERTIFICATE_FORMAT = "exact-block-sdp-certificate-v1"
TRACE_ALGORITHM = "symmetric-schur-v1"


class ExactSDPError(Exception):
    """Base class for controlled verifier errors."""


class FormatError(ExactSDPError):
    """The model or certificate is malformed or ambiguous."""


class VerificationFailure(ExactSDPError):
    """A well-formed certificate fails an exact mathematical check."""


@dataclass(frozen=True)
class Term:
    block: str
    row: int
    col: int
    coefficient: Fraction


@dataclass(frozen=True)
class Expression:
    constant: Fraction
    terms: tuple[Term, ...]


@dataclass(frozen=True)
class Constraint:
    name: str
    sense: str
    expression: Expression


@dataclass(frozen=True)
class Objective:
    sense: str
    expression: Expression


@dataclass(frozen=True)
class BlockSpec:
    name: str
    size: int


@dataclass(frozen=True)
class Model:
    blocks: tuple[BlockSpec, ...]
    constraints: tuple[Constraint, ...]
    objective: Objective

    @property
    def block_sizes(self) -> dict[str, int]:
        return {block.name: block.size for block in self.blocks}


@dataclass(frozen=True)
class TraceStep:
    index: int
    pivot: Fraction


@dataclass(frozen=True)
class PSDTrace:
    steps: tuple[TraceStep, ...]


Matrix = tuple[tuple[Fraction, ...], ...]


@dataclass(frozen=True)
class CertificateBlock:
    name: str
    matrix: Matrix
    psd_trace: PSDTrace | None


@dataclass(frozen=True)
class Certificate:
    claimed_objective: Fraction
    blocks: tuple[CertificateBlock, ...]

    @property
    def block_map(self) -> dict[str, CertificateBlock]:
        return {block.name: block for block in self.blocks}


_RATIONAL_RE = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")
_DECIMAL_CHUNK_DIGITS = 100
_DECIMAL_CHUNK_BASE = 10**_DECIMAL_CHUNK_DIGITS


def _unsigned_decimal_to_int(digits: str) -> int:
    """Parse arbitrary-length decimal text without changing Python's global guard."""

    result = 0
    first_chunk_size = len(digits) % _DECIMAL_CHUNK_DIGITS or _DECIMAL_CHUNK_DIGITS
    result = int(digits[:first_chunk_size])
    for offset in range(first_chunk_size, len(digits), _DECIMAL_CHUNK_DIGITS):
        result = result * _DECIMAL_CHUNK_BASE + int(digits[offset : offset + _DECIMAL_CHUNK_DIGITS])
    return result


def _int_to_decimal(value: int) -> str:
    """Render an arbitrary-length integer through guard-safe decimal chunks."""

    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    remaining = -value if value < 0 else value
    chunks: list[int] = []
    while remaining >= _DECIMAL_CHUNK_BASE:
        remaining, chunk = divmod(remaining, _DECIMAL_CHUNK_BASE)
        chunks.append(chunk)
    tail = "".join(str(chunk).zfill(_DECIMAL_CHUNK_DIGITS) for chunk in reversed(chunks))
    return sign + str(remaining) + tail


def _rational_to_text(value: Fraction) -> str:
    numerator = _int_to_decimal(value.numerator)
    if value.denominator == 1:
        return numerator
    return numerator + "/" + _int_to_decimal(value.denominator)


def _canonical_rational(value: Any, path: str) -> Fraction:
    if not isinstance(value, str) or _RATIONAL_RE.fullmatch(value) is None:
        raise FormatError(f"{path}: expected a canonical rational string")
    numerator_text, separator, denominator_text = value.partition("/")
    negative = numerator_text.startswith("-")
    numerator_digits = numerator_text[1:] if negative else numerator_text
    numerator = _unsigned_decimal_to_int(numerator_digits)
    if negative:
        numerator = -numerator
    denominator = _unsigned_decimal_to_int(denominator_text) if separator else 1
    common_divisor = gcd(abs(numerator), denominator)
    result = Fraction(numerator // common_divisor, denominator // common_divisor)
    canonical = _rational_to_text(result)
    if canonical != value:
        raise FormatError(f"{path}: rational must be reduced and canonical; use {canonical!r}")
    return result


def _name(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise FormatError(f"{path}: expected a nonempty string")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FormatError(f"{path}: expected an integer >= {minimum}")
    return value


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise FormatError(f"{path}: expected an object")
    return value


def _array(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise FormatError(f"{path}: expected an array")
    return value


def _fields(
    value: Any,
    path: str,
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> Mapping[str, Any]:
    obj = _object(value, path)
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - obj.keys())
    unknown = sorted(obj.keys() - allowed)
    if missing:
        raise FormatError(f"{path}: missing field(s): {', '.join(missing)}")
    if unknown:
        raise FormatError(f"{path}: unknown field(s): {', '.join(unknown)}")
    return obj


def _parse_expression(value: Any, path: str, block_sizes: Mapping[str, int]) -> Expression:
    obj = _fields(value, path, required=("constant", "terms"))
    constant = _canonical_rational(obj["constant"], f"{path}.constant")
    terms: list[Term] = []
    seen: set[tuple[str, int, int]] = set()
    for position, raw_term in enumerate(_array(obj["terms"], f"{path}.terms")):
        term_path = f"{path}.terms[{position}]"
        term_obj = _fields(
            raw_term,
            term_path,
            required=("block", "row", "col", "coefficient"),
        )
        block = _name(term_obj["block"], f"{term_path}.block")
        if block not in block_sizes:
            raise FormatError(f"{term_path}.block: unknown block {block!r}")
        row = _integer(term_obj["row"], f"{term_path}.row")
        col = _integer(term_obj["col"], f"{term_path}.col")
        size = block_sizes[block]
        if row > col:
            raise FormatError(f"{term_path}: coordinates must satisfy row <= col")
        if col >= size:
            raise FormatError(f"{term_path}: coordinate is outside {block!r} of size {size}")
        coordinate = (block, row, col)
        if coordinate in seen:
            raise FormatError(f"{term_path}: duplicate affine coordinate {coordinate!r}")
        seen.add(coordinate)
        terms.append(
            Term(
                block,
                row,
                col,
                _canonical_rational(term_obj["coefficient"], f"{term_path}.coefficient"),
            )
        )
    return Expression(constant, tuple(terms))


def parse_model(raw: Any) -> Model:
    obj = _fields(raw, "model", required=("format", "blocks", "constraints", "objective"))
    if obj["format"] != MODEL_FORMAT:
        raise FormatError(f"model.format: expected {MODEL_FORMAT!r}")

    blocks: list[BlockSpec] = []
    block_sizes: dict[str, int] = {}
    for position, raw_block in enumerate(_array(obj["blocks"], "model.blocks")):
        path = f"model.blocks[{position}]"
        block_obj = _fields(raw_block, path, required=("name", "size"))
        name = _name(block_obj["name"], f"{path}.name")
        if name in block_sizes:
            raise FormatError(f"{path}.name: duplicate block name {name!r}")
        size = _integer(block_obj["size"], f"{path}.size", minimum=1)
        block_sizes[name] = size
        blocks.append(BlockSpec(name, size))
    if not blocks:
        raise FormatError("model.blocks: at least one block is required")

    constraints: list[Constraint] = []
    constraint_names: set[str] = set()
    for position, raw_constraint in enumerate(_array(obj["constraints"], "model.constraints")):
        path = f"model.constraints[{position}]"
        constraint_obj = _fields(raw_constraint, path, required=("name", "sense", "expression"))
        name = _name(constraint_obj["name"], f"{path}.name")
        if name in constraint_names:
            raise FormatError(f"{path}.name: duplicate constraint name {name!r}")
        constraint_names.add(name)
        sense = constraint_obj["sense"]
        if sense not in ("eq", "ge", "le"):
            raise FormatError(f"{path}.sense: expected 'eq', 'ge', or 'le'")
        constraints.append(
            Constraint(name, sense, _parse_expression(constraint_obj["expression"], f"{path}.expression", block_sizes))
        )

    objective_obj = _fields(obj["objective"], "model.objective", required=("sense", "expression"))
    objective_sense = objective_obj["sense"]
    if objective_sense not in ("maximize", "minimize"):
        raise FormatError("model.objective.sense: expected 'maximize' or 'minimize'")
    objective = Objective(
        objective_sense,
        _parse_expression(objective_obj["expression"], "model.objective.expression", block_sizes),
    )
    return Model(tuple(blocks), tuple(constraints), objective)


def _parse_matrix(value: Any, path: str, size: int) -> Matrix:
    rows = _array(value, path)
    if len(rows) != size:
        raise FormatError(f"{path}: expected {size} rows, found {len(rows)}")
    matrix_rows: list[tuple[Fraction, ...]] = []
    for row_index, raw_row in enumerate(rows):
        row = _array(raw_row, f"{path}[{row_index}]")
        if len(row) != size:
            raise FormatError(f"{path}[{row_index}]: expected {size} entries, found {len(row)}")
        matrix_rows.append(
            tuple(
                _canonical_rational(entry, f"{path}[{row_index}][{col_index}]")
                for col_index, entry in enumerate(row)
            )
        )
    matrix = tuple(matrix_rows)
    for row in range(size):
        for col in range(row + 1, size):
            if matrix[row][col] != matrix[col][row]:
                raise FormatError(f"{path}: matrix is not symmetric at ({row},{col})")
    return matrix


def _parse_trace(value: Any, path: str) -> PSDTrace:
    obj = _fields(value, path, required=("algorithm", "steps"))
    if obj["algorithm"] != TRACE_ALGORITHM:
        raise FormatError(f"{path}.algorithm: expected {TRACE_ALGORITHM!r}")
    steps: list[TraceStep] = []
    for position, raw_step in enumerate(_array(obj["steps"], f"{path}.steps")):
        step_path = f"{path}.steps[{position}]"
        step_obj = _fields(raw_step, step_path, required=("index", "pivot"))
        steps.append(
            TraceStep(
                _integer(step_obj["index"], f"{step_path}.index"),
                _canonical_rational(step_obj["pivot"], f"{step_path}.pivot"),
            )
        )
    return PSDTrace(tuple(steps))


def parse_certificate(raw: Any, model: Model, *, require_traces: bool = True) -> Certificate:
    obj = _fields(raw, "certificate", required=("format", "claimed_objective", "blocks"))
    if obj["format"] != CERTIFICATE_FORMAT:
        raise FormatError(f"certificate.format: expected {CERTIFICATE_FORMAT!r}")
    claimed = _canonical_rational(obj["claimed_objective"], "certificate.claimed_objective")
    block_sizes = model.block_sizes

    blocks: list[CertificateBlock] = []
    seen: set[str] = set()
    for position, raw_block in enumerate(_array(obj["blocks"], "certificate.blocks")):
        path = f"certificate.blocks[{position}]"
        required = ("name", "matrix", "psd_trace") if require_traces else ("name", "matrix")
        optional = () if require_traces else ("psd_trace",)
        block_obj = _fields(raw_block, path, required=required, optional=optional)
        name = _name(block_obj["name"], f"{path}.name")
        if name not in block_sizes:
            raise FormatError(f"{path}.name: unknown certificate block {name!r}")
        if name in seen:
            raise FormatError(f"{path}.name: duplicate certificate block {name!r}")
        seen.add(name)
        trace = _parse_trace(block_obj["psd_trace"], f"{path}.psd_trace") if "psd_trace" in block_obj else None
        blocks.append(CertificateBlock(name, _parse_matrix(block_obj["matrix"], f"{path}.matrix", block_sizes[name]), trace))

    missing = sorted(block_sizes.keys() - seen)
    if missing:
        raise FormatError(f"certificate.blocks: missing block(s): {', '.join(missing)}")
    return Certificate(claimed, tuple(blocks))


def _without_position(matrix: Sequence[Sequence[Fraction]], position: int, pivot: Fraction) -> list[list[Fraction]]:
    remaining = [index for index in range(len(matrix)) if index != position]
    return [
        [matrix[row][col] - matrix[row][position] * matrix[position][col] / pivot for col in remaining]
        for row in remaining
    ]


def validate_psd_trace(matrix: Matrix, trace: PSDTrace, *, block_name: str = "matrix") -> int:
    """Replay a Schur trace exactly and return the proven matrix rank."""

    size = len(matrix)
    if len(trace.steps) != size:
        raise VerificationFailure(
            f"block {block_name!r}: PSD trace has {len(trace.steps)} steps, expected {size}"
        )
    active = list(range(size))
    current = [list(row) for row in matrix]
    rank = 0
    for step_number, step in enumerate(trace.steps):
        if step.index not in active:
            raise VerificationFailure(
                f"block {block_name!r}: PSD step {step_number} index {step.index} is not active"
            )
        position = active.index(step.index)
        actual = current[position][position]
        if step.pivot != actual:
            raise VerificationFailure(
                f"block {block_name!r}: PSD step {step_number} claims pivot "
                f"{_rational_to_text(step.pivot)}, actual pivot is {_rational_to_text(actual)}"
            )
        if actual < 0:
            raise VerificationFailure(
                f"block {block_name!r}: PSD step {step_number} has negative pivot {_rational_to_text(actual)}"
            )
        if actual == 0:
            if any(current[position][col] != 0 for col in range(len(current))):
                raise VerificationFailure(
                    f"block {block_name!r}: PSD step {step_number} has zero pivot with a nonzero active row"
                )
            current = [
                [entry for col, entry in enumerate(row) if col != position]
                for row_index, row in enumerate(current)
                if row_index != position
            ]
        else:
            current = _without_position(current, position, actual)
            rank += 1
        active.pop(position)
    return rank


def generate_psd_trace(matrix: Matrix, *, block_name: str = "matrix") -> PSDTrace:
    """Generate a deterministic exact trace, or reject a non-PSD matrix."""

    active = list(range(len(matrix)))
    current = [list(row) for row in matrix]
    steps: list[TraceStep] = []
    while active:
        position = 0
        index = active[position]
        pivot = current[position][position]
        steps.append(TraceStep(index, pivot))
        if pivot < 0:
            raise VerificationFailure(
                f"block {block_name!r}: negative Schur pivot {_rational_to_text(pivot)} at index {index}"
            )
        if pivot == 0:
            if any(current[position][col] != 0 for col in range(len(current))):
                raise VerificationFailure(
                    f"block {block_name!r}: zero Schur pivot at index {index} has a nonzero active row"
                )
            current = [row[1:] for row in current[1:]]
        else:
            current = _without_position(current, position, pivot)
        active.pop(position)
    return PSDTrace(tuple(steps))


def _evaluate(expression: Expression, matrices: Mapping[str, Matrix]) -> Fraction:
    value = expression.constant
    for term in expression.terms:
        value += term.coefficient * matrices[term.block][term.row][term.col]
    return value


def verify_certificate(model: Model, certificate: Certificate) -> dict[str, Any]:
    """Verify all exact claims and return a JSON-compatible success report."""

    block_map = certificate.block_map
    matrices = {name: block.matrix for name, block in block_map.items()}
    ranks: dict[str, int] = {}
    for block_spec in model.blocks:
        block = block_map[block_spec.name]
        if block.psd_trace is None:
            raise FormatError(f"certificate block {block.name!r}: missing psd_trace")
        ranks[block.name] = validate_psd_trace(block.matrix, block.psd_trace, block_name=block.name)

    for constraint in model.constraints:
        value = _evaluate(constraint.expression, matrices)
        satisfied = (
            (constraint.sense == "eq" and value == 0)
            or (constraint.sense == "ge" and value >= 0)
            or (constraint.sense == "le" and value <= 0)
        )
        if not satisfied:
            relation = {"eq": "= 0", "ge": ">= 0", "le": "<= 0"}[constraint.sense]
            raise VerificationFailure(
                f"constraint {constraint.name!r} fails: exact value {_rational_to_text(value)} "
                f"does not satisfy {relation}"
            )

    objective_value = _evaluate(model.objective.expression, matrices)
    if objective_value != certificate.claimed_objective:
        raise VerificationFailure(
            f"objective claim fails: exact value is {_rational_to_text(objective_value)}, "
            f"claimed {_rational_to_text(certificate.claimed_objective)}"
        )
    return {
        "status": "verified",
        "objective": _rational_to_text(objective_value),
        "blocks_checked": len(model.blocks),
        "constraints_checked": len(model.constraints),
        "ranks": ranks,
    }


def emit_traces(model: Model, certificate: Certificate) -> Certificate:
    """Replace all traces with deterministic exact Schur traces."""

    by_name = certificate.block_map
    blocks = tuple(
        CertificateBlock(
            spec.name,
            by_name[spec.name].matrix,
            generate_psd_trace(by_name[spec.name].matrix, block_name=spec.name),
        )
        for spec in model.blocks
    )
    traced = Certificate(certificate.claimed_objective, blocks)
    verify_certificate(model, traced)
    return traced


def _reject_json_float(value: str) -> None:
    raise FormatError(f"JSON floating-point value {value!r} is forbidden; use a rational string")


def _reject_json_constant(value: str) -> None:
    raise FormatError(f"nonstandard JSON value {value!r} is forbidden")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FormatError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> Any:
    try:
        with Path(path).open("r", encoding="utf-8") as source:
            return json.load(
                source,
                object_pairs_hook=_unique_object,
                parse_float=_reject_json_float,
                parse_constant=_reject_json_constant,
            )
    except ExactSDPError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FormatError(f"cannot read JSON file {str(path)!r}: {error}") from error


def load_model(path: str | Path) -> Model:
    return parse_model(_load_json(path))


def load_certificate(path: str | Path, model: Model, *, require_traces: bool = True) -> Certificate:
    return parse_certificate(_load_json(path), model, require_traces=require_traces)


def certificate_as_json(certificate: Certificate) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for block in certificate.blocks:
        block_json: dict[str, Any] = {
            "name": block.name,
            "matrix": [[_rational_to_text(entry) for entry in row] for row in block.matrix],
        }
        if block.psd_trace is not None:
            block_json["psd_trace"] = {
                "algorithm": TRACE_ALGORITHM,
                "steps": [
                    {"index": step.index, "pivot": _rational_to_text(step.pivot)}
                    for step in block.psd_trace.steps
                ],
            }
        blocks.append(block_json)
    return {
        "format": CERTIFICATE_FORMAT,
        "claimed_objective": _rational_to_text(certificate.claimed_objective),
        "blocks": blocks,
    }
