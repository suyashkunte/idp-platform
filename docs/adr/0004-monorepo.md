# 0004. Single monorepo for app and IDP platform

- **Status:** Superseded by [ADR-0009](0009-platform-as-a-product.md)
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
Design doc §4.7 keeps product services in their own repos and IDP assets in a monorepo.
## Decision
One repo `idp-platform` contains `services/studytimer`, `services/gatekeeper`, `packages/`, `policy/`, `infra/`, `deploy/` and the AI configuration. Ownership is enforced with CODEOWNERS and path-filtered workflows.
## Consequences
+ Atomic changes, one set of agent rules, simplest possible handover.
- The "15-line Jenkinsfile in a service repo" onboarding pattern is shown as a reusable workflow call instead; a split with `git filter-repo` remains straightforward.
