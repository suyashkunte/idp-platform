---
key: IDP-15
type: Bug
status: To Do
summary: "idp CLI: validate ticket keys before using them as paths (approve-spec can write outside specs/)"
parent:
labels: [component:pipeline, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T01:49:37.675+0530
updated: 2026-10-07T01:49:37.749+0530
resolved:
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-15
---

# IDP-15: idp CLI: validate ticket keys before using them as paths (approve-spec can write outside specs/)

## Description

## Context / why

Raised as a minor by the security reviewer on IDP-13 (it predates that change). `idp spec-trace <KEY>` and `idp approve-spec <KEY>` build `specs/<KEY>/...` from an unchecked argument. `approve-spec` WRITES a file there, so `../../x` writes outside `specs/`. A human runs it, so the risk is low, but path inputs must be validated.

## Acceptance criteria

* AC-1 Given a key not matching `^[A-Z][A-Z0-9]+-[0-9]+$`, when any `idp` command takes it, then it exits 2 with "invalid ticket key" and touches no files.
* AC-2 Given `../IDP-1` or `IDP-1/../../x`, when `idp approve-spec` runs, then nothing is written anywhere.
* AC-3 Given a valid key, then behaviour and output are unchanged (existing tests pass).

## Non-functional criteria

none

## Out of scope

Other path inputs (`--root`).

## Test approach

Unit tests in `packages/idp-gate/tests/` tagged with this ticket's ACs.

Found in phase: DEV (review of IDP-13).

## Comments (0)
