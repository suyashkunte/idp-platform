# 0011. Distribute the agentic SDLC as a Claude Code plugin

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
Design doc §21 places CLAUDE.md, skills, subagents and hooks inside each repo. Copying those files to many repos makes them drift apart.
## Decision
Package the skills, subagents, hooks and spec templates as the `idp-agentic` plugin, listed in a marketplace at `idp-platform/.claude-plugin/marketplace.json`. Tenant repos enable it through `.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`) and keep only an app-specific `CLAUDE.md` and permission additions. Skills depend only on the Make contract and `idp.yaml`. Plugin changes ship with platform releases, and eval suites in `evals/` serve as their release tests. Validate the exact settings keys against the Claude Code version in use.
## Consequences
+ One source of truth for the agentic workflow; versioned upgrades; identical guardrails in every repo.
- Repo-local guardrails still need GitHub rulesets (plugins can't enforce server-side rules).
