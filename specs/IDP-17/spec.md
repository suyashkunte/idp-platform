---
ticket: IDP-17
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: auto
---

# IDP-17: idp validate: auto-discover idp.yaml, check the Make contract, add --json

## Context
`idp validate` (iteration 1, IDP-8) only checks `idp.yaml` against the `idp-service.v1` schema. The PR pipeline and the
service template need it to also check that the repo honours the Make contract (I2, `docs/platform/service-contract.md`)
and to emit machine-readable output for job summaries. This ticket adds static Makefile target checks next to the schema
check and an opt-in `--json` flag. Catalog consistency and tighten-only override checks stay in iteration 3.

## Requirements
- **AC-1** Given a directory containing a schema-valid `idp.yaml` and a Makefile with all required targets, when I run `idp validate` with no file argument from that directory, then it validates `./idp.yaml` and exits 0.
  - The `file` argument already defaults to `idp.yaml` (relative to the current directory); this AC is about the full
    check (schema + Make contract) passing in that setup.
  - The Makefile checked is `Makefile` in the same directory as the validated `idp.yaml` (`Path(file).parent / "Makefile"`),
    for both the default and an explicit file argument. ASSUMPTION A1.
  - Text output on success is unchanged: `<file>: valid (idp-service.v1.json)`.
- **AC-2** Given `spec.tests.<kind>: true` for any of smoke, api, e2e, perf, when the Makefile next to `idp.yaml` has no `test-<kind>` target, then validation fails (exit 1) and the violation names the missing target.
  - One violation per missing `test-<kind>` target, `path` = `Makefile`, message
    `missing target 'test-<kind>' (required because spec.tests.<kind> is true)`. ASSUMPTION A2.
  - Only the literal boolean `true` triggers the check; `false`, absent or non-boolean values do not (a non-boolean value
    is already a schema violation).
- **AC-3** Given a Makefile missing one or more required targets (`lint`, `test`, `test-component`, `verify`, `spec-trace`), then validation fails and lists every missing target, not only the first.
  - One violation per missing target, `path` = `Makefile`, message `missing required target '<name>'` (A2).
  - Order: required targets in the contract-table order above, then `test-<kind>` targets in the order smoke, api, e2e,
    perf. Make violations come after schema violations.
  - `verify-fast` and `format` are "recommended" in the contract table and are NOT checked. ASSUMPTION A3.
- **AC-4** Given `--json`, then stdout is exactly one JSON object `{"file", "valid", "schema", "violations": [{"path", "message"}]}` and exit codes are unchanged (0 valid, 1 invalid, 2 usage).
  - Keys in exactly this order; each violation object has exactly `path` and `message`. Printed as one compact line
    (`json.dumps` defaults) followed by a newline; nothing else on stdout. ASSUMPTION A4.
  - `file` = the path string as given/defaulted (e.g. `"idp.yaml"`), not resolved. `valid` = `violations == []`.
  - `schema` = `"idp-service.v1"` (the schema id, without `.json`). ASSUMPTION A5, see Q2.
  - Schema violations keep today's `path` (dotted JSON path, `""` for the document root); Make violations use `"Makefile"`.
  - Exit-2 cases (file not found, argparse usage errors) do not print JSON: stdout stays empty and the message goes to
    stderr as today. ASSUMPTION A6, see Q3.
- **AC-5** (edge) Given no `idp.yaml` in the current directory and no argument, then it exits 2 with a message containing "idp.yaml not found".
  - Already today's behaviour (`validate: idp.yaml not found` on stderr, exit 2); it must remain so, with and without
    `--json`.
  - The ticket writes this AC as `**AC-5 (edge)**`; the marker is moved outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged.
- **AC-6** (edge) Given `idp.yaml` exists but there is no Makefile beside it, then validation fails with a single violation "Makefile not found".
  - Exactly one Make-related violation: `path` = `Makefile`, message `Makefile not found`; no per-target violations are
    added. Exit code 1.
  - "Single" refers to Make violations: schema violations in the same `idp.yaml`, if any, are still reported alongside it
    (with a schema-valid `idp.yaml` the result is exactly one violation). ASSUMPTION A7.
  - Only the file name `Makefile` is looked for; `makefile` and `GNUmakefile` are not recognised. ASSUMPTION A8, see Q5.

## Edge cases and assumptions
- Schema-invalid but parseable `idp.yaml`: Make checks still run and all violations are reported together (A7).
  `spec.tests` is read defensively (ignored unless it is a mapping).
- Unparseable YAML (`invalid YAML: ...`) or a document that is not a mapping: Make checks are skipped; only the
  YAML/schema violation(s) are reported. ASSUMPTION A9.
- Target detection (NFR) - a line defines targets when it matches, at column 0, one or more whitespace-separated names
  followed by `:` or `::` (double-colon rules count) and the colon is not part of `:=`, `::=` or `:::=`. Comments after
  `#` are ignored, so `spec-trace: ## help text` defines `spec-trace`. ASSUMPTION A10.
  - Recipe lines (leading tab) and indented lines are never rule lines.
  - Names containing `%` (pattern rules) and special targets starting with `.` (`.PHONY`, `.DEFAULT`, ...) are ignored.
    A target named only in `.PHONY:` is NOT defined.
  - Variable assignments (`X = y`, `X := y`, `X ?= y`, `X += y`) are not rules.
  - Not handled (documented limitation): `define`/`endef` bodies, `$(...)` in target names (skipped), conditionals
    (`ifeq`/`ifdef` - targets in either branch count), line continuations in rule lines, target-specific variable
    lines (`name: VAR = x` counts as defining `name`). ASSUMPTION A10.
- `include` handling (NFR) - `include`, `-include` and `sinclude` lines are followed, treated identically: each
  whitespace-separated word is a literal path resolved relative to the Makefile's directory; words containing `$` or
  glob characters (`*?[`) are skipped; files not present on disk are skipped silently; includes are followed
  recursively with a visited-set guard against cycles. ASSUMPTION A11, see Q1.
- The validated file has a different name (e.g. `idp validate path/good.yaml`): the Makefile looked for is
  `path/Makefile` (A1).
- Text output format is unchanged: one line per violation `<file>: <path>: <message>`, e.g.
  `idp.yaml: Makefile: missing required target 'lint'`. ASSUMPTION A12.
- Existing test `test_cli_validate_reports_violation_paths` (IDP-8:AC-5) validates a YAML in `tmp_path` with no Makefile
  and expects exit 0 for the valid file; under AC-6 that now exits 1. The test is updated minimally by writing a Makefile
  with all targets into `tmp_path` before the assertions. Its assertions and AC tags are not weakened. The other existing
  test `test_invalid_yaml_and_missing_file` is unaffected (`contract.validate_file` stays schema-only; missing file still
  exits 2). ASSUMPTION A13.
- The platform repo itself has no `idp.yaml`, so its `make verify` does not call `idp validate` and is unaffected.
- ASSUMPTION A1: Makefile = `Path(file).parent / "Makefile"`.
- ASSUMPTION A2: Make violation `path` is `"Makefile"` (not a filesystem path) and messages are as above.
- ASSUMPTION A3: only the five "yes" targets plus enabled `test-<kind>` targets are checked; recommended ones are not.
- ASSUMPTION A4: compact single-line JSON in the key order `file`, `valid`, `schema`, `violations`.
- ASSUMPTION A5: `schema` value is `"idp-service.v1"`.
- ASSUMPTION A6: exit-2 cases write nothing to stdout in `--json` mode.
- ASSUMPTION A7: Make checks run even when schema validation failed; "single violation" in AC-6 counts Make violations.
- ASSUMPTION A8: only `Makefile` is recognised.
- ASSUMPTION A9: unparseable YAML or a non-mapping document skips Make checks.
- ASSUMPTION A10: line-based rule parsing with the limitations listed.
- ASSUMPTION A11: literal include paths relative to the Makefile directory; `$`/glob words and missing files skipped.
- ASSUMPTION A12: human-readable output format unchanged (prefix `<file>: ` on every violation line).
- ASSUMPTION A13: the IDP-8 CLI test gets a Makefile fixture; no other existing test changes.

## Non-functional requirements
- Target detection parses Makefile rule lines only; `make` (or any subprocess) is never executed. Verified by a test that
  monkeypatches `subprocess.run`/`subprocess.Popen` to raise and still gets correct results, and by code review (no
  `subprocess` import in `contract.py`).
- Included files are read only if present on disk; a missing include never raises.
- No new runtime dependencies: only the standard library (`re`, `json`, `pathlib`) plus the existing `yaml` and
  `jsonschema`; `pyproject.toml` and `uv.lock` unchanged.
- Deterministic output: violation order is fixed (schema violations as today, then Make violations in the order defined
  in AC-3), so two runs produce byte-identical stdout.

## Out of scope
- Catalog consistency and tighten-only override checks (iteration 3).
- `--fix`.
- Executing `make` (e.g. `make -n`/`make -p`) or full GNU make semantics (variable expansion, conditionals, `define`).
- Checking recommended targets (`verify-fast`, `format`) or optional ones (`sbom`, `sca`), or what targets do.
- Directory arguments (`idp validate some/dir`) and discovery in parent directories.
- Changing the platform repo's own Makefile (protected path; not needed).

## Open questions
- Q1: How far should `include` support go? Proposed default: `include`/`-include`/`sinclude` with literal paths relative
  to the Makefile directory, recursive, missing files and `$(...)`/glob words skipped (A11). Alternative: expand simple
  `VAR := literal` variables, or not follow includes at all.
- Q2: Value of `schema` in JSON: `"idp-service.v1"` (schema id) or `"idp-service.v1.json"` (file name, as printed in the
  text output today)? Proposed default: `"idp-service.v1"` (A5).
- Q3: With `--json`, should exit-2 cases (file not found) print a JSON object (e.g. with `valid: false` and an `error`
  key) instead of only stderr? AC-4 fixes the key set and argparse usage errors cannot produce JSON, so proposed default:
  no JSON, stderr only, stdout empty (A6).
- Q4: Should Make checks run when schema validation fails? Proposed default: yes, report all violations together; skip
  them only when the YAML cannot be parsed into a mapping (A7, A9).
- Q5: Recognise `makefile` / `GNUmakefile` too? Proposed default: no, `Makefile` only (template and contract use it) (A8).
- Q6: Should the violation `path` for Make violations be `"Makefile"` or the actual path (e.g. `path/to/Makefile`)?
  Proposed default: `"Makefile"` (A2).

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_contract.py::test_validate_without_argument_uses_cwd_idp_yaml_and_exits_0, packages/idp-gate/tests/test_contract.py::test_makefile_targets_parses_rules_includes_and_ignores_non_rules |
| AC-2 | packages/idp-gate/tests/test_contract.py::test_enabled_test_kind_without_target_is_reported, packages/idp-gate/tests/test_contract.py::test_disabled_test_kind_does_not_require_target |
| AC-3 | packages/idp-gate/tests/test_contract.py::test_every_missing_required_target_is_listed, packages/idp-gate/tests/test_contract.py::test_phony_only_and_pattern_rules_do_not_define_targets, packages/idp-gate/tests/test_contract.py::test_make_checks_run_with_schema_violations, packages/idp-gate/tests/test_contract.py::test_target_detection_never_runs_make |
| AC-4 | packages/idp-gate/tests/test_contract.py::test_json_valid_output_and_exit_0, packages/idp-gate/tests/test_contract.py::test_json_invalid_output_lists_violations_and_exits_1, packages/idp-gate/tests/test_contract.py::test_json_missing_file_exits_2_with_empty_stdout |
| AC-5 | packages/idp-gate/tests/test_contract.py::test_no_idp_yaml_in_cwd_exits_2_with_not_found_message |
| AC-6 | packages/idp-gate/tests/test_contract.py::test_missing_makefile_is_single_violation |
