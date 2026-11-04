---
key: IDP-33
type: Story
status: To Do
summary: "templates/python-fastapi: copier template for a new tenant repo, checked by platform CI"
parent: IDP-16
labels: [component:pipeline, layer:app, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T13:00:46.905+0530
updated: 2026-10-20T13:01:53.728+0530
resolved:
links:
  - {type: "blocks", key: IDP-36}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-33
---

# IDP-33: templates/python-fastapi: copier template for a new tenant repo, checked by platform CI

Epic/parent: [IDP-16](IDP-16.md)

Links: blocks [IDP-36](IDP-36.md)

## Description

## Context / why

Iteration 2 must produce StudyTimer from a template (PROJECT_PLAN §4.2, §9). Tenants create a repo with `copier copy gh:suyashkunte/idp-platform --vcs-ref <tag>` (onboarding.md). The template has to produce a repo that passes `idp validate` and `make verify` straight away, and is ready for the pipeline and the agent.

## Acceptance criteria

* **AC-1** Given `copier copy templates/python-fastapi <dir>` with the default answers plus a service name, when I run `idp validate` and `make verify` in the generated directory, then both exit 0.
* **AC-2** Given the generated repo, then:

    * `idp.yaml` `metadata.name`, `owner`, `tier` and `tracker` (site, project, labels) come from the answers;
    * the Python package name is derived from the service name;
    * `.github/workflows/idp.yml` calls `suyashkunte/idp-platform/.github/workflows/service-pipeline.yml@v0`;
    * `.claude/settings.json` enables `idp-agentic@idp-platform`;
    * `CLAUDE.md` names the service and points to the plugin conventions;
    * `specs/` exists.

* **AC-3** (edge) Given a service name that is not a valid DNS label (uppercase, spaces, a leading digit, or more than 63 characters), when I run copier, then it rejects the answer with a validation message and writes no files.
* **AC-4** Given platform `make verify`, then a template check renders the template into a temporary directory with the default answers and runs `idp validate` and `make verify` there. It fails the build if either fails, and finishes within 120 s.

## Non-functional criteria

* Python 3.12. FastAPI and test dependencies are pinned in the generated `pyproject.toml`. The generated `uv.lock` comes from copier's post-generation task (`uv lock`) or is committed in the template; decide in the spec.
* No secrets or tokens in the template.
* Generating needs no network access except `uv`.

## Out of scope

* Dockerfile and image build (G0, iteration 3).
* Migrations and database.
* Chart values.
* Renovate config.
* The `dockerfile-generic` template (iteration 11).

## Interfaces / dependencies

* Depends on IDP-18 (python-uv profile).
* `copier` becomes a dev dependency in the root `pyproject.toml`, which is protected, so a human makes that edit.
* The generated `idp.yml` references the reusable workflows from the "reusable workflows" story. The file can be written now, but runs only once those workflows exist.
* Open question for the spec: does the agent protected-path glob `.github/**` also block writes to `templates/python-fastapi/.github/**`? If it does, those template files are human tasks.

## Test approach

* A unit test renders the template with `copier`'s Python API into `tmp_path` (valid answers and each invalid name) and asserts the files and `idp.yaml` values.
* A conformance-style test runs `idp validate` and `make verify` on the rendered repo, with the same real-make conventions as `tests/conformance`.

## Definition of Done

* ACs traced; `make verify` green.
* `docs/platform/onboarding.md` updated with the exact copier command and the answers.
* CHANGELOG entry.

## Comments (0)
