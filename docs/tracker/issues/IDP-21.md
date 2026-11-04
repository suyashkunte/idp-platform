---
key: IDP-21
type: Story
status: Done
summary: "python-uv profile hardening: reproducible tool resolution and a clean wheel"
parent: IDP-16
labels: [component:pipeline, repo:idp-platform, risk:low, spec:auto]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T15:23:40.485+0530
updated: 2026-10-07T23:09:39.174+0530
resolved: 2026-10-07T23:09:39.152+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-21
---

# IDP-21: python-uv profile hardening: reproducible tool resolution and a clean wheel

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

These are review findings #2, #7 and #9 from IDP-18 (PR #6), deferred by the reviewer.

* The sbom/sca tools are pinned only at the top level, so their transitive dependencies resolve fresh on every run.
* The wheel's force-include copies the whole `build-profiles/` tree.
* A wheel built from the sdist has no profiles.
* Tests build the wheel twice.

All of this needs fixing before S5 consumes the idp-gate wheel.

## Acceptance criteria

* **AC-1** Given the python-uv defaults, when `make sbom` / `make sca` run, then each `uv tool run` passes `--exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER)` (a fixed date set with `?=`, overridable).
* **AC-2** Given a stray file such as `notes.txt` or `.env` in `build-profiles/python-uv/`, when the idp-gate wheel is built, then `idp_gate/build_profiles/` contains only `*.yaml`, `*.mk` and `*.md` files.
* **AC-3** Given the idp-gate sdist, when a wheel is built from it, then `idp profile show python-uv` works from that install.
* **AC-4** (edge) Given `IDP_TOOLS_EXCLUDE_NEWER` is empty, when `make sbom` / `make sca` run, then they fail closed with a clear message.

## Non-functional criteria

No network at make parse time. Tests build the wheel at most once per session. No secrets.

## Out of scope

Hashed constraints files for the tools; the gate engine, severity thresholds and waivers; the report-existence check (that belongs to S5).

## Interfaces / dependencies

IDP-18 (PR #6) must be merged first. ADR-0012.

## Test approach

Dry-run assertions on the default command lines; a wheel content allow-list check; an sdist → wheel → `profile show` check (skipped without uv); a session-scoped wheel fixture.

## Definition of Done

ACs traced; `make verify` green; ADR-0012 updated; CHANGELOG entry.

## Comments (1)

### Suyash Kunte, 2026-10-07T22:43:06.309+0530

Draft PR: https://github.com/suyashkunte/idp-platform/pull/8 (CI verify green). Auto mode: please approve specs/IDP-21/ as part of the PR review.

**Spec summary**

* AC-1: the python-uv defaults now pass `--exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER)` (default `2026-10-06T00:00:00Z`, `?=`, overridable) to both `uv tool run` calls.
* AC-4: an empty value makes `make sbom` / `make sca` fail at recipe time (exit 2, clear message). Make parse time stays command-free.
* AC-2/AC-3: the static wheel force-include is replaced by a hatch build hook (`packages/idp-gate/hatch_build.py`). It ships only regular, non-symlink `*.yaml`/`*.mk`/`*.md` profile files with no dot-prefixed path parts, into both the sdist and the wheel, so a wheel built from the sdist now has the profiles. Before, that build failed with "Forced include not found".
* hatchling was added as a dev-only dependency of idp-gate, so mypy strict checks the hook without `type: ignore`.

**Open questions** (the proposed defaults are implemented; accept or change them on the PR)

* Q1: Default date `2026-10-06T00:00:00Z`, written as a UTC timestamp. **Needs one networked run, which the agent was blocked from doing:** `make -f build-profiles/python-uv/defaults.mk REPORTS_DIR=/tmp/idp21 sbom sca`
* Q2: "Wheel built at most once per session" is read as once per kind of build: one direct wheel build plus one sdist→wheel build.
* Q3: Packaging uses a build hook rather than static config.
* Q4: The empty-value guard applies even when `IDP_*_CMD` is overridden.
* Q5: The allow-list also excludes dotfiles and symlinks.
* Q6: ADR-0012 stays Proposed, with implementation notes added.
* Q7: One bullet was added to agent-notes.md about session-scoped fixtures.

Five minor review findings are left for the human reviewer; the PR body lists them.
