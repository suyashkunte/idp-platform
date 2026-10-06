"""Assertion-quality lint (design doc §11.3, Listing 22): mandatory for agent-written tests, applied to all tests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _is_status_only(node: ast.Assert) -> bool:
    t = node.test
    return isinstance(t, ast.Compare) and isinstance(t.left, ast.Attribute) and t.left.attr == "status_code"


def _uses_pytest_raises(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                expr = item.context_expr
                if (
                    isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Attribute)
                    and expr.func.attr in {"raises", "warns"}
                ):
                    return True
    return False


def _check_function(path: str, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Problem]:
    problems: list[Problem] = []
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    if not asserts and not _uses_pytest_raises(fn):
        problems.append(Problem(path, fn.lineno, f"{fn.name}: no assertions"))
    for a in asserts:
        if isinstance(a.test, ast.Constant) and a.test.value:
            problems.append(Problem(path, a.lineno, f"{fn.name}: constant-true assertion"))
    if asserts and all(_is_status_only(a) for a in asserts):
        problems.append(Problem(path, fn.lineno, f"{fn.name}: asserts status code only"))
    for call in ast.walk(fn):
        if isinstance(call, ast.Call):
            name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
            if name == "sleep":
                problems.append(Problem(path, call.lineno, f"{fn.name}: sleep() used; use a condition-based wait"))
    return problems


def lint_source(source: str, path: str = "<string>") -> list[Problem]:
    tree = ast.parse(source, filename=path)
    problems: list[Problem] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_"):
            problems.extend(_check_function(path, node))
    return sorted(problems, key=lambda p: (p.path, p.line))


def lint_files(paths: list[Path]) -> list[Problem]:
    problems: list[Problem] = []
    for p in paths:
        if p.suffix == ".py" and p.is_file():
            problems.extend(lint_source(p.read_text(encoding="utf-8"), str(p)))
    return problems
