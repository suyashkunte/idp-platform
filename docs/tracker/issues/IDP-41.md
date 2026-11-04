---
key: IDP-41
type: Task
status: To Do
summary: "guard_bash protected-path rule runs in linear time"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T21:12:24.643+0530
updated: 2026-10-20T21:13:04.743+0530
resolved:
links:
  - {type: "blocks", key: IDP-43}
  - {type: "relates to", key: IDP-14}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-41
---

# IDP-41: guard_bash protected-path rule runs in linear time

Epic/parent: [IDP-16](IDP-16.md)

Links: blocks [IDP-43](IDP-43.md); relates to [IDP-14](IDP-14.md)

## Description

## Context / why

Follow-up from the IDP-14 review (PR #15). The protected-path rule in `guard_bash.py` (`(>|tee|sed -i|cp|mv|rm)[^;&|]*(\.github/|\.claude/settings\.json|\.claude/idp-protected-paths)`) is unchanged and backtracks quadratically. It takes 0.5–1.9 s on 400 × (`>` + 1000 spaces), which breaks the hook's under-1-second NFR on adversarial input. IDP-14 AC-4 kept it unchanged on purpose.

## Acceptance criteria

* **AC-1** Given 400 × (`>` + 1000 spaces), or a 200 KB line of redirect operators and spaces, when guard_bash `check()` runs, then it returns in under 1 s.
* **AC-2** (edge) Given every command in the existing IDP-10 dangerous/normal lists (including `sed -i 's/a/b/' .github/workflows/ci.yml`) and the IDP-14 lists, when guard_bash runs, then each verdict is unchanged.
* **AC-3** Given the other legacy RULES, then each is checked for the same quadratic pattern; any found get the same fix or a recorded follow-up.

## Non-functional criteria

Stdlib-only, Python 3.9+.

## Out of scope

Changing which commands the rule blocks (that's the `.github` false-positive ticket).

## Interfaces / dependencies

`plugins/idp-agentic/hooks/**` is protected: human placement after spec approval. Related: IDP-14.

## Test approach

In-process timing tests (as in IDP-14's `test_large_command_is_checked_within_a_second`), red on the current hook; the existing lists stay green.

## Definition of Done

Spec approved; hook placed; `make verify` green; spec-trace OK; review; CHANGELOG.

## Comments (0)
