---
key: IDP-25
type: Story
status: Done
summary: "idp-gate: constrain the build backend for editable uv sync builds (CI and make setup)"
parent: IDP-16
labels: [component:pipeline, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-08T17:33:57.666+0530
updated: 2026-10-10T10:40:42.261+0530
resolved: 2026-10-10T10:38:19.261+0530
links:
  - {type: "relates to", key: IDP-26}
  - {type: "relates to", key: IDP-27}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-25
---

# IDP-25: idp-gate: constrain the build backend for editable uv sync builds (CI and make setup)

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-26](IDP-26.md); relates to [IDP-27](IDP-27.md)

## Description

## Context / why

IDP-24 (PR #9, d5c0b85) pinned hatchling with hashes, but only for the two `uv build` runs inside the tests. Both reviewers found the same remaining gap (MAJOR, recorded under "Known gaps" in ADR-0012):

* idp-gate is an editable workspace member (`uv.lock`: `source = { editable = "packages/idp-gate" }`).
* So every `uv sync --all-packages` builds it with hatchling and runs `hatch_build.py`. That happens in CI (`.github/workflows/platform-ci.yml:32`) and in `make setup`.
* That build gets `hatchling>=1.25` fresh from the index: not from `uv.lock`, with no hashes.
* `uv sync` has no `--build-constraint` flag. The supported way is `[tool.uv] build-constraint-dependencies` in the root workspace `pyproject.toml`.

## Acceptance criteria

* **AC-1** Given the root `pyproject.toml`, when the workspace is synced, then `[tool.uv] build-constraint-dependencies` pins exactly the same packages and versions as `packages/idp-gate/build-constraints.txt` (hatchling and its dependencies, all `==`).
* **AC-2** Given CI has run `uv sync --all-packages --frozen`, when the tests read the installed idp-gate's `dist-info/WHEEL`, then `Generator` names the hatchling version locked in `uv.lock`.
* **AC-3** (edge) Given `uv.lock`, `build-constraints.txt` and the root `build-constraint-dependencies` list disagree, when the test session runs, then a drift test fails and says which source is out of date and how to regenerate it. Examples of disagreeing: only one of them was bumped, a package is missing or extra, or an entry is a range such as `hatchling>=1.25` instead of `==`.
* **AC-4** Given ADR-0012, when this change merges, then its "Known gaps" no longer lists the `uv sync` gap. Instead it states the remaining limit: sync builds pin versions but not hashes.

## Non-functional criteria

No network at test time. No new dependencies. `uv build` still runs at most twice per test session. CI `--frozen` sync still passes.

## Out of scope

* Hash checking for `uv sync` builds (not supported by uv).
* Removing `PYTHONPATH`/`HATCH_BUILD_*` from the build environment (IDP-24 sec-1).
* Trust in the local uv cache (IDP-24 sec-2).
* Windows junctions and hardlinks.

## Interfaces / dependencies

* Depends on IDP-24 (Done) and ADR-0012.
* The root `pyproject.toml` is a protected path, so **the human makes that edit**. Best done right after spec approval.
* `uv.lock` will probably change too, because uv records build constraints in the lock file.

## Test approach

* Unit drift test comparing `uv.lock`, `build-constraints.txt` and the root `pyproject.toml` list.
* A test that reads the installed idp-gate's `WHEEL` `Generator` line. It needs no extra build, because the editable install already exists in `.venv`.

## Definition of Done

ACs traced; `make verify` green locally and in CI; ADR-0012 and CHANGELOG updated.

## Comments (3)

### Suyash Kunte, 2026-10-08T18:46:44.900+0530

**Spec drafted** on branch `feature/IDP-25-sync-build-constraints` (commit b8c5ad6): `specs/IDP-25/spec.md`, `plan.md`, `tasks.md`. Mode: guided, so this waits for spec approval.

**Approach:** Only test code, ADR-0012 and the CHANGELOG change, plus one human edit (H1) to the root `pyproject.toml`, which is a protected path. That edit adds `[tool.uv] build-constraint-dependencies` with the 6 pins from `build-constraints.txt` (hatchling 1.32.4 + packaging, pathspec, pluggy, tomlkit, trove-classifiers), then runs `uv lock`. A stdlib-only drift test treats `uv.lock` as the reference and compares the three sources. A failure message names the stale source and the exact command to fix it. The AC-2 test reads `WHEEL` `Generator` from the editable install in `.venv`. No network, no new `uv build`, no new dependencies.

**Facts found:** hatchling 1.32.4 is in `uv.lock` (as idp-gate's dev dependency); `[manifest]` holds only `members`; root `[tool.uv]` holds only `package = false`; the local `.venv` WHEEL already says `hatchling 1.32.4`, so the AC-2 test starts green locally.

**Open questions (details in spec.md):**

* Q1 Is a static config check enough for AC-1, with proof that sync actually uses it resting on AC-2 and the H1 run?
* Q2 For AC-2, compare against the `uv.lock` hatchling entry (proposed) or against the `build-constraints.txt` pin?
* Q3 Does `uv lock` record the build constraints in `uv.lock`, and does `uv sync --frozen` read them from `pyproject.toml` or from the lock? H1 answers this.
* Q4 Trace AC-4 with a text test on the ADR (proposed) or leave it to reviewers?
* Q5 Should `uv run --frozen`/`--locked` in the protected Makefile be a separate follow-up (proposed)?
* Q6 In H1, try `uv lock --offline` first and fall back to the network?
* Q7 Add a one-line comment above the new TOML key (proposed yes)?

### Suyash Kunte, 2026-10-10T10:14:01.894+0530

**Progress and spec amendment (needs re-approval)**

* T1–T4 are done; `make verify` is green and AC-1..AC-4 are all traced. Review loop 1 fixes are committed (f206b02). The drift test now names only the stale source, reports a missing uv.lock record, and rejects non-exact pins in every source.
* The security review found a MAJOR, which I confirmed in hatchling's source. For an editable build, `get_requires_for_build_editable` always adds `editables~=0.3`, so every `uv sync` build still installed an unpinned `editables`.
* Decision: fix it in this PR (Q8). The spec is amended in 5562174; the AC text is unchanged.
* Next steps: the human re-approves the spec, then T5 (the agent adds `editables` to idp-gate's dev group, re-locks, regenerates `build-constraints.txt` and extends the drift test), then H2 (the human adds `editables==<locked>` to the root list and runs `uv lock`).

### Suyash Kunte, 2026-10-10T10:29:42.364+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/10

* `make verify` passes: 322 tests, 97.85% coverage, conformance passes. spec-trace shows AC-1..AC-4 covered.
* The root `build-constraint-dependencies` now pins hatchling 1.32.4 and its dependencies plus `editables==0.6` (H1 and H2). A drift test keeps the root list, `build-constraints.txt` and the `uv.lock` record in line, and a guard test fails if idp-gate's build config ever declares extra build dependencies.
* Review findings left for the human are listed in the PR: `UV_LOCKED`/`--locked` for CI and `make setup` (needs a follow-up ticket, protected paths), markers still stripped from `build-constraints.txt`, and AC-2 being only a smoke check.
