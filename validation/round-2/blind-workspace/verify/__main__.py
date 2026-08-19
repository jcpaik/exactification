"""Command-line entry point for ``python -m verify``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .exact_sdp import (
    ExactSDPError,
    FormatError,
    VerificationFailure,
    certificate_as_json,
    emit_traces,
    load_certificate,
    load_model,
    verify_certificate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify exact rational block-SDP certificates")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="check an exact certificate")
    check.add_argument("model")
    check.add_argument("certificate")
    check.add_argument("--json", action="store_true", dest="json_output")

    emit = commands.add_parser("emit-traces", help="add exact Schur PSD traces to a candidate")
    emit.add_argument("model")
    emit.add_argument("candidate")
    emit.add_argument("-o", "--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        model = load_model(args.model)
        if args.command == "check":
            certificate = load_certificate(args.certificate, model)
            report = verify_certificate(model, certificate)
            if args.json_output:
                print(json.dumps(report, sort_keys=True))
            else:
                rank_summary = ", ".join(f"{name}={rank}" for name, rank in report["ranks"].items())
                print(
                    f"verified: objective={report['objective']}; "
                    f"blocks={report['blocks_checked']}; constraints={report['constraints_checked']}; "
                    f"ranks: {rank_summary}"
                )
            return 0

        candidate = load_certificate(args.candidate, model, require_traces=False)
        traced = emit_traces(model, candidate)
        output = Path(args.output)
        try:
            output.write_text(json.dumps(certificate_as_json(traced), indent=2) + "\n", encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise FormatError(f"cannot write certificate {str(output)!r}: {error}") from error
        print(f"wrote verified certificate with exact PSD traces to {output}")
        return 0
    except VerificationFailure as error:
        print(f"verification failed: {error}", file=sys.stderr)
        return 1
    except (FormatError, ExactSDPError) as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
