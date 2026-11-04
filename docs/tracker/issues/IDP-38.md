---
key: IDP-38
type: Story
status: To Do
summary: "Guard ADR-0013's premise: workflows that run make verify or idp conformance must hold no credentials"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T14:01:16.781+0530
updated: 2026-10-20T14:06:39.852+0530
resolved:
links:
  - {type: "relates to", key: IDP-31}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-38
---

# IDP-38: Guard ADR-0013's premise: workflows that run make verify or idp conformance must hold no credentials

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-31](IDP-31.md)

## Description

## Context / why

ADR-0013 (IDP-31, PR #13) says the static Makefile scanner is not a security boundary. It also says today's `platform-ci.yml` job is outside the scanner-hardening rule, because it holds no credentials: it is triggered by `pull_request`/`push`/`workflow_dispatch`, has `permissions: contents: read`, and uses no secrets. Nothing enforces that premise. Any of these changes would silently invalidate the ADR's reasoning:

* switching a trigger to `pull_request_target` or `workflow_run`;
* adding `id-token: write` or any write permission;
* referencing `secrets.*` in a job that runs repository `make` or `idp conformance`.

This was raised as security-review finding m1 on PR #13 and is left open there. The test only reads `.github/workflows/`, so agents can write it. `persist-credentials: false` is already covered by IDP-23 AC-4 and is out of scope here.

## Acceptance criteria

* **AC-1** Given any workflow under `.github/workflows/` with a job that runs `make` (any target) or `idp conformance` in a `run:` step, then a test in `tests/ci/` fails if that workflow has a `pull_request_target` or `workflow_run` trigger. The failure names the file.
* **AC-2** Given such a job, then the test fails if the effective permissions (workflow-level, overridden by job-level) are anything other than `contents: read`. That includes `id-token: write`, any `write`, `write-all`, and missing permissions (GitHub's default token scope). The failure names the file and job.
* **AC-3** Given such a job, then the test fails if any of its steps or env reference `secrets.` other than `secrets.GITHUB_TOKEN`. The failure names the file and job.
* **AC-4** (edge) Given today's `platform-ci.yml`, then the test passes. Given workflows whose jobs run no `make` or `idp conformance` (for example `oidc-smoke.yml` with `id-token: write`), then those jobs are ignored. Given a reusable workflow call (`uses:` at job level), then the test fails closed with a message asking for the called workflow to be checked by hand, unless it is listed in an explicit allow-list in the test.
* **AC-5** Given ADR-0013, then its Decision outcome links the test as the enforcement of the "today's `platform-ci.yml` job is outside the rule" premise. Only a link is added; no other change to the decision.

## Non-functional criteria

None beyond `make verify` staying green; the test runs in under 1 s.

## Out of scope

* `persist-credentials: false` (IDP-23 AC-4).
* Making job separation for credentialed jobs a binding requirement. ADR-0013 records it as input for the iteration-3 threat model (decided 2026-10-20 at PR #13 review).
* Changing any workflow.

## Interfaces / dependencies

Relates to IDP-31 (ADR-0013) and IDP-23. Reuses the YAML loading pattern of `tests/ci/test_workflow_runners.py` (IDP-12). No protected-path edits.

## Test approach

Unit tests in `tests/ci/` over the real workflows, plus synthetic workflow fixtures (in `tmp_path`) for each failing case.

## Definition of Done

ACs traced; `make verify` green; CHANGELOG entry.

## Comments (0)
