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

## Amendment 1 (2026-10-10, after review loop 1)
T1-T6 are implemented (265eefb, 3a68006, 31fea1b, 864e721, 1959fa4, 429b6a2); T7 (docs) is open. The review found
bypasses of the same kind as AC-1 (the scanner and make disagree about which lines are directives), all reproduced on
GNU Make 3.81. The human chose to fix all of them in this ticket (spec re-approval needed) and to move the minor
items listed under "Out of scope" to follow-ups:
- B1 (code review, regression from T1): continuations are joined, but `\` + newline stays in the logical line and
  only `_rule_names` collapses it. make collapses `[blanks]\` + newline + `[blanks]` into one space before it
  recognises directives (in `eval` and in `do_define`). So a line holding only `\` followed by `-include gen.mk`
  (top level), or `define Y` / `body` / `\` + `  endef` / `-include gen.mk` (also with CRLF), hides `gen.mk`:
  conformance PASSes and make generates it. Also `override \` + `define Y` is a define in make, but the scanner
  credits targets in its body. Added as AC-6, AC-7 and AC-8 (supersedes Q2).
- Security B1 (pre-existing, Q16): inside a define body the scanner strips comments before it looks for a nested
  `define`, so `define#` nests in the scanner but not in make. make's `do_define` counts nesting only for a bare
  `define` followed by a blank or the end of the line, without stripping comments, and skips tab-prefixed lines.
  Added as AC-9; AC-10 covers body lines make reads differently depending on the conditional branch (Q19).
- Security B2 / code review M1 (pre-existing): characters Python treats as whitespace but make does not (`\x1f`,
  U+00A0, U+1680, U+2000-U+200A, U+202F, U+205F, U+3000) change `str.split()`, `\s` and rule names. Repros:
  `-include a.mk\x1fb.mk` (the scanner pins `a.mk` and `b.mk`; make remakes and reads the single file
  `a.mk\x1fb.mk`), the same with U+00A0, `define\x1fX = 1` at top level, `define\x1fB` inside a body. Added as AC-11
  (fail closed, with the remaining C0 controls and NUL; supersedes Q15).
- Security M3: `private define X = 1` / `export define X = 1` are assignments on make 3.81 (no `private`, no
  `export define`) and defines on 4.x. The scanner opens a block and hides the rest. Added as AC-12 (fail closed, so
  the scanner never has to pick a make version).
- Security M4 (pre-existing): make expands a leading `~` in include words, so `-include ~/evil.mk` reads
  `$HOME/evil.mk`, which is never scanned. Added as AC-13.
- Security M5 (new path from T6): `$(IDP_PROFILE_DIR)/../<x>` or an absolute `<rest>` is pinned (not remade), but
  make still reads an unscanned file anywhere on disk. Added as AC-14 (supersedes Q7).
- Minors handled inside tasks (no AC): conformance `_shown` duplicates `contract._shown` (security m8); the
  `_FOREIGN_SEPARATOR` comment is stale (m2); the conformance call site does not say that an empty scan only comes
  with violations (m3).

Facts checked for amendment 1 (branch at 429b6a2):
- `contract._parsed_lines` strips comments from the raw logical line (still containing `\` + newline), then matches
  `_DEFINE_START` (`^\s*(?:(?:override|export|private)\s+)*define(?:\s|$)(?!...)`) and `_DEFINE_END`
  (`^\s*endef(?:\s|$)`) on it, at every depth. `_rule_names` does `line.replace("\\\n", " ")`. `_Scanner.visit`
  runs the IDP-22 AC-7 check (`"\\" in line`) and `_include_words`/`_dynamic_include_words` (`str.split()`) on the
  same comment-stripped raw line.
- `_FOREIGN_SEPARATOR` (`\r(?!\n)|[\x0b\x0c\x1c-\x1e\x85  ]`) is the only character check.
  `_locate` reports a NUL in an include word as `cannot read '<word>'`.
- `_lexically_outside(word, root)` rejects absolute words and `..` escapes; a leading `~` is treated as a relative
  directory name. `conformance._profile_names` accepts any `<rest>` without `$*?[`, including `..` segments and a
  leading `/`. `conformance._shown` copies `contract._shown`.
- In-repo makefiles (`Makefile`, `examples/**/Makefile`, `build-profiles/**/*.mk`, `tests/conformance/fixtures/**`):
  no `define`/`endef` at all, no character outside TAB, LF, CR and printable ASCII, no `~`, no line holding only `\`,
  no `.RECIPEPREFIX`. So the amendment changes no in-repo scan result and no repo makefile needs editing.
- Existing tests whose expectations change are listed under "Tests that change (amendment 1)".

### Amendment log
- Amendment 1 (2026-10-10, after review loop 1): AC-6..AC-14 added; Q2, Q7, Q15 and Q16 superseded (old and new
  answers recorded in place); Q18-Q28 added; edge cases, NFRs, out of scope and traceability extended; T8-T14 added;
  T7 extended to document the new behaviour. AC-1..AC-5 are unchanged.
- Amendment 2 (2026-10-10, after T8; narrow): AC-13's text amended minimally to also cover `~` after make's
  leading `./` runs (`./~/x.mk`); edge case and ASSUMPTION A13 corrected; AC-13 test list extended; T8 results
  recorded. AC-1..AC-12 and AC-14 are unchanged.

## Amendment 2 (2026-10-10, after T8)
T8 ran the amendment 1 assumptions against GNU Make 3.81 in the scratchpad (`t8/`, evidence in `t8/out.txt`).
- Finding (A13 was wrong in one detail): make 3.81 strips leading `./` runs from an include word (`./`, `.//`,
  `././`: a `.` followed by one or more `/`, repeated) and only then expands a leading `~`. So `-include ./~/x.mk`
  reads `$HOME/x.mk` (`make -d`: "Reading makefile `<home>/x.mk' ... (no ~ expansion)", case `tilde_mid`/iso1).
  Amendment 1 called `./~/x.mk` a literal word. AC-13 now rejects it.
- Still literal (confirmed): `a~b.mk` (read as `a~b.mk`) and `sub/../~/x.mk` (no leading `./` run, so no tilde
  expansion; make reads `<svc>/sub/../~/x.mk`).
- Confirmations relevant for the reviewer:
  - A8 confirmed: in a skipped branch, `ifeq (a,b)` / `define A` / `define B` / `endef` / `endif` /
    `-include gen.mk` makes make read the include (the nested `define` is not counted), so counting nesting like
    `do_define` would have hidden it. AC-10 failing closed is the right choice (Q19).
  - Q18 confirmed: make defines `verify` from `\` + `verify:`; the scanner does not credit it (fail closed, as
    specified in AC-8).
  - A7 and A12 and the other T8 checks matched the spec.

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
  - Amendment 1: the "continuation stays as written" design above is superseded (Q2). Each logical line is now
    collapsed the way make collapses it before any directive is recognised (AC-6..AC-8); only the IDP-22 AC-7
    backslash check still looks at the uncollapsed text. The AC-1 behaviour and its tests are unchanged.
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
  - Amendment 1: AC-11 adds a second, separate character check (other characters make reads differently). The
    separator check runs first, so every AC-2 message and test stays unchanged.
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
  - Amendment 1: a `<rest>` with a `..` segment or a leading `/` is no longer pinnable (AC-14, Q7 superseded).
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
- **AC-6** Given an example whose `Makefile` has `define Y`, a body line, a line holding only `\` followed by a line `  endef`, then `-include gen.mk` and a rule that generates `gen.mk`, all with CRLF line endings, when I run `idp conformance`, then that `endef` closes the define block, `gen.mk` is recorded in the scan's include words and pinned with `--assume-old`, make does not create `gen.mk`, and the validated `verify` recipe runs.
  - Added by amendment 1 (code review B1). Supersedes the Q2 design (A7).
  - Collapsing (shared with AC-7, AC-8 and AC-9), applied to every logical line before comment stripping,
    `define`/`endef` recognition, rule names and include words, as make's `collapse_continuations` does:
    - each internal newline of a logical line is preceded by a run of n backslashes, n odd (that is why the lines
      were joined). The run is replaced by (n-1)/2 backslashes. If that leaves no backslash, the blanks (space, tab)
      before the run are removed too;
    - the newline and the blanks at the start of the next physical line are removed, and one space is inserted;
    - so `\` + `  endef` becomes ` endef`, `override \` + `define Y` becomes `override define Y`, and
      `lint \` + `  verify:` becomes `lint verify:`.
  - The collapsed line is used for everything except the IDP-22 AC-7 backslash check, which keeps looking at the
    comment-stripped uncollapsed line (AC-7).
  - Inside a define body, the collapsed line is classified as in AC-9: ` endef` (leading blank) closes the block.
  - CRLF: the `\r` before each `\n` is dropped before the trailing backslashes are counted (AC-2), so the CRLF file
    gives the same result as the LF one.
  - Verified by:
    - a scanner unit test parametrized over LF and CRLF: the AC-6 layout gives `include_words == ("gen.mk",)` and
      the `gen.mk` target; plus collapse cases (`define \` + `  Y` opens a block; `x \` + `endef` in a body does
      not close it, AC-1 case unchanged; three trailing backslashes leave one literal backslash);
    - a real-make (`needs_make`) conformance test with the AC-6 layout written with CRLF, explicit `os.utime`, no
      sleeps. Expected: PASS, `validated-ran` present, `evil-ran` and `gen.mk` absent. It must be red before the fix
      (reproduced: the scanner stays in the block, make generates `gen.mk`).
- **AC-7** (edge) Given a `Makefile` with a line holding only `\` followed by `-include gen.mk`, when I run `idp validate`, then it exits 1 with the violation `include line in 'Makefile' uses a backslash (continuation or escape); write each include word literally on one line`, and `idp conformance` reports that example `FAIL <x>: idp validate: 1 violation(s)` without running make.
  - Added by amendment 1 (code review B1).
  - After collapsing, the logical line is ` -include gen.mk`, an include line. The uncollapsed comment-stripped text
    contains `\`, so the IDP-22 AC-7 check fires (fail closed, Q3 unchanged). Its words are not queued or recorded.
  - Rule: a logical line is an include line if its collapsed, comment-stripped text starts (after blanks) with
    `include`, `-include` or `sinclude` as the first word. It violates IDP-22 AC-7 if its uncollapsed,
    comment-stripped text contains `\`.
  - Not a violation: `X = \` + `-include gen.mk` (collapsed `X = -include gen.mk` is an assignment; make includes
    nothing and the scanner records nothing), and `include common.mk # see notes \` as the last line (the backslash
    is in the comment; the IDP-22 `comment-only` case stays valid).
  - Verified by:
    - a `tmp_path` validate test parametrized over LF and CRLF (also with leading blanks before `-include`), with
      exact stdout and exit 1, and a negative case `X = \` + `-include gen.mk` (exit 0, `gen.mk` not recorded);
    - a real-make conformance test with the reviewer's layout. Expected: FAIL with the detail line, exit 1, and no
      `evil-ran`, `validated-ran` or `gen.mk`. It must be red before the fix (reproduced: PASS and `evil-ran`).
- **AC-8** Given a `Makefile` with `override \` followed by `define Y`, a body line `verify:` and `endef`, and no other `verify` rule, when I run `idp validate`, then `verify` is not credited and the output reports `missing required target 'verify'`.
  - Added by amendment 1 (code review B1). After collapsing, the line is `override define Y`, which opens a block in
    GNU make 3.81 and 4.x (Q20), so the body is not scanned.
  - Output: exactly `idp.yaml: Makefile: missing required target 'verify'` (all other required targets defined
    normally), exit 1.
  - Related (Q18, fail closed, documented): a line holding only `\` followed by `verify:` collapses to ` verify:`.
    make defines `verify` there, but the scanner keeps the IDP-17 rule that a rule line starting with a blank is not
    credited, so `idp validate` reports `missing required target 'verify'`.
  - Verified by a `tmp_path` validate test (exact stdout, exit 1) parametrized over LF and CRLF, plus the Q18 case.
- **AC-9** Given an example whose `Makefile` has `define A`, then a body line `define#` or `override define B`, then `endef`, `-include gen.mk` and a rule that generates `gen.mk`, when I run `idp conformance`, then that `endef` closes the block, `gen.mk` is recorded and pinned with `--assume-old`, make does not create `gen.mk`, and the validated `verify` recipe runs.
  - Added by amendment 1 (security B1; supersedes Q16).
  - Body lines are classified like GNU make's `do_define` (3.81 and 4.x), on the collapsed line (AC-6) and without
    stripping comments:
    - a line starting with a tab never nests and never closes the block (but see AC-10 for a tab-prefixed `endef`);
    - otherwise let `p` be the line with leading blanks (space, tab) removed;
    - `p == "endef"`, or `p` starts with `endef` followed by a blank, closes the block (any text after it, such as
      `endef # done`, is allowed, as in make);
    - `p == "define"`, or `p` starts with `define` followed by a blank, is a nested define. make counts it in a live
      branch but not in an ignored conditional branch, so it is reported by AC-10 instead of being counted (Q19);
    - everything else is body text: `define#`, `define#x`, `override define B`, `export define B`, a tab-prefixed
      `define B`, `defineX`.
  - So the scanner's define depth is never more than 1, and the block closes exactly where make closes it.
  - Verified by:
    - a scanner unit test parametrized over the body lines `define#`, `define#x`, `override define B`,
      `export define B`, tab + `define B`, and over the closing lines `endef`, `  endef`, `endef # done`, with CRLF
      for one case: the first closing line closes the block, and a target after it is credited;
    - a real-make conformance test parametrized over `define#` and `override define B` with the AC-9 layout,
      explicit `os.utime`, no sleeps. Expected: PASS, `validated-ran`, no `evil-ran`, no `gen.mk`. It must be red
      before the fix (reproduced for `define#`: the scanner nests, make does not).
- **AC-10** (edge) Given a `Makefile` or scanned include whose `define` body contains a nested `define B` line, a line `endef#...`, or a tab-prefixed `endef` line, when I run `idp validate`, then it exits 1 with a violation naming the file, and `idp conformance` reports that example `FAIL <x>: idp validate: 1 violation(s)` without running make.
  - Added by amendment 1 (follows from security B1; Q19, ASSUMPTION A8). These are the body lines whose meaning
    depends on whether the enclosing conditional branch is taken:
    - in a taken branch, `do_define` counts a nested `define` and ignores `endef#c` and tab-prefixed `endef`;
    - in a branch that is not taken, make only skips lines until the first line whose first word, after comment
      removal, is `endef` (no nesting count), so it does not count the nested `define` and stops at `endef#c` (and at a
      tab-prefixed `endef` when no rule precedes it).
    The scanner does not evaluate conditionals, so it cannot model either choice safely: counting the nested define
    lets `ifeq (a,b)` / `define A` / `define B` / `endef` / `endif` / `-include gen.mk` hide the include.
  - Rule (body lines, collapsed, not comment-stripped): a non-tab line with `p == "define"` or `p` starting with
    `define` + blank; a non-tab line whose `p` starts with `endef#`; a tab-prefixed line whose text after leading
    blanks is `endef` or starts with `endef` followed by a blank or `#`.
  - Violation (ASSUMPTION A9): `path` `Makefile`, message
    `define body in <file> has a line make reads differently in skipped conditional branches (nested define, endef followed by '#', or tab-indented endef); remove it`,
    with `<file>` shown as in AC-2 (repr, truncated at 200 characters). One violation per offending line, counted toward
    `MAX_INCLUDE_PROBLEMS` (20); like the other scan problems it replaces the missing-target list. The scan of the
    file goes on: a nested `define` does not change the depth, and the other two lines do not close the block.
  - Verified by:
    - a `tmp_path` validate test parametrized over `define B`, `define`, `define # c`, `endef#c`, tab + `endef` and
      a CRLF case, plus one case in an included file (exact stdout, exit 1);
    - a real-make conformance test with `ifeq (a,b)` / `define A` / `define B` / `endef` / `endif` /
      `-include gen.mk` and a generating rule. Expected: FAIL with the detail line, exit 1, no `evil-ran`,
      `validated-ran` or `gen.mk`. It must be red before the fix (expected PASS today).
- **AC-11** (edge) Given a `Makefile` or scanned include that contains a character Python treats as whitespace but make does not (for example `\x1f`, U+00A0, U+1680, U+2000–U+200A, U+202F, U+205F, U+3000) or a C0 control character other than tab, LF and CR before LF (including NUL), when I run `idp validate`, then it exits 1 with a violation naming that file and the character, and a file using only spaces, tabs and LF or CRLF line endings is still accepted.
  - Added by amendment 1 (security B2, code review M1; supersedes Q15). Fail closed instead of tokenising like make
    (Q22, Q23).
  - The rejected set (ASSUMPTION A10): every character `c` with `c.isspace()` other than space, tab, LF and CR,
    plus the C0 controls U+0000-U+0008 and U+000E-U+001B. Line separators listed in AC-2 (`\x0b`, `\x0c`,
    `\x1c`-`\x1e`, `\x85`, U+2028, U+2029, lone CR) keep the AC-2 check and message, which runs first. The new
    class is therefore `[\x00-\x08\x0e-\x1b\x1f\xa0  -   　]`.
  - Not rejected: DEL (U+007F), the other C1 controls, U+200B and U+FEFF. Neither `str.isspace()` nor make treats
    them as blanks, so they cannot split words differently.
  - Checked in `_load_makefile` after the AC-2 check, with one linear regex search. Violation (ASSUMPTION A10):
    `path` `Makefile`, message
    `<file> contains a control or space character make reads differently (<what>); use only spaces, tabs and LF or CRLF line endings`,
    `<what>` as in AC-2 (`U+001F`). Example:
    `idp.yaml: Makefile: 'Makefile' contains a control or space character make reads differently (U+00A0); use only spaces, tabs and LF or CRLF line endings`.
  - Like AC-2, the file is not parsed, the violation counts toward `MAX_INCLUDE_PROBLEMS`, and other queued files are
    still scanned. `idp conformance` fails the example with `idp validate: 1 violation(s)` and does not run make.
  - A NUL anywhere in a scanned file now gives this violation. Before, a NUL inside an include word gave
    `cannot read '<word>'` (IDP-17 test updated, see "Tests that change").
  - Verified by:
    - a `tmp_path` validate test whose parameters are computed from Python itself (every `chr(i)` with
      `isspace()`, except space, tab, LF, CR and the AC-2 separators) plus the listed C0 controls, so a Python
      Unicode update cannot silently widen the gap. Exact stdout, exit 1. Plus an in-include case and `--json`;
    - a test that a CRLF file with tabs and spaces is valid (the AC-2 CRLF test stays green unchanged);
    - a real-make conformance test parametrized over `-include a.mk\x1fb.mk` with a rule that generates
      `a.mk\x1fb.mk`, the same with U+00A0, and `define\x1fX = 1` followed by the AC-1 `gen.mk` attack. Expected:
      FAIL with the detail line, exit 1, no `evil-ran`, `validated-ran` or generated file. It must be red before the
      fix (reproduced: PASS and the injected content runs).
- **AC-12** (edge) Given a `Makefile` or scanned include with a top-level `define` line that has an `export`, `unexport` or `private` modifier (for example `private define X = 1` or `export define X`), when I run `idp validate`, then it exits 1 with a violation naming the file, while `define X` and `override define X` blocks are still accepted.
  - Added by amendment 1 (security M3). GNU make 3.81 has no `private` and no `export define`: it reads these lines
    as assignments or `export` directives, while 4.x opens a define block. Rejecting them means the scanner never
    has to pick a make version (Q20).
  - Rule: at define depth 0, on a non-tab collapsed comment-stripped line, the text matches blanks, then one or
    more of `override`, `export`, `unexport`, `private` each followed by blanks, then `define`, then a blank or the
    end of the line, and what follows is not an assignment operator (`=`, `:=`, `::=`, `:::=`, `+=`, `?=`, `!=`).
    If the modifiers are exactly one `override`, it opens a block (AC-8). Any other modifier list is this violation.
  - Not affected: `export define ?= 3` and `define := 1` (assignments to a variable named `define`; the existing
    IDP-17 test stays green), `define X = 1` (a define block in 3.81 and 4.x; Q21).
  - Violation (ASSUMPTION A11): `path` `Makefile`, message
    `<file> has a define with export, unexport or private, which GNU make 3.81 and 4.x read differently; use define or override define`.
    One per offending line, counted toward `MAX_INCLUDE_PROBLEMS`. The line opens no block, so the scanner keeps
    reading the lines after it (it never hides lines either make version reads).
  - Verified by:
    - a `tmp_path` validate test parametrized over `export define X = 1`, `private define X = 1`,
      `unexport define X`, `override export define X`, `export override define X` and a CRLF case (exact stdout,
      exit 1), plus accepted cases `define X`, `override define X`, `export define ?= 3`, `define X = 1`;
    - a real-make conformance test parametrized over `private define X = 1` and `export define X = 1`, each followed
      by the AC-1 `gen.mk` attack. Expected: FAIL with the detail line, exit 1, no `evil-ran`, `validated-ran` or
      `gen.mk`. It must be red before the fix (reproduced on 3.81: PASS and `evil-ran`; on 4.x: PASS).
- **AC-13** (edge) Given a `Makefile` or scanned include with an include word that starts with `~`, also after leading `./` runs (for example `-include ~/evil.mk`, `include ~user/x.mk` or `-include ./~/evil.mk`), when I run `idp validate`, then it exits 1 with `include '<word>' is outside the service directory`, and `idp conformance` does not run make for that example.
  - Added by amendment 1 (security M4). make expands a leading `~` (`$HOME`) or `~user` in include words.
  - Amendment 2 (T8 finding): make first strips leading `./` runs and then expands `~`. The AC text gained
    "also after leading `./` runs" and the `./~/evil.mk` example; meaning otherwise unchanged.
  - Rule: strip leading `./` runs from the word as make does (repeatedly remove a `.` followed by one or more `/`,
    e.g. with `re.sub(r"^(?:\./+)+", "", word)`, linear), then reject if what remains starts with `~`. The message
    shows the word as written (`include './~/evil.mk' is outside the service directory`).
  - Checked in `_lexically_outside`, next to absolute words and `..` escapes, so the IDP-17 message, cap and
    "not queued" behaviour apply unchanged (Q24). A `~` elsewhere in a word (`a~b.mk`) is not expanded by make and
    stays a normal literal word. A `$` word starting with `~` is already unpinnable (AC-4).
  - `sub/../~/x.mk` stays an accepted literal word (amendment 2 decision): make does not expand it (no leading `./`
    run), and the IDP-17 outside-directory check does not fire because `normpath` gives `~/x.mk`, a relative path
    inside the service directory. make reads `<svc>/sub/../~/x.mk`, which is the file the scanner follows, scans and
    pins as written.
  - Verified by:
    - a `tmp_path` validate test parametrized over `~/evil.mk`, `~user/x.mk`, `~`, `./~/evil.mk`, `.//~/evil.mk`
      and `././~/evil.mk` (exact JSON message with the word as written, exit 1), and the accepted literal words
      `a~b.mk` and `sub/../~/x.mk` (exit 0, recorded in `include_words`);
    - a real-make conformance test parametrized over `-include ~/evil.mk` and `-include ./~/evil.mk`, with `HOME`
      set (monkeypatched) to `tmp_path/home` holding an `evil.mk` with `EVIL_INCLUDE`. Expected: FAIL with the
      detail line, exit 1, no `evil-ran`, no `validated-ran`. It must be red before the fix (reproduced on 3.81 for
      both: PASS and `evil-ran`).
- **AC-14** (edge) Given an example whose Makefile includes `$(IDP_PROFILE_DIR)/<rest>` where a `/`-separated segment of `<rest>` is `..` or `<rest>` starts with `/`, when I run `idp conformance`, then that example is reported `FAIL <x>: dynamic include '<word>' cannot be pinned` and make is not run.
  - Added by amendment 1 (security M5; supersedes Q7's "`..` is allowed").
  - `_profile_names` treats such a word as unpinnable, with the AC-4 message and order (first unpinnable word,
    before the argument budget). Pinning would stop make from remaking the file, but make would still read an
    unscanned file outside the profile directory.
  - Still pinnable: `$(IDP_PROFILE_DIR)/defaults.mk`, `$(IDP_PROFILE_DIR)/sub/x.mk`, `$(IDP_PROFILE_DIR)/./x.mk`
    (no `..` segment, no leading `/`). Symlinks inside the platform-owned profile directory are not resolved (Q25).
  - `idp validate` is unchanged for `$` words (Q9), and the profile's `defaults.mk` is still not scanned.
  - Verified by:
    - new cases in the parametrized fake-`Popen` rejection test (`$(IDP_PROFILE_DIR)/../x.mk`,
      `$(IDP_PROFILE_DIR)/a/../../x.mk`, `$(IDP_PROFILE_DIR)/..`, `$(IDP_PROFILE_DIR)//etc/x.mk`);
    - a real-make conformance test: `-include $(IDP_PROFILE_DIR)/../outside/evil.mk` with a monkeypatched
      `tmp_path` profile and `tmp_path/outside/evil.mk` holding `EVIL_INCLUDE`. Expected: FAIL
      `dynamic include '...' cannot be pinned`, exit 1, no `evil-ran`. It must be red before the fix (reproduced:
      PASS and `evil-ran`).
    - `test_profile_dir_include_is_pinned_with_resolved_path` drops its `$(IDP_PROFILE_DIR)/../shared/extra.mk`
      word and pins `$(IDP_PROFILE_DIR)/sub/extra.mk` instead (see "Tests that change").

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
- NUL bytes in a Makefile are not covered by AC-2 (see Q15). Amendment 1: they are rejected by AC-11.
- The profile directory path is absolute and contains no whitespace or `$` (it comes from the installed package or
  the checkout). If it did, the command-line `IDP_PROFILE_DIR=` value would already misbehave in make. Not handled
  (ASSUMPTION A5).
- `override IDP_PROFILE_DIR = ...` in the Makefile, or `$(eval ...)`, would make `$(IDP_PROFILE_DIR)` resolve to a
  path other than the pinned one (Q6). Remains a documented residual risk.
- Includes produced by `$(eval ...)`, or by include lines inside `define` bodies that are later evaluated, are still
  not scanned or pinned (residual risk; making the parser run make is out of scope).
- The scanner and make may disagree on `define` nesting inside a body (tab-prefixed `define`/`endef`, and
  `override define`/`export define` lines inside a body). This is a separate finding found while writing this spec
  (Q16). Not in the ACs. Amendment 1: now in scope (AC-9, AC-10).
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
- Amendment 1 edge cases:
  - Safety rule used for every define decision: the scanner may read lines that make hides (over-scan: at worst
    extra pins or over-credited targets, which make then fails on), but it must never hide a line that any supported
    make version reads in any conditional branch. So a block opens only on lines every version opens a block for
    (`define NAME`, `override define NAME`), closes on every line every version closes on, never nests, and any line
    where versions or branches disagree is a violation (AC-10, AC-12) or read as an assignment (Q21).
  - `define = x` / `define := 1` (operator right after `define`, also when written `define \` + `= x`): the scanner
    reads an assignment to a variable named `define`, as 4.x does. 3.81 may open a block there; then the scanner
    only over-scans (Q21). The IDP-17 test `test_variable_named_define_does_not_start_a_define_block` stays green.
  - A collapsed line that starts with a blank (`\` + `verify:` gives ` verify:`) is not credited as a rule (Q18,
    fail closed). An include on such a line is still found (the first word is taken after blanks) and is rejected by
    IDP-22 AC-7 because the uncollapsed text holds the `\` (AC-7).
  - Three trailing backslashes (`a\\\` + `b`) collapse to `a\ b` (one literal backslash), as in make. Only the
    rule-name and include-word extraction see it; an include line with any backslash is still rejected.
  - A modifier define (AC-12) or an ambiguous body line (AC-10) inside an included file names that file's include
    word, like the other per-file problems.
  - A file with an AC-11 character is not parsed, so AC-10/AC-12 violations in it are not reported. Validation
    fails anyway.
  - An ignored conditional branch that contains a plain `define A` ... `endef`: make skips it and the scanner skips
    the same lines (same closing rule), so nothing changes.
  - `~` inside a word (`a~b.mk`) or after a non-`./` prefix (`sub/../~/x.mk`) is not expanded by make: a normal
    literal word. Amendment 2 correction: after leading `./` runs (`./~/x.mk`, `.//~/x.mk`, `././~/x.mk`) it IS
    expanded, and AC-13 rejects it.
  - `.RECIPEPREFIX` (make 3.82+, so 4.x in CI) changes which lines are recipe lines, which also changes the
    "tab-prefixed" rules of AC-9 and AC-10. Not covered by this amendment (Q27).
- ASSUMPTION A7 (AC-6): GNU make 3.81 and 4.x collapse `[blanks]` + an odd backslash run + newline + `[blanks]`
  into (n-1)/2 backslashes and one space (removing the blanks before the run only when no backslash remains) before
  recognising directives in `eval` and before classifying lines in `do_define`. Tokenisation is the same if a 4.x
  POSIX mode keeps the blanks before the run. Checked first in T8 (scratchpad) and by the AC-6/AC-7 real-make tests.
- ASSUMPTION A8 (AC-10): in a conditional branch that is not taken, GNU make (3.81 and 4.x) marks a `define` as an
  ignored define and ends it at the first line whose first word after comment removal is `endef`, without counting
  nested `define` lines. Checked first in T8 with `ifeq (a,b)` / `define A` / `define B` / `endef` / `endif` /
  `-include gen.mk`. AC-10 holds whatever the result (it fails closed in both cases); the result is recorded for the
  human and decides only the docs wording.
- ASSUMPTION A9: AC-10 message and `path` `Makefile`; scanning of the file continues.
- ASSUMPTION A10: AC-11 character set and message; separators keep the AC-2 message.
- ASSUMPTION A11: AC-12 message and `path` `Makefile`; the offending line opens no block.
- ASSUMPTION A12: `override define NAME` opens a define block in GNU make 3.81 and 4.x, in taken and skipped
  branches, so it needs no violation (Q20). `export`/`unexport`/`private define` differ (3.81 reads an assignment or
  an export directive). Checked in T8.
- ASSUMPTION A13 (corrected by amendment 2 after T8): GNU make strips leading `./` runs (a `.` followed by one or
  more `/`, repeated) from an include word and then expands a leading `~` or `~user` (reproduced on 3.81:
  `./~/x.mk` reads `$HOME/x.mk`; 4.x is expected to behave the same and is covered by the CI run of the real-make
  test). No other position is expanded (`a~b.mk`, `sub/../~/x.mk` stay literal, confirmed on 3.81).

### Tests that change (amendment 1)
Existing tests whose expectations the amendment changes (all others, including every IDP-22 AC-7 case and every
AC-1..AC-5 test, stay green unchanged):
- `packages/idp-gate/tests/test_contract.py::test_define_bodies_are_skipped_including_nested_ones` (IDP-17 AC-3):
  it uses a nested `define INNER` (now an AC-10 violation) and `export define EXPORTED =` (now an AC-12 violation),
  and expects targets `{"after-define"}`. Rewritten to keep its intent with accepted forms: `define RECIPE` /
  `inside-define:` / `endef`, `override define OUTER` / `inside-override:` / `endef # done`, then `after-define:`.
  The nested and modifier cases move to the AC-10 and AC-12 tests.
- `packages/idp-gate/tests/test_contract.py::test_nul_byte_in_include_word_is_a_violation_not_a_traceback` (IDP-17
  AC-6/AC-4): `include a\x00b.mk` now gives the AC-11 message
  `'Makefile' contains a control or space character make reads differently (U+0000); use only spaces, tabs and LF or CRLF line endings`
  instead of `cannot read 'a\x00b.mk'`. Its intent (a violation, not a traceback) holds; tag kept. `_locate`'s
  NUL guard stays as defence in depth (Q26).
- `packages/idp-gate/tests/test_conformance.py::test_profile_dir_include_is_pinned_with_resolved_path` (IDP-28 AC-4):
  its `$(IDP_PROFILE_DIR)/../shared/extra.mk` word becomes unpinnable (AC-14). Replaced by
  `$(IDP_PROFILE_DIR)/sub/extra.mk`, pinned as `<profile_dir>/sub/extra.mk`.
- Checked and unchanged: `test_variable_named_define_does_not_start_a_define_block` (`export define ?= 3` is an
  assignment), all `test_logical_lines_join_odd_trailing_backslashes` cases, `test_trailing_comment_ending_in_backslash_hides_next_line`,
  `test_include_line_with_backslash_is_a_violation` (four cases), `test_dynamic_words_on_backslash_include_lines_are_not_recorded`,
  `test_line_separator_make_does_not_use_is_a_violation`, `test_crlf_makefile_is_accepted`,
  `test_conformance_module_uses_no_private_contract_members` (conformance switches to a public helper),
  `test_default_targets_have_recipes_in_defaults_mk` and `test_root_make_verify_runs_conformance`.

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
- Amendment 1:
  - Still no new dependencies (stdlib `re` only).
  - Still linear: collapsing touches each physical line once (one `rstrip` of backslashes, one `rstrip`/`lstrip` of
    blanks, one join per logical line); the AC-11 check is one regex search over a single character class; body-line
    classification is a constant number of prefix checks per line; the define-line regex is anchored with
    `re.match` and its modifier repetition consumes distinct words, so it does not backtrack quadratically.
    `test_many_continued_lines_are_joined_in_linear_time` gains a case with 200 000 lines of `\` + newline +
    `  x` (collapsing, no timing assertion), and `test_long_lines_without_colon_are_parsed_in_linear_time` gains a
    line of 100 000 `override ` words followed by `x` (no timing assertion).
  - Caps unchanged. AC-10 and AC-12 violations count toward `MAX_INCLUDE_PROBLEMS` (20), so their number is bounded.
  - Every new real-make test runs on GNU Make 3.81 (macOS, local) and 4.x (Linux CI), uses explicit `os.utime`
    with `OLD_MTIME`/`NEW_MTIME`, and never sleeps. The AC-10 and AC-12 rules are chosen so the expected result is
    the same on both versions.
  - `idp validate` output stays byte-for-byte unchanged for Makefiles without continuations, defines, `~` include
    words or the AC-11 characters (all in-repo makefiles; see "Facts checked for amendment 1").

## Out of scope
- Replacing static parsing with `make -pn` in a sandbox (ADR candidate after IDP-23).
- An environment allow-list or sandboxing for `idp conformance` (IDP-23).
- Tenant CI running plain `make verify` without conformance (no pinning there).
- Scanning the profile's `defaults.mk` (platform-owned) or any other file named by a `$` word (Q9).
- Glob include words without `$` (unchanged: skipped, not pinned; Q11), `$(eval ...)`-generated includes, and
  `override IDP_PROFILE_DIR` (Q6): residual risks, documented.
- Changing IDP-22 AC-7 (backslash on include lines stays a violation; Q3).
- Aligning in-body `define` nesting with make (Q16), unless the human adds it by amendment. (Superseded by amendment
  1: in scope as AC-9 and AC-10.)
- Editing `specs/IDP-22/*` (approved). The D5-D7 notes are resolved in the docs, not in that spec.

### Out of scope / follow-ups (amendment 1)
Deferred by the human to follow-up tickets (recorded in the docs' residual-risk text where it applies):
- make's default include search path: a missing literal include (`-include x.mk` with no `x.mk` beside the
  Makefile) is looked up by make in `/usr/local/include`, `/usr/include` and similar directories, which are never
  scanned. Pinning stops a rule from creating it, but a file already present there is read.
- Bounding make output size and line length in conformance (`communicate()` reads everything; `_tail` keeps the last
  40 lines but not a bounded number of bytes).
- The TOCTOU window between the scan and make (IDP-23).
- Replacing static parsing with `make -pn` in a sandbox (ADR candidate after IDP-23).
- `.RECIPEPREFIX` and other make 4.x reader features (`load`/`-load`, `guile`) that the scanner does not model
  (Q27; not reproduced, 4.x only).

## Open questions
- Q1: Which backslash rule do we model? Proposed: GNU make's reader. An odd number of trailing backslashes joins the
  next physical line, in every context (comments, recipes, define bodies, `endef` lines), before comment stripping
  and directive recognition. An even number is literal. So a `\` at the end of a comment line continues the comment
  (AC-3), and a `\` at the end of a recipe line continues the recipe. Recipe lines differ from other lines only in what
  make does with the joined text (it keeps the backslash-newline for the shell), which the scanner never needs (A1).
- Q2: How should a continuation look in the logical line? Proposed: keep `\` + `\n` as written. Rule-name extraction
  reads each as one space, and the IDP-22 AC-7 include-line check still sees the backslash. Alternative: collapse to a
  space everywhere and flag continued lines separately (more state for the same result).
  - Superseded by amendment 1 (code review B1). Old answer: keep `\` + `\n` in the logical line and collapse only in
    `_rule_names`. New answer: collapse every logical line with make's rule (A7) before comment stripping, define and
    endef recognition, rule names and include words; keep the comment-stripped uncollapsed text only for the IDP-22
    AC-7 backslash check (AC-6, AC-7, AC-8). Why: make collapses before it recognises any directive, so the old
    design hid `\` + `-include gen.mk` and `\` + `  endef`, and missed `override \` + `define Y`. The "same result"
    claim above was wrong.
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
  - Superseded by amendment 1 (security M5), for `..` only; the rest of the answer stands. Old answer: `..` in
    `<rest>` is allowed. New answer: a `<rest>` with a `..` segment or a leading `/` cannot be pinned (AC-14).
    Why: the pin stops make from remaking the file, but make still reads it, and a file outside the profile
    directory is neither platform-owned nor scanned. A leading `/` stays inside the profile directory
    (`<dir>//x`), but no profile needs it and rejecting it keeps the rule simple. Symlinks are not resolved (Q25).
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
  - Superseded by amendment 1. Old answer: not in this ticket. New answer: NUL is rejected by AC-11 (with the other
    C0 controls), with the AC-11 message, not the AC-2 one (a NUL is not a line separator). Why: make and the
    scanner disagree about a line containing NUL (4.x drops the rest of the line), and the human asked to close
    the whole class of "characters make reads differently". Consequence: the IDP-17 NUL test changes its expected
    message (see "Tests that change").
- Q16 (new finding, outside the ACs): inside a `define` body, GNU make (3.81 and 4.x `do_define`) skips
  tab-prefixed lines when it looks for nested `define`/`endef`. It counts only a bare `define` word as nesting, not
  `override define` or `export define`. `_parsed_lines` nests on `^\s*(override|export|private)* define` and also
  matches tab-prefixed lines. Example: `define A`, `override define B`, `endef`. make closes `A` at that `endef`. The
  scanner stays at depth 1 and hides every later line, a define-tracking bypass like AC-1. Proposed: confirm with
  real make in T1, then file a follow-up ticket, or extend this ticket by amendment with a new AC if the human
  prefers. Not implemented without that decision.
  - Superseded by amendment 1 (security B1; the human chose to fix it here). Old answer: out of scope, follow-up.
    New answer: in scope. Body lines are classified like `do_define` on the collapsed line without stripping
    comments (AC-9): tab-prefixed lines, `define#`, `override/export define B` never nest; `endef` followed by a
    blank or the end of the line closes. A nested bare `define`, `endef#...` and a tab-prefixed `endef` are AC-10
    violations instead of being counted (Q19). Why: `define#` in a body hid the rest of the Makefile (reproduced on
    3.81), and the review asked for make's `do_define` rules.
- Q17: Docs and CHANGELOG. Proposed: update `docs/platform/service-contract.md` (logical lines, the separator
  violation, the removed D7 limitation, the AC-7 rationale text) and `docs/platform/onboarding.md` (single scan,
  profile-word pinning, `dynamic include ... cannot be pinned`, a residual-risk sentence narrowed to globs,
  `$(eval)`/`define`-body includes and `override IDP_PROFILE_DIR`). Add one IDP-28 line under `[Unreleased]` /
  `### Changed`, and update the `conformance.py` module docstring.
  - Amendment 1: the docs, docstring and CHANGELOG line also cover AC-6..AC-14 (collapsed continuations, the define
    body rules and the two new define violations, the new character violation, `~` include words, and the
    `..`/absolute profile words), and the residual-risk text adds the follow-ups listed under "Out of scope /
    follow-ups (amendment 1)". Done in T7, after T14.

### Open questions added by amendment 1
- Q18 (m1): after collapsing, `\` + `verify:` is ` verify:`, which make defines. Credit it (strip leading blanks as
  make does) or fail closed? Proposed: fail closed and document it. The scanner keeps the IDP-17 rule that a rule line
  starting with a blank is not credited, so `idp validate` reports `missing required target 'verify'`. Crediting it
  would also change IDP-17 behaviour for every blank-indented rule line. Alternative: strip leading blanks before
  `_rule_end` (credits indented rules too; needs IDP-17 doc changes).
- Q19 (needs the human's decision; deviates from the review's direction): the review asked to count nesting exactly
  like `do_define`. In a conditional branch that is not taken, make does not count nesting and stops at `endef#c`
  (A8), and the scanner cannot tell which branches are taken. Proposed: count nothing; report a nested bare
  `define`, `endef#...` and a tab-prefixed `endef` inside a body as AC-10 violations (fail closed, the same answer
  on 3.81 and 4.x and in every branch). Cost: a Makefile with legitimately nested defines fails validation (no
  in-repo makefile uses `define`). Alternative: count nesting as `do_define` does and accept the skipped-branch
  bypass as a documented residual risk (not recommended).
- Q20 (needs the human's decision; narrows the review's proposal): which define modifiers are rejected? The review
  proposed rejecting `override`, `export` and `private`. Proposed: reject `export`, `unexport` and `private` (and any
  list containing them), but accept a single `override` (`override define NAME`), because 3.81 and 4.x both open a
  block for it in taken and skipped branches (A12), and IDP-17 already treats it as a define. Alternative: also reject
  `override define` (one simpler rule; no in-repo makefile is affected).
- Q21: the review also suggested failing on "assignment-operator text after the name". Proposed: no extra
  violation. `define NAME = value` opens a block in both 3.81 and 4.x. `define = x` / `define := 1` (operator right
  after `define`, also via `define \` + `= x`) is read by the scanner as an assignment (4.x behaviour); 3.81 may open
  a block, but then the scanner only over-scans and never hides a line make reads. Keeps
  `test_variable_named_define_does_not_start_a_define_block` (IDP-17) green.
- Q22: AC-11 character set. Proposed: every `str.isspace()` character other than space, tab, LF and CR, plus C0
  controls U+0000-U+0008 and U+000E-U+001B; AC-2 separators keep their check and message (checked first). DEL, the
  other C1 controls, U+200B and U+FEFF are not rejected (nobody treats them as blanks). Alternative: reject only the
  `isspace()` characters and NUL, leaving U+0001-U+0008/U+000E-U+001B alone (tenant Makefiles with a raw ESC byte in
  a recipe keep passing). Also confirm the message text (A10).
- Q23: tokenise on `[ \t]` only instead of `str.split()`/`\s`? Proposed: no wholesale change. After AC-11 and AC-2 a
  scanned file holds no other whitespace, so `split()` and `[ \t]` give the same words. The regexes rewritten by this
  amendment (define line) use `[ \t]` explicitly; `_TARGET_VARIABLE` and `split()` stay as they are (smaller diff).
- Q24: `~` include words. Proposed: reuse the IDP-17 message `include '<word>' is outside the service directory`
  (AC-13), reject only a leading `~`, and keep the existing problem cap and "not queued" behaviour. Alternative: a
  dedicated message (`... uses ~, which make expands to a home directory`).
  - Amendment 2: "leading" means after make's leading `./` runs are stripped (T8 finding); the message still shows
    the word as written.
- Q25: should AC-14 also resolve `<profile_dir>/<rest>` and require the real path to stay inside the real profile
  directory (symlinks)? Proposed: no. The profile directory is platform-owned and reviewed; a lexical rule is enough
  and needs no filesystem access in conformance.
- Q26: with AC-11, a NUL never reaches `_locate`, so its NUL guard (`cannot read '<word>'`) becomes unreachable from
  a scanned file. Proposed: keep it as defence in depth (one uncovered line; coverage bars still met). Alternative:
  delete it.
- Q27 (new finding, not reproduced; needs the human's decision): make 3.82+ (4.x in CI) supports `.RECIPEPREFIX`,
  which changes which lines are recipe lines and which body lines `do_define` skips; the scanner always assumes a
  tab. 4.x also has `load`/`-load` (loads a shared object, which make can remake like an include) and `guile`.
  Proposed: a follow-up ticket (listed under "Out of scope / follow-ups"). Alternative: an extra fail-closed rule in
  this ticket (a violation for any line that assigns `.RECIPEPREFIX` or starts with `load`/`-load`).
- Q28 (security m8, minor): conformance needs the repr-and-truncate helper without a private `contract` member.
  Proposed: rename `contract._shown` to a public `contract.shown(text)` (all contract call sites updated), delete
  `conformance._shown`, and call `contract.shown`. `test_conformance_module_uses_no_private_contract_members` stays
  green because the name is public. Alternative: keep `_shown` and add a public alias.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_contract.py::test_logical_lines_join_odd_trailing_backslashes, packages/idp-gate/tests/test_contract.py::test_continuation_into_define_does_not_hide_later_lines, packages/idp-gate/tests/test_conformance.py::test_continuation_cannot_hide_generated_include_from_pinning |
| AC-2 | packages/idp-gate/tests/test_contract.py::test_line_separator_make_does_not_use_is_a_violation, packages/idp-gate/tests/test_contract.py::test_crlf_makefile_is_accepted, packages/idp-gate/tests/test_conformance.py::test_conformance_rejects_foreign_line_separators_without_running_make |
| AC-3 | packages/idp-gate/tests/test_contract.py::test_comment_ending_in_backslash_continues_onto_next_line, packages/idp-gate/tests/test_contract.py::test_trailing_comment_ending_in_backslash_hides_next_line |
| AC-4 | packages/idp-gate/tests/test_contract.py::test_makefile_scan_records_dynamic_include_words, packages/idp-gate/tests/test_conformance.py::test_profile_dir_include_is_pinned_with_resolved_path, packages/idp-gate/tests/test_conformance.py::test_unpinnable_dynamic_include_fails_without_running_make, packages/idp-gate/tests/test_conformance.py::test_make_cannot_remake_profile_dir_include, tests/conformance/test_examples.py::test_platform_examples_pass_conformance_within_60_seconds |
| AC-5 | packages/idp-gate/tests/test_conformance.py::test_conformance_scans_makefile_once_and_pins_from_validated_scan |
| AC-6 | packages/idp-gate/tests/test_contract.py::test_continuations_are_collapsed_before_directives, packages/idp-gate/tests/test_conformance.py::test_continued_endef_cannot_hide_generated_include |
| AC-7 | packages/idp-gate/tests/test_contract.py::test_continued_include_directive_is_a_backslash_violation, packages/idp-gate/tests/test_conformance.py::test_conformance_rejects_continued_include_directive_without_running_make |
| AC-8 | packages/idp-gate/tests/test_contract.py::test_override_continued_into_define_hides_its_body |
| AC-9 | packages/idp-gate/tests/test_contract.py::test_define_body_lines_close_and_nest_like_make, packages/idp-gate/tests/test_conformance.py::test_non_nesting_define_body_line_cannot_hide_generated_include |
| AC-10 | packages/idp-gate/tests/test_contract.py::test_ambiguous_define_body_line_is_a_violation, packages/idp-gate/tests/test_conformance.py::test_define_in_skipped_conditional_cannot_hide_generated_include |
| AC-11 | packages/idp-gate/tests/test_contract.py::test_character_make_reads_differently_is_a_violation, packages/idp-gate/tests/test_contract.py::test_spaces_tabs_and_crlf_are_accepted, packages/idp-gate/tests/test_conformance.py::test_conformance_rejects_characters_make_reads_differently_without_running_make |
| AC-12 | packages/idp-gate/tests/test_contract.py::test_define_with_export_unexport_or_private_is_a_violation, packages/idp-gate/tests/test_conformance.py::test_modifier_define_cannot_hide_generated_include |
| AC-13 | packages/idp-gate/tests/test_contract.py::test_include_word_starting_with_tilde_is_a_violation, packages/idp-gate/tests/test_conformance.py::test_tilde_include_cannot_read_home_file |
| AC-14 | packages/idp-gate/tests/test_conformance.py::test_unpinnable_dynamic_include_fails_without_running_make, packages/idp-gate/tests/test_conformance.py::test_profile_dir_include_cannot_read_outside_profile_dir |
