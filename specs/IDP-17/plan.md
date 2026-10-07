# IDP-17: plan

## Approach
Keep `contract.validate_file()` (schema only) unchanged and add, in `contract.py`, a small static Makefile target
scanner plus one combined entry point `validate_service(path) -> list[Violation]` = schema violations + Make contract
violations. `_cmd_validate` calls `validate_service` instead of `validate_file` and gains a `--json` flag that prints a
single JSON object built by a new `contract.to_dict(file, violations)`. The not-found branch (exit 2) is untouched, so
AC-5 needs no code change, only a test. No subprocess, no new dependency.

## Changes
| File | Change |
|------|--------|
| packages/idp-gate/src/idp_gate/contract.py | Add `SCHEMA_ID = "idp-service.v1"`, `REQUIRED_TARGETS = ("lint", "test", "test-component", "verify", "spec-trace")`, `TEST_KINDS = ("smoke", "api", "e2e", "perf")`, `MAKE_PATH = "Makefile"`. Add `makefile_targets(makefile: Path) -> set[str]`: reads lines, strips `#` comments, follows `include`/`-include`/`sinclude` (literal words relative to `makefile.parent`; skip words with `$` or `*?[`; skip non-existent files; visited set for cycles); rule regex at column 0, roughly `^(?P<names>[^\s:=#][^:=#]*?)\s*::?(?!=)` with a guard against `:=`/`::=`/`:::=`; split names on whitespace; drop names starting with `.`, containing `%` or `$`. Add `check_make_contract(doc: Any, makefile: Path) -> list[Violation]`: if the Makefile is not a file return `[Violation("Makefile", "Makefile not found")]`; else one violation per missing required target (`missing required target '<t>'`), then per `spec.tests.<kind> is True` without `test-<kind>` (`missing target 'test-<kind>' (required because spec.tests.<kind> is true)`); reads `spec.tests` defensively. Add `validate_service(path: Path) -> list[Violation]`: parse YAML once; on `YAMLError` return the same `invalid YAML` violation as today; otherwise schema violations, plus `check_make_contract(doc, path.parent / "Makefile")` when `doc` is a dict. Add `to_dict(file: str, violations) -> dict[str, object]` returning `{"file", "valid", "schema", "violations": [{"path", "message"}]}` in that order. Refactor `validate_file` only as far as sharing the YAML-loading helper; behaviour unchanged. |
| packages/idp-gate/src/idp_gate/cli.py | `validate` subparser: add `--json` (`store_true`, help "print a JSON object instead of text"); update help to "validate idp.yaml against the service contract schema and the Make contract". `_cmd_validate`: keep the not-found branch as is (stderr, exit 2, nothing on stdout); call `contract.validate_service(path)`; if `args.json` print `json.dumps(contract.to_dict(args.file, violations))`, else today's text lines; return `1 if violations else 0`. |
| packages/idp-gate/tests/test_contract.py | Add a `_write_makefile(dir, targets=...)` helper (default: all required targets plus `test-smoke/api/e2e/perf`, since the docs example enables all four kinds) and new tests tagged `@pytest.mark.ac("IDP-17:AC-n")` per the spec traceability (AC-1/AC-5 use `monkeypatch.chdir(tmp_path)`; AC-4 uses `capsys` + `json.loads`). Minimal change to the existing `test_cli_validate_reports_violation_paths`: call `_write_makefile(tmp_path)` before the assertions (needed because of AC-6); its assertions and tags are unchanged. `test_invalid_yaml_and_missing_file` unchanged. Makefile fixtures are written as string literals into `tmp_path`. |
| docs/platform/service-contract.md | After the Make contract table, add a short "How `idp validate` checks it" subsection: discovery of `./idp.yaml`, `Makefile` beside it, required targets and `tests.*: true` → `test-<kind>`, static parsing rules and limitations (includes, `.PHONY`-only, pattern rules, no make execution), the `--json` object with an example (fenced as `json`, not `yaml`, and placed after the existing YAML example so `_doc_example()`'s first-```yaml-block regex still finds the StudyTimer example), and exit codes 0/1/2. |
| CHANGELOG.md | Under `[Unreleased]` / `### Added`: `- IDP-17: \`idp validate\` checks the Make contract (required targets, \`test-<kind>\` for enabled \`spec.tests\`) and adds \`--json\`; validates \`./idp.yaml\` by default.` |

No protected paths (`Makefile`, `pyproject.toml`, `.github/**`) need changes.

## Interfaces and data
- CLI: `idp validate [FILE] [--json]`; `FILE` defaults to `idp.yaml` (unchanged). Additive flag.
- Behaviour change: a repo whose `idp.yaml` is schema-valid but whose Makefile is missing or lacks required targets now
  fails (exit 1). No tenant repos exist yet, so no consumer breaks.
- Exit codes unchanged: 0 valid, 1 violations, 2 file not found / usage.
- Text output: unchanged format; Make violations appear as `idp.yaml: Makefile: missing required target 'lint'`.
- JSON (valid): `{"file": "idp.yaml", "valid": true, "schema": "idp-service.v1", "violations": []}`
- JSON (invalid): `{"file": "idp.yaml", "valid": false, "schema": "idp-service.v1", "violations": [{"path": "spec.runtime", "message": "'port' is a required property"}, {"path": "Makefile", "message": "missing required target 'test-component'"}]}`
- Python API: new `contract.makefile_targets`, `contract.check_make_contract`, `contract.validate_service`,
  `contract.to_dict`, constants `SCHEMA_ID`, `REQUIRED_TARGETS`, `TEST_KINDS`. `validate_file`/`validate_document` and
  `Violation` unchanged. No schema, config or migration changes; no new dependencies.

## Telemetry
None. Local CLI without runtime telemetry; the `--json` object is the artefact the PR pipeline will put in job summaries.

## Risks, rollout and rollback
- Risk: the line-based parser misses targets defined in unusual ways (variables, `define`, conditionals), producing a
  false "missing target". Mitigation: limitations documented in service-contract.md; the template Makefile uses plain
  rules; unit tests cover rules, double-colon, comments, includes. Detection: false failures in tenant PRs.
- Risk: the parser counts a non-rule line as a target (false pass), e.g. `.PHONY`-only. Mitigation: explicit tests for
  `.PHONY`-only, pattern rules and variable assignments.
- Risk: existing IDP-8 test breaks due to AC-6. Mitigation: add a Makefile fixture in that test (planned, T1).
- Risk: docs edit breaks `_doc_example()` (first ```yaml block). Mitigation: new examples fenced as `json`/`make` and
  placed after the YAML example; `test_documented_example_is_valid` guards it.
- Rollout: ships with the next `idp-gate` release via the workspace; no flags or migrations.
- Rollback: revert the PR; `idp validate` returns to schema-only behaviour.
