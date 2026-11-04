---
key: IDP-43
type: Bug
status: To Do
summary: "guard_bash protected-path rule blocks heredocs that only mention .github/ paths"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T21:12:41.499+0530
updated: 2026-10-20T21:13:07.911+0530
resolved:
links:
  - {type: "is blocked by", key: IDP-41}
  - {type: "relates to", key: IDP-14}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-43
---

# IDP-43: guard_bash protected-path rule blocks heredocs that only mention .github/ paths

Epic/parent: [IDP-16](IDP-16.md)

Links: is blocked by [IDP-41](IDP-41.md); relates to [IDP-14](IDP-14.md)

## Description

## Context / why

IDP-14 Q1, deferred to a follow-up. The protected-path rule blocks any command with `>`, `tee`, `sed -i`, `cp`, `mv` or `rm` followed anywhere by `.github/`, `.claude/settings.json` or `.claude/idp-protected-paths`. So `cat > pr.md <<'EOF' … edit .github/workflows/ci.yml … EOF` is blocked: a PR body that only _mentions_ a protected path. Agents hit this when writing PR bodies and notes (iteration-2 learnings) and route around it with Write/Edit. IDP-14 fixed the same class of problem for the approval rules with relax-only span accounting.

## Acceptance criteria

* **AC-1** Given quoted or heredoc text that only mentions `.github/…`, `.claude/settings.json` or `.claude/idp-protected-paths`, given to an inert printer (with every command in the line inert, as in IDP-14), when guard_bash runs, then it is allowed.
* **AC-2** Given a redirect, `tee`, `sed -i`, `cp`, `mv` or `rm` whose target is one of those paths (quoted or not), when guard_bash runs, then it blocks; the existing IDP-10 case `sed -i 's/a/b/' .github/workflows/ci.yml` still blocks.
* **AC-3** (edge) Given an input the lexer is unsure about (unterminated quote or heredoc, backticks, `((`), when guard_bash runs, then the old raw rule decides.
* **AC-4** Given the existing IDP-10 and IDP-14 lists, then they all still pass.

## Non-functional criteria

Stdlib-only, Python 3.9+, under 1 s.

## Out of scope

Changing which paths are protected; protect_paths.py (Edit/Write).

## Interfaces / dependencies

`plugins/idp-agentic/hooks/**` is protected: human placement after spec approval. Depends on the linear-time protected-path rule ticket (same rule; do that first). Related: IDP-14.

## Test approach

Relax-only, as in IDP-14: mention-only cases (red on the current hook) and write cases (must stay blocked); confirm writes with a throwaway dir.

## Definition of Done

Spec approved; hook placed; `make verify` green; spec-trace OK; independent review; CHANGELOG.

## Comments (0)
