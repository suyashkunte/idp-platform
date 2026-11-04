---
key: IDP-12
type: Task
status: Done
summary: "Pin GitHub Actions runners to ubuntu-24.04 before the ubuntu-latest migration (Oct 19)"
parent: IDP-16
labels: [component:pipeline, layer:infra, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T01:32:44.784+0530
updated: 2026-10-07T10:39:07.997+0530
resolved: 2026-10-07T10:39:07.978+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-12
---

# IDP-12: Pin GitHub Actions runners to ubuntu-24.04 before the ubuntu-latest migration (Oct 19)

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

GitHub announced that `ubuntu-latest` moves to Ubuntu 26 from **2026-10-19** (actions/runner-images#14748). Unpinned runners make builds change underneath us without a commit, which breaks reproducibility (design doc §6.1). Found as an annotation on platform-ci run 37521491729.

## Acceptance criteria

* AC-1 Given any workflow in `.github/workflows/`, when it is inspected, then every job uses `runs-on: ubuntu-24.04` (no `*-latest` labels).
* AC-2 Given a PR that adds `runs-on: ubuntu-latest`, when platform-ci runs, then a check fails and names the file and job.
* AC-3 Given the change, when platform-ci and oidc-smoke run on main, then both pass.

## Non-functional criteria

none

## Out of scope

Moving to Ubuntu 26 (separate, deliberate upgrade later).

## Dependencies

None. Note: `.github/**` is protected, so the PR needs human review as usual.

## Test approach

A unit test in `tests/` that parses all workflow YAML (covers AC-1 and AC-2); CI runs (AC-3).

**Due: before 2026-10-19.**

## Comments (3)

### Suyash Kunte, 2026-10-07T09:35:55.130+0530

Spec drafted on branch `feature/IDP-12-pin-ubuntu-runners` (specs/IDP-12/, commit 96d3e5e). Guided mode: waiting for human spec approval.

**Design:** a pytest module `tests/ci/test_workflow_runners.py` parses every `.github/workflows/*.y*ml` and checks each job's `runs-on`. It runs inside `make verify`, so a regression fails the required `verify` check and names the file and job (AC-2). The two one-line workflow edits are human-only (`.github/**` is protected).

**Open questions**

* Q1: strict allowlist (`ubuntu-24.04` only; expressions fail) vs a `*-latest` ban only.
* Q2: AC-3 is evidenced by CI runs; a local stand-in test checks the required `verify` job and the oidc-smoke job still exist and are pinned.
* Q3: oidc-smoke is verified by its run on main after merge.
* Q4: one-line CHANGELOG entry.

### Suyash Kunte, 2026-10-07T09:55:57.428+0530

Draft PR: https://github.com/suyashkunte/idp-platform/pull/4 — `make verify` green (116 tests), spec-trace 3/3, reviewers: 0 blocker / 0 major. After merge (before 2026-10-16), record the platform-ci and oidc-smoke runs on main here as AC-3 evidence.

### Suyash Kunte, 2026-10-07T10:38:08.794+0530

AC-3 evidence (PR #4 squash-merged as 7dcdbea):

* platform-ci on main: ✅ https://github.com/suyashkunte/idp-platform/actions/runs/37574726278
* oidc-smoke on main: ✅ https://github.com/suyashkunte/idp-platform/actions/runs/37574726280 (runner image ubuntu-24.04; assumed role idp-bootstrap-oidc-smoke)

All ACs met. Ready for Done (human transition).
