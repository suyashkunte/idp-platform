---
key: IDP-31
type: Story
status: Done
summary: "ADR-0013: conformance trust model (the Makefile scanner is a correctness check, not a security boundary)"
parent: IDP-16
labels: [component:pipeline, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T13:00:26.055+0530
updated: 2026-10-20T14:06:39.828+0530
resolved: 2026-10-20T14:06:34.904+0530
links:
  - {type: "relates to", key: IDP-23}
  - {type: "relates to", key: IDP-29}
  - {type: "relates to", key: IDP-30}
  - {type: "relates to", key: IDP-38}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-31
---

# IDP-31: ADR-0013: conformance trust model (the Makefile scanner is a correctness check, not a security boundary)

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-23](IDP-23.md); relates to [IDP-29](IDP-29.md); relates to [IDP-30](IDP-30.md); relates to [IDP-38](IDP-38.md)

## Description

## Context / why

IDP-22 and IDP-28 hardened the static Makefile scanner over four review rounds, and each round found another place where it disagrees with GNU make. IDP-29 and IDP-30 would continue that. IDP-22 decision D3 already concluded that `idp validate` "is not a security boundary for tenant content":

* In `platform-ci.yml`, a PR's own root `Makefile` and its own copy of the scanner run in the same job, so a malicious PR would change them rather than get past them.
* `examples/` is written by the platform team (IDP-23).
* The validated `verify` recipe is arbitrary shell anyway.

The real protections are the conformance sandbox (IDP-23: minimal environment, process cleanup, no stored credentials) and per-tenant, least-privilege AWS roles (iteration 3). This decision was agreed with the human on 2026-10-20 and needs to be recorded, so that future reviews and tickets weigh scanner findings correctly.

## Acceptance criteria

* **AC-1** Given `docs/adr/0013-conformance-trust-model.md`, then it uses the headings of `docs/adr/0000-template.md`, has status Accepted, and records:

    * the decision: `idp validate` and the conformance scan are a fail-closed, best-effort correctness check, and the security boundary is IDP-23 plus least-privilege roles;
    * the rule that new scanner-hardening work is only taken on for a regression, or for a bypass in a job that holds credentials or runs code it didn't write;
    * that IDP-29 and IDP-30 are parked;
    * that using make's own database (`make -pn` in a sandbox) is reconsidered after IDP-23.

* **AC-2** Given the residual-risk text in `docs/platform/service-contract.md` and `docs/platform/onboarding.md`, then each links ADR-0013 and says in one sentence that validation and conformance are not a security boundary.
* **AC-3** (edge) Given the existing ADRs 0001–0012, then none changes except for added "Related" links, and 0013 is the next free number (no clash).

## Non-functional criteria

None (documentation only). `make verify` stays green.

## Out of scope

* Changing scanner behaviour.
* Implementing IDP-23.
* The iteration-3 threat model (`docs/architecture/threat-model.md`), which will build on this ADR.

## Interfaces / dependencies

* Relates to IDP-22 (decision D3), IDP-28, IDP-29, IDP-30 and IDP-23.
* After merge, a human adds a "parked per ADR-0013" comment on IDP-29 and IDP-30 (already done when this ticket was created).

## Test approach

* `make verify`.
* Check by hand that the links resolve and the headings match the template.

## Definition of Done

* ACs traced (the docs are the evidence; a doc-structure test is optional).
* `make verify` green.
* CHANGELOG entry.

## Comments (3)

### Suyash Kunte, 2026-10-20T13:13:22.549+0530

Spec committed on `feature/IDP-31-conformance-trust-adr` (e044ac4): `specs/IDP-31/spec.md`, `plan.md`, `tasks.md`. This ticket runs in auto mode (spec:auto + risk:low), so the spec is approved at PR review.

**Plan:**

* **T1:** add doc-structure tests in `tests/docs/test_adr_0013.py`, tagged IDP-31:AC-1..3. spec-trace needs one test per AC.
* **T2:** write ADR-0013 with the template headings and status Accepted.
* **T3:** add one sentence and a link to ADR-0013 in both residual-risk texts.
* **T4:** CHANGELOG entry, `git diff --stat` of `docs/adr/`, then `make verify`.

No protected paths and no human tasks.

**Open questions (proposed answer in brackets):**

* **Q1:** Should "ADRs 0001–0012 unchanged" be a permanent test? \[No. It is shown by the PR diff, and a test would block later implementation notes in ADRs.\]
* **Q2:** Should any existing ADR get a "Related" link? \[None. An optional one-liner in ADR-0010 is possible.\]
* **Q3:** Should the service-contract text "`make -pn` … is an ADR candidate after IDP-23" become "is reconsidered after IDP-23 (ADR-0013)"? \[Yes\]
* **Q4:** Should IDP-29 and IDP-30 be cited by key only, or with one-line titles? \[Key plus title\]
* **Q5:** Should reviewer agent prompts be updated to apply ADR-0013? \[Not here; that belongs to IDP-32.\]
* **Q6:** Does "a job that runs code it didn't write" mean a job whose Makefile or scanner does not come from the change being checked? Today's `platform-ci.yml` job (contents: read, no credentials, the PR's own scanner) is then outside the rule. \[Confirm\]

### Suyash Kunte, 2026-10-20T13:34:16.615+0530

Draft PR: https://github.com/suyashkunte/idp-platform/pull/13

* **Checks:** `make verify` is green (580 tests, coverage 98.23%) and spec-trace reports AC-1..3 OK.
* **Review:** the code and security reviewers found no blockers, and their MAJORs were fixed.
* **Spec:** this ticket ran in auto mode, so approve the spec, including Decisions Q1–Q6, when you review the PR.

**Open for the human:**

1. Should job separation for credentialed jobs be a binding requirement, or input for the iteration-3 threat model? The ADR currently records it as input.
2. Should there be a follow-up ticket (human-owned, because it touches `.github`) to test that `platform-ci.yml` stays `pull_request` + `contents: read` + no secrets, and to consider `persist-credentials: false`?

### Suyash Kunte, 2026-10-20T14:06:26.455+0530

Merged in b4db326 (PR #13); the spec approval is committed.

How the open review items were resolved (the human delegated these decisions on 2026-10-20):

1. **Job separation for credentialed jobs:** stays as input for the iteration-3 threat model, as ADR-0013 is written. It is not a binding requirement now.
2. **Enforcing that platform-ci holds no credentials:** follow-up **IDP-38**, a test-only guard in `tests/ci/`. `persist-credentials: false` is already covered by IDP-23 AC-4.
3. **ADR-0013 link in** `docs/architecture/overview.md`: deferred to the iteration-3 threat-model work. That work builds on ADR-0013 and will update the trust-boundaries section anyway.
