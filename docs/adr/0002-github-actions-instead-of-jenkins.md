# 0002. GitHub Actions instead of Jenkins

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
Design doc §6 specifies Jenkins with a shared library. The user asked for GitHub Actions; a Jenkins controller would add cost and operations work for one developer.
## Decision
Use GitHub Actions for PR checks and for G0–G5 orchestration. Reusable workflows (`_gate-*.yml`) and composite actions (`.github/actions/*`) play the role of `idp-jenkins-lib`. All logic stays in the Python `idp-gate` CLI, which keeps the orchestrator replaceable (design doc §5). Third-party actions are pinned by commit SHA.
## Consequences
+ No controller to run; native OIDC to AWS; Environments give G4 approvals.
- Long G3 runs are bounded by job limits (6 h per job), which is acceptable for scaled durations. Runner minutes are free on public repos.
