---
key: IDP-9
type: Story
status: Done
summary: "Service contract schema idp-service.v1 (draft)"
parent: IDP-6
labels: [component:pipeline, iteration:1, repo:idp-platform, risk:low]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T00:42:16.426+0530
updated: 2026-10-07T02:00:50.359+0530
resolved: 2026-10-07T02:00:50.340+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-9
---

# IDP-9: Service contract schema idp-service.v1 (draft)

Epic/parent: [IDP-6](IDP-6.md)

## Description

## Context / why

`idp.yaml` is the platform's main public interface (I1, ADR-0010). Its schema has to exist before any tenant or template.

## Acceptance criteria

* AC-1 Given `docs/platform/service-contract.md`'s StudyTimer example, when it is validated, then it passes.
* AC-2 Given an unknown top-level or `spec` field (other than `x-*`), when it is validated, then it fails, naming the field.
* AC-3 Given `metadata.name` that is not DNS-safe, or `tier` outside 1–3, when it is validated, then it fails.
* AC-4 Given `spec.build.profile` other than `python-uv` or `dockerfile`, when it is validated, then it fails, listing the allowed values.

## Out of scope

Catalog consistency checks; policy override "tighten-only" checks (iteration 3).

## Comments (0)
