"""Service contract (`idp.yaml`) validation against schema idp-service.v1 (ADR-0010)."""

from __future__ import annotations

import json
import os
import re
from collections import deque
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

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
# A top-level define line: blanks, modifiers, `define`, then a blank or the end, and no assignment operator after it
# (`define := 1` and `export define ?= 3` assign a variable named `define`). Linear: each modifier word and its blanks
# have one way to match, so a failed match backtracks at most once per word.
_DEFINE_LINE = re.compile(
    r"[ \t]*((?:(?:override|export|unexport|private)[ \t]+)*)define(?:[ \t]|$)(?![ \t]*(?::{1,3}|[+?!])?=)"
)
# Leading `./` runs, which make strips from an include word before expanding a leading `~`. Anchored; each `/+` run
# is bounded by the next `.`, so a failed match backtracks at most once per run: linear.
_LEADING_DOT_SLASH = re.compile(r"^(?:\./+)+")
_COMMENT = re.compile(r"(?<!\\)#")  # `\#` is a literal hash, not a comment
# Line separators make does not use (make splits on LF only and drops a CR before LF), rejected so that no line
# boundary is ambiguous. One character class plus a one-character lookahead: never backtracks.
_FOREIGN_SEPARATOR = re.compile("\r(?!\n)|[\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
# Characters make reads differently from Python (checked after _FOREIGN_SEPARATOR): every `str.isspace()` character
# except space, tab, LF, CR and the separators above, plus the C0 controls (incl. NUL). One character class: linear.
_FOREIGN_CHARACTER = re.compile("[\x00-\x08\x0e-\x1b\x1f\xa0\u1680\u2000-\u200a\u202f\u205f\u3000]")
# Tenant repos are untrusted (CI runs this on PRs): cap what a Makefile and its includes can make us read or report.
MAX_MAKEFILE_BYTES = 1024 * 1024
MAX_MAKEFILES = 64
MAX_INCLUDE_WORDS = 1024  # distinct include spellings recorded and queued
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
    include_words: tuple[str, ...] = ()  # distinct literal include words as written, in first-seen order
    dynamic_include_words: tuple[str, ...] = ()  # distinct `$` include words as written (never followed)


_EMPTY_SCAN = MakefileScan(frozenset(), ())  # returned when the Makefile was not scanned


def _is_include_line(line: str) -> bool:
    """True if the first word of `line` is `include`, `-include` or `sinclude`."""
    words = line.split(maxsplit=1)
    return bool(words) and words[0] in _INCLUDE_DIRECTIVES


def _include_words(line: str) -> list[str]:
    """Words named by an `include`/`-include`/`sinclude` line without `$` (literal and glob words; `_Scanner.queue`
    rejects outside words and skips glob words)."""
    if not _is_include_line(line):
        return []
    return [w for w in line.split()[1:] if "$" not in w]


def _dynamic_include_words(line: str) -> list[str]:
    """Words of an `include`/`-include`/`sinclude` line that contain `$` (make expands them; never followed)."""
    if not _is_include_line(line):
        return []
    return [w for w in line.split()[1:] if "$" in w]


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
    target-specific variable lines (`name: VAR = x`) are dropped. `line` is already collapsed (`_collapse`)."""
    end = _rule_end(line)
    if end is None or _TARGET_VARIABLE.match(line, end):
        return set()
    names = (n.replace("\\#", "#") for n in line[: line.find(":")].split())
    return {n for n in names if not n.startswith(".") and "%" not in n and "$" not in n}


def _logical_lines(text: str) -> list[str]:
    """make's logical lines: LF-split, one trailing CR dropped, and a line ending in an odd number of backslashes
    joined (with its `\\` + newline kept) to the next one. Linear: each physical line is stripped and joined once."""
    lines: list[str] = []
    pending: list[str] = []
    for physical in text.split("\n"):
        part = physical.removesuffix("\r")
        pending.append(part)
        if (len(part) - len(part.rstrip("\\"))) % 2 == 0:
            lines.append("\n".join(pending))
            pending = []
    if pending:
        lines.append("\n".join(pending))
    return lines


def _collapse(raw: str) -> str:
    """make's `collapse_continuations` on one logical line: each `\\`+newline (ending an odd backslash run) becomes one
    space with the blanks after it dropped; with n >= 3 backslashes, (n-1)/2 are kept and the blanks before them
    stay, otherwise the blanks before it are dropped too. Tokens and directives match make; the exact spacing of
    consecutive blank-only continuation lines may differ. Linear."""
    if "\n" not in raw:
        return raw
    *joined, last = raw.split("\n")
    parts: list[str] = []
    for index, part in enumerate(joined):
        n = len(part) - len(part.rstrip("\\"))
        kept = part[:-n] + "\\" * (n // 2)
        kept = kept if n // 2 else kept.rstrip(" \t")
        parts.append(kept if index == 0 else kept.lstrip(" \t"))
    parts.append(last.lstrip(" \t"))
    return " ".join(parts)


@dataclass(frozen=True)
class _Line:
    """One parsed logical line: `code` is collapsed and comment-stripped; `raw_code` is comment-stripped but not
    collapsed (only for the IDP-22 AC-7 backslash check on include lines)."""

    code: str
    raw_code: str


def _body_line(collapsed: str) -> Literal["end", "ambiguous", "text"]:
    """Classify a collapsed, not comment-stripped define body line like make's `do_define`. Lines whose meaning
    depends on whether the enclosing conditional branch is taken (nested `define`, `endef#`, tab-indented `endef`)
    are "ambiguous": the scanner cannot evaluate conditionals, so they fail closed."""
    p = collapsed.lstrip(" \t")
    if collapsed.startswith("\t"):
        return "ambiguous" if p == "endef" or (p[:5] == "endef" and p[5:6] in (" ", "\t", "#")) else "text"
    if p == "endef" or (p[:5] == "endef" and p[5:6] in (" ", "\t")):
        return "end"
    if p[:6] == "endef#" or p == "define" or (p[:6] == "define" and p[6:7] in (" ", "\t")):
        return "ambiguous"
    return "text"


def _parsed_lines(text: str) -> tuple[list[_Line], list[str]]:
    """Collapsed logical lines with comments (unescaped `#`) removed and `define ... endef` bodies skipped (body lines
    classified by `_body_line`; no nesting count), plus the define problems ("ambiguous", "modifier") in line order.
    Only `define` and a single `override define` open a block; other modifier lists are "modifier" and open none."""
    lines: list[_Line] = []
    problems: list[str] = []
    in_define = False
    for raw in _logical_lines(text):
        collapsed = _collapse(raw)
        if in_define:
            kind = _body_line(collapsed)
            in_define = kind != "end"
            if kind == "ambiguous":
                problems.append(kind)
            continue
        code = _COMMENT.split(collapsed, maxsplit=1)[0]
        define = None if raw.startswith("\t") else _DEFINE_LINE.match(code)  # make tests the tab before collapsing
        if define is not None and define.group(1).split() in ([], ["override"]):
            in_define = True
            continue
        if define is not None:
            problems.append("modifier")
        lines.append(_Line(code, _COMMENT.split(raw, maxsplit=1)[0]))
    return lines, problems


def _read_capped(path: Path) -> str | None:
    """UTF-8 text of `path`, or None if it exceeds MAX_MAKEFILE_BYTES. Raises OSError/UnicodeDecodeError."""
    with path.open("rb") as fh:
        data = fh.read(MAX_MAKEFILE_BYTES + 1)
    return None if len(data) > MAX_MAKEFILE_BYTES else data.decode("utf-8")


def shown(name: str) -> str:
    """`repr(name)` for messages, truncated to MAX_SHOWN_WORD characters (untrusted input is echoed)."""
    text = repr(name)
    return text if len(text) <= MAX_SHOWN_WORD else text[:MAX_SHOWN_WORD] + "…"


def _cannot_read(name: str) -> Violation:
    return Violation(MAKE_PATH, f"cannot read {shown(name)}")


def _outside(word: str | None) -> Violation:
    if word is None:
        return Violation(MAKE_PATH, "Makefile resolves outside the service directory")
    return Violation(MAKE_PATH, f"include {shown(word)} is outside the service directory")


def _backslash_include(name: str) -> Violation:
    return Violation(
        MAKE_PATH,
        f"include line in {shown(name)} uses a backslash (continuation or escape); write each include word literally"
        " on one line",
    )


def _ambiguous_define_line(name: str) -> Violation:
    return Violation(
        MAKE_PATH,
        f"define body in {shown(name)} has a line make reads differently in skipped conditional branches"
        " (nested define, endef followed by '#', or tab-indented endef); remove it",
    )


def _modifier_define(name: str) -> Violation:
    return Violation(
        MAKE_PATH,
        f"{shown(name)} has a define with export, unexport or private, which GNU make 3.81 and 4.x read differently;"
        " use define or override define",
    )


def _foreign_character(name: str, match: re.Match[str]) -> Violation:
    return Violation(
        MAKE_PATH,
        f"{shown(name)} contains a control or space character make reads differently (U+{ord(match.group()):04X});"
        " use only spaces, tabs and LF or CRLF line endings",
    )


def _foreign_separator(name: str, match: re.Match[str]) -> Violation:
    char = match.group()
    what = "CR not followed by LF" if char == "\r" else f"U+{ord(char):04X}"
    return Violation(
        MAKE_PATH, f"{shown(name)} contains a line separator make does not use ({what}); use LF or CRLF line endings"
    )


def _lexically_outside(word: str) -> bool:
    """Absolute words, `..` escapes and words make tilde-expands (`~`, `~user`, also after leading `./` runs) are
    rejected before touching the filesystem. String-only (no pathlib objects): cheap enough for every distinct word."""
    if _LEADING_DOT_SLASH.sub("", word).startswith("~"):
        return True
    normalised = os.path.normpath(word)
    return os.path.isabs(word) or normalised == ".." or normalised.startswith("../")


def _locate(path: Path, word: str | None, root: Path) -> Path | Violation | None:
    """Real path of `path` inside `root`; a Violation if it escapes or cannot be resolved; None if not on disk.
    Lexically outside words never get here (`_Scanner.queue` reports them)."""
    if word is not None and "\x00" in word:  # the OS cannot name such a path (resolve would raise ValueError)
        return _cannot_read(word)
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return None
    except (OSError, RuntimeError):
        return _cannot_read(word or MAKE_PATH)
    return resolved if resolved.is_relative_to(root) else _outside(word)


def _load_makefile(resolved: Path, name: str, limit: int) -> tuple[list[_Line], list[Violation]] | Violation:
    """Parsed lines and at most `limit` define violations of a confined regular file, or a Violation (not a regular
    file, unreadable, too large, using a line separator make does not use, or a character make reads differently)."""
    if not resolved.is_file():  # directories, FIFOs, devices: never opened
        return _cannot_read(name)
    try:
        text = _read_capped(resolved)
    except (OSError, UnicodeDecodeError):
        return _cannot_read(name)
    if text is None:
        return Violation(MAKE_PATH, f"{shown(name)} exceeds 1 MiB")
    if match := _FOREIGN_SEPARATOR.search(text):
        return _foreign_separator(name, match)
    if match := _FOREIGN_CHARACTER.search(text):
        return _foreign_character(name, match)
    lines, problems = _parsed_lines(text)
    kept = problems[:limit]  # past the problem cap the scan stops: do not build the rest
    return lines, [_ambiguous_define_line(name) if p == "ambiguous" else _modifier_define(name) for p in kept]


@dataclass
class _Scanner:
    """Mutable state of one `makefile_targets` scan: FIFO queue (line order), caps and collected results."""

    root: Path
    base: Path
    targets: set[str] = field(default_factory=set)
    problems: list[Violation] = field(default_factory=list)
    pending: deque[tuple[Path, str | None]] = field(default_factory=deque)
    outside: set[str] = field(default_factory=set)
    globs: set[str] = field(default_factory=set)
    spellings: list[str] = field(default_factory=list)
    seen_spellings: set[str] = field(default_factory=set)
    dynamic: list[str] = field(default_factory=list)
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
        """Handle each distinct spelling once (repeats are O(1) set lookups). A lexically outside word (also a glob)
        is reported at once and never recorded or queued. Other glob words are skipped. Other words are recorded and
        queued as written: `visit` dedupes files by real path, as make reads `link/../b.mk` through the link. Stop
        past MAX_INCLUDE_WORDS distinct spellings."""
        if self.stopped or word in self.seen_spellings or word in self.outside or word in self.globs:
            return
        if _lexically_outside(word):
            self.outside.add(word)  # bounded: the problem cap stops the scan after MAX_INCLUDE_PROBLEMS
            self.problem(_outside(word))
            return
        if any(c in word for c in "*?["):  # globs are not followed (IDP-17); remembered so repeats are O(1)
            self.globs.add(word)
            return
        if len(self.seen_spellings) >= MAX_INCLUDE_WORDS:
            self.stop(f"too many include words (limit {MAX_INCLUDE_WORDS})")
            return
        self.seen_spellings.add(word)
        self.spellings.append(word)
        self.pending.append((self.base / word, word))

    def record_dynamic(self, word: str) -> None:
        """Record a distinct `$` word as written; it shares the spelling cap with literal words and is never queued."""
        if self.stopped or word in self.seen_spellings:
            return
        if len(self.seen_spellings) >= MAX_INCLUDE_WORDS:
            self.stop(f"too many include words (limit {MAX_INCLUDE_WORDS})")
            return
        self.seen_spellings.add(word)
        self.dynamic.append(word)

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
        loaded = _load_makefile(located, word or MAKE_PATH, MAX_INCLUDE_PROBLEMS + 1 - len(self.problems))
        if isinstance(loaded, Violation):
            self.problem(loaded)
            return
        lines, define_problems = loaded
        for define_problem in define_problems:
            self.problem(define_problem)
        for line in lines:
            self.targets |= _rule_names(line.code)
            if _is_include_line(line.code) and "\\" in line.raw_code:  # make would read other words than the scan sees
                self.problem(_backslash_include(word or MAKE_PATH))
                continue
            for dynamic in _dynamic_include_words(line.code):
                self.record_dynamic(dynamic)
            for included in _include_words(line.code):
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
    return MakefileScan(
        frozenset(scanner.targets), tuple(scanner.problems), tuple(scanner.spellings), tuple(scanner.dynamic)
    )


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
    return _make_contract(doc, makefile)[0]


def _make_contract(doc: Any, makefile: Path) -> tuple[list[Violation], MakefileScan]:
    """`check_make_contract`'s violations and the single scan they were computed from (empty if not scanned)."""
    if not makefile.is_file():
        return [Violation(MAKE_PATH, "Makefile not found")], _EMPTY_SCAN
    extra = _extra_makefiles(makefile.parent)
    scan = makefile_targets(makefile)
    if scan.violations:
        return extra + list(scan.violations), scan
    targets = scan.targets
    violations = extra + [
        Violation(MAKE_PATH, f"missing required target '{t}'") for t in REQUIRED_TARGETS if t not in targets
    ]
    return violations + [
        Violation(MAKE_PATH, f"missing target 'test-{k}' (required because spec.tests.{k} is true)")
        for k in _enabled_test_kinds(doc)
        if f"test-{k}" not in targets
    ], scan


def _enabled_test_kinds(doc: Any) -> list[str]:
    """Kinds whose `spec.tests.<kind>` is literally `true`; non-mapping `spec`/`tests` are ignored."""
    spec = doc.get("spec") if isinstance(doc, dict) else None
    tests = spec.get("tests") if isinstance(spec, dict) else None
    if not isinstance(tests, dict):
        return []
    return [k for k in TEST_KINDS if tests.get(k) is True]


def load_service(path: Path) -> tuple[Any, list[Violation], MakefileScan]:
    """Parsed `idp.yaml`, its violations (schema, then Make contract; skipped if the YAML is not a mapping) and the
    Makefile scan those violations were computed from (empty if the Makefile was not scanned).

    On invalid YAML, or a file that cannot be read or decoded, the document is None and the only violation says so."""
    try:
        doc, errors = _load_yaml(path)
    except UnicodeDecodeError as exc:  # a ValueError, not an OSError
        return None, [Violation("", f"cannot read: not valid UTF-8 ({exc.reason} at byte {exc.start})")], _EMPTY_SCAN
    except OSError as exc:
        return None, [Violation("", f"cannot read: {exc.strerror or exc}")], _EMPTY_SCAN
    except RecursionError:  # the YAML parser recurses per nesting level
        return None, [Violation("", "cannot parse: nesting too deep")], _EMPTY_SCAN
    if errors:
        return None, errors, _EMPTY_SCAN
    violations = validate_document(doc)
    if not isinstance(doc, dict):
        return doc, violations, _EMPTY_SCAN
    make_violations, scan = _make_contract(doc, path.parent / MAKE_PATH)
    return doc, violations + make_violations, scan


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
