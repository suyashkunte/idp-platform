---
key: IDP-8
type: Story
status: Done
summary: "idp CLI v0: spec-trace, test-quality-lint, approve-spec, validate"
parent: IDP-6
labels: [component:pipeline, iteration:1, repo:idp-platform, risk:medium]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T00:42:15.240+0530
updated: 2026-10-07T02:00:49.636+0530
resolved: 2026-10-07T02:00:49.618+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-8
---

# IDP-8: idp CLI v0: spec-trace, test-quality-lint, approve-spec, validate

Epic/parent: [IDP-6](IDP-6.md)

## Description

## Context / why

The agentic workflow's deterministic checks must live in tested Python, not in prompts (design doc §21.8, §11.3). These four commands are what the hooks, `make verify` and CI call.

## Acceptance criteria

* AC-1 Given `specs/<KEY>/spec.md` with ACs `AC-1..n`, when `idp spec-trace <KEY>` runs, then it exits 1 and lists every AC without a test tagged `@pytest.mark.ac("<KEY>:AC-n")`, and every tagged test that cites an unknown AC; otherwise it exits 0.
* AC-2 Given test files, when `idp test-quality-lint <files>` runs, then it reports tests with no assertions, constant-true assertions, status-code-only assertions, or `sleep()` calls, and exits 1 if any are found.
* AC-3 Given the environment variable `CLAUDECODE=1` (an agent session), when `idp approve-spec <KEY>` runs, then it refuses with exit 2 and writes nothing.
* AC-4 Given a human shell and an existing spec, when `idp approve-spec <KEY>` runs, then it writes `specs/<KEY>/APPROVED` containing approver name and email, UTC time, and the spec's sha256.
* AC-5 Given an `idp.yaml`, when `idp validate` runs, then it validates against `schemas/idp-service.v1.json` and prints each violation with its path.

## Non-functional criteria

Pure Python 3.12, typed (mypy strict), ≥ 85 % line coverage on the package.

## Out of scope

Gate evaluation and evidence commands (iteration 3).

## Comments (0)
