"""Traceability from acceptance criteria to tests (design doc §21.8).

A spec lists criteria as markdown bullets ``- **AC-1** ...``. Tests cite them with ``@pytest.mark.ac("KEY:AC-1")``.
Every AC needs at least one test, and a test may not cite an AC the spec does not define.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

AC_LINE = re.compile(r"^\s*[-*]\s+\*\*(AC-\d+)\*\*", re.MULTILINE)
SKIP_DIRS = {".git", ".venv", "node_modules", ".mypy_cache", ".ruff_cache", ".pytest_cache", "build", "dist"}


@dataclass
class TraceReport:
    ticket: str
    required: set[str]
    found: dict[str, list[str]] = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        return sorted(a for a in self.required if a not in self.found)

    @property
    def unknown(self) -> list[str]:
        prefix = f"{self.ticket}:"
        return sorted(a for a in self.found if a.startswith(prefix) and a not in self.required)

    @property
    def ok(self) -> bool:
        return bool(self.required) and not self.missing and not self.unknown


def acs_in_spec(spec: Path, ticket: str) -> set[str]:
    return {f"{ticket}:{ac}" for ac in AC_LINE.findall(spec.read_text(encoding="utf-8"))}


def _test_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        for path in root.rglob("test_*.py"):
            if not SKIP_DIRS.intersection(path.parts):
                yield path


def _ac_ids(decorator: ast.expr) -> list[str]:
    """Return AC ids from ``@pytest.mark.ac("KEY:AC-n", ...)`` or ``@mark.ac(...)``."""
    if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
        return []
    if decorator.func.attr != "ac":
        return []
    return [a.value for a in decorator.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def acs_in_tests(roots: Iterable[Path]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in _test_files(roots):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                for dec in node.decorator_list:
                    for ac in _ac_ids(dec):
                        found.setdefault(ac, []).append(f"{path}::{node.name}")
    return found


def trace(ticket: str, repo_root: Path = Path()) -> TraceReport:
    spec = repo_root / "specs" / ticket / "spec.md"
    if not spec.is_file():
        raise FileNotFoundError(f"spec not found: {spec}")
    return TraceReport(ticket=ticket, required=acs_in_spec(spec, ticket), found=acs_in_tests([repo_root]))


def render(report: TraceReport) -> str:
    lines = [f"spec-trace {report.ticket}: {len(report.required)} AC(s)"]
    if not report.required:
        lines.append("  NO ACCEPTANCE CRITERIA found in spec (expected lines like '- **AC-1** ...')")
    for ac in sorted(report.required):
        tests = report.found.get(ac, [])
        lines.append(f"  {'OK     ' if tests else 'MISSING'} {ac}" + (f"  <- {', '.join(tests)}" if tests else ""))
    lines.extend(f"  UNKNOWN {ac} cited by {', '.join(report.found[ac])}" for ac in report.unknown)
    return "\n".join(lines)
