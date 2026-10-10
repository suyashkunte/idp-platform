---
ticket: IDP-22
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: guided
---

# IDP-22: idp validate/conformance: close Makefile contract-check bypasses

## Context
Follow-up from the IDP-19 review (PR #7). `idp validate` (IDP-17) checks only the file named `Makefile` beside
`idp.yaml`, but GNU make reads `GNUmakefile`, then `makefile`, then `Makefile` and uses the first one it finds. So a
service can pass the contract check with a valid `Makefile` while `make verify` runs a `GNUmakefile` whose `verify` is
`@true`. Separately, `idp conformance` (IDP-19) discovers `examples/<x>` with `Path.is_dir()`, which follows symlinks,
so a symlinked example directory can point the runner (and make) outside `examples/`. Parent epic IDP-16; depends on
IDP-19 (Done).

Facts checked in the repository (2026-10-10, branch `feature/IDP-22-makefile-contract-bypasses`):
- `packages/idp-gate/src/idp_gate/contract.py`: `check_make_contract(doc, makefile)` returns the single violation
  `Makefile not found` when `makefile.is_file()` is false, else scans it (`makefile_targets`). Nothing looks at other
  entries of the service directory. `validate_service(path)` parses `idp.yaml` with the private `_load_yaml`.
- `packages/idp-gate/src/idp_gate/conformance.py`: `find_examples(root)` keeps non-dot entries with `p.is_dir()` and
  `(p / "idp.yaml").is_file()` (both follow symlinks). `check_example(directory, make)` calls
  `contract.validate_service(path)` and then parses `idp.yaml` a second time through `contract._load_yaml(path)` for
  profile resolution. `_run_make_verify` runs
  `[make, "--no-print-directory", "-C", <dir>, "verify", "IDP_PROFILE_DIR=<dir>"]` (no `-f`) with
  `Popen(start_new_session=True)` and `os.killpg` on timeout.
- `packages/idp-gate/src/idp_gate/cli.py` `_cmd_conformance` prints `"\n".join(result.lines())` per example; the
  example is shown as the path built from DIR, e.g. `PASS examples/minimal-service`, `FAIL examples/bad: ...`.
- Existing tests that pin current behaviour: `test_contract.py::test_missing_makefile_is_single_violation` and
  `::test_gnumakefile_is_not_recognised` (IDP-17 AC-6: only `GNUmakefile`, no `Makefile` -> exactly
  `Makefile: Makefile not found`); `test_conformance.py::test_conformance_reports_make_timeout` (IDP-19 AC-2) asserts
  `argv[1:5] == ["--no-print-directory", "-C", "examples/slow", "verify"]` and `argv[5]` starts with `IDP_PROFILE_DIR=`.
- `profiles.py` also calls `contract._load_yaml` (profile.yaml); `test_profiles.py` monkeypatches it. Not touched here.
- `examples/minimal-service/` contains only `Makefile` (no `GNUmakefile`/`makefile`) and is a real directory.
- The service-contract doc is `docs/platform/service-contract.md` (repository root `docs/`, not under
  `packages/idp-gate/` as the ticket's Interfaces line says); it currently states "`makefile` and `GNUmakefile` are not
  recognised". `idp conformance` is described in `docs/platform/onboarding.md`.
- Negative conformance fixtures live in `tests/conformance/fixtures/<name>/` and are used by
  `tests/conformance/test_examples.py`.

## Amendment (2026-10-10, after review loop 1)
AC-1..AC-4 were implemented (draft PR #11: dba546c tests; 214fe8f, f9e3879, df4515e, 96cbd1e T1-T5; b2c45f3 docs).
The review found two important gaps, and the human decided to fix them in this PR (spec re-approval needed):
- M1 (security): a makefile can remake itself. With `Makefile: evil.txt ; cp evil.txt Makefile`, GNU make
  remakes `Makefile`, restarts and runs the new content, so `-f Makefile` (AC-2) alone does not guarantee that the
  validated file runs (reproduced by the reviewer with GNU Make 3.81). The same applies to a literal include that a
  rule generates or updates (`-include gen.mk` plus `gen.mk: ...`). Added as AC-5.
- M3 (security, pre-existing): `contract._load_yaml` catches only `yaml.YAMLError`, so an `idp.yaml` that cannot be
  read (`OSError`) or decoded (`UnicodeDecodeError`) raises a traceback out of `idp validate` and stops
  `idp conformance` for all remaining examples. Added as AC-6.
- Test hardening under existing ACs (no new AC): an `OSError` case for the AC-3 "resolves outside" test, and the AC-4
  private-member test also catching `from idp_gate.contract import _x` / `from .contract import _x`.

Facts checked for the amendment (current code on the branch):
- `contract.MakefileScan` has `targets` and `violations` only. `_Scanner.queue(word)` dedups include words by
  `os.path.normpath(word)` and caps them at `MAX_INCLUDE_WORDS` (1024) distinct keys; words for files not on disk are
  queued and then skipped by `_locate` (returns None); `$`/glob words never reach `queue` (`_include_words`).
- `conformance._run_make_verify(directory, make, profile_dir)` builds
  `[make, "--no-print-directory", "-C", dir, "-f", "Makefile", "verify", "IDP_PROFILE_DIR=..."]`.
  `check_example` gets `(doc, violations)` from `contract.load_service(path)`; the scan result is not exposed.
- `contract.load_service` calls `_load_yaml(path)`, which raises `OSError`/`UnicodeDecodeError` from
  `path.read_text`. `profiles.load` relies on that: it wraps `contract._load_yaml` in
  `except (OSError, UnicodeDecodeError)` and reports `cannot read '<name>': <exc>` (pinned by
  `test_profiles.py::test_profile_show_unreadable_profile_exits_2`, IDP-18 AC-5, which also monkeypatches `_load_yaml`
  to raise `PermissionError`).
- `test_conformance.py::test_check_example_parses_idp_yaml_once_for_validation_and_profile` stubs `_run_make_verify`
  with the 3-argument signature; `test_conformance_reports_make_timeout` (IDP-19) and
  `test_make_verify_is_invoked_with_f_makefile` (IDP-22 AC-2) assert the exact argv.

## Amendment 2 (2026-10-10, after review loop 2)
T7-T9 were implemented (ba886b9, d74e0c2, 1e5827f); the IDP-17 include-word cap test was aligned in 3671157 (decision
D4). Both reviewers independently found, and reproduced on GNU Make 3.81 (4.3 behaves the same), that AC-5 can be
bypassed by literal include lines the scanner misreads:
- MJ1: `-include gen\#.mk`. make unescapes the word to `gen#.mk`; the scanner records and pins `gen\#.mk`, so the
  real file is neither pinned nor scanned (a static variant includes an outside symlink that is never scanned).
- MJ2: backslash-newline continuation (`-include common.mk \` then `  gen.mk`). `_parsed_lines` does not join
  continuations, so `gen.mk` is neither pinned nor scanned.

The human chose to fail closed (consistent with D3 and with how `$`/glob words are handled): an include directive
line containing a backslash is a validation violation. Added as AC-7. Why this suffices: make treats a line as an
include only when it starts a logical line, so if a preceding line ends in `\`, make does not include it while the
scanner still pins and scans it (over-pinning, the safe direction). The amendment also adds an AC-6 clarification for
deeply nested `idp.yaml` (`RecursionError`), test and typing hardening (T13), and records the review items that are
not fixed (D5-D7).

Facts checked for amendment 2 (current code on the branch):
- `_parsed_lines` strips comments at the first unescaped `#` (`_COMMENT = (?<!\\)#`), so `gen\#.mk` survives as
  written, and lines are not joined. `_include_words(line)` splits on whitespace and drops words containing
  `$*?[`; there is no backslash handling.
- `contract.load_service` catches `UnicodeDecodeError` and `OSError` around `_load_yaml` but not `RecursionError`.
  `yaml.safe_load` uses the pure-Python `SafeLoader`, whose composer recurses once per nesting level (the scanner
  and parser are iterative), so `"[" * 100000` should raise `RecursionError` within a few hundred levels, long before
  the input ends. ASSUMPTION A17, verified first in T12.
- Test minors found in review: `test_makefile_scan_records_literal_include_words_as_written` and
  `test_makefile_scan_caps_recorded_include_spellings` read `getattr(scan, "include_words", ...)`;
  `test_conformance_fails_when_include_words_exceed_make_argument_limit` monkeypatches `MAX_ASSUME_OLD_BYTES` with
  `raising=False`; `conformance._invalid` is annotated `list[contract.Violation] | tuple[contract.Violation, ...]`;
  `test_unreadable_or_undecodable_idp_yaml_is_a_violation` has no case for an `OSError` whose `strerror` is None.

## Requirements
- **AC-1** Given a service directory containing a valid `Makefile` and also a `GNUmakefile` or `makefile`, when I run `idp validate`, then it exits 1 and reports a violation naming the extra file.
  - "Extra file": a directory entry, found by listing the service directory (the directory of the validated
    `idp.yaml`) and comparing the stored entry names, not by `Path.exists()`/`is_file()` (which would match
    `Makefile` itself on a case-insensitive filesystem). An entry is extra when its name is not exactly `Makefile` and
    its name compared case-insensitively (`str.casefold()`) equals `gnumakefile` or `makefile`. So `GNUmakefile`,
    `makefile`, and on any filesystem also `gnumakefile`, `MAKEFILE`, `MakeFile` are extra; `Makefile.bak`,
    `GNUmakefile.orig`, `common.mk` are not. The entry type does not matter (file, directory, symlink, dangling
    symlink). ASSUMPTION A1, see Q2.
  - Each extra entry gives one violation with `path` = the entry name as stored (e.g. `GNUmakefile`) and message
    `GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it`. Text output:
    `idp.yaml: GNUmakefile: GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it`.
    `--json`: `{"path": "GNUmakefile", "message": "..."}`. ASSUMPTION A2, see Q4.
  - Extra-file violations come first among the Make violations, sorted by entry name, followed by whatever the
    existing Makefile scan reports (read/confinement problems, or missing targets). They are reported even if the
    `Makefile` itself is otherwise valid (that is the AC) and also if it has other problems.
  - The check runs only when the Makefile check runs today (the YAML parsed into a mapping) and only when `Makefile`
    is present (`(dir / "Makefile").is_file()`). With no `Makefile`, the result stays the single IDP-17 AC-6 violation
    `Makefile not found`. ASSUMPTION A3, see Q3.
  - If the service directory cannot be listed (`OSError`), the check fails closed with one violation
    `Makefile: cannot list the service directory` (in place of the extra-file violations).
  - Exit code 1 comes from the existing rule (any violation -> 1); no CLI change.
  - Verified with `tmp_path` unit tests in `test_contract.py` and end to end with the negative conformance fixture
    `tests/conformance/fixtures/gnumakefile-bypass/` (valid `idp.yaml`, valid `Makefile` whose `verify` fails, and a
    `GNUmakefile` whose `verify` is `@true`): `idp conformance` reports it `FAIL ... idp validate: 1 violation(s)`
    naming `GNUmakefile` instead of `PASS`.
- **AC-2** Given `idp conformance` runs `make verify` for an example, then make is invoked with `-f Makefile`, so only the validated file is read.
  - argv becomes `[make, "--no-print-directory", "-C", <dir>, "-f", "Makefile", "verify", "IDP_PROFILE_DIR=<dir>"]`.
    `-f Makefile` is relative: GNU make processes `-C` before reading makefiles, so it names `<dir>/Makefile`, the
    file `idp validate` checked (`contract.MAKE_PATH`).
  - Everything else in `_run_make_verify` is unchanged: list-form argv, no shell, stripped make variables
    (`MAKEFLAGS`, `GNUMAKEFLAGS`, `MAKELEVEL`, `MFLAGS`, `MAKEFILES`), `Popen(start_new_session=True)`,
    `communicate(timeout=MAKE_TIMEOUT_S)` and `os.killpg(proc.pid, SIGKILL)` on timeout.
  - "Only the validated file is read" refers to the top-level makefile choice. Files the `Makefile` itself `include`s
    are read by make as before (make include-following is out of scope; `idp validate` already confines and scans
    literal includes).
  - Verified by an argv test (fake `Popen`, no make) and by a real-make test calling `_run_make_verify` on a
    directory whose `Makefile` `verify` exits 3 and whose `GNUmakefile` `verify` is `@true`: the result is
    `FAIL ...: make verify exited 2` (make never reads the `GNUmakefile`).
  - The IDP-19 test `test_conformance_reports_make_timeout` asserts the old argv slice; it is updated to the new argv
    (same intent, stronger assertion). ASSUMPTION A4, see Q7.
- **AC-3** (edge) Given `examples/<x>` is a symlink, or an `examples/<x>` whose resolved path is outside DIR, when I run `idp conformance`, then that entry is reported `FAIL <x>: outside examples directory` and make is not run for it.
  - The ticket writes the edge marker after the bold id; it stays outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged.
  - `<x>` is shown the same way as on every other result line: the example path as built from DIR, e.g.
    `FAIL examples/linked: outside examples directory` (no detail lines). The reason text is literally
    `outside examples directory` whatever DIR is called. ASSUMPTION A5, see Q1.
  - Which entries: discovery (`find_examples`) is unchanged, so the check applies to every entry that is listed as an
    example today (non-dot, a directory after following links, containing `idp.yaml`). For each, before anything
    else: if `entry.is_symlink()`, or `entry.resolve(strict=True)` is not inside `DIR.resolve(strict=True)`, or
    resolving raises `OSError`/`RuntimeError`, the result is `FAIL <x>: outside examples directory`. A symlink is
    reported even when its target is inside DIR (for example `examples/alias -> minimal-service`). ASSUMPTION A6,
    see Q5 and Q6.
  - For such an entry neither `idp validate` nor profile resolution nor make runs: `idp.yaml` behind the link is not
    read. It counts as failed in the summary and makes the exit code 1.
  - DIR itself may be a symlink (for example `examples -> ../shared/examples`): entries are compared with the
    resolved DIR, so real subdirectories still pass.
  - The non-symlink "resolved outside DIR" branch is defence in depth (for example a mount point or an entry replaced
    between listing and checking); it is tested by monkeypatching the resolution of one entry.
  - Hardening (amendment): that test also covers resolution raising `OSError` (for example `FileNotFoundError`,
    an entry removed between listing and checking), next to the existing "resolves elsewhere" and `RuntimeError`
    cases.
- **AC-4** Given a valid example, then `idp.yaml` is parsed once and the same document is validated and used for profile resolution (no private `contract._load_yaml` call from `conformance.py`).
  - New public `contract.load_service(path) -> tuple[Any, list[Violation]]`: parses `idp.yaml` once and returns the
    parsed document together with the same violations `validate_service(path)` returns today (schema, then Make
    contract, including AC-1). `validate_service(path)` becomes `load_service(path)[1]`, so `idp validate` output is
    unchanged. ASSUMPTION A7, see Q8.
  - `conformance.check_example` calls `contract.load_service(path)` once; if there are violations it fails as today,
    otherwise it resolves `doc["spec"]["build"]["profile"]` from that same document.
  - "No private call": `conformance.py` contains no attribute access to a `contract` member whose name starts with
    `_` (checked with `ast` on the module source).
  - Verified by a test that wraps `contract._load_yaml` to count parses of `idp.yaml` (exactly 1 for a valid example)
    and records the profile name passed to `profiles.resolve` (equal to the one in the parsed document), with
    `_run_make_verify` stubbed (no make needed), plus the `ast` test.
  - Hardening (amendment): the `ast` test also fails on `from idp_gate.contract import _x` and
    `from .contract import _x` (any imported name starting with `_` from the contract module).
- **AC-5** Given an example whose `Makefile`, or a file it names in a literal `include`/`-include`/`sinclude` word, has a rule that would remake that makefile (for example `Makefile: evil.txt ; cp evil.txt Makefile`, or `-include gen.mk` with a rule that generates `gen.mk`), when `idp conformance` runs `make verify`, then make is invoked with assume-old (`-o`) for `Makefile` and for every literal include word the validation scan saw, so make neither remakes those files nor restarts with unvalidated content, and the validated `verify` recipe runs.
  - Added by the amendment (review M1). Builds on AC-2 (`-f Makefile` stays).
  - Option form: `--assume-old=<word>` (the long form of `-o`, same GNU make semantics, supported by 3.81 and 4.x).
    The `=` form keeps a word that starts with `-` from being read as another option. One option per name, placed
    after `-f Makefile` and before the target `verify` (no reliance on argument permutation). ASSUMPTION A9, Q12.
  - Names passed: `Makefile` first, then every distinct literal include word in the order the scan first saw it,
    exactly as written in the include line (make names an included makefile's target by the word as written,
    relative to the `-C` directory). A word written with leading `./` is passed both as written and with the leading
    `./` segments removed, in case make strips them when it enters the file. ASSUMPTION A10, Q15.
  - "Every literal include word the scan saw" includes words for files that do not exist at validation time: a
    missing `-include gen.mk` with a rule that creates it is the generated-include attack. Words the scan rejects
    (absolute, `..`, NUL, outside the service directory) already make `idp validate` fail, so make never runs for
    them. ASSUMPTION A11, Q13.
  - Source of the words: `contract.MakefileScan` gains `include_words: tuple[str, ...]` (default `()`), filled by
    `_Scanner.queue` with each distinct word as written. `idp.yaml` is still parsed once (AC-4 holds): after
    `load_service` reports no violations, `check_example` obtains the words from one more
    `contract.makefile_targets(directory / "Makefile")` scan of the Makefile only. If that scan reports violations
    (the files changed between the two scans), the example fails `idp validate: <n> violation(s)` with those
    violations and make does not run. ASSUMPTION A12, Q11.
  - Bounded argv: the scan records at most `MAX_INCLUDE_WORDS` (1024) distinct spellings (exceeding it stops the
    scan with the existing `too many include words (limit 1024)` violation, so validation fails). In addition,
    conformance caps the total size of the `--assume-old=` arguments at `MAX_ASSUME_OLD_BYTES` = 64 KiB (well under
    Linux `MAX_ARG_STRLEN` 128 KiB per argument and macOS/Linux `ARG_MAX`); above it the example fails
    `FAIL <x>: include words exceed the make argument limit` and make does not run. ASSUMPTION A13, Q14.
  - Not covered (residual risk): includes whose words contain `$`, globs or come from `$(eval ...)`/`define`
    bodies are not scanned (IDP-17), so they are not pinned; for example `examples/minimal-service`'s
    `include $(IDP_PROFILE_DIR)/defaults.mk`. A rule targeting `$(IDP_PROFILE_DIR)/defaults.mk` could still remake
    it. Changing include-following is out of scope per the ticket; see Q16.
  - Assume-old semantics (to be confirmed by the real-make tests on GNU Make 3.81 locally and 4.x in CI): an
    existing named file is not remade even if its prerequisites are newer; a missing named file is treated as
    up to date, so no rule creates it (`-include` then skips it; plain `include` makes make fail). ASSUMPTION A14.
  - Verified by: scanner unit tests (`include_words` order, dedup by exact spelling, missing files included,
    `$`/glob words excluded, the cap); an argv test with a fake `Popen`; the argument-limit test; and real-make tests
    (`needs_make`) run through `idp conformance` for (1) a self-remaking `Makefile` (an `evil.txt` newer than
    `Makefile`), (2) a missing `-include gen.mk` generated by a rule, (3) an existing `include common.mk` that a rule
    regenerates from a newer source, and (4) the `./gen.mk` spelling. Each must print `PASS`, leave a marker written
    by the validated `verify` recipe, leave no marker from the injected content, and leave `Makefile`/the include
    byte-for-byte unchanged (or still absent).
  - Amendment 2: include words written with a backslash (escape or continuation) could make the pinned word differ
    from the one make uses (review MJ1, MJ2); AC-7 rejects such lines during validation. The residual risk covers
    every include word containing `$`, not only the profile include (D5).
- **AC-6** (edge) Given an `idp.yaml` that cannot be read or is not valid UTF-8, when I run `idp validate` or `idp conformance`, then it is reported as a violation (`idp validate` exits 1; `idp conformance` prints a FAIL line for that example) instead of a traceback, and conformance continues with the remaining examples.
  - Added by the amendment (review M3, pre-existing since IDP-17).
  - `contract.load_service` catches `OSError` and `UnicodeDecodeError` around its `_load_yaml` call and returns
    `(None, [Violation("", message)])`; Make checks are skipped (as for invalid YAML). Messages
    (ASSUMPTION A15, Q17):
    - `OSError`: `cannot read: <strerror>` (for example `cannot read: Permission denied`; falls back to `str(exc)`
      when `strerror` is None).
    - `UnicodeDecodeError`: `cannot read: not valid UTF-8 (<reason> at byte <start>)` (for example
      `cannot read: not valid UTF-8 (invalid start byte at byte 6)`).
    Text output: `idp.yaml: <root>: cannot read: Permission denied`; `--json`: `{"path": "", "message": ...}`.
  - `_load_yaml` keeps raising: `profiles.load` depends on catching the exceptions itself and its messages
    (`cannot read '<name>': ...`, IDP-18 AC-5) stay unchanged; `test_profiles.py` stays green unchanged.
  - `idp validate`: the existing "not found" path is unchanged (`validate: <path> not found`, exit 2, when
    `is_file()` is false); everything that passes that check but cannot be read is now exit 1 with the violation.
  - `idp conformance`: the example fails `idp validate: 1 violation(s)` with the violation as detail line; the loop
    continues and the summary counts it as failed.
  - `contract.validate_file` (schema-only helper, not used by the CLI) is unchanged (Q18).
  - Verified by `tmp_path` tests: non-UTF-8 bytes in `idp.yaml` (real file) and an unreadable file (monkeypatched
    `contract._load_yaml` raising `PermissionError`, so the test does not depend on running as non-root), for
    `idp validate` (text and `--json`) and for `idp conformance` with a second, valid example that still PASSes.
  - Amendment 2 (clarification): an `idp.yaml` nested too deeply to parse (for example 100000 `[`) makes
    `yaml.safe_load` raise `RecursionError`. `load_service` catches it around the same `_load_yaml` call and returns
    `(None, [Violation("", "cannot parse: nesting too deep")])`, so `idp validate` prints
    `idp.yaml: <root>: cannot parse: nesting too deep` (exit 1) and conformance FAILs that example and continues.
    Only the parse is guarded; `validate_document` cannot see a deeper document than the parser produced (Q21).
    Verified by a `tmp_path` test for `idp validate` and a third case in the conformance "continues" test. The test
    must run in well under a second (no timing assertion; it stops at the recursion limit, not at the end of the
    input). ASSUMPTION A17.
  - Amendment 2 (hardening): the `idp validate` test gains an `OSError("boom")` case (`strerror` is None), expected
    `cannot read: boom`.
- **AC-7** (edge) Given a `Makefile`, or a file it includes, with an `include`/`-include`/`sinclude` line that contains a backslash (a line continuation such as `-include common.mk \` followed by `  gen.mk`, or an escape such as `-include gen\#.mk`), when I run `idp validate` or `idp conformance`, then validation reports a violation for that include line (`idp validate` exits 1; conformance prints `FAIL <x>: idp validate: ...`) and make is not run for that example.
  - Added by amendment 2 (review MJ1, MJ2). It closes the AC-5 bypasses by failing closed rather than modelling
    make's escape and continuation rules.
  - Which lines: every line of every scanned file (the `Makefile` and its followed literal includes), after comment
    stripping and `define` skipping (`_parsed_lines`), whose first whitespace-separated word is `include`,
    `-include` or `sinclude`, and which contains `\` anywhere. Examples: a trailing `\` (continuation), `\#`, `\ `
    (escaped space), `sub\x.mk`. Not flagged: an include line whose backslash is inside a stripped comment, and
    backslashes on non-include lines.
  - Violation: `path` `Makefile` (like the other scan problems), message
    `include line in '<file>' uses a backslash (continuation or escape); write each include word literally on one line`,
    where `<file>` is `Makefile` or the include word of the file containing the line (shown with `_shown`, so long
    words are truncated). Text output example:
    `idp.yaml: Makefile: include line in 'Makefile' uses a backslash (continuation or escape); write each include word literally on one line`.
    ASSUMPTION A16, Q19.
  - One violation per offending line, counted toward the existing `MAX_INCLUDE_PROBLEMS` (20) cap. The words of an
    offending line are not queued, so they are neither scanned nor recorded in `include_words` (validation fails
    anyway). Like the other scan problems, they replace the missing-target list (incomplete targets). Q20.
  - Why it is enough (to be kept in the docs): make honours an include directive only at the start of a logical
    line. If the line before an include line ends in `\`, make reads the include line as part of that line and does
    not include anything, while the scanner still pins and scans the words: over-pinning only. And a continued or
    escaped include line itself is now a violation, so no include word make sees can differ from the one pinned.
  - Verified by a `tmp_path` validate test (parametrized: continuation, `\#` escape, an escape inside an included
    file, and a negative case with a backslash only in a comment) and by a `needs_make` conformance test with the
    two reviewer reproductions (MJ1, MJ2): each prints `FAIL examples/<x>: idp validate: 1 violation(s)` with the
    detail line, exit 1, and the injected marker and generated file never appear (make not run).

## Edge cases and assumptions
- Case-insensitive filesystems (macOS APFS default): `Makefile` and `makefile` cannot both exist. A directory holding
  only `makefile` (stored lowercase) has `Path("Makefile").is_file()` true there, so validation reads it as
  `Makefile` and AC-1 reports `makefile` as extra (exit 1). On a case-sensitive filesystem (Linux CI) the same
  directory gives `Makefile not found` (exit 1). Both fail; the message differs. Accepted (see Q3).
- `Makefile` is a symlink to a `GNUmakefile` in the same directory: the `GNUmakefile` entry is still reported
  (fail closed; the contract file must be named `Makefile` and be the only candidate).
- An extra entry that is a directory or a dangling symlink is reported too (make would try to read it, or the next
  checkout may fill it).
- Many directory entries: the listing reads only names (`os.listdir`), O(n), no file is opened; no new cap.
- `idp validate path/to/service.yaml`: the directory listed is `path/to/` (same rule as the Makefile, IDP-17 A1).
- A symlinked `idp.yaml` or `Makefile` inside a real example directory is not an AC-3 case; `Makefile` confinement is
  already enforced by `idp validate` (`Makefile resolves outside the service directory`). A symlinked `idp.yaml` is
  out of scope here (see Out of scope).
- Symlinks in DIR that are not discovered as examples (dangling, pointing to a file, or to a directory without
  `idp.yaml`) stay ignored, as today (see Q5).
- TOCTOU: an entry swapped for a symlink after the check is not prevented (examples/ is platform-owned and reviewed
  like code; sandboxing is IDP-23).
- ASSUMPTION A1: case-insensitive matching of extra names on every platform (portable result; a repository checked
  out on macOS would otherwise be bypassable with `GNUMakefile`-style spellings).
- ASSUMPTION A2: violation `path` is the extra entry name; message as in AC-1.
- ASSUMPTION A3: extra-file check only when `Makefile` is present, keeping IDP-17 AC-6 and its two tests unchanged.
- ASSUMPTION A4: updating the IDP-19 timeout test's argv assertion in place is acceptable (its `IDP-19:AC-2` tag is
  kept; a separate new test carries `IDP-22:AC-2`).
- ASSUMPTION A5: `<x>` in AC-3 means the displayed example path (`examples/<x>` when DIR is `examples`).
- ASSUMPTION A6: every symlinked example entry fails, including links to another example inside DIR.
- ASSUMPTION A7: the new public API name is `contract.load_service`; `contract._load_yaml` stays (used by
  `profiles.py` and monkeypatched in `test_profiles.py`).
- ASSUMPTION A8: docs to update are `docs/platform/service-contract.md` (as the ticket says, at its real path) and one
  sentence in `docs/platform/onboarding.md` (conformance behaviour); CHANGELOG entry under `[Unreleased]` /
  `### Changed`.
- Amendment edge cases (AC-5, AC-6):
  - A Makefile with a rule for `Makefile` (or for an include) is still valid for `idp validate`; only the conformance
    run pins it (decision D3).
  - `include a.mk ./a.mk` (two spellings of one file): both spellings are passed (distinct written words); the
    scan still reads the file once (normpath dedup unchanged).
  - The same word in several files or lines is passed once.
  - A literal include word that names a directory or a file make cannot read: validation already reports it
    (`cannot read`), so make does not run.
  - Plain `include gen.mk` with a missing `gen.mk` and a generating rule: with assume-old, make does not create it and
    fails (`No such file or directory`), so the example FAILs with `make verify exited 2`. That is correct: the
    validated content alone cannot satisfy the include.
  - Recipes that call `$(MAKE) -f other.mk` or write files during `verify` are not prevented (sandboxing is IDP-23).
  - An `idp.yaml` that is a FIFO or device is not discovered (`is_file()` false) and is not opened.
- ASSUMPTION A9: `--assume-old=<word>` long form, before the target.
- ASSUMPTION A10: words passed exactly as written, plus the `./`-stripped variant when the word starts with `./`.
- ASSUMPTION A11: words for missing files are recorded and pinned.
- ASSUMPTION A12: conformance re-scans the Makefile (not `idp.yaml`) to obtain the words; `load_service` keeps its
  `(doc, violations)` return type.
- ASSUMPTION A13: 1024-spelling cap in the scanner plus a 64 KiB argument budget in conformance.
- ASSUMPTION A14: GNU make assume-old behaves as described for both existing and missing files (3.81 and 4.x);
  confirmed by the real-make tests.
- ASSUMPTION A15: AC-6 messages as written; the violation path is `""` (shown as `<root>`), like invalid YAML.
- Amendment 2 edge cases (AC-6, AC-7):
  - A non-include line ending in `\` followed by an include line (`FOO = a \` then `include gen.mk`): make does not
    include `gen.mk`; the scanner pins and scans it anyway (safe over-pinning, no violation).
  - An include line ending in a comment that ends in `\` (`include a.mk # note \`): the comment is stripped before
    the check, so there is no AC-7 violation. make continues the comment onto the next line, so a following
    `include gen.mk` is not included by make but is pinned and scanned (over-pinning). Its targets are over-credited:
    the pre-existing IDP-17 issue in D7.
  - Words containing `$` (including `$$`) stay unscanned and unpinned (mn1, D5); AC-7 does not change that.
  - `idp.yaml` nested just below the recursion limit parses normally and is validated as today.
- ASSUMPTION A16: AC-7 message text and `path` `Makefile`; the offending line's words are not queued.
- ASSUMPTION A17: `yaml.safe_load` raises `RecursionError` (not `yaml.YAMLError`) for `"[" * 100000` with the
  pure-Python loader, quickly; T12 checks this first and stops to revise the spec if it does not.

## Non-functional requirements
- No new dependencies: stdlib only (`os.listdir`, `pathlib`, `ast` in tests). `packages/idp-gate/pyproject.toml` and
  `uv.lock` unchanged.
- `examples/minimal-service` still passes: `test_platform_examples_pass_conformance_within_60_seconds` and
  `test_minimal_service_passes_idp_validate_and_make_verify` (IDP-19) stay green unchanged; `make verify` (which runs
  `make conformance`) is green locally and in CI.
- The conformance runner keeps `Popen(start_new_session=True)` + `os.killpg` on timeout; the IDP-19 timeout and
  child-kill tests stay green.
- `idp validate` output for services without extra makefiles is byte-for-byte unchanged (existing IDP-17 tests pass
  unchanged); the IDP-17 AC-6 tests pass unchanged.
- Tests are deterministic on case-sensitive (Linux CI) and case-insensitive (macOS) filesystems: tests that need two
  spellings of `makefile` detect the filesystem's case sensitivity in `tmp_path` and build the matching setup; no
  committed fixture contains two names that differ only in case.
- Protected paths unchanged: root `Makefile`, root `pyproject.toml`, `.github/**`, `.pre-commit-config.yaml`,
  `infra/**`, plugin hooks, `.claude-plugin/**`. No human task needed.
- Quality bars unchanged: mypy strict, ruff, bandit, coverage >= 85 %, diff-cover >= 80 %; `idp spec-trace IDP-22`
  green.
- Amendment: the make argv stays bounded: at most 1024 recorded include spellings (scanner cap) and at most 64 KiB of
  `--assume-old=` arguments (conformance cap). The extra Makefile scan in conformance reads at most the same capped
  bytes as validation (1 MiB per file, 64 files). `idp.yaml` is still parsed once per example.
- Amendment: `examples/minimal-service` still PASSes with the new argv (its only include is dynamic, so the argv
  gains just `--assume-old=Makefile`). The real-make tests run on GNU Make 3.81 (macOS) and 4.x (Linux CI).
- Amendment: no traceback escapes `idp validate`/`idp conformance` for an unreadable or undecodable `idp.yaml`.

## Out of scope
- Sandboxing make / an environment allow-list for `idp conformance` (IDP-23).
- Changes to make include-following (what `include` lines in `Makefile` pull in at run time).
- Symlinked `idp.yaml` inside a real example directory; `profiles.py`'s use of `contract._load_yaml`.
- Preventing TOCTOU swaps of example entries; Windows junctions.
- Detecting makefiles selected by `MAKEFILES` or `-f` in tenant CI (the runner already strips `MAKEFILES`).
- Amendment: pinning dynamic includes (`$(...)`, globs, `$(eval)`, `define` bodies), including the profile's
  `$(IDP_PROFILE_DIR)/defaults.mk` (residual risk, Q16); include files make finds through its default include
  directories (`/usr/include`, `-I`) rather than relative to the example; recursive `$(MAKE)` calls in recipes.
- Amendment: making `idp validate` reject rules that target `Makefile` or an include (decision D3).
- Amendment 2: modelling make's backslash escapes and continuations in the scanner (AC-7 rejects them instead);
  the review items not fixed in D5-D7.

## Decisions (review loop 1, 2026-10-10, by the human)
- D1: Not done: de-duplicating the `_case_sensitive` test helper that exists in both `test_contract.py` and
  `test_conformance.py` (cosmetic).
- D2: Not done: changing the front-matter `status`; repository convention keeps `DRAFT` (see IDP-25).
- D3: Not done: a scanner-level violation for rules whose target is `Makefile` or an include. A valid Makefile can
  already make `verify` a no-op, so `idp validate` is not a security boundary for tenant content; the conformance
  assume-old pinning (AC-5) is the guarantee that the validated file is what runs.

## Decisions (review loop 2, 2026-10-10, by the human)
- D4: The IDP-17 include-word cap test was aligned with the AC-5 spelling cap (3671157): 1025 spellings of
  1024 or fewer files now fail validation with `too many include words (limit 1024)`. Before, the cap counted only
  distinct normalised words.
- D5: Not fixed (mn1): any include word containing `$` is an unscanned, unpinned path that a rule could generate or
  remake, not only the profile's `$(IDP_PROFILE_DIR)/defaults.mk`. Reason: the ticket excludes include-following
  changes, and examples/ is platform-owned and reviewed. Follow-up next to IDP-23 (Q16). The residual-risk note in
  the docs covers every `$` include.
- D6: Not fixed (mn2): conformance's second Makefile scan is not compared with the validated one (only its own
  violations are checked). Reason: within the accepted TOCTOU window (examples/ is platform-owned; make reads the
  files later anyway). Follow-up: a single scan shared by validation and conformance.
- D7: Not fixed (pre-existing, IDP-17): a comment ending in `\` continues onto the next line in make, but the
  scanner treats that next line as code, so a target defined there is credited although make never sees it.
  Reason: make then fails at run time (`No rule to make target`), so this does not hide a failing `verify`.
  Follow-up ticket.

## Open questions
- Q1: AC-3 says `FAIL <x>: outside examples directory`. Every other result line shows the path built from DIR
  (`FAIL examples/bad: ...`). Proposed: same display, so the line is `FAIL examples/<x>: outside examples directory`
  (A5). Alternative: bare entry name `FAIL <x>: ...`, which would be the only line formatted that way.
- Q2: Match extra names case-insensitively on all platforms (`gnumakefile`, `MAKEFILE`, `MakeFile` are also flagged,
  even on Linux where GNU make would not read them)? Proposed: yes; the same tree gives the same result on macOS and
  Linux, and false positives are trivially fixed by renaming (A1). Alternative: exact names `GNUmakefile` and
  `makefile` only, which leaves `GNUMakefile` (read by make on macOS) undetected.
- Q3: Should extra files also be reported when there is no `Makefile`? Proposed: no; keep IDP-17 AC-6 ("single
  violation `Makefile not found`") and its tests unchanged (A3). Consequence: on macOS a lone `makefile` is reported
  as extra, on Linux as `Makefile not found`; both exit 1.
- Q4: Violation format. Proposed: `path` = extra entry name, message `GNU make reads this file before Makefile, but
  only Makefile is validated; remove or rename it` (A2). Alternative: `path` = `Makefile` with the name in the
  message, matching "Make violations use `Makefile`" in today's doc.
- Q5: Symlinks in DIR that today are not discovered (dangling, to a file, to a directory without `idp.yaml`): keep
  ignoring them? Proposed: yes, discovery unchanged; AC-3 applies to entries that would be run. Alternative: report
  every non-dot symlink in DIR as `outside examples directory`.
- Q6: A symlink whose target is another directory inside DIR (alias of a real example): FAIL too? Proposed: yes, the
  AC says "is a symlink" (A6); it also avoids running the same example twice.
- Q7: The IDP-19 test `test_conformance_reports_make_timeout` must change its `argv[1:5]` / `argv[5]` assertions to
  the new argv. Proposed: update it in place (keep its `IDP-19:AC-2` tag) and add a separate `IDP-22:AC-2` argv test
  (A4).
- Q8: Public API name for "parse once, return doc and violations". Proposed: `contract.load_service(path)`, with
  `validate_service` delegating to it (A7). Alternative: make `_load_yaml` public and add
  `validate_service_document(doc, directory)`.
- Q9: Docs placement. The ticket names `service-contract.md` "under packages/idp-gate/", but it lives at
  `docs/platform/service-contract.md`. Proposed: edit that file, plus one sentence in `docs/platform/onboarding.md`
  for the conformance changes (`-f Makefile`, symlinked entries FAIL) (A8).
- Q10: Should `profiles.py`'s own `contract._load_yaml` call move to the new public API in this ticket? Proposed: no
  (not in the AC, and `test_profiles.py` monkeypatches `_load_yaml`); a follow-up if wanted.
- Q11 (amendment): How does conformance get the include words without re-parsing `idp.yaml`? Proposed: after
  `load_service` passes, one more `contract.makefile_targets(directory / "Makefile")` scan (Makefile and includes
  only, same caps); a violation in that scan fails the example as `idp validate`. `load_service` keeps returning
  `(doc, violations)` (A12). Alternative: `load_service` returns a small result object carrying the scan, which
  changes its return type and the conformance unpacking.
- Q12 (amendment): `--assume-old=<word>` (long form) instead of `-o <word>`? Proposed: yes; same semantics, and a
  word starting with `-` cannot be read as an option (A9).
- Q13 (amendment): Pin include words whose file does not exist at validation time? Proposed: yes; that is exactly
  the generated-include case (`-include gen.mk` plus a rule creating it) (A11).
- Q14 (amendment): Argument budget for the `--assume-old=` list: 64 KiB total, above it
  `FAIL <x>: include words exceed the make argument limit` without running make? Proposed: yes (A13). Alternative:
  a per-word length cap in the scanner reported by `idp validate`.
- Q15 (amendment): Also pass the `./`-stripped spelling of a word that starts with `./`? Proposed: yes, both
  spellings, because it is unconfirmed whether make keys the include target with or without the `./`; the real-make
  test for `./gen.mk` confirms that one of them is effective (A10).
- Q16 (amendment): Residual risk: dynamic includes are not pinned, notably `$(IDP_PROFILE_DIR)/defaults.mk`, which
  conformance could pin as `--assume-old=<profile_dir>/defaults.mk` because it knows `profile_dir`. Proposed: not in
  this PR (the ticket excludes include-following changes, and the name would depend on how the example spells its
  include); record in the docs and file a follow-up next to IDP-23.
- Q17 (amendment): AC-6 message text: `cannot read: <strerror>` and
  `cannot read: not valid UTF-8 (<reason> at byte <start>)`, path `""` (shown `<root>`)? Proposed: yes (A15).
  Alternative: path `idp.yaml`.
- Q18 (amendment): Should the schema-only `contract.validate_file` also turn read errors into violations? Proposed:
  no; the CLI does not use it, and AC-6 names `idp validate`/`idp conformance` only.
- Q19 (amendment 2): AC-7 message text
  `include line in '<file>' uses a backslash (continuation or escape); write each include word literally on one line`
  with `path` `Makefile`? Proposed: yes (A16). It avoids putting a literal `\` in the message, which `--json` would
  show doubled.
- Q20 (amendment 2): Leave the words of an offending include line unqueued, so they are not scanned or pinned?
  Proposed: yes; validation fails anyway, and the words may not be what make sees.
- Q21 (amendment 2): Guard only the YAML parse against `RecursionError`, not `validate_document`? Proposed: yes;
  the composer's recursion limit bounds the depth of any document that reaches validation, and the schema does not
  descend into free-form content. If T12 shows otherwise, extend the guard to validation with the same message.
- Q22 (amendment 2): Reject every backslash on an include line, including Windows-style `sub\x.mk`? Proposed: yes;
  make treats `\` specially in file names, and one simple rule is easier to document and trust.
- Q23 (amendment 2): Should the follow-ups for D5 (pin or forbid `$` includes), D6 (single shared scan) and D7
  (comment continuation) be filed as one ticket next to IDP-23 or as three? Proposed: one ticket "make
  include/continuation hardening", with three ACs.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_contract.py::test_extra_gnumakefile_or_makefile_beside_valid_makefile_is_a_violation, packages/idp-gate/tests/test_contract.py::test_extra_makefile_names_match_case_insensitively, packages/idp-gate/tests/test_contract.py::test_extra_makefile_names_are_compared_as_listed_on_every_filesystem, packages/idp-gate/tests/test_contract.py::test_extra_makefile_check_fails_closed_when_directory_cannot_be_listed, packages/idp-gate/tests/test_contract.py::test_extra_makefile_violation_in_json_output, tests/conformance/test_examples.py::test_conformance_fails_example_with_gnumakefile_bypass |
| AC-2 | packages/idp-gate/tests/test_conformance.py::test_make_verify_is_invoked_with_f_makefile, packages/idp-gate/tests/test_conformance.py::test_make_verify_ignores_gnumakefile_and_makefile |
| AC-3 | packages/idp-gate/tests/test_conformance.py::test_conformance_fails_symlinked_example_without_running_make, packages/idp-gate/tests/test_conformance.py::test_conformance_fails_example_resolving_outside_dir, packages/idp-gate/tests/test_conformance.py::test_conformance_accepts_real_examples_under_symlinked_dir |
| AC-4 | packages/idp-gate/tests/test_conformance.py::test_check_example_parses_idp_yaml_once_for_validation_and_profile, packages/idp-gate/tests/test_conformance.py::test_conformance_module_uses_no_private_contract_members |
| AC-5 | packages/idp-gate/tests/test_contract.py::test_makefile_scan_records_literal_include_words_as_written, packages/idp-gate/tests/test_contract.py::test_makefile_scan_caps_recorded_include_spellings, packages/idp-gate/tests/test_conformance.py::test_make_verify_pins_makefile_and_include_words_with_assume_old, packages/idp-gate/tests/test_conformance.py::test_conformance_fails_when_include_words_exceed_make_argument_limit, packages/idp-gate/tests/test_conformance.py::test_conformance_fails_when_makefile_changes_between_scans, packages/idp-gate/tests/test_conformance.py::test_make_cannot_remake_validated_makefiles |
| AC-6 | packages/idp-gate/tests/test_contract.py::test_unreadable_or_undecodable_idp_yaml_is_a_violation, packages/idp-gate/tests/test_contract.py::test_deeply_nested_idp_yaml_is_a_violation, packages/idp-gate/tests/test_conformance.py::test_conformance_reports_unreadable_idp_yaml_and_continues |
| AC-7 | packages/idp-gate/tests/test_contract.py::test_include_line_with_backslash_is_a_violation, packages/idp-gate/tests/test_conformance.py::test_conformance_rejects_backslash_include_lines_without_running_make |
