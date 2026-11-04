---
key: IDP-16
type: Epic
status: To Do
summary: "Iteration 2: Contract, template & PR pipeline → StudyTimer born"
parent:
labels: [component:pipeline, repo:idp-platform]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T09:32:23.108+0530
updated: 2026-10-07T15:23:42.558+0530
resolved:
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-16
---

# IDP-16: Iteration 2: Contract, template & PR pipeline → StudyTimer born

## Description

## Context / why

Iteration 2 of docs/plan/PROJECT_PLAN.md §9. Turns the platform skeleton into something a tenant can consume: contract tooling, a build profile, a conformance fixture, a service template, reusable PR workflows, a first platform release, and the StudyTimer repo generated from the template.

## Exit criteria

* StudyTimer PR checks run entirely from `@v0` reusable workflows.
* The first `/implement-ticket` in StudyTimer reaches a draft PR.

## Plan

* Phase A (now): IDP-12 (runner pin), S1 `idp validate` semantic checks, S2 `python-uv` build profile, S3 `examples/minimal-service` conformance.
* Phase B (written after Phase A learnings): S4 template, S5 reusable workflows, S6 release-please v0.1.0, S7 StudyTimer repo, S8 first StudyTimer ticket.

Labels: repo:idp-platform

## Comments (1)

### Suyash Kunte, 2026-10-07T15:23:42.558+0530

**For S5, from the IDP-18 review (PR #6, findings #6 and #10):** after `make sbom` / `make sca`, the pipeline must check that `reports/sbom.cdx.json` and `reports/sca.json` exist and parse, and must not trust make's exit code alone. Two cases make the exit code unreliable:

* Environment overrides (`IDP_SBOM_CMD` / `IDP_SCA_CMD`) can replace the commands.
* A tenant listing `sbom` / `sca` in `.PHONY` without defining them gets a silent no-op.

Also from IDP-18: revisit Q2, how tenants locate `defaults.mk` (`IDP_PROFILE_DIR`), when designing the S5 setup action.
