---
ticket: IDP-21
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: auto
---

# IDP-21: python-uv profile hardening: reproducible tool resolution and a clean wheel

## Context
The IDP-18 review (PR #6) deferred findings #2, #7 and #9. The `sbom`/`sca` defaults pin only the top-level tools
(`cyclonedx-bom==7.5.0`, `pip-audit==2.10.1`), so their transitive dependencies resolve fresh on every run. The wheel's
static `force-include` copies the whole `build-profiles/` tree, including stray files. A wheel built from the sdist
has no profiles, because `../../build-profiles` does not exist next to an unpacked sdist. Tests also build the wheel
twice. All of this has to be fixed before S5 uses the `idp-gate` wheel. Parent epic IDP-16; depends on IDP-18
(718c1ca) and ADR-0012.

## Requirements
- **AC-1** Given the python-uv defaults, when `make sbom` / `make sca` run, then each `uv tool run` passes `--exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER)` (a fixed date set with `?=`, overridable).
  - `defaults.mk` gains `IDP_TOOLS_EXCLUDE_NEWER ?= 2026-10-06T00:00:00Z`. The value is a fixed RFC 3339 UTC timestamp,
    not a relative value and not computed. ASSUMPTION A1, see Q1.
  - Both tool invocations become `$(UV) tool run --exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER) --from <spec> <tool> ...`.
    The option goes before `--from` and the command name, because uv reads options only before the command. Nothing
    else in the command lines changes. `uv export` does not get the option: it reads the existing `uv.lock` and does
    not resolve anything.
  - "Overridable": `make sca IDP_TOOLS_EXCLUDE_NEWER=2030-01-01T00:00:00Z` (or a tenant Makefile assignment) puts that
    value in both command lines.
  - Verified with `make -n` (dry run, `UV=/nonexistent/uv`). The tests assert the full default command lines and run
    no real tools.
- **AC-2** Given a stray file such as `notes.txt` or `.env` in `build-profiles/python-uv/`, when the idp-gate wheel is built, then `idp_gate/build_profiles/` contains only `*.yaml`, `*.mk` and `*.md` files.
  - Allow-list rule (ASSUMPTION A2, see Q5): a file under `build-profiles/` is packaged only if all of these hold:
    it is a regular file and not a symlink, its suffix is `.yaml`, `.mk` or `.md`, and no path component starts with
    `.`. Everything else is left out silently. So `notes.txt`, `.env`, `.hidden.md` and `__pycache__/x.pyc` are all
    left out.
  - For the real repository the wheel then holds exactly `idp_gate/build_profiles/python-uv/profile.yaml`,
    `.../defaults.mk` and `.../agent-notes.md` under `idp_gate/build_profiles/`.
  - The sdist applies the same rule to its copy of the profiles (see AC-3).
  - Tests never write into the repository. Stray files are added to a temporary copy of the build tree, which the
    session wheel fixture builds (see NFRs).
- **AC-3** Given the idp-gate sdist, when a wheel is built from it, then `idp profile show python-uv` works from that install.
  - The sdist carries the allow-listed profiles at `build-profiles/` inside the sdist root
    (`idp_gate-0.1.0/build-profiles/python-uv/...`). A wheel built from that sdist maps them to
    `idp_gate/build_profiles/`.
  - The direct wheel build (`uv build --wheel`) and the sdist-to-wheel build (`uv build`, which by default builds an
    sdist and then a wheel from it) produce the same set of files under `idp_gate/build_profiles/`, with identical
    bytes.
  - "Works from that install" means the same check as the IDP-18 installed-wheel test. Unzip the sdist-built wheel
    into a temporary site directory and run `python -I` with that directory first on `sys.path`. Then
    `profile show python-uv --json` exits 0, prints `"name": "python-uv"`, and its `dir` is
    `<site>/idp_gate/build_profiles/python-uv`. Skipped without `uv`.
  - If no profiles source is found at build time, the build fails with a clear error instead of producing a wheel
    without profiles (fail closed). ASSUMPTION A3.
- **AC-4** (edge) Given `IDP_TOOLS_EXCLUDE_NEWER` is empty, when `make sbom` / `make sca` run, then they fail closed with a clear message.
  - The ticket writes the edge marker after the bold id. It stays outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged.
  - The check runs when the recipe runs, not at parse time. Each `idp-default-sbom` / `idp-default-sca` recipe gets a
    second guard line right after the existing `IDP_*_CMD` guard, using the same pattern:
    `$(if $(strip $(IDP_TOOLS_EXCLUDE_NEWER)),,$(error IDP_TOOLS_EXCLUDE_NEWER is empty: set it to a fixed date (RFC 3339, e.g. 2026-10-06T00:00:00Z) so tool dependencies resolve reproducibly))`.
    Consequences: `make` exits 2, the message appears on stderr, stdout is empty, nothing runs, and `$(REPORTS_DIR)`
    is not created. Make also expands recipes under `make -n`, so a dry run fails the same way.
  - "Empty" includes whitespace only (`$(strip ...)`). A non-empty but malformed value is not checked by make; uv
    rejects it when the recipe runs. ASSUMPTION A4.
  - The guard applies even when `IDP_SBOM_CMD` / `IDP_SCA_CMD` is overridden, since the AC says "when `make sbom` /
    `make sca` run". A tenant that defines its own `sbom`/`sca` target never runs the default recipe, so the guard
    does not apply to it. ASSUMPTION A5, see Q4.
  - Parse time stays command-free. Setting the variable empty and running an unrelated target (`make build`)
    succeeds.

## Edge cases and assumptions
- `IDP_TOOLS_EXCLUDE_NEWER` is set in the environment. `?=` takes the environment value, as for all other profile
  variables. Make-level tests remove it from the subprocess environment, together with the IDP-18 list.
- `UV_EXCLUDE_NEWER` is set in the environment. The explicit `--exclude-newer` flag takes precedence for `uv tool run`
  (uv's CLI-over-env rule), so the Makefile value wins.
- If the default date is older than a pinned tool release, `uv tool run` cannot resolve the pin and fails when the
  recipe runs. Bumping a `*_SPEC` pin therefore also requires moving `IDP_TOOLS_EXCLUDE_NEWER` forward. This is
  documented in `defaults.mk`, ADR-0012 and service-contract.md.
- Editable workspace install (`uv sync`): profiles keep resolving from the checkout, as today (IDP-18 discovery is
  unchanged). The build hook runs for editable builds too. It does nothing new there, because `idp_gate` is imported
  from `src/`.
- A stray file in a nested directory (`build-profiles/python-uv/sub/notes.txt`) follows the same allow-list rule.
- ASSUMPTION A1: default `IDP_TOOLS_EXCLUDE_NEWER ?= 2026-10-06T00:00:00Z`. 2026-10-06 is the date the IDP-18 pins
  were chosen as the current releases (ADR-0012 date), so both pins exist before it and transitive dependencies are
  frozen at that point. It is a UTC timestamp, not a bare date, because uv interprets a bare date in the local time
  zone, and that would make resolution differ between a developer laptop and CI. This must be confirmed with one real
  `make sbom` / `make sca` run (network) before merge.
- ASSUMPTION A2: allow-list = regular, non-symlink files with suffix `.yaml`/`.mk`/`.md` and no dot-prefixed path
  component.
- ASSUMPTION A3: the build fails when no profiles source exists or the allow-list selects no `profile.yaml`.
- ASSUMPTION A4: make checks only that the value is non-empty, not its format.
- ASSUMPTION A5: the empty-value guard is unconditional inside the default recipes.
- ASSUMPTION A6: the packaging fix uses a hatch custom build hook (`packages/idp-gate/hatch_build.py`) instead of
  static `force-include` (see plan.md, Q3).

## Non-functional requirements
- No network at make parse time. `defaults.mk` still uses only `?=` assignments of literals and variables. There is no
  `$(shell ...)` and no `!=`, and the new guard is inside recipes. Verified by the existing
  `test_defaults_mk_needs_no_commands_at_parse_time` (unchanged; it asserts no `$(shell` / `!=` and runs
  `make -n sbom UV=/nonexistent/uv`) and by the AC-4 test that runs an unrelated target with the variable empty.
- Tests build the wheel at most once per session. One session-scoped fixture `built_wheel` runs
  `uv build --wheel --offline` once and is shared by every test that needs the direct wheel. Today two tests each run
  their own build: `test_built_wheel_contains_build_profiles` and `test_installed_wheel_resolves_packaged_python_uv`
  in `packages/idp-gate/tests/test_profiles.py`. AC-3 needs a wheel built from the sdist, which is a different
  artefact. It comes from one more session-scoped fixture `sdist_built_wheel` (one `uv build --offline`, which writes
  an sdist and the wheel built from it). Total: two `uv build` runs per session, each run once (Q2). Both fixtures skip
  when `uv` is absent.
- No secrets: `defaults.mk`, `hatch_build.py` and the docs contain no credentials. The allow-list keeps `.env` and
  other dotfiles out of the wheel and the sdist, and the existing gitleaks pre-commit hook still applies.
- No protected path changes (root `Makefile`, root `pyproject.toml`, `.github/**`, `infra/**`, plugin hooks,
  `.claude-plugin/**`). No new runtime dependencies. `uv.lock` changes only to add `hatchling` (and its
  dependencies) for idp-gate's dev group, so mypy strict sees real hatchling types (plan.md).
  `packages/idp-gate/pyproject.toml` runtime dependencies unchanged.
- Quality bars unchanged: mypy strict (which also checks `packages/idp-gate/hatch_build.py`), ruff, bandit, coverage
  >= 85 %, diff-cover >= 80 %.

## Out of scope
- Hashed constraints files for the tools.
- The gate engine, severity thresholds and waivers.
- The report-existence check (S5).
- Pinning the `uv` version itself, and validating the format of the date in make.
- Publishing the wheel or sdist to an index.

## Open questions
- Q1: Default value and format of `IDP_TOOLS_EXCLUDE_NEWER`. Proposed default: `2026-10-06T00:00:00Z` (RFC 3339 UTC;
  the IDP-18 pin date), confirmed by one real `make sbom` / `make sca` run before merge (A1). Alternatives: today's
  date; a bare date `2026-10-06`, which uv reads in local time and is therefore not reproducible across time zones.
- Q2: Does the NFR "wheel at most once per session" allow a second, separate sdist-to-wheel build for AC-3? Proposed
  default: yes. The direct wheel is built once (`built_wheel`) and the sdist-built wheel is built once
  (`sdist_built_wheel`), both session-scoped. Today there are two direct builds, so the total stays at two `uv build`
  runs.
- Q3: Packaging mechanism. Proposed default: a hatch custom build hook (`packages/idp-gate/hatch_build.py`, configured
  under `[tool.hatch.build.hooks.custom]`). It selects the allow-listed files and adds them through
  `build_data["force_include"]`, mapping them to `build-profiles/` in the sdist and to `idp_gate/build_profiles/` in
  the wheel. The source is the copy inside the sdist when present, otherwise `../../build-profiles`. The alternative,
  static `force-include` for both targets, was rejected for two reasons, both unverified in this session (no shell
  access). (a) hatchling does not apply `exclude` patterns to force-included paths, so a static directory mapping
  cannot apply the allow-list. (b) A static wheel mapping to `../../build-profiles` points at a path that does not
  exist when building from the sdist; hatchling then either errors ("Forced include not found") or, as the ticket
  states, ships no profiles. The implementer should confirm the current behaviour of `uv build` from the sdist once
  before the change, for the record.
- Q4: Should the empty-`IDP_TOOLS_EXCLUDE_NEWER` guard apply only when the default tool command is in use, rather than
  also when `IDP_SBOM_CMD`/`IDP_SCA_CMD` is overridden? Proposed default: unconditional (A5). It is simpler and follows
  the AC text literally.
- Q5: Allow-list details: also exclude dot-prefixed `*.md`/`*.yaml` files and symlinks (proposed, A2), or apply the
  suffix rule only?
- Q6: ADR-0012 status. Proposed default: keep "Proposed" and add "Implementation notes (IDP-21)". Also remove the
  IDP-18 caveat "a wheel built from an sdist would not contain `build-profiles/`".
- Q7: Should `agent-notes.md` gain one fixture-convention bullet ("build expensive artefacts such as a wheel once, in
  a `scope="session"` fixture using `tmp_path_factory`")? Proposed default: yes, one bullet. It is the idiom this
  ticket introduces, and test agents should reuse it.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_profiles.py::test_tool_runs_pass_exclude_newer_in_dry_run, packages/idp-gate/tests/test_profiles.py::test_exclude_newer_default_is_fixed_and_conditional, packages/idp-gate/tests/test_profiles.py::test_exclude_newer_is_overridable |
| AC-2 | packages/idp-gate/tests/test_profiles.py::test_wheel_build_profiles_contain_only_allowed_files, packages/idp-gate/tests/test_profiles.py::test_sdist_build_profiles_contain_only_allowed_files, packages/idp-gate/tests/test_profiles.py::test_profile_file_selection_applies_allow_list, packages/idp-gate/tests/test_profiles.py::test_hatch_config_packages_profiles_through_build_hook |
| AC-3 | packages/idp-gate/tests/test_profiles.py::test_sdist_built_wheel_has_same_build_profiles_as_direct_wheel, packages/idp-gate/tests/test_profiles.py::test_profile_show_works_from_sdist_built_wheel, packages/idp-gate/tests/test_profiles.py::test_profile_file_selection_prefers_sdist_copy, packages/idp-gate/tests/test_profiles.py::test_profile_file_selection_fails_without_profiles |
| AC-4 | packages/idp-gate/tests/test_profiles.py::test_empty_exclude_newer_fails_closed, packages/idp-gate/tests/test_profiles.py::test_empty_exclude_newer_is_not_checked_at_parse_time |
