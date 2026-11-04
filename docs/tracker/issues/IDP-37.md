---
key: IDP-37
type: Story
status: To Do
summary: "StudyTimer dry run: GET /version via /implement-ticket (iteration 2 exit criterion)"
parent: IDP-16
labels: [component:app, layer:app, repo:studytimer, risk:low, spec:auto]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T13:01:37.654+0530
updated: 2026-10-20T13:01:57.732+0530
resolved:
links:
  - {type: "is blocked by", key: IDP-36}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-37
---

# IDP-37: StudyTimer dry run: GET /version via /implement-ticket (iteration 2 exit criterion)

Epic/parent: [IDP-16](IDP-16.md)

Links: is blocked by [IDP-36](IDP-36.md)

## Description

## Context / why

The iteration-2 exit criterion: "first `/implement-ticket` in StudyTimer reaches a draft PR". Like IDP-13 for the platform, this is a deliberately tiny ticket that proves the end-to-end agentic flow in a tenant repo before any MVP story (ST-1..ST-9). It covers the plugin loaded from the marketplace, intake from Jira, auto mode, the tests-first commit, the reviewers, and the draft PR with green `pr-checks / verify`.

## Acceptance criteria

* **AC-1** Given the running app, when a client sends `GET /version`, then it responds `200` with JSON `{"service": "studytimer", "version": "<version from pyproject.toml>"}`.
* **AC-2** (edge) Given the running app, when a client sends `POST /version`, then it responds `405`, and `GET /version/` (trailing slash) does not return a version.
* **AC-3** Given this ticket run through `/idp-agentic:implement-ticket` in the `studytimer` repo, then a draft PR exists with:

    * the failing-tests commit before the implementation commit;
    * `make spec-trace KEY=<this key>` all OK;
    * `pr-checks / verify` green;
    * the ticket moved to In Review.


## Non-functional criteria

* The version comes from package metadata at runtime and is not hard-coded.
* Response time is not measured (trivial endpoint).

## Out of scope

* Authentication.
* Build or commit SHA in the response.
* OpenAPI customisation beyond FastAPI's defaults.

## Interfaces / dependencies

* Blocked by the "Generate the studytimer repo" story.
* Runs in the `studytimer` repo, whose `idp.yaml` names Jira project IDP and label `repo:studytimer`.

## Test approach

* Unit tests with FastAPI's `TestClient`: the happy path, 405, and the trailing slash.
* The version is checked against `importlib.metadata`.

## Definition of Done

* ACs traced; `make verify` green in `studytimer`; draft PR open.
* Metrics recorded in the iteration-2 log (ticket-to-draft-PR time, rework loops, human interventions), as for IDP-13.

## Comments (0)
