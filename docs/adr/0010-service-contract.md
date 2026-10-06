# 0010. Service contract (idp.yaml), Make contract and generic chart

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Decision
Every tenant declares itself in `idp.yaml` (schema `idp-service.v1`), exposes a fixed set of `make` targets, emits standard evidence formats (JUnit, Cobertura, SARIF, CycloneDX, `test-summary.v1`) and meets a runtime contract (health endpoints, `/metrics`, JSON logs, `OTEL_*`). The platform renders deployment from `idp.yaml` through the generic `idp-service` chart; apps needing more may ship a chart built on the `idp-service-base` library chart. Policy `overrides` in `idp.yaml` may only tighten thresholds; the evaluator enforces this.
## Consequences
+ Agents, CI and gates are language- and app-agnostic; onboarding is configuration only.
- The contract becomes a compatibility commitment: schema changes follow semver with `idp validate --fix` migrations.
See docs/platform/service-contract.md.
