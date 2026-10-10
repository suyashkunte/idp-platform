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
