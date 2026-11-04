---
key: IDP-10
type: Story
status: Done
summary: "idp-agentic Claude Code plugin: skills, subagents, hooks, templates"
parent: IDP-6
labels: [component:ai-tooling, iteration:1, repo:idp-platform, risk:high]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T00:42:17.940+0530
updated: 2026-10-07T02:00:51.420+0530
resolved: 2026-10-07T02:00:51.402+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-10
---

# IDP-10: idp-agentic Claude Code plugin: skills, subagents, hooks, templates

Epic/parent: [IDP-6](IDP-6.md)

## Description

## Context / why

The spec-driven ticket-to-PR workflow (design doc §21), distributed as a versioned plugin so every repo gets identical behaviour and guardrails (ADR-0011).

## Acceptance criteria

* AC-1 Given this repo's `.claude-plugin/marketplace.json`, when a repo enables `idp-agentic@idp-platform`, then the skills and subagents load.
* AC-2 Given an agent edit to a path listed in `.claude/idp-protected-paths.txt` (or a default protected path), when the PreToolUse hook runs, then the edit is blocked with exit 2 and a reason.
* AC-3 Given a Bash command that pushes to main, force-pushes, merges or approves a PR, approves a spec, or applies Terraform/kubectl, when the PreToolUse hook runs, then it is blocked.
* AC-4 Given a feature branch `feature/<KEY>-*` whose spec has an AC without a test, when the agent tries to stop, then the Stop hook blocks once with the spec-trace output, and does not loop (`stop_hook_active`).
* AC-5 Given `/implement-ticket <KEY>` on a ticket failing the Definition of Ready, then the agent comments the gaps on the ticket and stops.
* AC-6 Plugin structure (manifest, frontmatter of every skill and agent, hook script paths) is validated by tests in CI.

## Non-functional criteria

Hooks use only POSIX shell or stdlib Python 3.9+ (they run before any venv exists); each runs in under 1 s.

## Out of scope

Advisory AI review in CI (Q10).

## Comments (0)
