---
key: IDP-32
type: Story
status: To Do
summary: "review-self: triage review findings (fix regressions and AC bypasses in the PR, follow up the rest) and confirm fixes"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T13:00:36.023+0530
updated: 2026-10-20T13:00:36.132+0530
resolved:
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-32
---

# IDP-32: review-self: triage review findings (fix regressions and AC bypasses in the PR, follow up the rest) and confirm fixes

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

On IDP-28 the review findings repeatedly grew the ticket. Findings outside the ticket's ACs became spec amendments, so the spec needed three human approvals. The same ticket also showed that a fix round can introduce new problems: the confirmation check after loop 2 caught an AC-13 bypass and a CPU slowdown that the fix itself introduced. The `review-self` skill should make both lessons the default.

## Acceptance criteria

* **AC-1** Given `review-self` has collected BLOCKER and MAJOR findings, then it fixes in the PR only findings that are a regression introduced by the branch or a failure or bypass of one of the ticket's ACs. Every other finding goes into the PR body under "Review findings left for the human reviewer", each with a proposed follow-up ticket summary.
* **AC-2** Given a fix round changed code, then before the PR is opened `review-self` runs a narrow confirmation check: the security-reviewer, plus the code-reviewer if production code changed, reviewing only the fix diff and re-running the original repros. Problems introduced by the fix count as regressions and are fixed. A confirmation check does not count as one of the two review loops.
* **AC-3** (edge) Given a finding whose fix would need an approved spec to change (a new or changed AC, or a decision recorded in `spec.md`), then the skill stops and asks the human to choose between amending the spec (with re-approval) and a follow-up ticket. It never amends an approved spec on its own.
* **AC-4** Given `implement-ticket` step 8 and the `pr-generate` PR body template, then both describe the same triage rule, and the template's findings section has a "Proposed follow-ups" sub-list.

## Non-functional criteria

None. The plugin still passes `claude plugin validate --strict`.

## Out of scope

* Changes to hooks (protected; IDP-14 and IDP-20).
* Changes to the reviewer agents' prompts beyond what the triage needs.

## Interfaces / dependencies

* Touches `plugins/idp-agentic/skills/review-self/SKILL.md`, `skills/implement-ticket/SKILL.md` and `skills/pr-generate/templates/pr-body.md`.
* No protected paths.

## Test approach

* Extend the plugin structure tests: assert that the skill texts contain the triage rule, the confirmation-check step and the stop-and-ask rule, and that the template has the new sub-list.

## Definition of Done

* ACs traced.
* `make verify` green, including `validate-plugin`.
* CHANGELOG entry and plugin version bump if the plugin has one.

## Comments (0)
