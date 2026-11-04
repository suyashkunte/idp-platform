---
key: IDP-24
type: Story
status: Done
summary: "idp-gate build hardening follow-ups: locked build backend, clean uv build env, symlinked-dir test"
parent: IDP-16
labels: [component:pipeline, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T23:09:54.863+0530
updated: 2026-10-08T17:31:34.247+0530
resolved: 2026-10-08T17:31:34.224+0530
links: []
jira_url: https://suyashkunte.atlassian.net/browse/IDP-24
---

# IDP-24: idp-gate build hardening follow-ups: locked build backend, clean uv build env, symlinked-dir test

Epic/parent: [IDP-16](IDP-16.md)

## Description

## Context / why

These are review findings from IDP-21 (PR #8, merged as e7990ca) that the reviewer deferred:

* **sec MINOR-3** (existed before IDP-21): `uv build` resolves the hatchling that runs the repo's build hook fresh from `build-system.requires = ["hatchling>=1.25"]`. It is not taken from `uv.lock`, it has no hashes, and it has no date cutoff.
* **sec MINOR-4**: the `_uv_build` test helper in `packages/idp-gate/tests/test_profiles.py` passes the full environment (`UV_*` and `PIP_*` variables, e.g. `UV_INDEX_URL` or `UV_NO_BUILD_ISOLATION`) to `uv build`, so results can differ from machine to machine.
* **code MINOR-6**: no test pins down that a symlinked _directory_ under `build-profiles/` is not followed. It holds today only because `Path.rglob` does not descend into directory symlinks on Python 3.12 and later.
* Nits: the allow-list matches by suffix, not by name, so a future `build-profiles/x/secrets.yaml` would ship. A `build-profiles` directory that is itself a symlink is followed.

## Acceptance criteria

* **AC-1** Given the idp-gate package, when it is built in CI or by the test fixtures, then the build backend version is constrained reproducibly: either `uv build --build-constraint` with a hashed constraints file, or `--exclude-newer`.
* **AC-2** Given `UV_INDEX_URL`, `UV_NO_BUILD_ISOLATION` or `PIP_INDEX_URL` is set in the environment, when the test session runs `uv build`, then those variables are not passed through, and the build result is the same as with a clean environment.
* **AC-3** (edge) Given `build-profiles/python-uv/linked` is a symlink to a directory outside the profiles tree that contains `x.md`, when the profile files are selected, then `x.md` is not selected.
* **AC-4** (edge) Given the `build-profiles` source directory is itself a symlink, when the idp-gate wheel or sdist is built, then the build fails closed with a clear message.

## Non-functional criteria

Tests still run `uv build` at most twice per session. No network at test time beyond what IDP-21 needs. No secrets.

## Out of scope

Name-based secret detection in profiles (gitleaks already covers this). Changes to tool pins.

## Interfaces / dependencies

IDP-21 (Done). ADR-0012. AC-1 may need a `.github/workflows` edit, which is a protected path, so the human places that change.

## Test approach

Unit tests on `select_profile_files` and `profiles_source` using `tmp_path` symlink trees. A session-fixture environment check (assert the stripped variables are absent from the environment passed to `uv build`). A config or dry-run assertion for the build constraint.

## Definition of Done

ACs traced; `make verify` green; ADR-0012 updated; CHANGELOG entry.

## Comments (3)

### Suyash Kunte, 2026-10-07T23:23:03.835+0530

**Spec drafted** on branch `feature/IDP-24-build-hardening` (commit fd76c3e): `specs/IDP-24/spec.md`, `plan.md`, `tasks.md`. Mode: **guided**, so it is waiting for human spec approval.

**Approach**

* **AC-1:** a committed hashed constraints file, `packages/idp-gate/build-constraints.txt`. It is generated from `uv.lock` (hatchling 1.32.4 and its dependencies, with sha256 hashes). The test builds use `uv build --build-constraint <file> --require-hashes --no-config --offline`. CI never calls `uv build` directly (it only runs make verify / pytest), so **no** `.github` or root Makefile edit is needed.
* **AC-2:** strip all `UV_*` and `PIP_*` variables except `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` before `uv build`. The two real session builds run with the three named variables deliberately polluted, so the existing content tests prove "same result as clean". This adds no extra builds (still 2 per session).
* **AC-3:** `select_profile_files` uses `os.walk(followlinks=False)` instead of `rglob`, and gets a unit test with a symlink tree.
* **AC-4:** `profiles_source` fails closed if `build-profiles` is a symlink, with the error `refusing to follow it`. It is tested through the real hook for both wheel and sdist.

**Open questions (spec.md Q1–Q8):**

* Q1: hashed constraints vs `--exclude-newer`
* Q2: the env keep-list
* Q3: strip by prefix vs only the three named variables
* Q4: `--no-config`
* Q5: polluted-env session builds
* Q6: fail vs fall back for a symlinked source
* Q7: commit the constraints file vs generate it at test time
* Q8: ADR-0012 status stays Proposed

Checked locally: uv 0.12.23 accepts `--build-constraint`, `--require-hashes`, `--no-config` and `--offline` on `uv build`. Task T1 still confirms offline hash checking before any code changes.

### Suyash Kunte, 2026-10-07T23:41:40.172+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/9

* **Checks:** `make verify` passed locally: 283 tests, 100% diff coverage, spec-trace OK for AC-1..4. CI is pending.
* **Review:** code and security review ran in 2 loops; there are no blockers, and the loop-1 fixes are in.
* **Decision needed: MAJOR finding.** CI's `uv sync` (and `make setup`) still builds the editable idp-gate with an unconstrained hatchling. The proposed fix is `[tool.uv] build-constraint-dependencies` in the root `pyproject.toml`, which is protected and needs a human edit. Decide whether it goes in this PR or a follow-up ticket.
* **Still to do by the human:**

    * commit the spec approval marker;
    * run the negative hash check (command in the PR body);
    * mark the PR ready and merge.

### Suyash Kunte, 2026-10-08T17:31:32.136+0530

Merged as d5c0b85 (PR #9). The `platform-ci` run on main passed (run 37773732961). The spec approval is committed.

Still open: the CI `uv sync` editable build of idp-gate is not covered by the build constraints. The proposed fix is `[tool.uv] build-constraint-dependencies` in the root pyproject.toml. It will be handled in a follow-up ticket; see "Known gaps" in ADR-0012.
