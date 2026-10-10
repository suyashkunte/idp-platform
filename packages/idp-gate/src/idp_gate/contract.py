"""Service contract (`idp.yaml`) validation against schema idp-service.v1 (ADR-0010)."""

from __future__ import annotations

import json
import os
import re
from collections import deque
from dataclasses import dataclass, field
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
# Casefolded names GNU make reads before `Makefile`; such an entry beside the validated Makefile would shadow it.
_SHADOWING_MAKEFILES = frozenset({"gnumakefile", "makefile"})
# After the rule colon: `[export|override|private ...] VAR <op>` makes it a target-specific variable line.
_TARGET_VARIABLE = re.compile(r"\s*(?:(?:export|override|private)\s+)*[^\s:=#;]+\s*(?::{1,3}|[+?!])?=")
# `define NAME` starts a block; `define := x` (a variable named `define`) does not.
_DEFINE_START = re.compile(r"^\s*(?:(?:override|export|private)\s+)*define(?:\s|$)(?!\s*(?::{1,3}|[+?!])?=)")
_DEFINE_END = re.compile(r"^\s*endef(?:\s|$)")
_COMMENT = re.compile(r"(?<!\\)#")  # `\#` is a literal hash, not a comment
# Tenant repos are untrusted (CI runs this on PRs): cap what a Makefile and its includes can make us read or report.
MAX_MAKEFILE_BYTES = 1024 * 1024
MAX_MAKEFILES = 64
MAX_INCLUDE_WORDS = 1024  # distinct (normalised) include words queued
MAX_INCLUDE_PROBLEMS = 20  # confinement/read violations before scanning stops
MAX_SHOWN_WORD = 200  # characters of an include word's repr echoed in a message


@dataclass(frozen=True)
class Violation:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path or '<root>'}: {self.message}"


def load_schema(name: str = SCHEMA_NAME) -> dict[str, Any]:
    text = resources.files("idp_gate.schemas").joinpath(name).read_text(encoding="utf-8")
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


def _rule_end(line: str) -> int | None:
    """Index just past the `:`/`::` of a column-0 rule line, or None (linear: no backtracking regex).

    Comments are already stripped, so any `#` left is an escaped `\\#`. Names precede the first `:`, contain no `=`
    and do not start with whitespace; `:=`, `::=` and `:::=` are assignments, not rules."""
    colon = line.find(":")
    if colon <= 0 or line[0].isspace() or "=" in line[:colon]:
        return None
    end = colon + 2 if line[colon + 1 : colon + 2] == ":" else colon + 1
    return None if line[end : end + 1] in {":", "="} else end


def _rule_names(line: str) -> set[str]:
    """Target names defined by a rule line (column 0); special, pattern, `$(...)` names and
    target-specific variable lines (`name: VAR = x`) are dropped."""
    end = _rule_end(line)
    if end is None or _TARGET_VARIABLE.match(line, end):
        return set()
    names = (n.replace("\\#", "#") for n in line[: line.find(":")].split())
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


def _shown(name: str) -> str:
    """`repr(name)` for messages, truncated to MAX_SHOWN_WORD characters (untrusted input is echoed)."""
    text = repr(name)
    return text if len(text) <= MAX_SHOWN_WORD else text[:MAX_SHOWN_WORD] + "…"


def _cannot_read(name: str) -> Violation:
    return Violation(MAKE_PATH, f"cannot read {_shown(name)}")


def _outside(word: str | None) -> Violation:
    if word is None:
        return Violation(MAKE_PATH, "Makefile resolves outside the service directory")
    return Violation(MAKE_PATH, f"include {_shown(word)} is outside the service directory")


def _lexically_outside(word: str, root: Path) -> bool:
    """Absolute words and `..` escapes are rejected before touching the filesystem."""
    return Path(word).is_absolute() or not Path(os.path.normpath(root / word)).is_relative_to(root)


def _locate(path: Path, word: str | None, root: Path) -> Path | Violation | None:
    """Real path of `path` inside `root`; a Violation if it escapes or cannot be resolved; None if not on disk."""
    if word is not None and "\x00" in word:  # the OS cannot name such a path (resolve would raise ValueError)
        return _cannot_read(word)
    if word is not None and _lexically_outside(word, root):
        return _outside(word)
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return None
    except (OSError, RuntimeError):
        return _cannot_read(word or MAKE_PATH)
    return resolved if resolved.is_relative_to(root) else _outside(word)


def _load_makefile(resolved: Path, name: str) -> list[str] | Violation:
    """Parsed lines of a confined regular file, or a Violation (not a regular file, unreadable, too large)."""
    if not resolved.is_file():  # directories, FIFOs, devices: never opened
        return _cannot_read(name)
    try:
        text = _read_capped(resolved)
    except (OSError, UnicodeDecodeError):
        return _cannot_read(name)
    if text is None:
        return Violation(MAKE_PATH, f"{_shown(name)} exceeds 1 MiB")
    return _parsed_lines(text)


@dataclass
class _Scanner:
    """Mutable state of one `makefile_targets` scan: FIFO queue (line order), caps and collected results."""

    root: Path
    base: Path
    targets: set[str] = field(default_factory=set)
    problems: list[Violation] = field(default_factory=list)
    pending: deque[tuple[Path, str | None]] = field(default_factory=deque)
    words: set[str] = field(default_factory=set)
    visited: set[Path] = field(default_factory=set)
    stopped: bool = False

    def stop(self, message: str) -> None:
        if not self.stopped:
            self.problems.append(Violation(MAKE_PATH, message))
            self.stopped = True

    def problem(self, violation: Violation) -> None:
        if len(self.problems) >= MAX_INCLUDE_PROBLEMS:
            self.stop(f"too many include problems (limit {MAX_INCLUDE_PROBLEMS})")
        elif not self.stopped:
            self.problems.append(violation)

    def queue(self, word: str) -> None:
        """Queue an include word once per normalised spelling; stop past MAX_INCLUDE_WORDS distinct words."""
        key = os.path.normpath(word)
        if self.stopped or key in self.words:
            return
        if len(self.words) >= MAX_INCLUDE_WORDS:
            self.stop(f"too many include words (limit {MAX_INCLUDE_WORDS})")
            return
        self.words.add(key)
        self.pending.append((self.base / word, word))

    def visit(self, path: Path, word: str | None) -> None:
        located = _locate(path, word, self.root)
        if located is None or located in self.visited:
            return
        if isinstance(located, Violation):
            self.problem(located)
            return
        if len(self.visited) >= MAX_MAKEFILES:
            self.stop(f"too many included files (limit {MAX_MAKEFILES})")
            return
        self.visited.add(located)
        lines = _load_makefile(located, word or MAKE_PATH)
        if isinstance(lines, Violation):
            self.problem(lines)
            return
        for line in lines:
            self.targets |= _rule_names(line)
            for included in _include_words(line):
                self.queue(included)


def makefile_targets(makefile: Path) -> MakefileScan:
    """Targets defined by rule lines in `makefile` and its literal includes. Static parsing only; make never runs.

    Reads are confined to the Makefile's directory (real paths), capped at MAX_MAKEFILE_BYTES per file,
    MAX_MAKEFILES files, MAX_INCLUDE_WORDS distinct include words and MAX_INCLUDE_PROBLEMS problems; problems are
    returned as violations instead of raising. Includes are scanned in line order (breadth-first)."""
    scanner = _Scanner(root=makefile.parent.resolve(), base=makefile.parent)
    scanner.pending.append((makefile, None))
    while scanner.pending and not scanner.stopped:
        scanner.visit(*scanner.pending.popleft())
    return MakefileScan(frozenset(scanner.targets), tuple(scanner.problems))


def _extra_makefiles(directory: Path) -> list[Violation]:
    """One violation per entry (stored name, sorted) that GNU make would read instead of `Makefile`.

    Names are compared as listed, so `Makefile` itself never matches; fails closed if the directory cannot be listed."""
    try:
        names = os.listdir(directory)
    except OSError:
        return [Violation(MAKE_PATH, "cannot list the service directory")]
    return [
        Violation(name, "GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it")
        for name in sorted(names)
        if name != MAKE_PATH and name.casefold() in _SHADOWING_MAKEFILES
    ]


def check_make_contract(doc: Any, makefile: Path) -> list[Violation]:
    """Make contract (I2) violations for the Makefile beside `idp.yaml`.

    Entries that would shadow the Makefile (`GNUmakefile`/`makefile`, any case) are reported first. If the Makefile
    or an include cannot be read safely, only those problems follow (the target list would be incomplete)."""
    if not makefile.is_file():
        return [Violation(MAKE_PATH, "Makefile not found")]
    extra = _extra_makefiles(makefile.parent)
    scan = makefile_targets(makefile)
    if scan.violations:
        return extra + list(scan.violations)
    targets = scan.targets
    violations = extra + [
        Violation(MAKE_PATH, f"missing required target '{t}'") for t in REQUIRED_TARGETS if t not in targets
    ]
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


def load_service(path: Path) -> tuple[Any, list[Violation]]:
    """Parsed `idp.yaml` and its violations: schema, then Make contract (skipped if the YAML is not a mapping).

    On invalid YAML the document is None and the only violation is the parse error."""
    doc, errors = _load_yaml(path)
    if errors:
        return None, errors
    violations = validate_document(doc)
    if isinstance(doc, dict):
        violations += check_make_contract(doc, path.parent / MAKE_PATH)
    return doc, violations


def validate_service(path: Path) -> list[Violation]:
    """Schema violations for `path`, then Make contract violations (skipped if the YAML is not a mapping)."""
    return load_service(path)[1]


def to_dict(file: str, violations: list[Violation]) -> dict[str, object]:
    """Machine-readable result for `idp validate --json` (key order is part of the interface)."""
    return {
        "file": file,
        "valid": not violations,
        "schema": SCHEMA_ID,
        "violations": [{"path": v.path, "message": v.message} for v in violations],
    }
