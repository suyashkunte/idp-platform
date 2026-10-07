"""Service contract (`idp.yaml`) validation against schema idp-service.v1 (ADR-0010)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_ID = "idp-service.v1"
SCHEMA_NAME = f"{SCHEMA_ID}.json"
MAKE_PATH = "Makefile"
REQUIRED_TARGETS = ("lint", "test", "test-component", "verify", "spec-trace")
TEST_KINDS = ("smoke", "api", "e2e", "perf")
_INCLUDE_DIRECTIVES = frozenset({"include", "-include", "sinclude"})
# Column-0 rule line (comments already stripped, so any `#` left is an escaped `\#`): names, then `:` or `::`
# not followed by `:` or `=` (excludes `:=`, `::=`, `:::=`).
_RULE_LINE = re.compile(r"^(?P<names>[^\s:=][^:=]*?)\s*::?(?![:=])")
# After the rule colon: `[export|override|private ...] VAR <op>` makes it a target-specific variable line.
_TARGET_VARIABLE = re.compile(r"\s*(?:(?:export|override|private)\s+)*[^\s:=#;]+\s*(?::{1,3}|[+?!])?=")
_DEFINE_START = re.compile(r"^\s*(?:(?:override|export|private)\s+)*define(?:\s|$)")
_DEFINE_END = re.compile(r"^\s*endef(?:\s|$)")
_COMMENT = re.compile(r"(?<!\\)#")  # `\#` is a literal hash, not a comment
# Tenant repos are untrusted (CI runs this on PRs): cap what a Makefile and its includes can make us read.
MAX_MAKEFILE_BYTES = 1024 * 1024
MAX_MAKEFILES = 64


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


@dataclass(frozen=True)
class MakefileScan:
    """Result of statically scanning a Makefile: targets found and read/confinement problems."""

    targets: frozenset[str]
    violations: tuple[Violation, ...]


def _include_words(line: str) -> list[str]:
    """Literal words named by an `include`/`-include`/`sinclude` line; `$`/glob words are skipped."""
    words = line.split()
    if not words or words[0] not in _INCLUDE_DIRECTIVES:
        return []
    return [w for w in words[1:] if not any(c in w for c in "$*?[")]


def _rule_names(line: str) -> set[str]:
    """Target names defined by a rule line (column 0); special, pattern, `$(...)` names and
    target-specific variable lines (`name: VAR = x`) are dropped."""
    match = _RULE_LINE.match(line)
    if not match or _TARGET_VARIABLE.match(line, match.end()):
        return set()
    names = (n.replace("\\#", "#") for n in match.group("names").split())
    return {n for n in names if not n.startswith(".") and "%" not in n and "$" not in n}


def _parsed_lines(text: str) -> list[str]:
    """Lines with comments (unescaped `#`) removed and `define ... endef` bodies (nested) skipped."""
    lines: list[str] = []
    depth = 0
    for raw in text.splitlines():
        line = _COMMENT.split(raw, maxsplit=1)[0]
        if depth:
            depth += 1 if _DEFINE_START.match(line) else -1 if _DEFINE_END.match(line) else 0
        elif not line.startswith("\t") and _DEFINE_START.match(line):
            depth = 1
        else:
            lines.append(line)
    return lines


def _read_capped(path: Path) -> str | None:
    """UTF-8 text of `path`, or None if it exceeds MAX_MAKEFILE_BYTES. Raises OSError/UnicodeDecodeError."""
    with path.open("rb") as fh:
        data = fh.read(MAX_MAKEFILE_BYTES + 1)
    return None if len(data) > MAX_MAKEFILE_BYTES else data.decode("utf-8")


def _outside(word: str | None) -> Violation:
    if word is None:
        return Violation(MAKE_PATH, "Makefile resolves outside the service directory")
    return Violation(MAKE_PATH, f"include {word!r} is outside the service directory")


def _lexically_outside(word: str, root: Path) -> bool:
    """Absolute words and `..` escapes are rejected before touching the filesystem."""
    return Path(word).is_absolute() or not Path(os.path.normpath(root / word)).is_relative_to(root)


def _locate(path: Path, word: str | None, root: Path) -> Path | Violation | None:
    """Real path of `path` inside `root`; a Violation if it escapes or cannot be resolved; None if not on disk."""
    if word is not None and _lexically_outside(word, root):
        return _outside(word)
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return None
    except (OSError, RuntimeError):
        return Violation(MAKE_PATH, f"cannot read {word or MAKE_PATH!r}")
    return resolved if resolved.is_relative_to(root) else _outside(word)


def _load_makefile(resolved: Path, name: str) -> list[str] | Violation:
    """Parsed lines of a confined regular file, or a Violation (not a regular file, unreadable, too large)."""
    if not resolved.is_file():  # directories, FIFOs, devices: never opened
        return Violation(MAKE_PATH, f"cannot read {name!r}")
    try:
        text = _read_capped(resolved)
    except (OSError, UnicodeDecodeError):
        return Violation(MAKE_PATH, f"cannot read {name!r}")
    if text is None:
        return Violation(MAKE_PATH, f"{name!r} exceeds 1 MiB")
    return _parsed_lines(text)


def makefile_targets(makefile: Path) -> MakefileScan:
    """Targets defined by rule lines in `makefile` and its literal includes. Static parsing only; make never runs.

    Reads are confined to the Makefile's directory (real paths), capped at MAX_MAKEFILE_BYTES per file and
    MAX_MAKEFILES files; problems are returned as violations instead of raising."""
    root = makefile.parent.resolve()
    targets: set[str] = set()
    problems: list[Violation] = []
    pending: list[tuple[Path, str | None]] = [(makefile, None)]
    visited: set[Path] = set()
    while pending:
        path, word = pending.pop()
        located = _locate(path, word, root)
        if located is None or located in visited:
            continue
        if isinstance(located, Violation):
            problems.append(located)
            continue
        if len(visited) >= MAX_MAKEFILES:
            problems.append(Violation(MAKE_PATH, f"too many included files (limit {MAX_MAKEFILES})"))
            break
        visited.add(located)
        lines = _load_makefile(located, word or MAKE_PATH)
        if isinstance(lines, Violation):
            problems.append(lines)
            continue
        for line in lines:
            pending.extend((makefile.parent / w, w) for w in _include_words(line))
            targets |= _rule_names(line)
    return MakefileScan(frozenset(targets), tuple(problems))


def check_make_contract(doc: Any, makefile: Path) -> list[Violation]:
    """Make contract (I2) violations for the Makefile beside `idp.yaml`.

    If the Makefile or an include cannot be read safely, only those problems are reported (the target list
    would be incomplete)."""
    if not makefile.is_file():
        return [Violation(MAKE_PATH, "Makefile not found")]
    scan = makefile_targets(makefile)
    if scan.violations:
        return list(scan.violations)
    targets = scan.targets
    violations = [Violation(MAKE_PATH, f"missing required target '{t}'") for t in REQUIRED_TARGETS if t not in targets]
    return violations + [
        Violation(MAKE_PATH, f"missing target 'test-{k}' (required because spec.tests.{k} is true)")
        for k in _enabled_test_kinds(doc)
        if f"test-{k}" not in targets
    ]


def _enabled_test_kinds(doc: Any) -> list[str]:
    """Kinds whose `spec.tests.<kind>` is literally `true`; non-mapping `spec`/`tests` are ignored."""
    spec = doc.get("spec") if isinstance(doc, dict) else None
    tests = spec.get("tests") if isinstance(spec, dict) else None
    if not isinstance(tests, dict):
        return []
    return [k for k in TEST_KINDS if tests.get(k) is True]


def validate_service(path: Path) -> list[Violation]:
    """Schema violations for `path`, then Make contract violations (skipped if the YAML is not a mapping)."""
    doc, errors = _load_yaml(path)
    if errors:
        return errors
    violations = validate_document(doc)
    if isinstance(doc, dict):
        violations += check_make_contract(doc, path.parent / MAKE_PATH)
    return violations


def to_dict(file: str, violations: list[Violation]) -> dict[str, object]:
    """Machine-readable result for `idp validate --json` (key order is part of the interface)."""
    return {
        "file": file,
        "valid": not violations,
        "schema": SCHEMA_ID,
        "violations": [{"path": v.path, "message": v.message} for v in violations],
    }
