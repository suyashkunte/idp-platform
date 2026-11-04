---
key: IDP-40
type: Bug
status: To Do
summary: "guard_bash blocks `git commit -F -` heredoc messages that mention spec approval"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T21:12:17.515+0530
updated: 2026-10-20T21:13:03.761+0530
resolved:
links:
  - {type: "relates to", key: IDP-14}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-40
---

# IDP-40: guard_bash blocks `git commit -F -` heredoc messages that mention spec approval

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-14](IDP-14.md)

## Description

## Context / why

Follow-up from the IDP-14 review (PR #15). Agents write multi-line commit messages with `git commit -F - <<'EOF' … EOF`. When the body mentions the approval make target or a `specs/<KEY>/APPROVED` marker, guard_bash blocks it. Main blocks it too, so this is not a regression, but it is a false positive that pushes agents towards workarounds. IDP-14 treats only the `-m/--message` values of git commit as data, not its stdin.

## Acceptance criteria

* **AC-1** Given `git commit -F - <<'EOF'` (or `--file=-`) whose quoted-delimiter heredoc body mentions the approval target or a marker path, with every command in the line inert, when guard_bash runs, then it is allowed.
* **AC-2** (edge) Given the same with an unquoted delimiter whose body contains `$(`, a backtick or `${`, or a line that also has a non-inert command (e.g. `make verify && git commit -F - <<'EOF' …`), when guard_bash runs, then it blocks.
* **AC-3** Given `git commit -F <marker path>`, `git commit --file=<marker path>` or `git commit -m x -- <marker path>`, when guard_bash runs, then it still blocks.
* **AC-4** Given the existing IDP-10 and IDP-14 lists in `tests/plugin/test_hooks.py`, then they all still pass.

## Non-functional criteria

Hook stays stdlib-only, Python 3.9+, under 1 s.

## Out of scope

Other git subcommands (`tag -F`, `notes -F`); other rules.

## Interfaces / dependencies

`plugins/idp-agentic/hooks/**` is protected: the human places the hook code after spec approval. Related: IDP-14. Coordinate with IDP-39 (same hook).

## Test approach

MENTIONS_ONLY and block-list cases, red on the IDP-14 hook where expected; a fake-git check is not needed (no execution path).

## Definition of Done

Spec approved; hook placed; `make verify` green; spec-trace OK; independent review; CHANGELOG.

## Comments (0)
