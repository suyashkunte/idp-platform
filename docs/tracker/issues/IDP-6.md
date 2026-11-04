---
key: IDP-6
type: Epic
status: Done
summary: "E2 Platform skeleton & agentic plugin (iteration 1)"
parent:
labels: [component:ai-tooling, iteration:1, repo:idp-platform]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T00:41:38.028+0530
updated: 2026-10-07T02:09:15.215+0530
resolved: 2026-10-07T02:09:15.207+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-6
---

# IDP-6: E2 Platform skeleton & agentic plugin (iteration 1)

## Description

## Context / why

Last hand-built iteration. It delivers the tooling that every later change runs through: the platform workspace, the `idp` CLI, the service-contract schema, and the `idp-agentic` Claude Code plugin (skills, subagents, hooks, templates), plus platform CI and branch protection. See `docs/plan/PROJECT_PLAN.md` §8–§9.

## Exit criteria

* The `idp-agentic` plugin installs from this repo's marketplace and its structure is validated in CI
* Guardrail demos pass: protected-path edit blocked, push to main blocked, approve-spec refused for agents, early Stop blocked until DoD passes
* A dummy Ready ticket goes through `/implement-ticket` to a draft PR with spec, AC-tagged tests, code and evidence
* `main` protected by a ruleset; platform CI is a required check

## Comments (1)

### Suyash Kunte, 2026-10-07T01:18:41.995+0530

PR opened: https://github.com/suyashkunte/idp-platform/pull/1. `platform-ci / verify` is green ([run 37521491729](https://github.com/suyashkunte/idp-platform/actions/runs/37521491729)): 84 tests, 96 % coverage, strict plugin validation, gitleaks clean. IDP-7…IDP-11 moved to In Review. Waiting for human review and merge; then the main ruleset is applied and the dry-run ticket follows.
