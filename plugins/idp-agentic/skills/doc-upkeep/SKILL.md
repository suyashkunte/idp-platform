---
name: doc-upkeep
description: Keep docs consistent with the change - README, docs/, ADRs for design decisions, runbooks, metrics dictionary and CHANGELOG. Use after implementation and before the PR, or on a schedule to detect doc drift.
---

# Documentation upkeep

Delegate to `doc-upkeeper` with the branch diff and the spec. It must:
- add an entry under `## [Unreleased]` in `CHANGELOG.md` (Keep a Changelog), prefixed with the ticket key;
- update any doc whose described behaviour, command, config or interface changed;
- add an ADR in `docs/adr/` (MADR, next free number, status Proposed) only if the plan records a design decision;
- check that relative links in touched docs resolve.
Docs only. No code changes.
