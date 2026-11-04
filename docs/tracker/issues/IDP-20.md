---
key: IDP-20
type: Bug
status: In Progress
summary: "Definition-of-Done Stop hook runs spec-trace before a guided spec is approved"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T10:46:15.375+0530
updated: 2026-10-20T22:16:32.459+0530
resolved:
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-20
---

# IDP-20: Definition-of-Done Stop hook runs spec-trace before a guided spec is approved

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

Found while running IDP-12 (guided mode). `plugins/idp-agentic/hooks/scripts/definition_of_done.py` activates on any `feature/<KEY>-*` branch that has `specs/<KEY>/spec.md` and unpushed work, and runs `make spec-trace KEY=<KEY>`. Right after the spec commit (implement-ticket step 3) no tests exist yet, so the hook blocks the agent's stop with "Definition of Done NOT met … keep working". In guided mode the agent must STOP at checkpoint A until the human approves, so the hook pushes the agent to write tests before approval, which bypasses the human checkpoint. The agent correctly ignored it in IDP-12, but the guardrails contradict each other.

## Acceptance criteria

* **AC-1** Given a branch `feature/<KEY>-…` whose `specs/<KEY>/spec.md` front matter has `mode: guided` and no `specs/<KEY>/APPROVED` exists, when the agent stops, then the hook does not run spec-trace and does not block on missing AC citations (it still runs `make verify-fast` when defined).
* **AC-2** Given `specs/<KEY>/APPROVED` exists, or the spec has `mode: auto`, when tests do not cite every AC, then the hook still blocks exactly as today.
* **AC-3 (edge)** Given the spec has no front matter or an unrecognised `mode`, then the hook behaves as today (runs spec-trace; fail closed).
* **AC-4** Given AC-1's skip, then the hook's stderr/exit is silent (exit 0) so no "keep working" prompt is sent.

## Non-functional criteria

Stdlib only, Python 3.9+ (unchanged hook constraints). No new latency beyond reading one small file.

## Out of scope

guard_bash false positives (IDP-14). Changing the spec front-matter format.

## Interfaces / dependencies

`plugins/idp-agentic/hooks/scripts/definition_of_done.py`; spec front matter written by the spec-author skill (`mode: guided|auto`); `tests/plugin/test_hooks.py`.
`plugins/idp-agentic/hooks/**` is a protected path: the agent prepares tests and the proposed patch, a human places the hook change (same as IDP-14).

## Test approach

Extend `tests/plugin/test_hooks.py`: temp git repo fixtures on a feature branch with guided spec without/with APPROVED, auto spec, and spec without front matter; assert exit codes and stderr.

## Definition of Done

ACs traced; `make verify` green; plugin version bumped; CHANGELOG entry.

Labels: repo:idp-platform, component:ai-tooling, risk:medium, spec:guided

## Comments (1)

### Suyash Kunte, 2026-10-20T22:16:32.459+0530

**Spec drafted** (branch `feature/IDP-20-dod-hook-guided-approval`, `specs/IDP-20/`). Guided mode: waiting for spec approval.

**Approach:** `definition_of_done.py` skips spec-trace, silently, while a spec with `mode: guided` in its front matter has no current approval marker. `verify-fast` still runs. An approved or `auto` spec, missing front matter, or an unknown mode keeps today's behaviour (fail closed). AC-3 is reformatted to `**AC-3** (edge)` so spec-trace can parse it; the words are unchanged.

**Human tasks:** H1, place the hook from plan.md right after approval. H2, the marketplace.json version bump in the same PR.

**Pre-check of H1:** ruff is clean and it parses as Python 3.9. In 11 temp-repo scenarios it gave the right result every time; the old hook blocks in all of them.

**Open questions (recommendation in brackets):**

* Q1: a stale marker (spec edited after approval) counts as not approved, so the hook stays quiet while re-approval is pending \[yes\]
* Q2: a failing `verify-fast` still blocks during the skip \[yes\]
* Q3: an agent could set `mode: guided` to silence the hook. Residual risk, because CI does **not** run spec-trace today: PR checkouts are detached, so the Makefile's branch-based key is empty. Confirmed: PR #15's CI log has no spec-trace output. \[accept here; follow-up ticket for CI spec-trace via `GITHUB_HEAD_REF`, a protected Makefile edit\]
* Q4: version bump to the next patch after main (0.1.2 if PR #16 merges first)
* Q5: strict parsing (exact unquoted lowercase `guided`) \[yes\]
