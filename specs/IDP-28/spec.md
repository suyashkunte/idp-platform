---
ticket: IDP-28
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: medium
mode: guided
---

# IDP-28: idp validate/conformance: read Makefiles in make's logical lines, pin profile includes, scan once

## Context
Follow-up to IDP-22 (merged in bc36f6f). One security MAJOR and three minor review items stayed open:
- The MAJOR: `contract._parsed_lines` splits with `str.splitlines()` and does not join backslash-newline continuations
  before it tracks `define`/`endef`. Given `X = \` followed by `define Y`, make reads `X = define Y`, but the scanner
  opens a define block there and treats everything after it as define body. As a result, a later `-include gen.mk` and
  the rule that generates it are neither scanned nor pinned. The same happens with separators that Python splits on
  but make does not (`\x0b`, `\x0c`, `\x1c`-`\x1e`, `\x85`, lone `\r`, U+2028, U+2029). Reproduced on GNU Make 3.81.
- D5: include words containing `$` (e.g. `$(IDP_PROFILE_DIR)/defaults.mk`) are neither scanned nor pinned.
- D6: conformance scans the Makefile a second time and pins from that scan. That scan is never compared with the
  validated one.
- D7: a comment ending in `\` continues onto the next line in make. The scanner credits targets on that line, but make
  never defines them.
Labels: repo:idp-platform, component:pipeline, layer:test. Depends on IDP-22 (done).

Facts checked in the repository (2026-10-10, branch `feature/IDP-28-makefile-logical-lines`, at bc36f6f):
- `packages/idp-gate/src/idp_gate/contract.py`:
  - `_parsed_lines(text)` iterates `text.splitlines()`. It strips comments at the first `#` not preceded by `\`
    (`_COMMENT`) and then tracks define depth with `_DEFINE_START` / `_DEFINE_END`. In that check, tab-prefixed lines
    never open a block at depth 0, but at depth > 0 any line matching `^\s*(override|export|private)* define` nests.
  - `_load_makefile` decodes the file (UTF-8, at most 1 MiB) and returns `_parsed_lines(text)`. Nothing checks for
    line separators.
  - `_Scanner.visit` reports an include line that contains a backslash (IDP-22 AC-7) and does not queue its words.
    `_include_words` drops every word that contains `$`, `*`, `?` or `[`, so such words are never recorded.
  - `MakefileScan` has `targets`, `violations` and `include_words` (distinct literal spellings, capped at
    `MAX_INCLUDE_WORDS` = 1024 spellings).
  - `check_make_contract(doc, makefile)` calls `makefile_targets` and discards the scan after taking targets and
    violations from it. `load_service(path) -> (doc, violations)`, and `validate_service` returns `load_service(path)[1]`.
- `packages/idp-gate/src/idp_gate/conformance.py` `check_example`: `_outside`, then `contract.load_service`, then
  `profiles.resolve(...)["dir"]` (an absolute path), then a second `contract.makefile_targets(directory / "Makefile")`
  ("files may have changed"). Violations from that second scan fail the example. It then calls `_assume_old(scan.include_words)`
  and `_run_make_verify(..., f"IDP_PROFILE_DIR={profile_dir}")`, a command-line variable, so it overrides every
  Makefile assignment except `override`.
- Tests that encode today's behaviour:
  - `test_conformance.py::test_conformance_fails_when_makefile_changes_between_scans` (IDP-22 AC-5) asserts
    `len(scans) == 2`. AC-5 here makes that impossible (see Q14).
  - `test_contract.py::test_makefile_scan_records_literal_include_words_as_written` asserts that `$(V)/d.mk` and `*.mk`
    are not in `include_words`.
  - `test_contract.py::test_include_line_with_backslash_is_a_violation` (IDP-22 AC-7) has a `continuation` case and a
    `comment-only` case (`include common.mk # see notes \` as the last line, accepted).
  - The real-make tests use `os.utime` with fixed `OLD_MTIME`/`NEW_MTIME` (no sleeps) and the `GENERATE_EVIL` and
    `_append_to_makefile` helpers.
- Physical lines ending in `\` today: only recipe lines in the root `Makefile` (lines 27, 32, 39, 41, 43), each followed by
  another tab-indented recipe line. None in `build-profiles/**/*.mk`, `examples/minimal-service/Makefile` or
  `tests/conformance/fixtures/**`. So `test_root_make_verify_runs_conformance` (IDP-19) and
  `test_default_targets_have_recipes_in_defaults_mk` (IDP-18) keep their scan results.
- `examples/minimal-service/Makefile` has one include, `include $(IDP_PROFILE_DIR)/defaults.mk`, and
  `IDP_PROFILE_DIR ?= ../../build-profiles/python-uv` (no `override`).
- Docs: `docs/platform/service-contract.md` ("How `idp validate` checks it": the limitations sentence on continuations
  and the D7 comment sentence, the AC-7 "why it is enough" text) and `docs/platform/onboarding.md` ("Reference example":
  "scans the Makefile again", the residual-risk sentence on `$` includes). The `conformance.py` module docstring also
  states the residual risk. `CHANGELOG.md` has `[Unreleased]` / `### Changed` with the IDP-22 entry.

## Requirements
- **AC-1** Given an example whose `Makefile` has `X = \` followed by `define Y`, a `-include gen.mk` line, a rule that generates `gen.mk`, and a later `define Z`/`endef` pair, when I run `idp conformance`, then `gen.mk` is recorded in the scan's include words and pinned with `--assume-old`, make does not create `gen.mk`, and the validated `verify` recipe runs.
  - Logical lines (shared with AC-2 and AC-3; ASSUMPTION A1, Q1, Q2). The scanner reads every scanned file the way GNU
    make's reader does:
    - Split the text on `\n` only, and drop one trailing `\r` from each physical line (CRLF).
    - A physical line that ends in an odd number of backslashes continues onto the next physical line. An even number
      (`\\`) is a literal backslash, not a continuation. The joined text is one logical line.
    - Joining happens before anything else, so it applies to every kind of line: variable assignments, rule lines,
      recipe (tab) lines, comment lines, `define` bodies and `endef` lines.
    - Then, per logical line: comment stripping (unchanged rule: first `#` not preceded by `\`), define/endef tracking
      (unchanged regexes, matched at the start of the logical line), rule names, include words.
  - In the logical line, each continuation stays as written (`\` followed by `\n`). For rule names, `\`+`\n` is read
    as one space before the names are split (make collapses a backslash-newline outside recipes to a single space).
    So `verify: \` followed by `  lint` credits `verify`, and `lint \` followed by `verify:` credits both. The IDP-22
    AC-7 check (`"\\" in line` on include lines) still sees the backslash. So a continued include line is still a
    violation (Q3).
  - With this rule, `X = \` + `define Y` is the logical line `X = \` `define Y`. It does not start with `define`, so
    no block opens. `-include gen.mk` is a logical line of its own, so `gen.mk` is in `MakefileScan.include_words`.
    The `gen.mk:` rule is visible, and `define Z`/`endef` open and close one block.
  - Conformance passes `--assume-old=gen.mk` (existing IDP-22 AC-5 mechanism). make does not create `gen.mk`. The
    recipe of the validated `verify` runs (it writes a marker), and the injected content does not run.
  - Verified by:
    - logical-line unit tests: continuation, even backslashes, CRLF continuation, a continuation at EOF, a recipe
      continuation, a continuation inside a define body before `endef`;
    - a scanner unit test for the exact AC-1 layout (`include_words` contains `gen.mk`, and the targets after
      `define Z`/`endef` are found);
    - a real-make (`needs_make`) conformance test with that layout. It prints `PASS`, the `validated-ran` marker
      exists, and `evil-ran` and `gen.mk` are absent. It must be red before the fix: the scanner hides the include, make
      generates `gen.mk` and restarts.
- **AC-2** (edge) Given a `Makefile` or scanned include that contains a line separator make does not use (`\r` not followed by `\n`, `\x0b`, `\x0c`, `\x1c`–`\x1e`, `\x85`, U+2028, U+2029), when I run `idp validate`, then it exits 1 with a violation naming that file, and a file with CRLF line endings is still accepted.
  - The ticket writes the edge marker after the bold id. It stays outside the bold so `idp spec-trace` parses it.
    Meaning unchanged.
  - Checked in `_load_makefile` after UTF-8 decoding and before parsing, with one linear regex search for
    `\r(?!\n)|[\x0b\x0c\x1c-\x1e\x85  ]`. `\x85` means the code point U+0085, encoded in UTF-8 as
    `C2 85`. A raw `0x85` byte is not valid UTF-8 and is already `cannot read '<name>'`.
  - Violation (ASSUMPTION A2, Q4): `path` `Makefile` (like every scan problem), message
    `<file> contains a line separator make does not use (<what>); use LF or CRLF line endings`.
    - `<file>` is `'Makefile'` or the include word of the scanned file, shown with the existing `_shown` (repr,
      truncated at 200 characters).
    - `<what>` is `U+000B`-style for the first offending character, or `CR not followed by LF`.
    - Example: `idp.yaml: Makefile: 'common.mk' contains a line separator make does not use (U+0085); use LF or CRLF line endings`.
  - Like the other per-file problems (`cannot read`, `exceeds 1 MiB`), the file is not parsed: its targets and
    include words are not collected. The violation counts toward `MAX_INCLUDE_PROBLEMS` (20) and replaces the
    missing-target list. Other queued files are still scanned (Q5).
  - `idp conformance` reports such an example as `FAIL <x>: idp validate: 1 violation(s)` with the detail line, and
    make is not run.
  - CRLF: a file whose lines all end in `\r\n` is accepted. It gives the same targets, include words and continuations
    as the LF version (`\r` is dropped before the trailing backslashes are counted, so `X = \` + CRLF continues).
    Mixed LF and CRLF lines are accepted too.
  - Verified by:
    - a `tmp_path` validate test parametrized over every listed separator: in the `Makefile` for each of them, and
      in an included file for at least one;
    - a CRLF test (exit 0 and `valid`; continuation over CRLF joined);
    - a real-make conformance test for `\x0b` and `\x85`. In each, the separator sits between `X = 1` and `define Y`,
      followed by the AC-1 gen.mk attack, with explicit `os.utime` and no sleeps. Expected: FAIL with the detail line,
      exit 1, and no `evil-ran`, `validated-ran` or `gen.mk`. It must be red before the fix: the example PASSes but
      `evil-ran` appears.
- **AC-3** Given a `Makefile` where a comment line ends in `\` and the next line defines `verify:`, when I run `idp validate`, then `verify` is not credited and the output reports `missing required target 'verify'`.
  - Follows from the AC-1 logical-line rule: `# note \` + `verify:` is one logical line, and the whole line is a
    comment. Same for a trailing comment on a code line (`lint: # note \` + `verify:`) and for a comment inside a
    `define` body.
  - Output: exactly `idp.yaml: Makefile: missing required target 'verify'` (all other required targets defined
    normally), exit 1. `--json` gives the same message with `path` `Makefile`.
  - The IDP-22 AC-7 `comment-only` case (`include common.mk # see notes \` as the last line) stays valid.
  - Verified by a `tmp_path` validate test (text and `--json`) and a scanner unit test for the trailing-comment form.
- **AC-4** (edge) Given an example whose Makefile has an include word containing `$` that does not start with exactly `$(IDP_PROFILE_DIR)/`, when I run `idp conformance`, then that example is reported `FAIL <x>: dynamic include '<word>' cannot be pinned` and make is not run. A word starting with `$(IDP_PROFILE_DIR)/` is pinned as `--assume-old=<resolved profile dir>/<rest>`, and `examples/minimal-service` still passes.
  - Scanner (ASSUMPTION A3, Q8): `MakefileScan` gains `dynamic_include_words: tuple[str, ...] = ()`. It holds each
    distinct include word that contains `$`, as written, in first-seen order, from every scanned file (the
    `Makefile` and its followed literal includes).
    - These words are still not followed or read. Words with glob characters but no `$` are skipped as today (Q11).
    - Dynamic and literal spellings share the existing 1024-spelling cap (`too many include words (limit 1024)`), so
      the cap value and message do not change (Q12).
    - Words on include lines that IDP-22 AC-7 rejects (backslash) are not recorded.
  - `idp validate` does not change for `$` words: they are still skipped, with no violation (Q9). AC-4 applies to
    `idp conformance` only.
  - Conformance classifies each dynamic word after the profile has resolved (it needs the profile dir), in first-seen
    order:
    - Pinnable: the word starts with exactly `$(IDP_PROFILE_DIR)/` and the remainder `<rest>` is non-empty and contains
      none of `$`, `*`, `?`, `[`. The pinned name is `<profile_dir>/<rest>`, where `<profile_dir>` is
      `profiles.resolve(...)["dir"]`: the same string passed as `IDP_PROFILE_DIR=<profile_dir>` to make (Q6, Q7).
    - Everything else cannot be pinned, including `${IDP_PROFILE_DIR}/x.mk`, `$(IDP_PROFILE_DIR)x.mk`,
      `$(OTHER)/x.mk`, `a$$b.mk` (Q10), `$(IDP_PROFILE_DIR)/$(X).mk`, `$(IDP_PROFILE_DIR)/*.mk` and
      `$(IDP_PROFILE_DIR)/`. The last three start with the prefix but have a `<rest>` that make would expand or glob,
      or an empty `<rest>`, so the AC's literal pin would not match what make includes (fail closed; Q7).
  - For the first word that cannot be pinned, the example is `FAIL <x>: dynamic include '<word>' cannot be pinned`,
    with no detail lines (Q13).
    - `<word>` is shown as `repr(word)` truncated to `contract.MAX_SHOWN_WORD` characters plus `…`, the same format
      as validate messages, so a word containing `'` is shown in double quotes.
    - make is not run. The check comes before the argument budget.
  - Pinnable words are added to the `--assume-old=` list after the literal words: `Makefile`, the literal words (with
    their `./` variants), then the resolved profile words. Duplicates are removed and the list counts toward the
    existing 64 KiB budget.
  - `examples/minimal-service` PASSes with the extra `--assume-old=<profile_dir>/defaults.mk`
    (`test_platform_examples_pass_conformance_within_60_seconds` and the IDP-22 gnumakefile fixture test stay green).
  - Verified by:
    - a scanner unit test (`dynamic_include_words` order, dedup, cap sharing, `include_words` unchanged);
    - a fake-`Popen` argv test for the profile word;
    - a parametrized fake-`Popen` test for the rejected forms (exact FAIL line, `Popen` never called, the next
      example still runs);
    - a real-make test. `profiles.resolve` is monkeypatched to a `tmp_path` profile dir holding a benign
      `defaults.mk`. The Makefile has `include $(IDP_PROFILE_DIR)/defaults.mk` and a rule
      `$(IDP_PROFILE_DIR)/defaults.mk: $(IDP_PROFILE_DIR)/evil.src` with recipe `cp`, and `evil.src` is newer via
      `os.utime`. Expected: PASS, `validated-ran`, no `evil-ran`, `defaults.mk` byte-for-byte unchanged. It must be red
      before the fix. The platform's real profile directory is never a remake target in tests.
- **AC-5** Given a valid example, when I run `idp conformance`, then the Makefile is scanned exactly once, and the `--assume-old` words come from the same scan whose result was validated (no second `makefile_targets` call).
  - `contract.load_service(path)` returns `(doc, violations, scan)` (ASSUMPTION A4, Q14):
    - `scan` is the `MakefileScan` that `check_make_contract` used for the targets and violations.
    - When the Makefile was not scanned (invalid or non-mapping YAML, unreadable `idp.yaml`, `Makefile not found`),
      `scan` is an empty `MakefileScan(frozenset(), ())`. Then `violations` is non-empty, so conformance never uses it.
    - `check_make_contract(doc, makefile)` keeps its public signature and result. A private helper returns the
      violations together with the scan.
    - `validate_service(path)` returns `load_service(path)[1]`, so `idp validate` output does not change.
  - `conformance.check_example` unpacks the three values and takes `include_words` and `dynamic_include_words` from
    that `scan`. The second `contract.makefile_targets` call and its "files may have changed" failure path are
    removed.
  - "Scanned exactly once" means one `contract.makefile_targets` call per example. Included files are read within that
    call, once each, as today.
  - Verified by a test that wraps `contract.makefile_targets`. The wrapper counts calls and returns the real scan with
    one extra sentinel include word appended (`dataclasses.replace`). With a fake `Popen`, the expected result is
    exactly one call for the example and `--assume-old=<sentinel>` in the make argv. That shows the pinned words come
    from the validated scan.
  - The IDP-22 test `test_conformance_fails_when_makefile_changes_between_scans` asserts two scans. It is removed and
    replaced by this test (Q14).

## Edge cases and assumptions
- An even number of trailing backslashes (`a \\`) does not continue the line. In make it is a literal `\` (or `\\`)
  at the end of the line.
- A continuation on the last line of a file joins with nothing (no error). The text after the last `\n` is a line,
  as today.
- A recipe line ending in `\` swallows the next physical line, even if that line looks like `verify:`. make does the
  same (the line is part of the recipe), so the target is not credited.
- `X = a # c \` followed by `include gen.mk`: the comment swallows the include. make includes nothing, and the scanner
  now records nothing for it, where before it over-pinned.
- `FOO = a \` followed by `include gen.mk`: one logical line that is not an include line. make includes nothing, and
  the scanner now records nothing, where before it over-pinned (IDP-22 AC-7 rationale). The docs text changes from
  "over-pinning" to "exactly what make reads".
- A continued include line (`-include common.mk \` + `  gen.mk`) is still rejected by IDP-22 AC-7 (Q3). The
  `\#`/`\ ` escape cases are unchanged.
- Inside a `define` body, `foo \` followed by `endef` does not end the block (make's reader joins the lines first). The
  scanner matches this. ASSUMPTION A1 is confirmed by a real-make check in T1.
- `\\#` (escaped backslash, then `#`) is still read as "not a comment" by `_COMMENT`, although make treats the `#` as a
  comment start. This is pre-existing and only affects targets named with backslashes, never a required target name or
  an include word: a backslash on an include line is rejected. Not changed (out of scope).
- Mixed line endings (LF and CRLF) are accepted. `\r\r\n` is rejected (the first `\r` is not followed by `\n`).
- A file with a separator problem is not parsed, so its includes are not queued. Validation fails anyway.
- NUL bytes in a Makefile are not covered by AC-2 (see Q15).
- The profile directory path is absolute and contains no whitespace or `$` (it comes from the installed package or
  the checkout). If it did, the command-line `IDP_PROFILE_DIR=` value would already misbehave in make. Not handled
  (ASSUMPTION A5).
- `override IDP_PROFILE_DIR = ...` in the Makefile, or `$(eval ...)`, would make `$(IDP_PROFILE_DIR)` resolve to a
  path other than the pinned one (Q6). Remains a documented residual risk.
- Includes produced by `$(eval ...)`, or by include lines inside `define` bodies that are later evaluated, are still
  not scanned or pinned (residual risk; making the parser run make is out of scope).
- The scanner and make may disagree on `define` nesting inside a body (tab-prefixed `define`/`endef`, and
  `override define`/`export define` lines inside a body). This is a separate finding found while writing this spec
  (Q16). Not in the ACs.
- ASSUMPTION A1: GNU make 3.81 and 4.x join physical lines that end in an odd number of backslashes before
  classifying them (in comments, recipes and define bodies), drop `\r` before `\n`, and treat no other character
  as a line separator. Confirmed by the real-make tests (AC-1, AC-2) and a scratchpad check in T1 (comment and define
  body continuation). If make behaves differently, stop and revise the spec.
- ASSUMPTION A2: AC-2 violation text and `path` as above.
- ASSUMPTION A3: dynamic words go into a new `MakefileScan.dynamic_include_words` field, not into `include_words`
  (which stays "literal words", so the IDP-22 tests and the AC-1 wording hold).
- ASSUMPTION A4: changing `load_service`'s return to a 3-tuple is acceptable. Its only callers are `validate_service`
  and `conformance.check_example`; the `ast` test only parses a synthetic text that names it.
- ASSUMPTION A5: as in the profile-path edge case above.
- ASSUMPTION A6: `--assume-old=<profile_dir>/<rest>` stops make from remaking the included file, because make names
  that include target by the expanded word, the same string. Confirmed by the AC-4 real-make test.

## Non-functional requirements
- No new dependencies (stdlib `re` only). `packages/idp-gate/pyproject.toml` and `uv.lock` unchanged.
- Scanning stays linear in the input size:
  - the separator check is one regex search with no backtracking;
  - joining counts trailing backslashes with `rstrip` per physical line and joins each logical line once;
  - `test_long_lines_without_colon_are_parsed_in_linear_time` stays green, and a new case with 200 000 one-character
    continued lines finishes promptly (no timing assertion; quadratic joining would take minutes).
- Caps unchanged: `MAX_MAKEFILE_BYTES` (1 MiB), `MAX_MAKEFILES` (64), `MAX_INCLUDE_WORDS` (1024),
  `MAX_INCLUDE_PROBLEMS` (20), `MAX_SHOWN_WORD` (200), `MAX_ASSUME_OLD_BYTES` (64 KiB). Dynamic words count toward the
  existing spelling cap (Q12). The argv stays bounded by the 64 KiB budget.
- Real-make tests pass on GNU Make 3.81 (macOS, local) and 4.x (Linux CI), use explicit `os.utime` and never sleep.
- `examples/minimal-service` still passes `idp conformance` and the IDP-19 tests unchanged.
- `idp validate` output stays byte-for-byte unchanged for Makefiles with no continuation lines and no foreign separators
  (all existing IDP-17/IDP-22 validate tests pass unchanged).
- Quality bars unchanged: mypy strict, ruff, bandit, coverage >= 85 %, diff-cover >= 80 %, `idp test-quality-lint`
  on changed tests; `idp spec-trace IDP-28` green; `make verify` green.
- Protected paths unchanged: root `Makefile`, root `pyproject.toml`, `.github/**`, `.pre-commit-config.yaml`,
  `infra/**`, plugin hooks, `.claude-plugin/**`. No human task.

## Out of scope
- Replacing static parsing with `make -pn` in a sandbox (ADR candidate after IDP-23).
- An environment allow-list or sandboxing for `idp conformance` (IDP-23).
- Tenant CI running plain `make verify` without conformance (no pinning there).
- Scanning the profile's `defaults.mk` (platform-owned) or any other file named by a `$` word (Q9).
- Glob include words without `$` (unchanged: skipped, not pinned; Q11), `$(eval ...)`-generated includes, and
  `override IDP_PROFILE_DIR` (Q6): residual risks, documented.
- Changing IDP-22 AC-7 (backslash on include lines stays a violation; Q3).
- Aligning in-body `define` nesting with make (Q16), unless the human adds it by amendment.
- Editing `specs/IDP-22/*` (approved). The D5-D7 notes are resolved in the docs, not in that spec.

## Open questions
- Q1: Which backslash rule do we model? Proposed: GNU make's reader. An odd number of trailing backslashes joins the
  next physical line, in every context (comments, recipes, define bodies, `endef` lines), before comment stripping
  and directive recognition. An even number is literal. So a `\` at the end of a comment line continues the comment
  (AC-3), and a `\` at the end of a recipe line continues the recipe. Recipe lines differ from other lines only in what
  make does with the joined text (it keeps the backslash-newline for the shell), which the scanner never needs (A1).
- Q2: How should a continuation look in the logical line? Proposed: keep `\` + `\n` as written. Rule-name extraction
  reads each as one space, and the IDP-22 AC-7 include-line check still sees the backslash. Alternative: collapse to a
  space everywhere and flag continued lines separately (more state for the same result).
- Q3: Now that continuations are modelled, should a continued include line (`-include common.mk \` + `  gen.mk`) be
  accepted and both words pinned, instead of the IDP-22 AC-7 violation? Proposed: no, keep AC-7 unchanged (smallest
  change; its tests and docs stay; fail-closed). Revisit with the `make -pn` ADR.
- Q4: AC-2 violation text:
  `'<file>' contains a line separator make does not use (U+000B); use LF or CRLF line endings` (or
  `(CR not followed by LF)`), with `path` `Makefile`. Proposed: yes (A2). It names the file and the first offending
  character without echoing control characters. Alternative: add a line number (needs a newline count up to the
  match, still linear).
- Q5: How do violations surface for included files? Proposed: as every other per-file scan problem. `path` is
  `Makefile` and the message names the include word (`'common.mk' contains ...`). Validate prints
  `idp.yaml: Makefile: ...`. Conformance prints `FAIL <x>: idp validate: <n> violation(s)` with the indented detail.
  The file is not parsed, the problem counts toward the 20-problem cap, and other queued files are still scanned.
- Q6: How does `$(IDP_PROFILE_DIR)` resolve in conformance? Proposed: to `profiles.resolve(profile)["dir"]`, the
  string conformance passes as the command-line variable `IDP_PROFILE_DIR=<dir>`. A command-line variable overrides
  Makefile `=`, `:=`, `?=` and `+=` assignments and the environment, but not `override` or `$(eval ...)`. Proposed:
  treat `override IDP_PROFILE_DIR` as documented residual risk, like `$(eval)`. Alternative: the scanner flags any
  logical line that starts an `override` assignment of `IDP_PROFILE_DIR`, and conformance then treats profile words as
  unpinnable. That covers only the literal form.
- Q7: Should a word that starts with `$(IDP_PROFILE_DIR)/` but has a `<rest>` that make would expand or glob
  (`$(IDP_PROFILE_DIR)/$(X).mk`, `$(IDP_PROFILE_DIR)/*.mk`), or an empty `<rest>`, be pinned as the AC literally says?
  Proposed: no, FAIL `cannot be pinned`. Pinning the unexpanded text would not match what make includes, which is
  silently unpinned. This narrows the AC's second sentence to "`<rest>` is literal"; please confirm. `..` in `<rest>`
  is allowed (the pin is an exact string match).
- Q8: Should dynamic words be a new field `MakefileScan.dynamic_include_words`, or mixed into `include_words`?
  Proposed: a new field (A3). `include_words` keeps meaning "literal words". The IDP-22 scanner test, which asserts
  `$(V)/d.mk` is absent, stays green.
- Q9: Should `idp validate` also report dynamic includes, or scan the profile's `defaults.mk`? Proposed: no to both.
  AC-4 names conformance only. Tenant Makefiles legitimately include `$(IDP_PROFILE_DIR)/defaults.mk`, and validate is
  not the security boundary (IDP-22 D3). The profile is platform-owned.
- Q10: Does a doubled `$$` count as dynamic? Proposed: yes. Any word containing `$` (including `a$$b.mk`, which make
  reads as `a$b.mk`) and not starting with `$(IDP_PROFILE_DIR)/` fails conformance, as the AC says ("containing `$`").
  Alternative: unescape `$$` and pin the literal name (more parsing for no known use).
- Q11: Glob words without `$` (`include *.mk`) are still skipped and unpinned, a residual risk of the same kind.
  Should conformance also fail them (`dynamic include '*.mk' cannot be pinned`)? Proposed: not in this ticket (not in
  the ACs); keep them in the docs' residual-risk note and file a follow-up if wanted.
- Q12: Should dynamic words count toward the existing 1024-spelling cap? Proposed: yes. Memory and argv stay
  bounded, and the value and message do not change. Only a Makefile with more than 1024 distinct include spellings in
  total, literal plus dynamic, newly hits it (none exists in the repo).
- Q13: Several unpinnable words: name only the first (first-seen order) on the FAIL line, with no detail lines?
  Proposed: yes, matching the AC's single-word format. Alternative: list the rest as detail lines.
- Q14: How does conformance get the validated scan? Proposed: `load_service` returns `(doc, violations, scan)` (A4),
  with an empty scan when the Makefile was not scanned. The IDP-22 test
  `test_conformance_fails_when_makefile_changes_between_scans` checks the removed second scan, so it is deleted and
  replaced by the AC-5 test. IDP-22 AC-5 keeps its other five tests. Alternative: a new
  `contract.load_service_with_scan`, leaving `load_service` unchanged (two near-identical public functions).
- Q15: Should a NUL byte in a scanned Makefile also be rejected? GNU make 4.x warns "NUL character seen; rest of line
  ignored", so make and the scanner disagree about that line. Proposed: not in this ticket (not in AC-2's list);
  record as a follow-up next to Q16. Alternative: add `\x00` to the AC-2 character class with the same message
  (needs the human to extend AC-2).
- Q16 (new finding, outside the ACs): inside a `define` body, GNU make (3.81 and 4.x `do_define`) skips
  tab-prefixed lines when it looks for nested `define`/`endef`. It counts only a bare `define` word as nesting, not
  `override define` or `export define`. `_parsed_lines` nests on `^\s*(override|export|private)* define` and also
  matches tab-prefixed lines. Example: `define A`, `override define B`, `endef`. make closes `A` at that `endef`. The
  scanner stays at depth 1 and hides every later line, a define-tracking bypass like AC-1. Proposed: confirm with
  real make in T1, then file a follow-up ticket, or extend this ticket by amendment with a new AC if the human
  prefers. Not implemented without that decision.
- Q17: Docs and CHANGELOG. Proposed: update `docs/platform/service-contract.md` (logical lines, the separator
  violation, the removed D7 limitation, the AC-7 rationale text) and `docs/platform/onboarding.md` (single scan,
  profile-word pinning, `dynamic include ... cannot be pinned`, a residual-risk sentence narrowed to globs,
  `$(eval)`/`define`-body includes and `override IDP_PROFILE_DIR`). Add one IDP-28 line under `[Unreleased]` /
  `### Changed`, and update the `conformance.py` module docstring.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_contract.py::test_logical_lines_join_odd_trailing_backslashes, packages/idp-gate/tests/test_contract.py::test_continuation_into_define_does_not_hide_later_lines, packages/idp-gate/tests/test_conformance.py::test_continuation_cannot_hide_generated_include_from_pinning |
| AC-2 | packages/idp-gate/tests/test_contract.py::test_line_separator_make_does_not_use_is_a_violation, packages/idp-gate/tests/test_contract.py::test_crlf_makefile_is_accepted, packages/idp-gate/tests/test_conformance.py::test_conformance_rejects_foreign_line_separators_without_running_make |
| AC-3 | packages/idp-gate/tests/test_contract.py::test_comment_ending_in_backslash_continues_onto_next_line, packages/idp-gate/tests/test_contract.py::test_trailing_comment_ending_in_backslash_hides_next_line |
| AC-4 | packages/idp-gate/tests/test_contract.py::test_makefile_scan_records_dynamic_include_words, packages/idp-gate/tests/test_conformance.py::test_profile_dir_include_is_pinned_with_resolved_path, packages/idp-gate/tests/test_conformance.py::test_unpinnable_dynamic_include_fails_without_running_make, packages/idp-gate/tests/test_conformance.py::test_make_cannot_remake_profile_dir_include, tests/conformance/test_examples.py::test_platform_examples_pass_conformance_within_60_seconds |
| AC-5 | packages/idp-gate/tests/test_conformance.py::test_conformance_scans_makefile_once_and_pins_from_validated_scan |
