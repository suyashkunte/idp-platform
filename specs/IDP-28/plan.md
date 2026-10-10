# IDP-28: plan

## Approach
Smallest design. Make two changes inside the existing scanner in `contract.py`:
- read logical lines instead of `splitlines()`;
- reject foreign line separators.

Record `$` words in one new `MakefileScan` field. Return the validated scan from `load_service`. Then change three
small things in `conformance.check_example`:
- use that scan instead of a second one;
- classify `$` words;
- pin profile words.

No CLI or schema change. No protected path. No human task.

1. **Logical lines (AC-1, AC-3)**, `contract.py`:
   - New `_logical_lines(text: str) -> list[str]`:
     - Iterate `text.split("\n")` and drop one trailing `\r` from each physical line.
     - Append the line to `pending`.
     - Count trailing backslashes (`len(p) - len(p.rstrip("\\"))`). If the count is even, emit `"\n".join(pending)`
       and reset `pending`.
     - At the end, emit any non-empty `pending`.
     - Linear: each physical line is scanned once by `rstrip` and joined once.
   - `_parsed_lines(text)` iterates `_logical_lines(text)` instead of `text.splitlines()`. Comment stripping,
     `_DEFINE_START`/`_DEFINE_END` and the tab rule are unchanged and now apply per logical line. `_DEFINE_START`
     uses `re.match` without `MULTILINE`, so `X = \` + `define Y` does not match.
   - `_rule_names(line)`: first `line = line.replace("\\\n", " ")` (make collapses a backslash-newline to one space
     outside recipes). `_rule_end` and `_TARGET_VARIABLE` then work on single-line text, so `spec-trace: \` +
     `KEY = x` is still a target-specific variable line.
   - `_Scanner.visit`, the AC-7 check (`"\\" in line`) and `_include_words`' word filter are unchanged. A continued
     include line still contains `\`, so IDP-22 AC-7 still fires (spec Q3).
2. **Foreign separators (AC-2)**, `contract.py`:
   - `_FOREIGN_SEPARATOR = re.compile("\r(?!\n)|[\x0b\x0c\x1c-\x1e\x85  ]")` (a single-character class
     plus a one-character lookahead, so it never backtracks).
   - `_foreign_separator(name: str, match: re.Match[str]) -> Violation`:
     - message ``f"{_shown(name)} contains a line separator make does not use ({what}); use LF or CRLF line endings"``;
     - `what` is `CR not followed by LF` for `\r`, else `f"U+{ord(ch):04X}"`;
     - `path` is `MAKE_PATH`.
   - `_load_makefile`: after `text is None` (size), `if (m := _FOREIGN_SEPARATOR.search(text)): return
     _foreign_separator(name, m)`, before `_parsed_lines`. `visit` already passes it to `self.problem`.
3. **Dynamic words (AC-4, scanner side)**, `contract.py`:
   - `MakefileScan.dynamic_include_words: tuple[str, ...] = ()`.
   - `_include_words(line)` keeps returning literal words only. New `_dynamic_include_words(line)` returns the words
     of an include line that contain `$`. Both share `_is_include_line`.
   - `_Scanner` gains `dynamic: list[str]`. New `record_dynamic(word)`:
     - if not stopped and the word is a new spelling, check the shared spelling cap (`seen_spellings`, the same
       `too many include words (limit 1024)` stop);
     - then add it to `seen_spellings` and append it to `dynamic`;
     - never queue it (spec Q12).
   - In `visit`, after the AC-7 `continue`, call `record_dynamic` for each `_dynamic_include_words(line)`.
   - `makefile_targets` returns `MakefileScan(..., tuple(scanner.spellings), tuple(scanner.dynamic))`.
4. **Validated scan returned (AC-5)**, `contract.py`:
   - `_EMPTY_SCAN = MakefileScan(frozenset(), ())`.
   - `_make_contract(doc, makefile) -> tuple[list[Violation], MakefileScan]` holds today's body of
     `check_make_contract`:
     - `Makefile not found` returns `([...], _EMPTY_SCAN)`;
     - otherwise it returns the violations and the scan from the single `makefile_targets(makefile)` call, called
       through the module global so tests can wrap it.
   - `check_make_contract(doc, makefile)` returns `_make_contract(doc, makefile)[0]` (unchanged public API and tests).
   - `load_service(path) -> tuple[Any, list[Violation], MakefileScan]`. Every early return gets `_EMPTY_SCAN`. The
     mapping branch uses `_make_contract`. `validate_service` stays `load_service(path)[1]`.
5. **Conformance (AC-4, AC-5)**, `conformance.py`:
   - `PROFILE_DIR_PREFIX = "$(IDP_PROFILE_DIR)/"` and `_UNPINNABLE_CHARS = "$*?["`.
   - `_profile_names(words, profile_dir) -> tuple[list[str], str | None]`:
     - for each word in order: if it starts with the prefix and `rest = word[len(prefix):]` is non-empty with no
       character of `_UNPINNABLE_CHARS`, append `f"{profile_dir}/{rest}"`;
     - otherwise return `([], word)` (the first unpinnable word);
     - at the end, return `(names, None)`.
   - `_shown(word)`: `repr` truncated to `contract.MAX_SHOWN_WORD` plus `…`. This duplicates two lines on purpose:
     the IDP-22 AC-4 `ast` test forbids `contract._shown`.
   - `check_example`:
     - `doc, violations, scan = contract.load_service(path)`;
     - violations: fail as today;
     - profile: fail as today;
     - `names, bad = _profile_names(scan.dynamic_include_words, profile_dir)`. If `bad` is not None, return
       `Result(directory, ok=False, reason=f"dynamic include {_shown(bad)} cannot be pinned")`;
     - `assume_old = _assume_old((*scan.include_words, *names))`, then the budget check as today, then
       `_run_make_verify`.
     - The second `makefile_targets` call and its comment are deleted.
   - `_assume_old` is unchanged. Absolute profile names never start with `./`, and dedup keeps the order.
   - Module docstring: single validated scan, profile-word pinning, the `dynamic include ... cannot be pinned` FAIL,
     and the narrowed residual risk (globs, `$(eval)`, `override IDP_PROFILE_DIR`).
6. **Docs (DoD)**: see Changes.

### Tests (new tests tagged `@pytest.mark.ac("IDP-28:AC-n")`, written red-first)
`packages/idp-gate/tests/test_contract.py` (reuse `_write_idp`, `_write_makefile`, `_run`, `ALL_TARGETS`):
- `test_logical_lines_join_odd_trailing_backslashes` (AC-1): through `contract.makefile_targets` on `tmp_path` files
  (no private call needed), parametrized:
  - `a \` + `verify:` credits `a`, `verify` (rule continuation);
  - `X = \` + `verify:` credits nothing from that line;
  - `lint: \\` (two backslashes) + `verify:` credits `lint`, `verify` (even count: no continuation);
  - CRLF `X = \` + `\r\n` + `verify:` credits nothing;
  - `\techo \` + `verify:` after a `lint:` rule credits `lint` only (recipe continuation);
  - `define D` / `x \` / `endef` / `inside:` / `endef` / `after:` credits `after` only (the continued `endef` does
    not close);
  - a final line `lint: \` at EOF credits `lint`;
  - `spec-trace: \` + `  KEY = x` credits nothing (target-specific variable over a continuation).
- `test_continuation_into_define_does_not_hide_later_lines` (AC-1): the exact AC-1 layout appended after all required
  targets:

  ```
  X = \
  define Y
  -include gen.mk
  gen.mk:
  <recipe>
  define Z
  endef
  late:
  ```

  `include_words == ("gen.mk",)` and `{"gen.mk", "late"} <= targets`. Red today: `include_words == ()` and `late` is
  missing.
- `test_line_separator_make_does_not_use_is_a_violation` (AC-2): parametrized over `\r` (followed by `x`), `\x0b`,
  `\x0c`, `\x1c`, `\x1d`, `\x1e`, `\x85`, ` `, ` `, each placed after `lint:` in a `Makefile` that defines
  all targets:
  - exact stdout `idp.yaml: Makefile: 'Makefile' contains a line separator make does not use (<what>); use LF or
    CRLF line endings`, exit 1;
  - an `in-include` case: `include common.mk`, where `common.mk` holds `\x85`, names `'common.mk'`;
  - `--json` for one case: `{"path": "Makefile", ...}`.
- `test_crlf_makefile_is_accepted` (AC-2): `_write_makefile` content re-encoded with `\r\n`, plus a CRLF
  continuation `X = a \` + `  b`. The result is `idp.yaml: valid (idp-service.v1.json)`, exit 0. A mixed LF/CRLF file
  is valid too.
- `test_comment_ending_in_backslash_continues_onto_next_line` (AC-3): every required target except `verify`, then
  `# note \` + `verify:` + `\t@true`. Exact stdout `idp.yaml: Makefile: missing required target 'verify'`, exit 1, and
  `--json` gives the same message.
- `test_trailing_comment_ending_in_backslash_hides_next_line` (AC-3): `lint: # note \` + `verify:` credits `lint`
  only. Also a `#` comment ending in `\` inside a `define` body followed by `endef`: the block does not close there.
- `test_makefile_scan_records_dynamic_include_words` (AC-4):
  - `include $(IDP_PROFILE_DIR)/defaults.mk common.mk`, `-include $(V)/d.mk a$$b.mk *.mk`, and `common.mk` with
    `sinclude $(V)/d.mk`;
  - expected `dynamic_include_words == ("$(IDP_PROFILE_DIR)/defaults.mk", "$(V)/d.mk", "a$$b.mk")` and
    `include_words == ("common.mk",)` (`*.mk` in neither);
  - cap: 1000 literal spellings plus 25 dynamic ones give `too many include words (limit 1024)`; 1024 in total do not.
- `test_long_lines_without_colon_are_parsed_in_linear_time` gains a case: 200 000 physical lines of `a \` (no timing
  assertion; it must finish promptly).
- Unchanged and still green: all IDP-17 scanner tests; `test_include_line_with_backslash_is_a_violation` (all four
  cases); `test_makefile_scan_records_literal_include_words_as_written`.

`packages/idp-gate/tests/test_conformance.py` (reuse `_write_example`, `_append_to_makefile`, `_fake_make_on_path`,
`_recording_popen`, `OLD_MTIME`, `NEW_MTIME`, `GENERATE_EVIL`, `STRIPPED_MAKE_VARS`, `needs_make`):
- `test_continuation_cannot_hide_generated_include_from_pinning` (AC-1, `needs_make`):
  - `_write_example(..., verify="@touch validated-ran")`, then append
    `X = \`, `define Y`, `-include gen.mk`, `gen.mk:`, `{GENERATE_EVIL}gen.mk`, `define Z`, `endef`;
  - set `os.utime` on `Makefile` to `OLD_MTIME` and clear the stripped make vars;
  - expected stdout `PASS examples/<x>` plus the summary, exit 0, `validated-ran` present, `evil-ran` and `gen.mk`
    absent;
  - red-first today (make runs `$(shell touch evil-ran)` after generating `gen.mk`).
- `test_conformance_rejects_foreign_line_separators_without_running_make` (AC-2, `needs_make`, parametrized `vt`
  (`\x0b`) and `nel` (`\x85`)):
  - the same attack, with `X = 1<sep>define Y` instead of the continuation, written with `encoding="utf-8"`;
  - expected stdout `FAIL examples/<x>: idp validate: 1 violation(s)`, the detail line, and
    `conformance: 0 passed, 1 failed`; exit 1; the directory holds only `Makefile` and `idp.yaml`;
  - red-first today (PASS and `evil-ran`).
- `test_profile_dir_include_is_pinned_with_resolved_path` (AC-4, fake `Popen`): append
  `include $(IDP_PROFILE_DIR)/defaults.mk`. The argv between `-f Makefile` and `verify` is exactly
  `--assume-old=Makefile`, `--assume-old=<profile_dir>/defaults.mk`, where `<profile_dir>` equals the
  `IDP_PROFILE_DIR=` value in the same argv.
- `test_unpinnable_dynamic_include_fails_without_running_make` (AC-4, fake `Popen`):
  - parametrized words: `$(OTHER)/x.mk`, `${IDP_PROFILE_DIR}/x.mk`, `$(IDP_PROFILE_DIR)x.mk`, `a$$b.mk`,
    `$(IDP_PROFILE_DIR)/$(X).mk`, `$(IDP_PROFILE_DIR)/*.mk`, `$(IDP_PROFILE_DIR)/`;
  - one example `alpha` with `-include <word>` and a valid `bravo`;
  - expected stdout `FAIL examples/alpha: dynamic include '<word>' cannot be pinned`, then `PASS examples/bravo` and
    the summary; exit 1; `Popen` called only for `bravo`;
  - one extra case with a word of more than 200 characters checks the truncation.
- `test_make_cannot_remake_profile_dir_include` (AC-4, `needs_make`):
  - `tmp_path/profile/defaults.mk` (benign, `OLD_MTIME`) and `tmp_path/profile/evil.src` (`EVIL_INCLUDE`,
    `NEW_MTIME`);
  - monkeypatch `conformance.profiles.resolve` to return `{"dir": str(tmp_path / "profile")}`;
  - the Makefile appends `include $(IDP_PROFILE_DIR)/defaults.mk` and
    `$(IDP_PROFILE_DIR)/defaults.mk: $(IDP_PROFILE_DIR)/evil.src` with recipe `\tcp $< $@`;
  - expected: PASS, `validated-ran` present, no `evil-ran`, `defaults.mk` byte-for-byte unchanged;
  - red-first today (make remakes the profile file and restarts).
- `test_conformance_scans_makefile_once_and_pins_from_validated_scan` (AC-5):
  - wrap `contract.makefile_targets`: count calls and return
    `dataclasses.replace(scan, include_words=(*scan.include_words, "from-validated-scan.mk"))`;
  - fake `Popen`;
  - expected: PASS, exactly one wrapper call, and `--assume-old=from-validated-scan.mk` in the argv;
  - red today (two calls).
- Remove `test_conformance_fails_when_makefile_changes_between_scans` (IDP-22 AC-5; it asserts the second scan, spec
  Q14).
- Unchanged and still green:
  - `test_check_example_parses_idp_yaml_once_for_validation_and_profile` (its `stub_make` takes `*args`-compatible
    four arguments);
  - `test_conformance_module_uses_no_private_contract_members`;
  - all IDP-22 AC-5/AC-7 real-make tests;
  - `test_conformance_reports_make_timeout` (its example has no `$` include).

`tests/conformance/test_examples.py`: no new test. `test_platform_examples_pass_conformance_within_60_seconds` and
`test_conformance_fails_example_with_gnumakefile_bypass` must stay green with minimal-service's new profile pin.

## Changes
| File | Change |
|------|--------|
| packages/idp-gate/src/idp_gate/contract.py | `_logical_lines`; `_parsed_lines` uses it; `_rule_names` collapses `\`+newline; `_FOREIGN_SEPARATOR`, `_foreign_separator` and the check in `_load_makefile`; `MakefileScan.dynamic_include_words`, `_dynamic_include_words`, `_Scanner.dynamic`/`record_dynamic` (shared spelling cap); `_EMPTY_SCAN`, `_make_contract`; `check_make_contract` delegates; `load_service` returns `(doc, violations, scan)`. (AC-1, AC-2, AC-3, AC-4, AC-5) |
| packages/idp-gate/src/idp_gate/conformance.py | `PROFILE_DIR_PREFIX`, `_profile_names`, `_shown`; `check_example` uses the scan from `load_service` (second scan removed), fails `dynamic include '<word>' cannot be pinned`, and pins resolved profile words; module docstring. (AC-4, AC-5) |
| packages/idp-gate/tests/test_contract.py | AC-1, AC-2, AC-3 and AC-4 scanner/validate tests; linear-time continuation case. |
| packages/idp-gate/tests/test_conformance.py | AC-1, AC-2 and AC-4 real-make tests; AC-4 argv and rejection tests; AC-5 single-scan test; IDP-22 two-scan test removed. |
| docs/platform/service-contract.md | "How `idp validate` checks it": make's logical-line rule (continuations joined everywhere, CRLF accepted); new line-separator violation with message, reason and remedy; delete "line continuations in rule lines ... not interpreted" and the D7 comment-continuation limitation; the AC-7 "why it is enough" text now says a line after a continued line is read exactly as make reads it; `$` words are skipped by validate but conformance pins `$(IDP_PROFILE_DIR)/...` and fails the rest; the Build profile defaults bullet mentions the conformance pin. (DoD) |
| docs/platform/onboarding.md | Reference example paragraph: remove "scans the Makefile again"; pins come from the validated scan; `$(IDP_PROFILE_DIR)/<rest>` is pinned as `<profile dir>/<rest>`; any other `$` include fails `dynamic include '<word>' cannot be pinned` without running make; residual risk narrowed to glob words, `$(eval ...)`/`define`-body includes and `override IDP_PROFILE_DIR`. (DoD) |
| CHANGELOG.md | Under `[Unreleased]` / `### Changed`: `- IDP-28: idp validate reads Makefiles in make's logical lines (backslash-newline continuations joined before comments and define/endef, so a continuation can no longer hide includes or credit targets after a continued comment) and rejects line separators make does not use (lone CR, VT, FF, FS/GS/RS, NEL, U+2028/U+2029; CRLF stays accepted); idp conformance pins $(IDP_PROFILE_DIR)/<file> includes with the resolved profile path, fails any other $ include (dynamic include '<word>' cannot be pinned) without running make, and pins from the single validated Makefile scan.` (DoD) |

Unchanged: root `Makefile`, root `pyproject.toml`, `.github/**`, `cli.py`, `profiles.py`, `examples/**`,
`build-profiles/**`, `find_examples`, `Result`, `_run_make_verify`, `_assume_old`, all caps, the CLI output format and
exit codes.

## Interfaces and data
- `idp validate` adds one violation kind, `Makefile: '<file>' contains a line separator make does not use (...); use LF
  or CRLF line endings`. Target crediting changes only where make and the scanner disagreed:
  - a target on a line after a continued line or a continued comment is no longer credited;
  - an include after a continued line is no longer followed.
  A tenant whose `verify` was only "found" behind a continued comment now gets `missing required target` (intended:
  make never defined it).
- `idp conformance` adds the result reason `dynamic include '<word>' cannot be pinned`. The make argv gains
  `--assume-old=<profile_dir>/<rest>` for profile includes. There is no second scan, so the "files changed between
  scans" failure disappears.
- Python API:
  - `MakefileScan.dynamic_include_words` (defaulted, backwards compatible);
  - `contract.load_service` returns a 3-tuple (breaking for direct callers; in-repo callers are updated:
    `validate_service`, `conformance.check_example`);
  - `check_make_contract`, `validate_service` and `makefile_targets` signatures unchanged;
  - new public constant `conformance.PROFILE_DIR_PREFIX`.
- No schema, dependency or config change.

## Telemetry
None (CLI only). Operator signals: the new validate violation line and the new conformance FAIL reason.

## Risks, rollout and rollback
- Risk: GNU make's reader differs from the model on 3.81 or 4.x (continuation in comments or define bodies, CRLF).
  Detection: the real-make tests run locally (3.81) and in CI (4.x), plus the T1 scratchpad check. Mitigation: stop
  and revise the spec (A1).
- Risk: a tenant Makefile saved with CR-only line endings (old Mac) or containing a form feed (some editors insert
  `^L` page breaks) now fails `idp validate`. Detection: the violation names the file and the character. Mitigation:
  the documented remedy (convert to LF or CRLF). make itself would already misread such a file.
- Risk: target crediting changes for Makefiles with continued comments or continued lines before a rule. Detection:
  `missing required target` names the target. Mitigation: it is correct (make agrees). In-repo Makefiles have
  continuations only inside recipes (checked), so nothing changes there.
- Risk: the profile pin depends on `IDP_PROFILE_DIR` resolving to the passed value. `override` or `$(eval)` can
  redirect it (residual, spec Q6). Detection: none automatic. Mitigation: examples are platform-owned and reviewed;
  documented.
- Risk: the define-nesting mismatch (spec Q16) stays a bypass of the same kind until it is decided. Mitigation: listed
  as an open question with a reproduction; examples are reviewed.
- Risk: removing the second scan widens nothing: make reads the files later anyway (the TOCTOU between validation and
  make is unchanged and accepted, IDP-23).
- Risk: `load_service` callers outside the repo break on the 3-tuple. Detection: mypy and the tests in the repo.
  Mitigation: none outside the repo (internal package).
- Rollout: lands with the PR. CI runs `make verify` (includes `make conformance`). No migration.
- Rollback: revert the PR. No data or config to undo.

## Amendment 1 (2026-10-10, after review loop 1): AC-6..AC-14
T1-T6 are done (265eefb, 3a68006, 31fea1b, 864e721, 1959fa4, 429b6a2). Agent work only; no protected path, no new
dependency, caps unchanged. Spec decisions: Q2, Q7, Q15, Q16 superseded; Q18-Q28 new. The design rule behind every
define change (spec "Amendment 1 edge cases"): the scanner may over-scan, but never hides a line any make version
reads in any conditional branch.

### Scanner (`contract.py`)
1. **Collapsed logical lines (AC-6, AC-7, AC-8)**:
   - New `_collapse(raw: str) -> str` (make's `collapse_continuations`, A7). Split `raw` on `"\n"` (the joins made by
     `_logical_lines`; each part except the last ends in an odd backslash run). For each part except the last:
     `n = len(part) - len(part.rstrip("\\"))`, keep `part[:-n] + "\\" * (n // 2)`, and if `n // 2 == 0` also
     `rstrip(" \t")`. Strip `" \t"` from the start of every part after the first. Join the parts with one space.
     Linear: each part is stripped and joined once. A raw line without `"\n"` is returned unchanged (fast path).
   - `_parsed_lines(text)` now returns `tuple[list[_Line], list[str]]`:
     - `_Line` is a small frozen dataclass (or `NamedTuple`) `code: str` (collapsed, comment-stripped) and
       `raw_code: str` (uncollapsed, comment-stripped; only for the IDP-22 AC-7 check);
     - the second item lists define problems in line order (`"ambiguous"` for AC-10, `"modifier"` for AC-12).
   - For each raw logical line: `collapsed = _collapse(raw)`, `code = _COMMENT.split(collapsed, 1)[0]`,
     `raw_code = _COMMENT.split(raw, 1)[0]` (same comment position: collapsing only changes text at `\`+newline,
     where the character before a `#` is a newline or a space, never `\`).
   - `_rule_names(line)` drops its `replace("\\\n", " ")` (the input is already collapsed). A collapsed line starting
     with a blank is still not credited (spec Q18).
   - `_Scanner.visit` iterates `_Line`s: `_rule_names(l.code)`; include line test on `l.code`; IDP-22 AC-7 check
     `"\\" in l.raw_code`; `_dynamic_include_words(l.code)` and `_include_words(l.code)`.
2. **Define tracking (AC-8, AC-9, AC-10, AC-12)**, inside `_parsed_lines`; depth is a bool (`in_define`):
   - In a body: `_body_line(collapsed) -> Literal["end", "ambiguous", "text"]`:
     - tab-prefixed: `p = collapsed.lstrip(" \t")`; `"ambiguous"` if `p == "endef"` or `p[:5] == "endef"` and
       `p[5:6] in {" ", "\t", "#"}`; else `"text"`;
     - otherwise `p = collapsed.lstrip(" \t")`; `"end"` if `p == "endef"` or (`p[:5] == "endef"` and
       `p[5] in " \t"`); `"ambiguous"` if `p[:6] == "endef#"`, or `p == "define"`, or (`p[:6] == "define"` and
       `p[6] in " \t"`); else `"text"`.
     - `"end"` leaves the body; `"ambiguous"` appends `"ambiguous"` to the problems and stays in the body (no
       nesting count); body lines are never emitted.
   - At depth 0, non-tab raw line: `_DEFINE_LINE = re.compile(r"[ \t]*((?:(?:override|export|unexport|private)[ \t]+)*)define(?:[ \t]|$)(?![ \t]*(?::{1,3}|[+?!])?=)")`
     matched on `code`. No match: an ordinary line. Modifiers (`group(1).split()`) empty or `["override"]`: enter the
     body. Anything else: append `"modifier"` to the problems and emit the line as an ordinary line (no block).
   - Tab-prefixed lines at depth 0 never open a block (unchanged).
   - `_DEFINE_START` and `_DEFINE_END` are replaced by `_DEFINE_LINE` and `_body_line`.
3. **Characters make reads differently (AC-11)**:
   - `_FOREIGN_CHARACTER = re.compile("[\x00-\x08\x0e-\x1b\x1f\xa0  -   　]")` and
     `_foreign_character(name, match) -> Violation` with the AC-11 message (`U+XXXX`).
   - `_load_makefile`: after the `_FOREIGN_SEPARATOR` check, `if (m := _FOREIGN_CHARACTER.search(text)): return
     _foreign_character(name, m)`.
   - Fix the `_FOREIGN_SEPARATOR` comment (m2): it rejects line separators make does not use (make splits on LF only
     and drops a CR before LF) so that no line boundary is ambiguous; it is not about `splitlines()` any more.
   - `_locate`'s NUL guard stays (spec Q26).
4. **Define problems become violations (AC-10, AC-12)**: `_load_makefile(resolved, name)` returns
   `tuple[list[_Line], list[Violation]] | Violation`. It maps `"ambiguous"` to `_ambiguous_define_line(name)` and
   `"modifier"` to `_modifier_define(name)` (AC-10/AC-12 messages, `path` `Makefile`). `visit` reports each through
   `self.problem` (cap 20) and then scans the lines.
5. **`~` include words (AC-13)**: `_lexically_outside(word, root)` returns True also when
   `_LEADING_DOT_SLASH.sub("", word).startswith("~")`, with `_LEADING_DOT_SLASH = re.compile(r"^(?:\./+)+")`
   (amendment 2: make strips leading `./` runs before tilde expansion; anchored, linear). The violation shows the
   word as written.
   - T13 deviation: `_Scanner.queue` also skips recording the spelling of any `_lexically_outside` word (still queued, so `visit` reports it in the same order under the same caps), because IDP-17 recorded outside words in `include_words` despite Q24's "not queued" intent; outside words always fail validation so are never pinned, and they no longer count toward the spelling cap but stay bounded by the normalised-word and problem caps.
6. **Public display helper (spec Q28, m8)**: rename `_shown` to `shown` and update its contract call sites
   (`_cannot_read`, `_outside`, `_backslash_include`, `_foreign_separator`, the size message and the new messages).

### Conformance (`conformance.py`)
7. **Profile words (AC-14)**: in `_profile_names`, a word is also unpinnable when `".." in rest.split("/")` or
   `rest.startswith("/")`. Docstring updated.
8. **Minors**: delete `conformance._shown`; use `contract.shown(unpinnable)` (m8). At the `load_service` call site,
   a comment: the scan is empty only when the Makefile was not scanned, which always comes with violations, so it is
   never used below (m3). No `assert` (bandit B101).
9. Module docstring: collapsed logical lines, define rules, the new character violation, `~` words, `..`/absolute
   profile words, and the follow-up residual risks (default include path, `.RECIPEPREFIX`/`load`, TOCTOU). Done in T7.

### Tests (new tests tagged `@pytest.mark.ac("IDP-28:AC-n")`, written red-first)
`packages/idp-gate/tests/test_contract.py` (reuse `_scan_text`, `_write_idp`, `_write_makefile`, `_run`,
`_make_messages`, `ALL_TARGETS`, `BACKSLASH_INCLUDE`, `FOREIGN_SEPARATOR`):
- `test_continuations_are_collapsed_before_directives` (AC-6), parametrized:
  - the AC-6 layout (`define Y`, `body`, `\`, `  endef`, `-include gen.mk`, `gen.mk:`) in LF and in CRLF:
    `include_words == ("gen.mk",)`, `"gen.mk" in targets`, no violations;
  - `define \` + `  Y` / `inside:` / `endef` / `after:` credits `after` only (the collapsed `define Y` opens a block);
  - `X = a\\\` + `-include gen.mk` (three backslashes: one literal backslash kept, then a continuation) records no
    include word and gives no violation (one assignment line, as in make);
  - `lint  \` + `  verify:` credits `lint` and `verify` (blanks on both sides of the continuation collapse to one
    space).
- `test_continued_include_directive_is_a_backslash_violation` (AC-7), parametrized LF, CRLF and `\` + `   -include
  gen.mk` (leading blanks): exact stdout `idp.yaml: Makefile: include line in 'Makefile' {BACKSLASH_INCLUDE}`,
  exit 1, `gen.mk` not in `include_words`; negative case `X = \` + `-include gen.mk`: exit 0 and `include_words == ()`.
- `test_override_continued_into_define_hides_its_body` (AC-8), parametrized LF and CRLF (`override \` + `define Y` /
  `verify:` / `endef`) and the Q18 case (`\` + `verify:`): every other required target defined; exact stdout
  `idp.yaml: Makefile: missing required target 'verify'`, exit 1.
- `test_define_body_lines_close_and_nest_like_make` (AC-9), parametrized body lines `define#`, `define#x`,
  `override define B`, `export define B`, `\tdefine B`, `defineX` and closing lines `endef`, `  endef`, `endef # done`,
  one CRLF case: `define A` / `<body>` / `inside:` / `<closing>` / `after:` credits `after` only and gives no
  violation.
- `test_ambiguous_define_body_line_is_a_violation` (AC-10), parametrized `define B`, `define`, `define # c`,
  `endef#c`, `\tendef`, `\tendef#c`, a CRLF case and an in-include case (`include common.mk`, the body in
  `common.mk`): exact stdout `idp.yaml: Makefile: define body in '<file>' has a line make reads differently in
  skipped conditional branches (...); remove it`, exit 1. Plus one scanner assertion that two offending lines give two
  violations.
- `test_character_make_reads_differently_is_a_violation` (AC-11): parameters computed at import:
  `[c for c in map(chr, range(0x110000)) if c.isspace() and c not in " \t\n\r\x0b\x0c\x1c\x1d\x1e\x85  "]`
  plus `chr(0)`..`chr(8)` and `chr(0x0e)`..`chr(0x1b)`, each placed inside a word after `lint:`. Exact stdout
  `idp.yaml: Makefile: 'Makefile' contains a control or space character make reads differently (U+XXXX); use only
  spaces, tabs and LF or CRLF line endings`, exit 1. One in-include case (`'common.mk'`, U+00A0) and one `--json`
  case.
- `test_spaces_tabs_and_crlf_are_accepted` (AC-11): a CRLF Makefile with tabs and runs of spaces between words is
  `valid`, exit 0; DEL (U+007F) and U+FEFF inside a recipe line are accepted too.
- `test_define_with_export_unexport_or_private_is_a_violation` (AC-12), parametrized rejected lines
  (`export define X = 1`, `private define X = 1`, `unexport define X`, `override export define X`,
  `export override define X`, CRLF `private define X = 1`) with exact stdout, exit 1; accepted lines (`define X`,
  `override define X`, each followed by `endef`; `export define ?= 3`; `define X = 1` / `endef`) with exit 0.
- `test_include_word_starting_with_tilde_is_a_violation` (AC-13): `_make_messages` gives
  `["include '~/evil.mk' is outside the service directory"]` for `-include ~/evil.mk`, likewise `~user/x.mk` and
  `~`; amendment 2 adds `./~/evil.mk`, `.//~/evil.mk` and `././~/evil.mk` (message shows the word as written, e.g.
  `include './~/evil.mk' is outside the service directory`). Accepted literal words: `-include a~b.mk` and
  `-include sub/../~/x.mk` are valid and recorded in `include_words` (the latter normalises to `~/x.mk` inside the
  service directory, so the IDP-17 outside check does not fire, and make does not expand it).
- Changed (spec "Tests that change"): `test_define_bodies_are_skipped_including_nested_ones` (accepted forms only);
  `test_nul_byte_in_include_word_is_a_violation_not_a_traceback` (AC-11 message).
- Linear-time cases: `test_many_continued_lines_are_joined_in_linear_time` gains `"\\\n  x" * 200_000` (collapsing);
  `test_long_lines_without_colon_are_parsed_in_linear_time` gains `"override " * 100_000 + "x\n"`.

`packages/idp-gate/tests/test_conformance.py` (reuse `_write_example`, `_append_to_makefile`, `_temporary_profile`,
`_fake_make_on_path`, `_recording_popen`, `OLD_MTIME`, `NEW_MTIME`, `EVIL_INCLUDE`, `GENERATE_EVIL`,
`STRIPPED_MAKE_VARS`, `needs_make`). Every `needs_make` test: `os.utime(Makefile, (OLD_MTIME, OLD_MTIME))`, the
stripped make variables deleted, no sleeps; a shared helper `_assert_rejected_before_make(directory, capsys, code)`
may assert `FAIL ...: idp validate: 1 violation(s)`, the detail line, exit 1, and only `Makefile`/`idp.yaml` (plus
any test-written source) in the directory.
- `test_continued_endef_cannot_hide_generated_include` (AC-6, `needs_make`): the AC-6 layout written with
  `write_bytes` and CRLF line endings (the recipe line too; make strips the CR before LF). Expected PASS,
  `validated-ran`, no `evil-ran`, no `gen.mk`.
- `test_conformance_rejects_continued_include_directive_without_running_make` (AC-7, `needs_make`): `\` +
  `-include gen.mk` + `gen.mk:` + `{GENERATE_EVIL}gen.mk`. Expected FAIL with the AC-7 detail line.
- `test_non_nesting_define_body_line_cannot_hide_generated_include` (AC-9, `needs_make`, parametrized `define#` and
  `override define B`): `define A` / `<line>` / `endef` / `-include gen.mk` / the generating rule. Expected PASS,
  `validated-ran`, no `evil-ran`, no `gen.mk`.
- `test_define_in_skipped_conditional_cannot_hide_generated_include` (AC-10, `needs_make`): `ifeq (a,b)` /
  `define A` / `define B` / `endef` / `endif` / `-include gen.mk` / the generating rule. Expected FAIL with the AC-10
  detail line.
- `test_conformance_rejects_characters_make_reads_differently_without_running_make` (AC-11, `needs_make`,
  parametrized): `-include a.mk\x1fb.mk` plus the rule `a.mk\x1fb.mk:` with a recipe writing `EVIL_INCLUDE` to `'$@'`;
  the same with U+00A0; `define\x1fX = 1` plus the AC-1 `gen.mk` attack. Files written with `encoding="utf-8"`.
  Expected FAIL with the AC-11 detail line and no generated file.
- `test_modifier_define_cannot_hide_generated_include` (AC-12, `needs_make`, parametrized `private define X = 1`
  and `export define X = 1`, each followed by the `gen.mk` attack). Expected FAIL with the AC-12 detail line.
- `test_tilde_include_cannot_read_home_file` (AC-13, `needs_make`, parametrized `~/evil.mk` and `./~/evil.mk`
  (amendment 2)): `monkeypatch.setenv("HOME", str(tmp_path / "home"))`, `home/evil.mk` holding `EVIL_INCLUDE`, the
  example appends `-include <word>`. Expected FAIL with `Makefile: include '<word>' is outside the service
  directory`, no `evil-ran`.
- `test_profile_dir_include_cannot_read_outside_profile_dir` (AC-14, `needs_make`): `_temporary_profile`,
  `tmp_path/outside/evil.mk` holding `EVIL_INCLUDE`, the example appends
  `-include $(IDP_PROFILE_DIR)/../outside/evil.mk`. Expected stdout
  `FAIL examples/<x>: dynamic include '$(IDP_PROFILE_DIR)/../outside/evil.mk' cannot be pinned` and the summary,
  exit 1, no `evil-ran`.
- `test_unpinnable_dynamic_include_fails_without_running_make` gains `@pytest.mark.ac("IDP-28:AC-14")` and the cases
  `dotdot-segment` (`$(IDP_PROFILE_DIR)/../x.mk`), `nested-dotdot` (`$(IDP_PROFILE_DIR)/a/../../x.mk`),
  `bare-dotdot` (`$(IDP_PROFILE_DIR)/..`) and `absolute-rest` (`$(IDP_PROFILE_DIR)//etc/x.mk`).
- Changed: `test_profile_dir_include_is_pinned_with_resolved_path` pins `$(IDP_PROFILE_DIR)/sub/extra.mk` instead of
  `../shared/extra.mk`.
- Unchanged and still green: every IDP-22 and IDP-28 AC-1..AC-5 test not listed above,
  `test_conformance_module_uses_no_private_contract_members` (now satisfied by the public `contract.shown`),
  `tests/conformance/test_examples.py` (minimal-service PASSes).

### Changes (amendment 1)
| File | Change |
|------|--------|
| packages/idp-gate/src/idp_gate/contract.py | `_collapse`; `_Line`; `_parsed_lines` returns lines and define problems; `_DEFINE_LINE` and `_body_line` replace `_DEFINE_START`/`_DEFINE_END`; `_rule_names` without its own collapse; `visit` uses `code`/`raw_code` and reports define problems; `_FOREIGN_CHARACTER`, `_foreign_character`, the check in `_load_makefile`, corrected `_FOREIGN_SEPARATOR` comment; `_ambiguous_define_line`, `_modifier_define`; `~` in `_lexically_outside`; `_shown` renamed `shown`. (AC-6..AC-13, Q28) |
| packages/idp-gate/src/idp_gate/conformance.py | `_profile_names` rejects `..` segments and a leading `/`; `_shown` removed in favour of `contract.shown`; m3 comment; module docstring (T7). (AC-14, Q28) |
| packages/idp-gate/tests/test_contract.py | AC-6..AC-13 tests; two linear-time cases; the two changed IDP-17 tests. |
| packages/idp-gate/tests/test_conformance.py | AC-6, AC-7, AC-9..AC-14 real-make tests; AC-14 cases and mark on the rejection test; the changed pin test. |
| docs/platform/service-contract.md, docs/platform/onboarding.md, CHANGELOG.md | T7, extended to the amendment (spec Q17). |

### Interfaces and data (amendment 1)
- `idp validate` adds three violation kinds (AC-10, AC-11, AC-12). `~` include words reuse the IDP-17 "outside the
  service directory" message. Target crediting and include following change only where make and the scanner
  disagreed (collapsed continuations, define bodies).
- `idp conformance` keeps its result reasons; more words give `dynamic include '<word>' cannot be pinned`.
- Python API: `contract.shown` becomes public (was `_shown`); `MakefileScan`, `load_service`, `check_make_contract`
  and `makefile_targets` signatures are unchanged.

### Risks (amendment 1)
- Risk: make's reader differs from A7/A8/A12/A13 on 3.81 or 4.x. Detection: T8's scratchpad checks (3.81) and the
  real-make tests in CI (4.x). Mitigation: AC-10 and AC-12 fail closed whatever the result; if A7 or A12 is wrong, stop
  and revise the spec.
- Risk: a tenant Makefile with nested defines, `export define`, a raw control byte (for example ESC in a recipe) or a
  non-breaking space now fails `idp validate`. Detection: the message names the file and the character or line kind.
  Mitigation: documented remedies; spec Q19, Q20 and Q22 record the alternatives.
- Risk: the define rules over-scan (for example `define := 1` on 3.81, or a modifier define's body), which can credit a
  target make never defines. Mitigation: make then fails at run time (`No rule to make target`), and conformance
  reports it; it never hides an include.
- Risk: residual reader features (`.RECIPEPREFIX`, `load`, default include directories) stay unmodelled. Mitigation:
  follow-ups (spec "Out of scope / follow-ups"); examples are platform-owned and reviewed.
