---
key: IDP-7
type: Story
status: Done
summary: "Platform Python workspace and developer tooling"
parent: IDP-6
labels: [component:pipeline, iteration:1, repo:idp-platform, risk:low]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T00:42:07.941+0530
updated: 2026-10-07T02:00:48.587+0530
resolved: 2026-10-07T02:00:48.562+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-7
---

# IDP-7: Platform Python workspace and developer tooling

Epic/parent: [IDP-6](IDP-6.md)

## Description

## Context / why

Every package, check and agent workflow depends on one reproducible toolchain and one set of entry points (the Make contract, design doc §21.10).

## Acceptance criteria

* AC-1 Given a fresh clone, when I run `make setup`, then uv installs Python 3.12 and all workspace packages, and the pre-commit hooks are installed.
* AC-2 Given the repo, when I run `make verify`, then ruff (lint + format check), mypy strict, pytest with coverage and bandit all run, and the command fails on any finding.
* AC-3 Given a changed Python file, when I run `make format FILES=<path>`, then only that file is formatted.
* AC-4 Given a commit containing a secret pattern, when pre-commit runs, then gitleaks blocks the commit.

## Non-functional criteria

`make verify` completes in under 2 minutes on a laptop.

## Out of scope

Container builds, gate workflows.

## Definition of Done

Platform `CLAUDE.md` documents the commands; CONTRIBUTING.md explains the setup.

## Comments (0)
