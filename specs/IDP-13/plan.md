# IDP-13: plan

## Approach
Add a pure function `spec_trace.to_dict(report: TraceReport) -> dict[str, object]` next to the existing `render()`, and
an opt-in `--json` flag on the `spec-trace` subparser. `_cmd_spec_trace` branches on `args.json`: when set, it prints
`json.dumps(...)` of either `to_dict(report)` or the error object; otherwise it runs today's code path untouched.
`trace()`, `TraceReport`, `render()` and the scanner are not changed, so the human-readable output (AC-4) cannot drift.

## Changes
| File | Change |
|------|--------|
| packages/idp-gate/src/idp_gate/spec_trace.py | Add `to_dict(report)`: returns `{"ticket", "ok", "required", "missing", "unknown", "tests"}` in that insertion order. `required` = `sorted(report.required)`; `missing`/`unknown` reuse the already-sorted properties; `tests` = `{ac: sorted(set(report.found.get(ac, []))) for ac in sorted(report.required ∪ unknown)}`. |
| packages/idp-gate/src/idp_gate/cli.py | `import json`; `p.add_argument("--json", action="store_true", help="print a JSON object instead of text")` on `spec-trace`; in `_cmd_spec_trace`, on `FileNotFoundError` with `--json` print `json.dumps({"ticket": args.ticket, "ok": False, "error": str(exc)})` to stdout and return 1; on success with `--json` print `json.dumps(spec_trace.to_dict(report))` and return `0 if report.ok else 1`. Non-JSON branches unchanged. |
| packages/idp-gate/tests/test_spec_trace.py | Add tests tagged `@pytest.mark.ac("IDP-13:AC-n")` (see spec traceability). Reuse the existing `_repo` fixture helper and `IDP-42` fixture spec; fixture test sources stay string literals so they are not picked up by the real scan. Existing tests are not modified. |
| CHANGELOG.md | Under `[Unreleased]` / `### Added`: `- IDP-13: \`idp spec-trace --json\` machine-readable traceability output.` |

## Interfaces and data
- CLI: new optional flag `idp spec-trace <KEY> [--root DIR] [--json]`. Additive; default behaviour unchanged.
- Exit codes unchanged: 0 all ACs covered and no unknown ACs, 1 otherwise or spec missing.
- JSON (success):
  `{"ticket": "IDP-13", "ok": true, "required": ["IDP-13:AC-1"], "missing": [], "unknown": [], "tests": {"IDP-13:AC-1": ["packages/idp-gate/tests/test_spec_trace.py::test_x"]}}`
- JSON (missing spec): `{"ticket": "IDP-13", "ok": false, "error": "spec not found: specs/IDP-13/spec.md"}`
- Python API: new public function `spec_trace.to_dict`. No schema, config or migration changes. No new dependencies
  (stdlib `json` only).

## Telemetry
None. This is a local CLI with no runtime telemetry; the JSON output is itself the evidence artefact for later gates.

## Risks, rollout and rollback
- Risk: human-readable output changes by accident. Mitigation: the non-JSON path is not edited; existing IDP-8 tests and
  the new AC-4 test guard it.
- Risk: non-deterministic output (set iteration, duplicate ids). Mitigation: all lists sorted and de-duplicated; a test
  runs the command twice and compares stdout.
- Risk: consumers depend on the exact test-id path form, which varies with `--root`. Mitigation: documented in spec
  (A2); normalisation is out of scope.
- Rollout: ships with the next `idp-gate` release via the workspace; no flags or migrations.
- Rollback: revert the PR. The flag is additive and nothing else depends on it yet.
