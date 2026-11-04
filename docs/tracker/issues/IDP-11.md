---
key: IDP-11
type: Story
status: Done
summary: "Platform CI workflow and main branch ruleset"
parent: IDP-6
labels: [component:pipeline, iteration:1, repo:idp-platform, risk:medium]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T00:42:19.053+0530
updated: 2026-10-07T02:00:52.514+0530
resolved: 2026-10-07T02:00:52.499+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-11
---

# IDP-11: Platform CI workflow and main branch ruleset

Epic/parent: [IDP-6](IDP-6.md)

## Description

## Context / why

From now on nothing reaches `main` without a PR and green checks, including changes made by agents (demo-mode governance, Q4).

## Acceptance criteria

* AC-1 Given a PR to main, when it is opened, then `platform-ci / verify` runs `make verify` plus pre-commit (incl. gitleaks) and reports a status check.
* AC-2 Given the ruleset `main-protection` (stored in `.github/rulesets/main.json`), when anyone pushes directly to main, then the push is rejected.
* AC-3 Given a PR with a failing `verify` check, then it cannot be merged.
* AC-4 Given the ruleset, then force-push and branch deletion on main are blocked and history is linear (squash merge).

## Non-functional criteria

Third-party actions pinned by commit SHA; workflow `permissions` least privilege.

## Out of scope

Required approvals (0 in demo mode).

## Comments (0)
