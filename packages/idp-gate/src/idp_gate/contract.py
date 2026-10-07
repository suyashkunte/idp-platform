"""Service contract (`idp.yaml`) validation against schema idp-service.v1 (ADR-0010)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_NAME = "idp-service.v1.json"
MAKE_PATH = "Makefile"
REQUIRED_TARGETS = ("lint", "test", "test-component", "verify", "spec-trace")
_INCLUDE_DIRECTIVES = frozenset({"include", "-include", "sinclude"})
# Column-0 rule line: names, then `:` or `::` not followed by `:` or `=` (excludes `:=`, `::=`, `:::=`).
_RULE_LINE = re.compile(r"^(?P<names>[^\s:=#][^:=#]*?)\s*::?(?![:=])")


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path or '<root>'}: {self.message}"


def load_schema() -> dict[str, Any]:
    text = resources.files("idp_gate.schemas").joinpath(SCHEMA_NAME).read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def validate_document(doc: Any) -> list[Violation]:
    validator = Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [Violation(".".join(str(p) for p in e.absolute_path), e.message) for e in errors]


def _load_yaml(path: Path) -> tuple[Any, list[Violation]]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), []
    except yaml.YAMLError as exc:
        return None, [Violation("", f"invalid YAML: {exc}")]


def validate_file(path: Path) -> list[Violation]:
    doc, errors = _load_yaml(path)
    return errors or validate_document(doc)


def _include_paths(line: str, base: Path) -> list[Path]:
    """Literal paths named by an `include`/`-include`/`sinclude` line; `$`/glob words are skipped."""
    words = line.split()
    if not words or words[0] not in _INCLUDE_DIRECTIVES:
        return []
    return [base / w for w in words[1:] if not any(c in w for c in "$*?[")]


def _rule_names(line: str) -> set[str]:
    """Target names defined by a rule line (column 0); special, pattern and `$(...)` names are dropped."""
    match = _RULE_LINE.match(line)
    if not match:
        return set()
    return {n for n in match.group("names").split() if not n.startswith(".") and "%" not in n and "$" not in n}


def makefile_targets(makefile: Path) -> set[str]:
    """Targets defined by rule lines in `makefile` and its literal includes. Static parsing only; make never runs."""
    targets: set[str] = set()
    pending: list[Path] = [makefile]
    visited: set[Path] = set()
    while pending:
        current = pending.pop()
        key = current.resolve()
        if key in visited or not current.is_file():
            continue
        visited.add(key)
        for raw in current.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0]
            pending.extend(_include_paths(line, makefile.parent))
            targets |= _rule_names(line)
    return targets


def check_make_contract(doc: Any, makefile: Path) -> list[Violation]:
    """Make contract (I2) violations for the Makefile beside `idp.yaml`."""
    if not makefile.is_file():
        return [Violation(MAKE_PATH, "Makefile not found")]
    targets = makefile_targets(makefile)
    return [Violation(MAKE_PATH, f"missing required target '{t}'") for t in REQUIRED_TARGETS if t not in targets]


def validate_service(path: Path) -> list[Violation]:
    """Schema violations for `path`, then Make contract violations (skipped if the YAML is not a mapping)."""
    doc, errors = _load_yaml(path)
    if errors:
        return errors
    violations = validate_document(doc)
    if isinstance(doc, dict):
        violations += check_make_contract(doc, path.parent / MAKE_PATH)
    return violations
