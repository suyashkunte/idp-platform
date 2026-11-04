---
key: IDP-26
type: Story
status: To Do
summary: "CI and make setup: fail on a stale uv.lock instead of silently re-locking"
parent: IDP-16
labels: [component:pipeline, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-10T10:40:26.612+0530
updated: 2026-10-10T10:40:40.911+0530
resolved:
links:
  - {type: "relates to", key: IDP-25}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-26
---

# IDP-26: CI and make setup: fail on a stale uv.lock instead of silently re-locking

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-25](IDP-25.md)

## Description

## Context / why

Follow-up from the IDP-25 security review (finding m1, spec Q5; PR #10).

* CI syncs with `uv sync --all-packages --frozen` (`.github/workflows/platform-ci.yml:32`). `--frozen` does not check that `uv.lock` is up to date.
* After that, `make verify` calls plain `$(UV) run ...` (`Makefile:18-47`). Plain `uv run` re-locks silently when `uv.lock` is stale, so CI tests a lock file that nobody committed.
* `make setup` (`Makefile:14`) runs `uv sync --all-packages` with no `--locked`.
* IDP-25 example: a human edits the root `build-constraint-dependencies` but forgets `uv lock`. `uv run` then rewrites the `[manifest] build-constraints` record before pytest reads it, so the lock-record drift check passes on a file that was never committed.

## Acceptance criteria

* **AC-1** Given `platform-ci.yml`, when the `verify` job runs, then every uv command in the job runs in locked mode (job-level `env: UV_LOCKED: "1"`, or `--locked` on the sync step), so a stale `uv.lock` fails the job.
* **AC-2** Given the root `Makefile`, when `make setup` runs, then it syncs with `uv sync --all-packages --locked`.
* **AC-3** (edge) Given a branch where the root `pyproject.toml` changed but `uv.lock` was not regenerated, when CI runs, then the job fails with uv's message that the lockfile needs to be updated, and `uv.lock` is not rewritten.
* **AC-4** Given ADR-0012 "Known gaps" and the IDP-25 PR finding, when this merges, then the silent re-lock gap is recorded as closed.

## Non-functional criteria

No network at test time. No new dependencies. CI time unchanged (±10 s).

## Out of scope

* Hash checking for `uv sync` builds (not supported by uv).
* Changing the local `make test`/`make verify` behaviour other than `make setup`. Decide in the spec whether local `uv run` should also be locked.
* Markers in `build-constraints.txt` (a separate ticket).

## Interfaces / dependencies

* Depends on IDP-25 (Done).
* `.github/workflows/platform-ci.yml` and the root `Makefile` are protected paths, so **the human makes both edits**, right after spec approval.

## Test approach

* Static test: parse `platform-ci.yml` (job env or sync-step args) and the `Makefile` `setup` recipe, and assert locked mode (AC-1, AC-2).
* Negative check for AC-3: on a throwaway branch, edit the root `pyproject.toml` without `uv lock` and record the failing CI run on the ticket. This is manual evidence, because it needs CI.

## Definition of Done

ACs traced; `make verify` green locally and in CI; AC-3 evidence linked on the ticket; ADR-0012 and CHANGELOG updated.

## Comments (0)
