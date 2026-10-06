---
ticket: IDP-13
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: auto
---

# IDP-13: idp spec-trace --json: machine-readable traceability output

## Context
The pr-composer subagent and future gate evidence need the AC-to-test mapping as data instead of parsing the
human-readable output of `idp spec-trace`. This ticket adds an opt-in `--json` flag to `idp spec-trace`. It is also the
first ticket run end to end through `/implement-ticket` (iteration 1 dry run). Parent epic: IDP-6.

## Requirements
- **AC-1** Given a spec whose ACs are all covered, when I run `idp spec-trace <KEY> --json`, then stdout is a single JSON object with keys `ticket`, `ok`, `required`, `missing`, `unknown` and `tests` (a map from AC id to a list of test ids), and the exit code is 0.
  - AC ids everywhere in the object use the existing qualified form `<KEY>:AC-n` (as in today's `missing`/`unknown`). ASSUMPTION A1.
  - A test id is the existing `<path>::<name>` string that `spec_trace.acs_in_tests` already produces (path as discovered under `--root`). ASSUMPTION A2.
  - `tests` has one key per required AC (value `[]` when uncovered) plus one key per unknown AC of this ticket. ACs of other tickets are excluded. ASSUMPTION A3.
  - Keys appear in the order `ticket`, `ok`, `required`, `missing`, `unknown`, `tests`. The object is printed as one line followed by a newline. ASSUMPTION A4.
  - Nothing else goes to stdout.
- **AC-2** Given a spec with an uncovered AC, when I run it with `--json`, then `ok` is `false`, `missing` lists that AC, and the exit code is 1.
  - The uncovered AC also appears in `required`, and in `tests` with an empty list (A3).
- **AC-3** Given a missing spec, when I run it with `--json`, then stdout is `{"ticket": "<KEY>", "ok": false, "error": "spec not found: <path>"}` and the exit code is 1.
  - `<path>` is the same path the human-readable mode reports today (`<root>/specs/<KEY>/spec.md`). The object has exactly these three keys, in this order.
  - Nothing is written to stderr in `--json` mode for this case. ASSUMPTION A5.
- **AC-4** Given no `--json` flag, when I run `idp spec-trace <KEY>`, then the output and exit codes are unchanged from today (existing tests still pass).

## Edge cases and assumptions
- Spec with no AC lines and `--json`: `required` is `[]`, `ok` is `false` (as `TraceReport.ok` defines today), `tests` is `{}`, exit code 1.
- Unknown AC cited (e.g. `<KEY>:AC-7` not in the spec): it appears in `unknown` and as a key in `tests`; `ok` is `false`; exit code 1.
- The same test cites the same AC twice (two decorators): its id appears once in that AC's list. ASSUMPTION A6.
- `--json` combines with `--root`; flag position follows normal argparse rules (`idp spec-trace KEY --json --root X` and `idp spec-trace --json KEY` both work).
- ASSUMPTION A1: AC ids are qualified (`IDP-13:AC-1`), not bare (`AC-1`), matching existing `required`/`missing`/`unknown` values.
- ASSUMPTION A2: test ids are reused unchanged from the existing scanner (`<path>::<function or class name>`). The path is relative when `--root` is relative (default `.`) and absolute when `--root` is absolute; it is not normalised in this ticket.
- ASSUMPTION A3: `tests` keys = required ACs and unknown ACs of this ticket.
- ASSUMPTION A4: compact single-line JSON (`json.dumps` defaults, no `sort_keys`, no indent) in the key order above.
- ASSUMPTION A5: in `--json` mode the missing-spec error goes only to stdout as JSON; stderr stays empty.
- ASSUMPTION A6: test-id lists are de-duplicated and sorted.

## Non-functional requirements
- Deterministic output: `required`, `missing`, `unknown` and every list in `tests` are sorted ascending (Python string order), and `tests` keys are emitted in sorted order. Two runs on the same tree produce byte-identical stdout.
- No new dependencies: only the standard library `json` module is used; `pyproject.toml` and `uv.lock` are unchanged.

## Out of scope
- Changing the human-readable format.
- JSON output for other commands (`test-quality-lint`, `approve-spec`, `validate`).
- Normalising test-id paths (relative vs absolute) or adding a schema version field.

## Open questions
- Q1: What does a "test id" look like? Proposed default: the existing `<path>::<name>` string, unchanged (A2).
- Q2: Does `tests` include keys for uncovered ACs (and for unknown ACs)? Proposed default: yes, uncovered map to `[]`; unknown ACs of this ticket are included; other tickets' ACs are excluded (A3).
- Q3: Are AC ids qualified (`IDP-13:AC-1`) or bare (`AC-1`)? Proposed default: qualified (A1).
- Q4: Key ordering and formatting? Proposed default: ticket, ok, required, missing, unknown, tests; single line (A4).
- Q5: Should the missing-spec case also write to stderr in `--json` mode? Proposed default: no (A5).
- Q6: Should test-id lists be de-duplicated? Proposed default: yes (A6).
- Q7: Should the JSON carry a version field (e.g. `"schema": "idp-spec-trace.v1"`) for future consumers? Proposed default: no, out of scope for this ticket; AC-1 fixes the key set.

## Traceability
| AC | Tests |
|----|-------|
| AC-1 | packages/idp-gate/tests/test_spec_trace.py::test_json_all_covered_prints_object_and_exits_0, packages/idp-gate/tests/test_spec_trace.py::test_json_flag_before_ticket_is_accepted, packages/idp-gate/tests/test_spec_trace.py::test_to_dict_returns_keys_in_spec_order, packages/idp-gate/tests/test_spec_trace.py::test_json_output_is_sorted_and_deterministic |
| AC-2 | packages/idp-gate/tests/test_spec_trace.py::test_json_uncovered_ac_listed_in_missing_and_exits_1, packages/idp-gate/tests/test_spec_trace.py::test_json_spec_without_acs_is_not_ok |
| AC-3 | packages/idp-gate/tests/test_spec_trace.py::test_json_missing_spec_prints_error_object_and_exits_1 |
| AC-4 | packages/idp-gate/tests/test_spec_trace.py::test_without_json_flag_output_is_unchanged, packages/idp-gate/tests/test_spec_trace.py::test_without_json_flag_missing_spec_still_reports_on_stderr (plus the existing IDP-8 tests in the same file, which must pass unmodified) |
