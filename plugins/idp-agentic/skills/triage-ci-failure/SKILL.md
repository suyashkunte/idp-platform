---
name: triage-ci-failure
description: Classify a failing PR check (product defect, test defect, environment, data, infrastructure) and propose a fix. Advisory only. Use when a PR check fails ("why did CI fail on my PR?").
---

# CI failure triage (design doc §11.4)

Delegate to the `ci-triage` subagent with the PR number. It reads `gh pr checks`, `gh run view --log-failed` and the
branch diff, and returns JSON: `classification`, `confidence`, `evidence` (quotes with file:line or log lines),
`suggested_next_step`, `requires_human_confirmation: true`.
Never re-run CI to make a failure disappear, and never reclassify a product failure as environment without evidence.
