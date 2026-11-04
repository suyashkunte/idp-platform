---
key: IDP-18
type: Story
status: Done
summary: "python-uv build profile with default make targets and agent notes"
parent: IDP-16
labels: [component:pipeline, layer:app, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T09:32:47.192+0530
updated: 2026-10-07T15:30:06.146+0530
resolved: 2026-10-07T15:30:06.135+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-18
---

# IDP-18: python-uv build profile with default make targets and agent notes

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

ADR-0012: language toolchains are build profiles so the pipeline and agents stay stack-agnostic. `python-uv` is the first profile; StudyTimer and the template (S4) use it. A tenant should get sensible defaults for targets it does not define, and the plugin's test generators need stack idioms from the profile.

## Acceptance criteria

* **AC-1** Given `build-profiles/python-uv/profile.yaml`, then it validates against a new schema `build-profile.v1` (fields: name, description, setup steps, default targets, coverage format, sbom/sca tools) shipped inside `idp-gate`.
* **AC-2** Given a tenant Makefile that includes the profile's `defaults.mk` and does not define `sbom` or `sca`, when I run `make sbom` / `make sca`, then the profile defaults run.
* **AC-3** Given a tenant Makefile that defines a target the profile also defaults (e.g. `sca`), then the tenant's recipe runs and make prints no override warnings.
* **AC-4** Given `idp profile show python-uv`, then it prints the resolved profile (YAML, or JSON with `--json`) and exits 0.
* **AC-5 (edge)** Given `idp profile show nope` or a profile.yaml that violates the schema, then it exits 2 with the profile name and the reason.
* **AC-6** Given `build-profiles/python-uv/agent-notes.md`, then it documents pytest idioms, AC tagging (`ac:<KEY>:AC-n`), and fixture conventions, and the unit-test-generator agent definition references it.

## Non-functional criteria

Defaults must not require network at `make` parse time. No secrets. Profiles are discoverable from the installed `idp` package (not only from the repo checkout) so tenants can resolve them in CI.

## Out of scope

`dockerfile` profile (later); CI setup action (`actions/setup-profile`, S5).

## Interfaces / dependencies

ADR-0012; `idp_gate.schemas`; IDP-? S1 for Make target parsing (reuse if merged first).

## Test approach

Schema unit tests (valid/invalid profile docs); CLI tests for `profile show`; a make-level test running a temp tenant Makefile that includes `defaults.mk` with and without overrides (skips if make is absent).

## Definition of Done

ACs traced; `make verify` green; ADR-0012 / service-contract.md updated; CHANGELOG entry.

Labels: repo:idp-platform, component:pipeline, layer:app, risk:low, spec:auto

## Comments (2)

### Suyash Kunte, 2026-10-07T12:16:20.618+0530

**Spec drafted** (branch `feature/IDP-18-python-uv-profile`, commit 42b3f8e, `specs/IDP-18/`). Auto mode (spec:auto + risk:low): the spec is approved at PR review.

**Design**

* Schema `build-profile.v1` ships in `idp_gate/schemas`. New `idp_gate/profiles.py` looks for profiles in the installed package first (hatch `force-include` of `build-profiles/` into the wheel) and falls back to the repo checkout under the editable workspace install.
* `defaults.mk` never defines `sbom`/`sca` directly. It defines `idp-default-sbom`/`idp-default-sca` plus a `%: idp-default-%` fallback, so a tenant's own rule wins with no "overriding recipe" warning. Tool commands are `?=` variables, and nothing runs at parse time.
* `idp profile show NAME [--json]` prints YAML or JSON and exits 0. Unknown, invalid or path-like names exit 2 with the name and the reason on stderr.
* `agent-notes.md` is referenced from the unit-test-generator agent.
* No protected paths change, so no human Makefile edit is needed.

**Open questions (proposed defaults in spec.md)**

* Q1: "resolved profile" = document + absolute `dir`.
* Q2: tenants use `include $(IDP_PROFILE_DIR)/defaults.mk`.
* Q3: no JSON error object on exit 2.
* Q4: exact `cyclonedx-py`/`pip-audit` flags and output paths.
* Q5: keep ADR-0012 Proposed and add implementation notes.
* Q6: wheel-build test in `make verify`, skipped without `uv`.

Note: the ticket writes `**AC-5 (edge)**`, which spec-trace's regex does not parse. The spec writes it as `**AC-5** (edge)`; the text and ID are unchanged.

### Suyash Kunte, 2026-10-07T13:41:25.435+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/6

* `make verify` is green: 213 tests, 97.65% coverage, 100% diff coverage, and spec-trace covers all 6 ACs.
* Real `make sbom`/`make sca` runs against the repo passed with the pinned tools (`uv export --locked`).
* Two rounds of code and security review. Fixed 1 BLOCKER (import-time IndexError in shallow installs) and 6 MAJORs; 11 MINOR or decision items are left for the reviewer in the PR body.
* Auto mode: approving the PR approves the spec.
* First full make 4.x run will be in CI.
