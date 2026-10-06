# 0009. Platform as a product: platform repo + tenant repos

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
The goal is to take this platform and use it for **any** application end to end. A single monorepo holding app and platform (ADR-0004) lets the app depend on platform internals without anyone noticing, which proves nothing about reusability.
## Decision
`idp-platform` is a versioned product (semver, release-please, moving major tag `v1`). It publishes reusable workflows, composite actions, the `idp` CLI, `idp-testkit`, a generic Helm chart, policy profiles, JSON schemas, a Claude Code plugin marketplace, copier templates and Terraform modules. It also operates the shared multi-tenant services (Gatekeeper, evidence store, cluster, observability) and owns the service catalog. Applications live in **their own repos** and consume only published interfaces; StudyTimer is tenant #1.
## Consequences
+ Reusability is enforced by structure; an upgrade path (Renovate) is part of the design; the design doc's §4.7 split is restored.
- Two repos to coordinate; mitigated by a VS Code multi-root workspace and platform CI that runs conformance tests against `examples/minimal-service`.
Supersedes ADR-0004.
