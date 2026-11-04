---
key: IDP-44
type: Task
status: To Do
summary: "Warn at session start when the installed idp-agentic plugin differs from the repo copy"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T21:12:48.961+0530
updated: 2026-10-20T21:13:10.612+0530
resolved:
links:
  - {type: "relates to", key: IDP-14}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-44
---

# IDP-44: Warn at session start when the installed idp-agentic plugin differs from the repo copy

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-14](IDP-14.md)

## Description

## Context / why

IDP-14 Q4/A8. Hooks run from `${CLAUDE_PLUGIN_ROOT}`, the installed plugin copy. A fix merged to the repo (such as IDP-14's guard) reaches a session only after the plugin is updated. Nothing tells the human or the agent that the installed guard is stale, so a stale copy can keep blocking or allowing commands the repo no longer does.

## Acceptance criteria

* **AC-1** Given a session that starts in a checkout of this repo, where a file under the installed plugin's `hooks/` differs from the repo's `plugins/idp-agentic/hooks/` (by content hash), when the SessionStart hook runs, then it prints one warning naming the differing files and the update command, and exits 0 (never blocks the session).
* **AC-2** Given the installed copy matches, or the session is not in this repo, when the hook runs, then it prints nothing.
* **AC-3** (edge) Given `CLAUDE_PLUGIN_ROOT` is unset or unreadable, or the plugin is loaded from the repo checkout itself, when the hook runs, then it exits 0 without a traceback.

## Non-functional criteria

Stdlib-only, Python 3.9+, under 200 ms.

## Out of scope

Auto-updating the plugin; checking skills/agents (hooks only for now); the version bump itself (a human edit to marketplace.json).

## Interfaces / dependencies

Adds a SessionStart entry to `plugins/idp-agentic/hooks/hooks.json` plus a script under `hooks/scripts/`: protected paths, human placement after spec approval. Related: IDP-14.

## Test approach

Unit tests with a temp "installed" plugin dir via run_hook (as in tests/plugin): differing, matching and missing cases.

## Definition of Done

Spec approved; hook placed; `make validate-plugin` and `make verify` green; spec-trace OK; review; CHANGELOG; docs note on updating the plugin.

## Comments (0)
