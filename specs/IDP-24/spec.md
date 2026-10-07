---
ticket: IDP-24
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: guided
---

# IDP-24: idp-gate build hardening follow-ups: locked build backend, clean uv build env, symlinked-dir test

## Context
The IDP-21 review (PR #8, merged e7990ca) deferred four findings about how the `idp-gate` package is built. `uv build`
resolves the hatchling that runs the repository's build hook fresh from `build-system.requires = ["hatchling>=1.25"]`:
not from `uv.lock`, without hashes, without a date cutoff (sec MINOR-3). The `_uv_build` test helper in
`packages/idp-gate/tests/test_profiles.py` passes the full environment, including `UV_*`/`PIP_*` variables, to
`uv build` (sec MINOR-4). Nothing pins down that `select_profile_files` does not follow a symlinked directory; today
this holds only because of `Path.rglob` behaviour (code MINOR-6). A `build-profiles` source that is itself a symlink is
followed (nit). Parent epic IDP-16; depends on IDP-21 (Done) and ADR-0012.

Where `uv build` runs today: only in the two session fixtures `built_wheel` and `sdist_built_wheel` of
`packages/idp-gate/tests/test_profiles.py`. CI (`.github/workflows/platform-ci.yml`) runs `uv sync --all-packages
--frozen`, `make verify` and pre-commit; it never calls `uv build` directly, and neither does the root `Makefile`.
So "built in CI" means "built by the test fixtures during `make verify` in CI", and no protected path has to change.

## Requirements
- **AC-1** Given the idp-gate package, when it is built in CI or by the test fixtures, then the build backend version is constrained reproducibly: either `uv build --build-constraint` with a hashed constraints file, or `--exclude-newer`.
  - Chosen option (ASSUMPTION A1, see Q1): a hashed build-constraints file,
    `packages/idp-gate/build-constraints.txt`. It pins hatchling and its whole dependency closure (today: `hatchling`,
    `packaging`, `pathspec`, `pluggy`, `tomlkit`, `trove-classifiers`) with `==<version>` and every `--hash=sha256:...`
    that `uv.lock` records for that version (sdist and wheels). `uv.lock` stays the single source of truth: the file
    is generated from it (command in plan.md) and a test fails when the two drift apart.
  - Every `uv build` run by the test fixtures passes
    `--build-constraint <repo>/packages/idp-gate/build-constraints.txt --require-hashes` (in addition to the existing
    `--offline` and `--out-dir`). The argv is built in one helper, so both session builds use the same flags.
  - "Constrained reproducibly" is verified three ways: (a) config: the constraints file matches `uv.lock` exactly
    (names, versions, hash sets) for the hatchling closure; (b) argv: both session builds recorded the constraint
    flags; (c) result: the `*.dist-info/WHEEL` file of both session-built wheels says
    `Generator: hatchling <version locked in uv.lock>`.
  - `build-system.requires` in `packages/idp-gate/pyproject.toml` stays `["hatchling>=1.25"]`; the constraint narrows
    it to the locked version at build time. ASSUMPTION A2.
- **AC-2** Given `UV_INDEX_URL`, `UV_NO_BUILD_ISOLATION` or `PIP_INDEX_URL` is set in the environment, when the test session runs `uv build`, then those variables are not passed through, and the build result is the same as with a clean environment.
  - Rule (ASSUMPTION A3, see Q2/Q3): the environment passed to `uv build` is the current environment minus every
    variable whose name starts with `UV_` or `PIP_`, except a short keep-list of location-only variables that do not
    change what is resolved: `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR`. So `UV_INDEX_URL`, `UV_EXTRA_INDEX_URL`,
    `UV_INDEX`, `UV_NO_BUILD_ISOLATION`, `UV_EXCLUDE_NEWER`, `UV_CONSTRAINT`, `UV_BUILD_CONSTRAINT`, `UV_CONFIG_FILE`,
    `UV_OFFLINE`, `PIP_INDEX_URL`, `PIP_EXTRA_INDEX_URL`, `PIP_CONSTRAINT` and so on are all removed.
  - `uv build` also gets `--no-config`, so a user-level `uv.toml` (for example one that sets `index-url`) cannot change
    the build either. ASSUMPTION A4, see Q4.
  - "The build result is the same as with a clean environment": the two session builds run with a base environment
    that deliberately contains `UV_INDEX_URL=http://127.0.0.1:9/simple`, `UV_NO_BUILD_ISOLATION=1` and
    `PIP_INDEX_URL=http://127.0.0.1:9/simple` (ASSUMPTION A5, see Q5). The existing IDP-18/IDP-21 session tests then
    still pass unchanged: the wheels and the sdist contain exactly the three repository profile files with identical
    bytes, and `profile show python-uv` works from both wheels. A unit test also shows that the environment derived
    from a polluted base equals the one derived from the clean base.
  - Only variable names are recorded for assertions, never values, so a token in the environment cannot end up in
    test output.
- **AC-3** (edge) Given `build-profiles/python-uv/linked` is a symlink to a directory outside the profiles tree that contains `x.md`, when the profile files are selected, then `x.md` is not selected.
  - The ticket writes the edge marker after the bold id. It stays outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged (same for AC-4).
  - `select_profile_files` walks the tree with `os.walk(source, followlinks=False)` instead of `Path.rglob("*")`, so
    "do not descend into directory symlinks" is explicit and does not depend on the Python version. The existing file
    rule (regular, non-symlink, `.yaml`/`.mk`/`.md`, no dot-prefixed component) is unchanged.
  - Also covered by the same test: a directory symlink that points back inside the profiles tree
    (`python-uv/alias -> ../python-uv`) is not followed either, so no file is selected twice and there is no loop.
- **AC-4** (edge) Given the `build-profiles` source directory is itself a symlink, when the idp-gate wheel or sdist is built, then the build fails closed with a clear message.
  - `profiles_source` checks each candidate with `is_symlink()` before `is_dir()`. A candidate that is a symlink
    (to a directory, to a file, or dangling) raises `RuntimeError` with the message
    `idp-gate build: build profiles source is a symlink, refusing to follow it: <path>`. It does not fall back to the
    next candidate (fail closed). ASSUMPTION A6, see Q6.
  - Applies to both candidates: `<root>/build-profiles` (sdist copy) and `<root>/../../build-profiles` (checkout).
  - Only the last path component (`build-profiles` itself) is checked, not its ancestors, so a checkout under a
    symlinked path (for example macOS `/tmp -> /private/tmp`) still builds. ASSUMPTION A7.
  - "When the wheel or sdist is built" is verified through the real `ProfilesBuildHook.initialize` for both the
    `wheel` and the `sdist` target (the same entry point hatchling calls), not through extra `uv build` runs (NFR).

## Edge cases and assumptions
- A dangling `build-profiles` symlink: `is_dir()` is false, so without the new check the hook would report "not found";
  with it, the symlink message is shown (AC-4).
- A symlinked directory deeper in the tree (`python-uv/sub/linked`) is pruned the same way as `python-uv/linked`.
- A symlinked file named `profile.yaml` is still rejected by the existing file rule; if it is the only `profile.yaml`,
  the build fails closed with the IDP-21 "no */profile.yaml selected" error.
- The keep-listed `UV_CACHE_DIR` is needed because `uv build --offline` must find hatchling and its dependencies in
  the same cache that `uv sync` filled (in CI, `astral-sh/setup-uv` with `enable-cache: true` points uv at its own
  cache directory). ASSUMPTION A8.
- `uv sync --all-packages` (Makefile `setup`, CI) installs idp-gate's dev group, which holds `hatchling>=1.25` as
  locked, so every distribution in the constraints file is in the uv cache before the offline builds run.
- Bumping hatchling is a deliberate change: `uv lock --upgrade-package hatchling`, regenerate
  `build-constraints.txt` with the command in plan.md, commit both. The drift test fails if only one is changed.
- Building idp-gate from its sdist outside this repository (no constraints file there) is not constrained; the sdist
  `only-include` list is unchanged. The constraint applies to the builds this repository runs.
- ASSUMPTION A1: hashed build constraints (`--build-constraint` + `--require-hashes`) rather than `--exclude-newer`.
- ASSUMPTION A2: `build-system.requires` stays `hatchling>=1.25`.
- ASSUMPTION A3: strip by prefix (`UV_*`, `PIP_*`) with the keep-list `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`.
- ASSUMPTION A4: add `--no-config` to the fixture's `uv build`.
- ASSUMPTION A5: the session builds run with the three AC-2 variables deliberately set in their base environment.
- ASSUMPTION A6: a symlinked `build-profiles` candidate fails the build; it is never skipped in favour of the next one.
- ASSUMPTION A7: only the `build-profiles` component is checked for being a symlink, not its ancestors.
- ASSUMPTION A8: `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` only choose locations and do not change resolution.
- ASSUMPTION A9: the installed uv supports `uv build --build-constraint ... --require-hashes --no-config --offline`
  and verifies the hashes of build dependencies taken from the cache. Not verified in this session (no shell access);
  task T1 confirms it before anything else is changed.

## Non-functional requirements
- Tests still run `uv build` at most twice per session: `built_wheel` (one `uv build --wheel`) and `sdist_built_wheel`
  (one `uv build`), both session-scoped, as in IDP-21. All new AC-1/AC-2 assertions reuse those two builds; the AC-3
  and AC-4 tests are unit tests on `tmp_path` trees and run no build.
- No network at test time beyond what IDP-21 needs: both builds keep `--offline`; the constraints file only narrows
  what is taken from the cache. The deliberately set index URLs point at `127.0.0.1:9` and are stripped anyway.
- No secrets: the constraints file holds only package names, versions and public hashes. Tests record environment
  variable names, never values. gitleaks still applies.
- No protected path changes: root `Makefile`, root `pyproject.toml`, `.github/**`, `.pre-commit-config.yaml`,
  `infra/**`, plugin hooks and `.claude-plugin/**` stay unchanged. No human edit is needed after spec approval.
- No new runtime or dev dependencies; `uv.lock` unchanged; `packages/idp-gate/pyproject.toml` unchanged.
- Quality bars unchanged: mypy strict (also on `hatch_build.py`), ruff, bandit, coverage >= 85 %, diff-cover >= 80 %;
  `make verify` green; `idp spec-trace IDP-24` green.

## Out of scope
- Name-based secret detection in profiles (gitleaks already covers this). The suffix-based allow-list stays as is.
- Changes to tool pins (`IDP_CYCLONEDX_SPEC`, `IDP_PIP_AUDIT_SPEC`, `IDP_TOOLS_EXCLUDE_NEWER`) and to the hatchling
  version in `uv.lock`.
- Pinning the uv version itself.
- A release or publish workflow that builds idp-gate in CI (none exists; ADR-0012 records that one must reuse the
  same flags).
- Constraining builds of the idp-gate sdist by third parties.

## Open questions
- Q1: AC-1 mechanism. Proposed: hashed constraints file + `--require-hashes` (A1). Reasons: it takes exactly the
  hatchling closure that `uv.lock` already records, with hashes, so the build backend is both version-pinned and
  integrity-checked; `--exclude-newer` gives only a date cutoff (no integrity check, and the version still floats up to
  that date). Fallback if T1 shows that uv cannot verify hashes for cached build dependencies offline: keep the
  hashed file but drop `--require-hashes` (uv still verifies hashes that are present), and if that also fails, use
  `--exclude-newer` with a fixed UTC instant. Either fallback needs re-approval of this spec.
- Q2: Keep-list for `UV_*` variables. Proposed: `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` only (A3, A8). Should
  any other variable be kept (for example `UV_PYTHON_CACHE_DIR`), or should the keep-list be empty, accepting that
  offline builds fail when the cache is only reachable through `UV_CACHE_DIR`?
- Q3: Strip by prefix (`UV_*`, `PIP_*`) or only the three variables named in AC-2? Proposed: by prefix; the AC names
  examples, and the finding is about results that differ between machines.
- Q4: Add `--no-config` to the fixture's `uv build` (A4)? Proposed: yes; a user-level `uv.toml` has the same effect
  as `UV_INDEX_URL`. It also makes uv ignore project config files, which is harmless because the build runs in a
  temporary copy without a root `pyproject.toml`.
- Q5: Run the two real session builds with the three AC-2 variables deliberately set (A5), so the existing content
  tests prove "same result as a clean environment" end to end? Proposed: yes, at no extra build cost. Alternative:
  only the unit-level env assertions.
- Q6: Symlinked `build-profiles` candidate: fail (proposed, A6) or skip it and try the next candidate?
- Q7: Commit `build-constraints.txt` (proposed; reviewable, reusable by a future CI or Make call) or generate it
  from `uv.lock` into a temporary file at test time (no drift test needed, but no file to reuse)?
- Q8: ADR-0012 status. Proposed: stays "Proposed"; add "Implementation notes (IDP-24)".

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_profiles.py::test_build_constraints_pin_locked_build_backend_with_hashes, packages/idp-gate/tests/test_profiles.py::test_session_builds_use_hashed_build_constraints, packages/idp-gate/tests/test_profiles.py::test_session_wheels_are_built_by_locked_hatchling |
| AC-2 | packages/idp-gate/tests/test_profiles.py::test_uv_build_env_strips_uv_and_pip_variables, packages/idp-gate/tests/test_profiles.py::test_session_builds_ran_without_uv_and_pip_variables |
| AC-3 | packages/idp-gate/tests/test_profiles.py::test_profile_file_selection_does_not_follow_symlinked_directories |
| AC-4 | packages/idp-gate/tests/test_profiles.py::test_profiles_source_fails_closed_on_symlinked_source, packages/idp-gate/tests/test_profiles.py::test_build_hook_fails_closed_on_symlinked_profiles_source |
