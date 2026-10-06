# Iteration 1: platform skeleton and agentic plugin

| | |
|---|---|
| **Epic** | IDP-6 (stories IDP-7 … IDP-11) |
| **Branch** | `feature/IDP-6-platform-skeleton` (not yet pushed) |
| **Status** | In progress, paused 2026-10-07 |

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

## Next steps (resume here)
1. Human copies the prepared workflow to `.github/workflows/platform-ci.yml` (placed by the human on 2026-10-07; spec for reference:
   regenerate it from this spec: checkout@v7.0.1, setup-uv@v10.2.0, `make verify`, pre-commit, `claude plugin validate
   --strict`, upload reports; job id `verify`; actions pinned by SHA).
2. Commit, push the branch, open the PR (do not merge). Watch `platform-ci / verify`.
3. Human merges the PR (squash). Then, with approval, apply the ruleset:
   `gh api -X POST repos/suyashkunte/idp-platform/rulesets --input .github/rulesets/main.json`.
4. Create the dry-run ticket (e.g. "add `idp version` command", risk:low, spec:auto) and have the human run
   `/implement-ticket IDP-<n>` in a fresh Claude Code session; record the guardrail demos.
5. Close IDP-7…IDP-11 and IDP-6 with evidence; write the outcome section of this log.
