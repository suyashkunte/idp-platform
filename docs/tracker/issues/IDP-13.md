---
key: IDP-13
type: Story
status: Done
summary: "idp spec-trace --json: machine-readable traceability output"
parent: IDP-6
labels: [component:pipeline, layer:app, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T01:32:59.557+0530
updated: 2026-10-07T02:00:56.823+0530
resolved: 2026-10-07T02:00:53.248+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-13
---

# IDP-13: idp spec-trace --json: machine-readable traceability output

Epic/parent: [IDP-6](IDP-6.md)

## Description

## Context / why

The `pr-composer` subagent and future gate evidence need the AC→test mapping as data, not by parsing human-readable text. This is also the first ticket run end to end through `/implement-ticket` (iteration 1 dry run).

## Acceptance criteria

* AC-1 Given a spec whose ACs are all covered, when I run `idp spec-trace <KEY> --json`, then stdout is a single JSON object with keys `ticket`, `ok`, `required`, `missing`, `unknown` and `tests` (a map from AC id to a list of test ids), and the exit code is 0.
* AC-2 Given a spec with an uncovered AC, when I run it with `--json`, then `ok` is `false`, `missing` lists that AC, and the exit code is 1.
* AC-3 Given a missing spec, when I run it with `--json`, then stdout is `{"ticket": "<KEY>", "ok": false, "error": "spec not found: <path>"}` and the exit code is 1.
* AC-4 Given no `--json` flag, when I run `idp spec-trace <KEY>`, then the output and exit codes are unchanged from today (existing tests still pass).

## Non-functional criteria

Lists in the JSON are sorted, so the output is deterministic. No new dependencies.

## Out of scope

Changing the human-readable format; JSON for other commands.

## Interfaces / dependencies

`packages/idp-gate/src/idp_gate/{cli.py,spec_trace.py}`. No blockers.

## Test approach

Unit tests in `packages/idp-gate/tests/test_spec_trace.py`, tagged with this ticket's AC ids.

## Definition of Done

Default DoD: `make verify` green, ACs traced, CHANGELOG entry, draft PR.

## Comments (3)

### Suyash Kunte, 2026-10-07T01:38:35.667+0530

**Spec drafted** (branch `feature/IDP-13-spec-trace-json`, `specs/IDP-13/`). Mode: **auto** (spec:auto + risk:low), so the spec is approved at PR time.

Plan: add a pure `spec_trace.to_dict(report)` and a `--json` flag on `idp spec-trace`; the text path (`trace`/`render`) is untouched (AC-4). Standard-library `json` only. Tasks: T1 success path (AC-1/2/4), T2 missing-spec error object (AC-3), T3 CHANGELOG + verify.

**Open questions (proposed defaults, will proceed with these unless corrected):**

1. Test id = existing scanner form `<path>::<test name>`.
2. `tests` has a key per required AC (`[]` if uncovered) plus unknown ACs for this ticket.
3. AC ids in full form `IDP-13:AC-1`, matching `required`/`missing`/`unknown`.
4. Key order `ticket, ok, required, missing, unknown, tests`; single-line JSON; `tests` keys sorted.
5. Missing spec in `--json` mode: error object on stdout only, nothing on stderr.
6. Duplicate test ids de-duplicated and sorted.
7. No schema/version field (AC-1 fixes the key set).

### Suyash Kunte, 2026-10-07T01:46:05.928+0530

Draft PR opened: https://github.com/suyashkunte/idp-platform/pull/2

`make verify` green (93 tests, diff coverage 100%), all 4 ACs traced (9 tests). Auto mode: the spec is approved by the human as part of the PR review. Reviewers found no blockers/majors; 5 minors listed in the PR body.

### Suyash Kunte, 2026-10-07T02:00:56.823+0530

Done. First ticket delivered end to end via `/implement-ticket`. Merged in PR #2 (ac962be). Independent check: test-first commit order confirmed, spec-trace 4/4 ACs, 93 tests pass, test-quality-lint clean. Spec approved by a human at PR time (`specs/IDP-13/APPROVED`, hash current). Follow-ups from the dry run: IDP-14 (Bash guard false positive), IDP-15 (ticket key validation).
