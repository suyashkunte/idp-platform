"""`idp` command-line entry point. Exit codes: 0 ok, 1 check failed, 2 refused or usage error."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from idp_gate import __version__, approve_spec, contract, spec_trace, test_quality


def _cmd_spec_trace(args: argparse.Namespace) -> int:
    try:
        report = spec_trace.trace(args.ticket, Path(args.root))
    except FileNotFoundError as exc:
        if args.json:
            print(json.dumps({"ticket": args.ticket, "ok": False, "error": str(exc)}))
        else:
            print(f"spec-trace: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(spec_trace.to_dict(report)) if args.json else spec_trace.render(report))
    return 0 if report.ok else 1


def _cmd_test_quality_lint(args: argparse.Namespace) -> int:
    problems = test_quality.lint_files([Path(f) for f in args.files])
    for p in problems:
        print(p)
    return 1 if problems else 0


def _cmd_approve_spec(args: argparse.Namespace) -> int:
    try:
        marker = approve_spec.approve(args.ticket, Path(args.root))
    except approve_spec.ApprovalRefused as exc:
        print(f"approve-spec: REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"approved: {marker}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"validate: {path} not found", file=sys.stderr)
        return 2
    violations = contract.validate_service(path)
    if args.json:
        print(json.dumps(contract.to_dict(args.file, violations)))
        return 1 if violations else 0
    for v in violations:
        print(f"{path}: {v}")
    if not violations:
        print(f"{path}: valid ({contract.SCHEMA_NAME})")
    return 1 if violations else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="idp", description="Intelligent Delivery Pipeline CLI")
    parser.add_argument("--version", action="version", version=f"idp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("spec-trace", help="check every acceptance criterion has a tagged test")
    p.add_argument("ticket")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true", help="print a JSON object instead of text")
    p.set_defaults(func=_cmd_spec_trace)

    p = sub.add_parser("test-quality-lint", help="flag tests that cannot fail meaningfully")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=_cmd_test_quality_lint)

    p = sub.add_parser("approve-spec", help="HUMANS ONLY: record approval of specs/<KEY>/spec.md")
    p.add_argument("ticket")
    p.add_argument("--root", default=".")
    p.set_defaults(func=_cmd_approve_spec)

    p = sub.add_parser("validate", help="validate idp.yaml against the service contract schema and the Make contract")
    p.add_argument("file", nargs="?", default="idp.yaml")
    p.add_argument("--json", action="store_true", help="print a JSON object instead of text")
    p.set_defaults(func=_cmd_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
