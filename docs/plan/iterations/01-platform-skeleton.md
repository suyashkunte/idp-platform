# Iteration 1: platform skeleton and agentic plugin

| | |
|---|---|
| **Epic** | IDP-6 (stories IDP-7 … IDP-11) |
| **PRs** | #1 platform skeleton (ab61f69), #2 IDP-13 dry run (ac962be) |
| **Status** | ✅ Done 2026-10-07 |

## Done
- IDP-7: uv workspace, `Makefile` contract, pre-commit (gitleaks), ruff/mypy strict.
- IDP-8: `idp` CLI v0: `spec-trace`, `test-quality-lint`, `approve-spec` (refused when `CLAUDECODE` is set), `validate`.
- IDP-9: `idp-service.v1` schema inside `idp-gate` (adds `metadata.tracker.site`).
- IDP-10: `idp-agentic` plugin v0.1.0 (11 skills, 9 subagents, 4 hooks), marketplace, `.claude/settings.json`
  (GitHub marketplace + allow/deny lists), `.claude/idp-protected-paths.txt`. `claude plugin validate --strict` passes for
  both the plugin and the marketplace.
- 84 tests green (62 plugin structure/guardrail tests), 96 % coverage.
- IDP-11 (partial): `.github/rulesets/main.json`, `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `CHANGELOG.md`.

## Guardrail event (kept on purpose as a record)
When the committed project settings took effect, Claude Code denied the agent's `Write` to `.github/workflows/platform-ci.yml`
(deny rule `Edit(.github/**)`). A shell heredoc in the same step had already written the three `.github/` files listed
above. That is the shell bypass the plugin's `guard_bash.py` blocks once the plugin is loaded (the plugin was not yet
active in that session). The human reviews those files in the PR, and places the CI workflow from the prepared copy.

## Outcome
| Exit criterion | Result |
|---|---|
| Plugin installs from the marketplace; structure validated in CI | ✅ `claude plugin validate --strict` in platform-ci |
| Guardrail demos | ✅ 62 automated hook/structure tests; live: Claude Code denied an agent `Write` to `.github/**`, a `git push origin main`, and an `rm -rf` during this iteration |
| Dummy Ready ticket through `/implement-ticket` to a draft PR | ✅ IDP-13 (`idp spec-trace --json`): spec → failing tests (separate commit) → 2 implementation commits → verify → reviewer agents → CHANGELOG → draft PR #2 → human spec approval → merge |
| `main` protected; platform CI required | ✅ Ruleset `main-protection` (id 24608294): PR, squash, required `verify`, linear history, no force-push or deletion |

## Learnings → tickets
| Learning | Action |
|---|---|
| Bash guard matched approval-command *text* inside heredocs (false positive) | IDP-14 |
| Ticket keys used unvalidated as paths (`approve-spec` writes) | IDP-15 |
| `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19 | IDP-12 (due 2026-10-16) |
| The committed settings' deny rules apply to the platform-building session too, so even hand-built work must go through the human for `.github/**` | Kept as a feature: guardrail files are human-placed (this iteration) |
| No CI check enforces spec approval yet | Planned in iteration 2 `_pr-checks.yml` (`spec-approved`, advisory in demo mode) |

## Metrics (first data points)
| Metric | IDP-13 |
|---|---|
| Ticket-to-draft-PR (agent time) | about 1 session |
| AC traceability | 4/4 (100 %) |
| Review rework loops | 1 (5 minors deferred) |
| Human interventions | 2 (removed a `type: ignore`; worked around guard false positive) |
