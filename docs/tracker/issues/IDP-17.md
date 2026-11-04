---
key: IDP-17
type: Story
status: Done
summary: "idp validate: auto-discover idp.yaml, check the Make contract, add --json"
parent: IDP-16
labels: [component:pipeline, layer:app, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T09:32:36.649+0530
updated: 2026-10-07T12:03:55.054+0530
resolved: 2026-10-07T12:03:55.036+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-17
---

# IDP-17: idp validate: auto-discover idp.yaml, check the Make contract, add --json

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

`idp validate` (iteration 1) only checks `idp.yaml` against the `idp-service.v1` schema. The PR pipeline (S5) and the template (S4) need it to also check that the repo honours the Make contract (I2, docs/platform/service-contract.md), and to emit machine-readable output for job summaries.

## Acceptance criteria

* **AC-1** Given a directory containing a schema-valid `idp.yaml` and a Makefile with all required targets, when I run `idp validate` with no file argument from that directory, then it validates `./idp.yaml` and exits 0.
* **AC-2** Given `spec.tests.<kind>: true` for any of smoke, api, e2e, perf, when the Makefile next to `idp.yaml` has no `test-<kind>` target, then validation fails (exit 1) and the violation names the missing target.
* **AC-3** Given a Makefile missing one or more required targets (`lint`, `test`, `test-component`, `verify`, `spec-trace`), then validation fails and lists every missing target, not only the first.
* **AC-4** Given `--json`, then stdout is exactly one JSON object `{"file", "valid", "schema", "violations": [{"path", "message"}]}` and exit codes are unchanged (0 valid, 1 invalid, 2 usage).
* **AC-5 (edge)** Given no `idp.yaml` in the current directory and no argument, then it exits 2 with a message containing "idp.yaml not found".
* **AC-6 (edge)** Given `idp.yaml` exists but there is no Makefile beside it, then validation fails with a single violation "Makefile not found".

## Non-functional criteria

Target detection parses Makefile rule lines (`name:` at line start, including targets declared via `include`d files only if present on disk); it must not execute make. No new runtime dependencies.

## Out of scope

Catalog consistency and tighten-only override checks (iteration 3). `--fix`.

## Interfaces / dependencies

`packages/idp-gate/src/idp_gate/contract.py`, `cli.py`; Make contract table in docs/platform/service-contract.md.

## Test approach

Unit tests with tmp_path fixtures (idp.yaml + Makefile variants); CLI tests via `main([...])` with capsys, including JSON parsing of output.

## Definition of Done

ACs traced by `idp spec-trace`; `make verify` green; service-contract.md documents the semantic checks and `--json`; CHANGELOG entry.

Labels: repo:idp-platform, component:pipeline, layer:app, risk:low, spec:auto

## Comments (2)

### Suyash Kunte, 2026-10-07T10:49:25.075+0530

Spec drafted on `feature/IDP-17-validate-make-contract` (specs/IDP-17/, commit f54f13e). Auto mode: spec approval happens at PR review.

**Design:** `contract.py` gains a Makefile target parser (reads rule lines, never runs make), `check_make_contract()`, `validate_service()` (schema + Make violations together) and `to_dict()`; `idp validate` gains `--json`. Existing IDP-8 CLI test gets a full Makefile fixture (AC-6 not weakened).

**Open questions (defaults in spec):** Q1 follow literal `include`/`-include` paths, skip `$(...)`; Q2 JSON `schema` = `idp-service.v1`; Q3 exit-2 with `--json` prints nothing on stdout; Q4 Make checks still run after schema failures; Q5 only `Makefile` filename; Q6 Make violation path = `Makefile`.
Note: AC-5/AC-6 written as `**AC-5** (edge)` in the spec so spec-trace parses them.

### Suyash Kunte, 2026-10-07T11:10:49.848+0530

Draft PR: https://github.com/suyashkunte/idp-platform/pull/5 — `make verify` green (162 tests, 97 % coverage, 100 % diff coverage), spec-trace 6/6. Two review loops; the final fix round (28c93b9, 5c6af12) was not re-reviewed — flagged in the PR. Spec approval happens at PR review (auto mode).
