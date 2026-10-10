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
- [ ] T5 Dynamic include words in the scanner.
  - Add `test_makefile_scan_records_dynamic_include_words` (order, dedup, `$$`, glob excluded, shared spelling cap)
    (red).
  - Then implement `MakefileScan.dynamic_include_words`, `_dynamic_include_words` and `_Scanner.record_dynamic`.
  - Confirm that `test_makefile_scan_records_literal_include_words_as_written` and
    `test_makefile_scan_caps_recorded_include_spellings` stay green unchanged.
  - (AC-4) Files: packages/idp-gate/src/idp_gate/contract.py, packages/idp-gate/tests/test_contract.py.
- [ ] T6 Pin or reject dynamic includes in conformance.
  - Add `test_profile_dir_include_is_pinned_with_resolved_path`, `test_unpinnable_dynamic_include_fails_without_running_make`
    and `needs_make` `test_make_cannot_remake_profile_dir_include` (monkeypatched `profiles.resolve` to a `tmp_path`
    profile; never the real profile dir) (red).
  - Then implement `PROFILE_DIR_PREFIX`, `_profile_names`, `_shown` and the `check_example` steps.
  - Run `test_platform_examples_pass_conformance_within_60_seconds` and `test_conformance_fails_example_with_gnumakefile_bypass`
    (minimal-service must still PASS with the new profile pin).
  - (AC-4) Files: packages/idp-gate/src/idp_gate/conformance.py, packages/idp-gate/tests/test_conformance.py.
- [ ] T7 Docs and wrap-up.
  - `docs/platform/service-contract.md`: logical lines, the separator violation, delete the continuation and D7
    limitations, the AC-7 rationale text, the conformance profile pin.
  - `docs/platform/onboarding.md`: the single scan, profile pin, `dynamic include ... cannot be pinned`, and the
    residual risk narrowed (the D5-D7 and define/continuation notes removed or adjusted).
  - The `conformance.py` module docstring.
  - An IDP-28 line under `[Unreleased]` / `### Changed` in `CHANGELOG.md`.
  - Run `make verify` (includes `make conformance`) and `idp spec-trace IDP-28` (AC-1..AC-5); both green.
  - (AC-1, AC-2, AC-3, AC-4, AC-5) Files: docs/platform/service-contract.md, docs/platform/onboarding.md, CHANGELOG.md,
    packages/idp-gate/src/idp_gate/conformance.py.
