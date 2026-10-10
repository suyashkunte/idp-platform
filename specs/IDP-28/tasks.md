# IDP-28: tasks

All tasks are agent tasks. None touches a protected path (`.claude/idp-protected-paths.txt`: root `Makefile`,
root `pyproject.toml`, `infra/**`, plugin hooks, `.claude-plugin/**`, `.pre-commit-config.yaml`, plus the built-in
defaults), so there is no human task.
Each task writes its tests first and sees them fail for the expected reason before implementing. Each ends with the
package tests green. Test names and exact expectations are in plan.md ("Tests").

- [x] T1 Logical lines.
  - First, confirm in the scratchpad (not committed) with the local GNU Make 3.81 that a comment ending in `\`
    swallows the next line, that `x \` + `endef` inside a define body does not close it, and that CRLF `\` continues.
    If any of these differs, stop and revise the spec (A1). Also try the spec Q16 reproduction and record the result
    for the human.
  - Then add `test_logical_lines_join_odd_trailing_backslashes`, `test_continuation_into_define_does_not_hide_later_lines`,
    `test_comment_ending_in_backslash_continues_onto_next_line`, `test_trailing_comment_ending_in_backslash_hides_next_line`
    and the linear-time continuation case (red).
  - Then implement `_logical_lines`, the `_parsed_lines` switch and the `_rule_names` collapse.
  - Confirm that the IDP-17/IDP-22 scanner tests (incl. `test_include_line_with_backslash_is_a_violation`, all four
    cases), `test_root_make_verify_runs_conformance` and `test_default_targets_have_recipes_in_defaults_mk` stay green
    unchanged.
  - (AC-1, AC-3) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py.
- [x] T2 Real-make continuation attack.
  - Add `needs_make` `test_continuation_cannot_hide_generated_include_from_pinning` (explicit `os.utime`, no sleeps).
  - Check red-first by stashing T1's `contract.py` change (make generates `gen.mk` and `evil-ran` appears), then
    green with T1.
  - (AC-1) Files: packages/idp-gate/tests/test_conformance.py.
- [x] T3 Foreign line separators.
  - Add `test_line_separator_make_does_not_use_is_a_violation` (every listed separator, an in-include case, `--json`),
    `test_crlf_makefile_is_accepted`, and the `needs_make` `test_conformance_rejects_foreign_line_separators_without_running_make`
    (`\x0b`, `\x85`; explicit `os.utime`, no sleeps). All red.
  - Then implement `_FOREIGN_SEPARATOR`, `_foreign_separator` and the check in `_load_makefile`.
  - (AC-2) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py,
    packages/idp-gate/tests/test_conformance.py.
- [x] T4 Single validated scan.
  - Add `test_conformance_scans_makefile_once_and_pins_from_validated_scan` (red: two calls, no sentinel pin).
  - Then implement `_EMPTY_SCAN`, `_make_contract`, the `check_make_contract` delegation, the 3-tuple
    `load_service`, and `check_example` using that scan (second `makefile_targets` call removed).
  - Delete `test_conformance_fails_when_makefile_changes_between_scans` (spec Q14).
  - Confirm that `test_check_example_parses_idp_yaml_once_for_validation_and_profile`,
    `test_conformance_module_uses_no_private_contract_members`, all IDP-17 validate tests and mypy strict stay green.
  - (AC-5) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/src/idp_gate/conformance.py,
    packages/idp-gate/tests/test_conformance.py.
- [x] T5 Dynamic include words in the scanner.
  - Add `test_makefile_scan_records_dynamic_include_words` (order, dedup, `$$`, glob excluded, shared spelling cap)
    (red).
  - Then implement `MakefileScan.dynamic_include_words`, `_dynamic_include_words` and `_Scanner.record_dynamic`.
  - Confirm that `test_makefile_scan_records_literal_include_words_as_written` and
    `test_makefile_scan_caps_recorded_include_spellings` stay green unchanged.
  - (AC-4) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py.
- [x] T6 Pin or reject dynamic includes in conformance.
  - Add `test_profile_dir_include_is_pinned_with_resolved_path`, `test_unpinnable_dynamic_include_fails_without_running_make`
    and `needs_make` `test_make_cannot_remake_profile_dir_include` (monkeypatched `profiles.resolve` to a `tmp_path`
    profile; never the real profile dir) (red).
  - Then implement `PROFILE_DIR_PREFIX`, `_profile_names`, `_shown` and the `check_example` steps.
  - Run `test_platform_examples_pass_conformance_within_60_seconds` and `test_conformance_fails_example_with_gnumakefile_bypass`
    (minimal-service must still PASS with the new profile pin).
  - (AC-4) Files: packages/idp-gate/src/idp_gate/conformance.py, packages/idp-gate/tests/test_conformance.py.
- [ ] T7 Docs and wrap-up. Amendment 1: do this task last, after T14.
  - `docs/platform/service-contract.md`: logical lines, the separator violation, delete the continuation and D7
    limitations, the AC-7 rationale text, the conformance profile pin.
  - `docs/platform/onboarding.md`: the single scan, profile pin, `dynamic include ... cannot be pinned`, and the
    residual risk narrowed (the D5-D7 and define/continuation notes removed or adjusted).
  - The `conformance.py` module docstring.
  - An IDP-28 line under `[Unreleased]` / `### Changed` in `CHANGELOG.md`.
  - Amendment 1 additions:
    - `service-contract.md`: continuations are collapsed as make does before directives are recognised; a continued
      include line (also one starting with `\`) is an AC-7 violation; a rule line that starts with a blank, also
      after a continuation, is not credited (spec Q18); define rules (`define NAME` and `override define NAME`
      blocks; body lines closing like make; the AC-10 and AC-12 violations with message, reason and remedy); the
      AC-11 character violation (set, message, remedy); `~` include words are outside the service directory.
    - `onboarding.md`: `$(IDP_PROFILE_DIR)/<rest>` with a `..` segment or leading `/` cannot be pinned; residual
      risks extended with the follow-ups (make's default include directories, `.RECIPEPREFIX`/`load`, unbounded make
      output, TOCTOU/IDP-23, `make -pn` ADR).
    - The `conformance.py` docstring and the CHANGELOG line mention AC-6..AC-14 in one or two clauses.
  - Run `make verify` (includes `make conformance`) and `idp spec-trace IDP-28` (AC-1..AC-14); both green.
  - (AC-1..AC-14) Files: docs/platform/service-contract.md, docs/platform/onboarding.md, CHANGELOG.md,
    packages/idp-gate/src/idp_gate/conformance.py.

## Amendment 1 tasks (after review loop 1)
Same rules as above: tests first and red for the expected reason (for real-make tests, red against the current
`contract.py`/`conformance.py`, which still has the bypass), then the implementation, then the package tests green.
Real-make tests use `needs_make`, explicit `os.utime` with `OLD_MTIME`/`NEW_MTIME` and no sleeps, and must hold on GNU
Make 3.81 (local) and 4.x (CI). Test names and expectations are in plan.md ("Amendment 1", "Tests"). T7 runs after
T14.

- [x] T8 Confirm make's reader in the scratchpad (not committed, no repo change). Done with a finding (amendment 2):
  every assumption held on 3.81 except A13. make strips leading `./` runs before tilde expansion, so
  `-include ./~/x.mk` reads `$HOME/x.mk` (scratchpad `t8/out.txt`). A8 confirmed (a skipped-branch nested define
  does not hide the include from make, so AC-10 failing closed is right); Q18 confirmed (make defines `verify` from
  `\` + `verify:`). The `./~` case is folded into T13; spec AC-13 and A13 amended.
  - With the local GNU Make 3.81, confirm: (a) a line holding only `\` + `  endef` closes a define body, also with CRLF
    (A7); (b) `override \` + `define Y` opens a block (A7, A12); (c) `override define Y` inside an `ifeq (a,b)` branch
    is skipped up to its `endef` (A12); (d) `private define X = 1` and `export define X = 1` are not define blocks
    on 3.81 (A12); (e) `ifeq (a,b)` / `define A` / `define B` / `endef` / `endif` / `-include gen.mk`: does make read
    the include (A8)? (f) `define A` / `endef#c` / `x:` / `endef` in a taken branch: `endef#c` does not close (AC-10);
    (g) `\` + `verify:` defines `verify` (Q18); (h) `-include ~/x.mk` reads `$HOME/x.mk` (A13).
  - If (a), (b), (c) or (h) differs, stop and revise the spec. Record (e) and (g) for the human (they change only
    docs wording). Optional: repeat on a 4.x if one is available.
  - (AC-6, AC-8, AC-10, AC-12, AC-13) Files: none.
- [x] T9 Collapse continuations before directives.
  - Add `test_continuations_are_collapsed_before_directives`, `test_continued_include_directive_is_a_backslash_violation`,
    `test_override_continued_into_define_hides_its_body` and the collapsing case in
    `test_many_continued_lines_are_joined_in_linear_time` (red).
  - Add `needs_make` `test_continued_endef_cannot_hide_generated_include` (CRLF) and
    `test_conformance_rejects_continued_include_directive_without_running_make` (red: PASS and `evil-ran`).
  - Then implement `_collapse`, `_Line` (`code`, `raw_code`), the `_parsed_lines` switch, `visit` on `code` with the
    AC-7 check on `raw_code`, and drop `_rule_names`' own collapse. Keep the existing define regexes in this task.
  - Confirm all AC-1/AC-3 tests and `test_include_line_with_backslash_is_a_violation` (four cases) stay green.
  - (AC-6, AC-7, AC-8) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py,
    packages/idp-gate/tests/test_conformance.py.
- [x] T10 Define bodies like make; ambiguous body lines fail closed.
  - Add `test_define_body_lines_close_and_nest_like_make` and `test_ambiguous_define_body_line_is_a_violation`
    (red), and `needs_make` `test_non_nesting_define_body_line_cannot_hide_generated_include` (`define#`,
    `override define B`; red: PASS and `evil-ran` for `define#`) and
    `test_define_in_skipped_conditional_cannot_hide_generated_include` (red: PASS).
  - Then implement `_body_line`, the boolean depth, the `"ambiguous"` problem and `_ambiguous_define_line`, and the
    `_load_makefile`/`visit` plumbing for define problems.
  - Rewrite `test_define_bodies_are_skipped_including_nested_ones` with accepted forms only (spec "Tests that
    change"); its nested case moves to the AC-10 test.
  - (AC-9, AC-10) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py,
    packages/idp-gate/tests/test_conformance.py.
- [ ] T11 Define lines with export, unexport or private fail closed.
  - Add `test_define_with_export_unexport_or_private_is_a_violation` and the `override` linear-time case (red), and
    `needs_make` `test_modifier_define_cannot_hide_generated_include` (`private define X = 1`,
    `export define X = 1`; red: PASS, with `evil-ran` on 3.81).
  - Then implement `_DEFINE_LINE` (replacing `_DEFINE_START`/`_DEFINE_END`), the `"modifier"` problem and
    `_modifier_define`.
  - Move the `export define EXPORTED =` case out of `test_define_bodies_are_skipped_including_nested_ones` into the
    new test. Confirm `test_variable_named_define_does_not_start_a_define_block` stays green unchanged.
  - (AC-12) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py,
    packages/idp-gate/tests/test_conformance.py.
- [ ] T12 Characters make reads differently (incl. NUL).
  - Add `test_character_make_reads_differently_is_a_violation` (parameters computed from `str.isspace()` plus the
    C0 controls), `test_spaces_tabs_and_crlf_are_accepted` (red), and `needs_make`
    `test_conformance_rejects_characters_make_reads_differently_without_running_make` (`a.mk\x1fb.mk`, U+00A0,
    `define\x1fX = 1`; red: PASS and the injected content runs).
  - Then implement `_FOREIGN_CHARACTER`, `_foreign_character` and the check in `_load_makefile`; fix the
    `_FOREIGN_SEPARATOR` comment (m2).
  - Update `test_nul_byte_in_include_word_is_a_violation_not_a_traceback` to the AC-11 message (spec "Tests that
    change"). Confirm every AC-2 test stays green unchanged.
  - (AC-11) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py,
    packages/idp-gate/tests/test_conformance.py.
- [ ] T13 Include words starting with `~` (also after leading `./` runs; amendment 2).
  - Add `test_include_word_starting_with_tilde_is_a_violation` (cases `~/evil.mk`, `~user/x.mk`, `~`,
    `./~/evil.mk`, `.//~/evil.mk`, `././~/evil.mk`; accepted literals `a~b.mk`, `sub/../~/x.mk`) (red) and
    `needs_make` `test_tilde_include_cannot_read_home_file` parametrized `~/evil.mk` and `./~/evil.mk` (`HOME`
    monkeypatched to `tmp_path/home`; red: PASS and `evil-ran`).
  - Then add the `~` check to `_lexically_outside`, after stripping leading `./` runs (`_LEADING_DOT_SLASH`).
  - (AC-13) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py,
    packages/idp-gate/tests/test_conformance.py.
- [ ] T14 Profile words outside the profile directory; shared display helper.
  - Add the AC-14 mark and the four new cases to `test_unpinnable_dynamic_include_fails_without_running_make`, and
    `needs_make` `test_profile_dir_include_cannot_read_outside_profile_dir` (red: PASS and `evil-ran`). Change
    `test_profile_dir_include_is_pinned_with_resolved_path` to `$(IDP_PROFILE_DIR)/sub/extra.mk`.
  - Then extend `_profile_names` (`..` segment, leading `/`).
  - Minors: rename `contract._shown` to public `contract.shown` and update its call sites; delete
    `conformance._shown` and use `contract.shown` (m8; `test_conformance_module_uses_no_private_contract_members`
    and the `long-word-truncated`/`quote-in-word` cases stay green); add the m3 comment at the `load_service` call
    site.
  - (AC-14) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/src/idp_gate/conformance.py,
    packages/idp-gate/tests/test_conformance.py.
