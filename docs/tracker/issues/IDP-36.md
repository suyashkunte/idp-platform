---
key: IDP-36
type: Story
status: To Do
summary: "Generate the studytimer repo from templates/python-fastapi@v0.1.0 with PR checks from the platform"
parent: IDP-16
labels: [component:pipeline, repo:studytimer, risk:low, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T13:01:27.518+0530
updated: 2026-10-20T13:01:57.708+0530
resolved:
links:
  - {type: "blocks", key: IDP-37}
  - {type: "is blocked by", key: IDP-33}
  - {type: "is blocked by", key: IDP-34}
  - {type: "is blocked by", key: IDP-35}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-36
---

# IDP-36: Generate the studytimer repo from templates/python-fastapi@v0.1.0 with PR checks from the platform

Epic/parent: [IDP-16](IDP-16.md)

Links: blocks [IDP-37](IDP-37.md); is blocked by [IDP-33](IDP-33.md); is blocked by [IDP-34](IDP-34.md); is blocked by [IDP-35](IDP-35.md)

## Description

## Context / why

StudyTimer is tenant #1 (PROJECT_PLAN §5). Iteration 2 ends when its PR checks run from the platform's `@v0` reusable workflows and its first ticket reaches a draft PR. This story creates the repo from the template and wires it up.

## Acceptance criteria

* **AC-1** Given template tag `v0.1.0`, when I run `copier copy --vcs-ref v0.1.0 gh:suyashkunte/idp-platform studytimer` with the answers name `studytimer`, owner, tier 2 and tracker `IDP` with labels `[repo:studytimer]`, then the public repo `github.com/suyashkunte/studytimer` holds the generated content as its first commit, and `.copier-answers.yml` records `_commit: v0.1.0`.
* **AC-2** Given a PR in `studytimer`, then the `idp` workflow runs the platform's `_pr-checks.yml@v0` and the required check `pr-checks / verify` passes on the first PR.
* **AC-3** Given `studytimer`'s `main`, then a ruleset requires a PR, the status check `pr-checks / verify`, linear history and squash merges, with no force-push or deletion and 0 approvals (demo mode, Q4).
* **AC-4** (edge) Given a test PR that removes the `verify` target from the `Makefile`, then the PR check fails with `missing required target 'verify'`. Close that PR unmerged; it is evidence only.

## Non-functional criteria

* No secrets in the repo.
* The Jira label `repo:studytimer` exists.
* The README links to the platform onboarding doc.

## Out of scope

* App features (the ST-1..ST-9 stories).
* AWS, OIDC roles and the G0+ stages (iteration 3+).
* Platform CI running StudyTimer conformance (after IDP-23).

## Interfaces / dependencies

* Blocked by the template story, the reusable PR pipeline story and the release v0.1.0 story.
* **Human tasks:** create the public GitHub repo; push the initial commit (agents cannot push to `main`); apply the ruleset; enable the `idp-agentic` marketplace in the user's Claude settings for that repo if needed.
* **Agent tasks:** run copier into a scratch directory, check `idp validate` and `make verify` locally, and prepare the ruleset JSON and the evidence PR.

## Test approach

* Evidence-based: links to the generation command output, the first green PR-check run, the ruleset JSON and the failing evidence PR from AC-4.
* No new platform code is expected. Any template fix found here becomes a platform ticket.

## Definition of Done

* ACs evidenced on the ticket.
* `docs/plan/iterations/02-*.md` notes the repo creation.
* The studytimer `CHANGELOG.md` is started.

## Comments (0)
