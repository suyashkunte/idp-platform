# 0013. Conformance trust model

- **Status:** Accepted
- **Date:** 2026-10-20
- **Deciders:** Suyash Kunte

## Context and problem statement
IDP-22 and IDP-28 hardened the static Makefile scanner (`idp validate`, and the scan inside `idp conformance`) over
four review rounds. Each round found another place where the scanner and GNU make disagree, and IDP-29 and IDP-30
would continue that. IDP-22 decision D3 already concluded that `idp validate` "is not a security boundary for tenant
content".

Why the scanner is not where the security boundary belongs:
- In `platform-ci.yml` the PR's own root `Makefile` and its own copy of the scanner run in the same job
  (`permissions: contents: read`; no secrets, only a read-only `GITHUB_TOKEN` that the PR's own code can already
  use). A malicious PR would change them rather than get past them.
- `examples/` is platform-owned and reviewed like code (see the trust comment in
  `packages/idp-gate/src/idp_gate/conformance.py`).
- The validated `verify` recipe is arbitrary shell anyway; a Makefile that passes the scan can still run anything.
- The intended protections are the conformance sandbox (IDP-23, not yet implemented: minimal environment, process
  cleanup, no stored credentials) and per-tenant, least-privilege AWS roles (iteration 3).

Agreed with the human on 2026-10-20 and recorded here so that reviews and tickets weigh scanner findings accordingly:
as correctness findings, not as security findings.

## Decision drivers
- A static model of make cannot match make exactly; every review round found more differences.
- The cost of each hardening round against the risk it actually removes.
- Where an attacker actually is in each job, and what that job can reach.
- Consistent weighting of scanner findings in reviews.
- Keep the fast, specific, fail-closed feedback the scanner gives on honest contract mistakes.

## Considered options
1. Keep treating the scanner as a security boundary and keep hardening it (IDP-29, IDP-30 and more).
2. Treat the scanner as a fail-closed, best-effort correctness check and put the security boundary in the conformance
   sandbox and least-privilege roles.
3. Replace the static scan with make's own database (`make -pn`) now. Rejected for now: make evaluates `$(shell ...)`
   and `!=` at parse time, and even with `-n` make still runs recipes that remake included makefiles and `+` or
   `$(MAKE)` lines, so this runs tenant code and needs the IDP-23 sandbox first.
4. Remove the scanner. Rejected: loses fast, specific feedback on contract mistakes.

## Decision outcome
Chosen option 2. `idp validate` and the conformance scan are a fail-closed, best-effort correctness check, not a
security boundary. The intended security boundary is the conformance sandbox (IDP-23, not yet implemented) plus
least-privilege roles (per-tenant roles are iteration 3). Until then, what protects is the platform owner's review of
`examples/` and `build-profiles/`, and that the only CI job that runs the scanner (`platform-ci.yml`) has no secrets.

Rule: new scanner-hardening work is only taken on for a regression, or for a bypass in a job that holds credentials or
runs code it didn't write. A job "holds credentials" when it has any of: repository or organisation secrets,
`id-token: write`, a write-scoped `GITHUB_TOKEN`, cloud credentials, or a developer or agent workstation environment.
A job "runs code it didn't write" when the Makefile or scanner it executes does not come from the same change that is
being checked (for example a platform job running conformance on a tenant repository, or a tenant pipeline running the
platform's scanner on tenant code). Today's `platform-ci.yml` job is outside the rule: it has no secrets, only a
read-only `GITHUB_TOKEN` that the PR's own code can already use, and it runs the PR's own scanner on the PR's own files.

Local and agent runs: `make verify` (through `make conformance`) and `make verify-fast` (the agent Stop hook, through
the conformance tests in `make test`) run repository code, including `idp conformance examples`, with the user's
environment by design. The boundary there is human review plus the agent permission and hook layer, not the scanner,
just as `make test` runs agent-written Python. Such runs are therefore not a reason for scanner hardening.

Existing checks stay and keep failing closed; this ADR changes no behaviour.

### Consequences
- IDP-29 and IDP-30 are parked.
- Using make's own database (`make -pn` in a sandbox) is reconsidered after IDP-23.
- Scanner findings in reviews are weighed as correctness findings unless the rule applies. Regressions are always
  fixed.
- The residual-risk lists in the service contract and onboarding docs stay as documentation of known gaps, not as a
  backlog.
- Until IDP-23 and the per-tenant roles exist, the intended boundary is not in place: protection rests on the
  platform owner's review of `examples/` and `build-profiles/` and on keeping secrets out of jobs that run the scanner.
- The iteration-3 threat model builds on this ADR.
- Negative: a bypass found in a credential-free job that runs its own code stays open.
- A compliant `verify` recipe can already run anything, so in a job that holds credentials and runs code it didn't
  write the mitigation is not to give that job the credentials (for example, run the OIDC signing of ADR-0007 and
  deploys in separate jobs that run no tenant `make`); scanner fixes there are defence in depth. This is an input
  for the iteration-3 threat model, not a new requirement of this ADR.

## Links
- [IDP-22 spec](../../specs/IDP-22/spec.md) (decision D3), [IDP-28 spec](../../specs/IDP-28/spec.md)
- [Service contract: How `idp validate` checks it](../platform/service-contract.md#how-idp-validate-checks-it)
- [Onboarding: Reference example](../platform/onboarding.md#reference-example)
- [`platform-ci.yml`](../../.github/workflows/platform-ci.yml)
- [ADR-0010](0010-service-contract.md), [ADR-0012](0012-build-profiles.md)
- IDP-23: idp conformance: minimal environment and guaranteed process cleanup for example runs
- IDP-29: idp validate/conformance: fail closed on archive-syntax includes and top-level tab define; strip pin spelling
  like make
- IDP-30: idp conformance: bound make output and fail examples whose includes make would look up outside the service
  directory
