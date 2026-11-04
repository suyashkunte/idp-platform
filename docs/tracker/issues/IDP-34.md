---
key: IDP-34
type: Story
status: To Do
summary: "Reusable PR pipeline: service-pipeline.yml + _pr-checks.yml with setup-profile and idp-validate composite actions"
parent: IDP-16
labels: [component:pipeline, layer:infra, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T13:01:01.202+0530
updated: 2026-10-20T13:02:03.091+0530
resolved:
links:
  - {type: "blocks", key: IDP-36}
  - {type: "relates to", key: IDP-23}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-34
---

# IDP-34: Reusable PR pipeline: service-pipeline.yml + _pr-checks.yml with setup-profile and idp-validate composite actions

Epic/parent: [IDP-16](IDP-16.md)

Links: blocks [IDP-36](IDP-36.md); relates to [IDP-23](IDP-23.md)

## Description

## Context / why

The iteration-2 exit criterion is that StudyTimer's PR checks run entirely from the platform's `@v0` reusable workflows (PROJECT_PLAN §4.1, §9). Tenants call one entry point, `service-pipeline.yml`, from a \~10-line `idp.yml`. For PRs it routes to `_pr-checks.yml`. Iteration 1 also planned a `spec-approved` check, advisory in demo mode (Q5).

## Acceptance criteria

* **AC-1** Given a repo whose `.github/workflows/idp.yml` calls `service-pipeline.yml` on `pull_request`, then `_pr-checks.yml` runs:

    * checkout;
    * `actions/setup-profile` (uv and Python from the build profile in `idp.yaml`);
    * installing the `idp` CLI at the platform ref;
    * `actions/idp-validate`;
    * `make verify`;
    * `make spec-trace KEY=<key>` when the branch name contains a ticket key.


    It also uploads `reports/` as an artifact. The required check name is stable (`pr-checks / verify`).


* **AC-2** (edge) Given a branch name with no ticket key (for example `renovate/...` or `main`), then spec-trace and spec-approved are skipped with a notice and do not fail.
* **AC-3** (edge) Given a PR for ticket `<KEY>` where `specs/<KEY>/spec.md` exists and the approval marker is missing or its `spec_sha256` does not match the spec, then the `spec-approved` job fails with a message naming the key. That job is not part of the required check (advisory, Q5).
* **AC-4** Given a push to `main` or a `workflow_dispatch`, then `service-pipeline.yml` does not run the PR checks and exits successfully with a "no deploy stages yet" notice (G0 comes in iteration 3).
* **AC-5** Given the workflows and composite actions, then:

    * every action is pinned by commit SHA;
    * the token permissions are `contents: read`;
    * no secrets are referenced;
    * `actionlint` passes (added to platform `make verify` or CI).

* **AC-6** Given platform CI, then a self-test workflow calls `./.github/workflows/service-pipeline.yml` against `examples/minimal-service` (using a `working-directory` input) on every platform PR, and it passes.

## Non-functional criteria

* A PR-check run for `minimal-service` takes under 5 minutes with a warm uv cache.
* The reusable-workflow nesting depth stays within GitHub's limit.

## Out of scope

* The G0–G5 stages.
* AWS OIDC roles.
* Release tagging (separate story).
* Making `spec-approved` required (only after demo mode).

## Interfaces / dependencies

* Every `.github/**` file is human-placed: the agent prepares them under `staging/github/` (agent-editable) with tests that parse them, and the human copies them into `.github/`.
* `actions/*` is agent-editable.
* Open question for the spec: how a reusable workflow learns its own ref so it installs the matching CLI (`github.workflow_ref` belongs to the caller; consider `job_workflow_sha` or an explicit `platform-ref` input with the default `v0`).
* How the CLI is installed: `uv tool install "idp-gate @ git+https://github.com/suyashkunte/idp-platform@<ref>#subdirectory=packages/idp-gate"` (decided 2026-10-20). PyPI comes at v1.
* Relates to IDP-23 (conformance sandbox).

## Test approach

* Unit tests parse the staged YAML: pinned SHAs, permissions, job names, the key-extraction regex, and the skip conditions.
* `actionlint` runs on the staged files.
* After the human places the files, the self-test workflow run is the end-to-end evidence (link the run in the PR).

## Definition of Done

* ACs traced; `make verify` green; the self-test workflow green on the PR.
* `docs/platform/onboarding.md` shows the tenant `idp.yml`.
* CHANGELOG entry.

## Comments (0)
