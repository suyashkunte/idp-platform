# 0012. Build profiles for language-agnostic pipelines

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Decision
A build profile (`build-profiles/<name>/profile.yaml` + scripts) supplies toolchain setup, default make targets, SCA/SBOM settings, the coverage format and agent notes for one stack. v1 ships `python-uv` and `dockerfile` (generic: any stack that has a Dockerfile and implements the Make contract). Further profiles (`node-pnpm`, `go`, `java-gradle`) are additive.
## Consequences
+ The gate engine never branches on language; tenant #2 (iteration 11) proves the `dockerfile` path.
- Profile-specific quality signals (mutation testing) are optional per profile and reported as advisory where unsupported.
