---
key: IDP-19
type: Story
status: Done
summary: "examples/minimal-service conformance fixture and make conformance"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T09:32:55.019+0530
updated: 2026-10-07T16:59:39.213+0530
resolved: 2026-10-07T16:59:36.538+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-19
---

# IDP-19: examples/minimal-service conformance fixture and make conformance

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

Platform changes must not break tenants (PROJECT_PLAN §12). A tiny, non-product fixture app exercises the contract (`idp validate`) and a build profile (`python-uv`) end to end in platform CI, so regressions show up before a release.

## Acceptance criteria

* **AC-1** Given `examples/minimal-service` (stdlib HTTP app exposing `/healthz/{live,ready,startup}`, an `idp.yaml`, a Makefile that includes the python-uv profile defaults, and at least one unit test), when I run `idp validate` and `make verify` inside it, then both exit 0.
* **AC-2** Given `make conformance` at the platform root, then it runs AC-1 for every directory under `examples/` that contains an `idp.yaml` and reports a pass/fail line per example.
* **AC-3 (edge)** Given an example whose `idp.yaml` has an unknown field (or whose Makefile lacks a required target), then `make conformance` exits non-zero and names the example. Proven by a negative fixture under `tests/`, not by breaking `examples/`.
* **AC-4** Given `make verify` at the platform root, then it runs `make conformance`, so platform CI (`verify` job) covers it without workflow changes.

## Non-functional criteria

Conformance runs in < 60 s locally; the fixture has no third-party runtime dependencies; it is not a workspace member that changes root coverage.

## Out of scope

Container build / chart render for the example (iterations 3–4); CI job changes under `.github/**`.

## Interfaces / dependencies

Depends on the S1 (`idp validate` Make checks) and S2 (`python-uv` defaults.mk) stories.

## Test approach

A pytest test that runs the conformance runner against a temp copy of a deliberately broken fixture and asserts failure; the real example is exercised by `make conformance`.

## Definition of Done

ACs traced; `make verify` green; docs/platform/onboarding.md mentions `examples/`; CHANGELOG entry.

Labels: repo:idp-platform, component:pipeline, layer:test, risk:low, spec:auto

## Comments (4)

### Suyash Kunte, 2026-10-07T15:44:16.589+0530

**Spec drafted** on branch `feature/IDP-19-minimal-service-conformance` (`specs/IDP-19/`, commit 426f050). Auto mode (spec:auto + risk:low): the spec is approved at PR review.

**Design:** new `idp conformance [DIR]` subcommand in idp-gate. For each `examples/*/` with an `idp.yaml` it runs `idp validate` (contract), resolves the build profile, then `make -C <ex> verify` with a 60 s timeout. It prints one PASS/FAIL line per example plus a summary. Exit codes: 0 = all pass, 1 = any fail, 2 = refused (e.g. no examples). `examples/minimal-service` is stdlib only. It has no `pyproject.toml`, so it is not a uv workspace member and does not affect root coverage, and its `verify` = `compileall` + `unittest`, with no network. The AC-3 negative fixtures live under `tests/conformance/fixtures/`.

**Human step:** the root `Makefile` is a protected path, so a human must add the `conformance` target and make it a prerequisite of `verify` (the snippet is in plan.md). The AC-4 test fails until then.

**Open questions:** Q1 immediate subdirs only? Q2 empty `examples/` → exit 2? Q3 always pass the resolved `IDP_PROFILE_DIR`? Q4 the fixture's `make test` writes no JUnit/Cobertura: acceptable? Q5 no-op `test-component` acceptable? Q6 skip `make verify` when validate fails? Q7 an example with no `pyproject.toml` acceptable for a "python-uv" fixture? Q8 output format / stderr for details?

### Suyash Kunte, 2026-10-07T16:03:17.421+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/7 (auto mode: the spec is approved at PR review).

**Human actions before merge:**

1. Paste the root `Makefile` snippet (task T5, in the PR body and plan.md) and push it to the branch. The root Makefile is a protected path. Until then, the AC-4 test and CI `verify` are red by design.
2. Approve the spec and answer Q1–Q8.

All 4 ACs are traced. Local checks, apart from the expected AC-4 test: 234 tests passed, coverage 97.9%. `idp conformance examples` passes in 0.8 s. Review: 2 loops; one MAJOR (timeout leaving orphaned child processes) fixed; 8 MINORs listed in the PR for the reviewer.

### Suyash Kunte, 2026-10-07T16:38:42.109+0530

**T5 done by a human** (4b972a7: root `make verify` now runs `make conformance`). CI `verify` passed on PR #7: https://github.com/suyashkunte/idp-platform/actions/runs/37611832244. Local `make verify`: 235 passed, `PASS examples/minimal-service`, spec-trace 4/4 AC OK (AC-4 included). Remaining before merge: spec approval and answers to Q1–Q8, then mark the PR ready and squash-merge.

### Suyash Kunte, 2026-10-07T16:59:39.213+0530

**Done.** PR #7 squash-merged as `421c541`, with the spec approved (approval marker on main). platform-ci on main passed: https://github.com/suyashkunte/idp-platform/actions/runs/37614144215. Q1–Q8: proposed answers accepted. Open MINOR review items (unsandboxed example Makefiles; a GNUmakefile could bypass the contract check) are candidates for follow-up tickets.
