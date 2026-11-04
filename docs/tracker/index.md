# IDP tickets (exported from Jira)

40 tickets. Each links to its file in [issues/](issues/). Grouped by epic; tickets without an epic last.

## [IDP-5](issues/IDP-5.md): E1 Setup & bootstrap (iteration 0) (Done)

| Key | Type | Status | Risk | Summary |
|---|---|---|---|---|

## [IDP-6](issues/IDP-6.md): E2 Platform skeleton & agentic plugin (iteration 1) (Done)

| Key | Type | Status | Risk | Summary |
|---|---|---|---|---|
| [IDP-7](issues/IDP-7.md) | Story | Done | low | Platform Python workspace and developer tooling |
| [IDP-8](issues/IDP-8.md) | Story | Done | medium | idp CLI v0: spec-trace, test-quality-lint, approve-spec, validate |
| [IDP-9](issues/IDP-9.md) | Story | Done | low | Service contract schema idp-service.v1 (draft) |
| [IDP-10](issues/IDP-10.md) | Story | Done | high | idp-agentic Claude Code plugin: skills, subagents, hooks, templates |
| [IDP-11](issues/IDP-11.md) | Story | Done | medium | Platform CI workflow and main branch ruleset |
| [IDP-13](issues/IDP-13.md) | Story | Done | low | idp spec-trace --json: machine-readable traceability output |

## [IDP-16](issues/IDP-16.md): Iteration 2: Contract, template & PR pipeline → StudyTimer born (To Do)

| Key | Type | Status | Risk | Summary |
|---|---|---|---|---|
| [IDP-12](issues/IDP-12.md) | Task | Done | low | Pin GitHub Actions runners to ubuntu-24.04 before the ubuntu-latest migration (Oct 19) |
| [IDP-17](issues/IDP-17.md) | Story | Done | low | idp validate: auto-discover idp.yaml, check the Make contract, add --json |
| [IDP-18](issues/IDP-18.md) | Story | Done | low | python-uv build profile with default make targets and agent notes |
| [IDP-19](issues/IDP-19.md) | Story | Done | low | examples/minimal-service conformance fixture and make conformance |
| [IDP-20](issues/IDP-20.md) | Bug | In Progress | medium | Definition-of-Done Stop hook runs spec-trace before a guided spec is approved |
| [IDP-21](issues/IDP-21.md) | Story | Done | low | python-uv profile hardening: reproducible tool resolution and a clean wheel |
| [IDP-22](issues/IDP-22.md) | Story | Done | low | idp validate/conformance: close Makefile contract-check bypasses |
| [IDP-23](issues/IDP-23.md) | Story | To Do | medium | idp conformance: minimal environment and guaranteed process cleanup for example runs |
| [IDP-24](issues/IDP-24.md) | Story | Done | low | idp-gate build hardening follow-ups: locked build backend, clean uv build env, symlinked-dir test |
| [IDP-25](issues/IDP-25.md) | Story | Done | low | idp-gate: constrain the build backend for editable uv sync builds (CI and make setup) |
| [IDP-26](issues/IDP-26.md) | Story | To Do | low | CI and make setup: fail on a stale uv.lock instead of silently re-locking |
| [IDP-27](issues/IDP-27.md) | Story | To Do | low | idp-gate: reject environment markers in build-constraints.txt |
| [IDP-28](issues/IDP-28.md) | Story | Done | medium | idp validate/conformance: read Makefiles as make does (logical lines) and pin dynamic includes |
| [IDP-29](issues/IDP-29.md) | Story | To Do | medium | idp validate/conformance: fail closed on archive-syntax includes and top-level tab define; strip pin spelling like make |
| [IDP-30](issues/IDP-30.md) | Story | To Do | medium | idp conformance: bound make output and fail examples whose includes make would look up outside the service directory |
| [IDP-31](issues/IDP-31.md) | Story | Done | low | ADR-0013: conformance trust model (the Makefile scanner is a correctness check, not a security boundary) |
| [IDP-32](issues/IDP-32.md) | Story | To Do | low | review-self: triage review findings (fix regressions and AC bypasses in the PR, follow up the rest) and confirm fixes |
| [IDP-33](issues/IDP-33.md) | Story | To Do | medium | templates/python-fastapi: copier template for a new tenant repo, checked by platform CI |
| [IDP-34](issues/IDP-34.md) | Story | To Do | medium | Reusable PR pipeline: service-pipeline.yml + _pr-checks.yml with setup-profile and idp-validate composite actions |
| [IDP-35](issues/IDP-35.md) | Story | To Do | medium | Platform release v0.1.0: release-please, moving v0 tag, CLI installable from the tag |
| [IDP-36](issues/IDP-36.md) | Story | To Do | low | Generate the studytimer repo from templates/python-fastapi@v0.1.0 with PR checks from the platform |
| [IDP-37](issues/IDP-37.md) | Story | To Do | low | StudyTimer dry run: GET /version via /implement-ticket (iteration 2 exit criterion) |
| [IDP-38](issues/IDP-38.md) | Story | To Do | low | Guard ADR-0013's premise: workflows that run make verify or idp conformance must hold no credentials |
| [IDP-39](issues/IDP-39.md) | Story | To Do | medium | Guard catches split-word approval runs (appr"ove"-spec, appr\ove-spec, $'\x61…') |
| [IDP-40](issues/IDP-40.md) | Bug | To Do | medium | guard_bash blocks `git commit -F -` heredoc messages that mention spec approval |
| [IDP-41](issues/IDP-41.md) | Task | To Do | low | guard_bash protected-path rule runs in linear time |
| [IDP-42](issues/IDP-42.md) | Task | To Do | low | guard_bash hardening: rg --hostname-bin as output option, real Python 3.9 test run |
| [IDP-43](issues/IDP-43.md) | Bug | To Do | medium | guard_bash protected-path rule blocks heredocs that only mention .github/ paths |
| [IDP-44](issues/IDP-44.md) | Task | To Do | low | Warn at session start when the installed idp-agentic plugin differs from the repo copy |

## No epic

| Key | Type | Status | Risk | Summary |
|---|---|---|---|---|
| [IDP-14](issues/IDP-14.md) | Bug | Done | medium | guard_bash false positive: blocks commands that only mention approve-spec or APPROVED as text |
| [IDP-15](issues/IDP-15.md) | Bug | To Do | low | idp CLI: validate ticket keys before using them as paths (approve-spec can write outside specs/) |
