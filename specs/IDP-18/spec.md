---
ticket: IDP-18
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: auto
---

# IDP-18: python-uv build profile with default make targets and agent notes

## Context
ADR-0012 makes language toolchains "build profiles" so the pipeline and the agents stay stack-agnostic. `python-uv` is
the first profile; StudyTimer and the service template (S4) use it. A tenant should get sensible defaults for Make
targets it does not define (`sbom`, `sca`), and the plugin's test generators need stack idioms from the profile. This
ticket adds the profile files under `build-profiles/python-uv/`, a `build-profile.v1` schema shipped in `idp-gate`, a
discovery mechanism that works from the installed package, and `idp profile show`.

## Requirements
- **AC-1** Given `build-profiles/python-uv/profile.yaml`, then it validates against a new schema `build-profile.v1` (fields: name, description, setup steps, default targets, coverage format, sbom/sca tools) shipped inside `idp-gate`.
  - Schema file `packages/idp-gate/src/idp_gate/schemas/build-profile.v1.json` (JSON Schema draft 2020-12, like
    `idp-service.v1.json`), loaded with `importlib.resources` from `idp_gate.schemas`. ASSUMPTION A1 (field names):
    top-level keys `name`, `description`, `setup`, `defaultTargets`, `coverage`, `sbom`, `sca`, all required, no other
    keys allowed (`additionalProperties: false`, consistent with "unknown fields fail validation" in the service
    contract).
    - `name`: string, pattern `^[a-z0-9][a-z0-9-]*$`.
    - `description`: non-empty string.
    - `setup`: non-empty array of `{name, run}` objects (both non-empty strings, no other keys).
    - `defaultTargets`: non-empty array of unique target names, pattern `^[a-z][a-z0-9-]*$`.
    - `coverage`: `{format}`, `format` one of `cobertura`, `lcov`, `jacoco`.
    - `sbom`: `{tool, format}`, `tool` non-empty string, `format` one of `cyclonedx-json`.
    - `sca`: `{tool}`, `tool` non-empty string.
  - The python-uv profile declares `defaultTargets: [sbom, sca]`, `coverage.format: cobertura`,
    `sbom: {tool: cyclonedx-py, format: cyclonedx-json}`, `sca: {tool: pip-audit}`.
  - Beyond the schema, a loaded profile's `name` must equal its directory name; otherwise it is a violation at path
    `name` (`name 'x' does not match directory 'y'`). ASSUMPTION A2.
  - Consistency (test-only, not a runtime check): every entry of `defaultTargets` has an `idp-default-<target>` rule in
    the profile's `defaults.mk`, checked with `contract.makefile_targets()` from IDP-17. ASSUMPTION A3.
- **AC-2** Given a tenant Makefile that includes the profile's `defaults.mk` and does not define `sbom` or `sca`, when I run `make sbom` / `make sca`, then the profile defaults run.
  - Defaults run the commands in variables `IDP_SBOM_CMD` and `IDP_SCA_CMD` (assigned with `?=`, so a tenant or a test
    can override them on the command line or in the Makefile). Default values (ASSUMPTION A4, Q4 resolved): both first
    run `IDP_EXPORT_CMD ?= $(UV) export --quiet --frozen --all-packages --no-emit-project --no-emit-workspace --format requirements-txt --output-file $(IDP_REQUIREMENTS)`
    (`IDP_REQUIREMENTS ?= $(REPORTS_DIR)/requirements.locked.txt`, hashed), then
    `IDP_SBOM_CMD ?= $(IDP_EXPORT_CMD) && $(UV) tool run --from $(IDP_CYCLONEDX_SPEC) cyclonedx-py requirements --output-format JSON --output-file $(REPORTS_DIR)/sbom.cdx.json $(IDP_REQUIREMENTS)`
    and `IDP_SCA_CMD ?= $(IDP_EXPORT_CMD) && $(UV) tool run --from $(IDP_PIP_AUDIT_SPEC) pip-audit --disable-pip --requirement $(IDP_REQUIREMENTS) --format json --output $(REPORTS_DIR)/sca.json`,
    with pinned tools `IDP_CYCLONEDX_SPEC ?= cyclonedx-bom==7.5.0` and `IDP_PIP_AUDIT_SPEC ?= pip-audit==2.10.1`,
    `UV ?= uv` and `REPORTS_DIR ?= reports`. Both recipes run `mkdir -p $(REPORTS_DIR)` first, and fail with an error
    naming the variable when `IDP_SBOM_CMD`/`IDP_SCA_CMD` is empty (fail closed). `defaults.mk` has an include guard.
  - Recommended inclusion is via a variable, `include $(IDP_PROFILE_DIR)/defaults.mk`, where `IDP_PROFILE_DIR` is the
    profile directory (see AC-4 `dir` and Q2). Tests stub the commands, e.g. `make sbom IDP_SBOM_CMD='echo default-sbom'`,
    and never run the real tools.
  - Including `defaults.mk` does not change the tenant's default goal (`make` with no target still runs the tenant's
    first target, whether the include is at the top or the bottom). ASSUMPTION A5.
- **AC-3** Given a tenant Makefile that defines a target the profile also defaults (e.g. `sca`), then the tenant's recipe runs and make prints no override warnings.
  - Only the tenant's recipe runs (the default recipe does not run in addition). Verified for the include placed both
    before and after the tenant's rule.
  - "No override warnings" is verified as: stderr of `make sca` is empty (no `warning:` and no
    `overriding recipe for target`). Holds with GNU make 3.81 (macOS) and 4.x (Linux CI); tests run with whichever
    `make` is installed and are skipped if `make` is absent.
  - Overriding one default does not affect the other: `make sbom` still runs the profile default.
- **AC-4** Given `idp profile show python-uv`, then it prints the resolved profile (YAML, or JSON with `--json`) and exits 0.
  - "Resolved profile" (ASSUMPTION A6, see Q1) = the schema-valid `profile.yaml` document as loaded (keys in file order),
    plus one added key `dir` (last): the absolute path of the profile directory it was resolved from, so tenants and
    agents can find `defaults.mk` and `agent-notes.md` in the installed package. No defaults are merged in.
  - Default output: YAML (`yaml.safe_dump(..., sort_keys=False)`) on stdout. `--json`: exactly one compact JSON line
    (`json.dumps` defaults) with the same keys, nothing else on stdout.
  - Discovery (NFR): profiles are resolved first from the installed package (`idp_gate/build_profiles/<name>/`, shipped
    in the wheel), then from the repo checkout (`build-profiles/<name>/`, for the editable workspace install). The first
    root that exists is used; profiles from the two roots are not merged. ASSUMPTION A7.
- **AC-5** (edge) Given `idp profile show nope` or a profile.yaml that violates the schema, then it exits 2 with the profile name and the reason.
  - The ticket writes this AC as `**AC-5 (edge)**`; the marker is moved outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged.
  - Messages go to stderr, stdout stays empty, also with `--json` (as `idp validate` does for exit 2). ASSUMPTION A8,
    see Q3. Formats (ASSUMPTION A9):
    - unknown profile: `profile show: 'nope' not found (available: python-uv)`;
    - schema or name violation: one line per violation, `profile show: 'NAME' is invalid (build-profile.v1): <path>: <message>`
      (`<root>` for the document root, as `contract.Violation` prints today);
    - unparseable YAML: `profile show: 'NAME' is invalid (build-profile.v1): <root>: invalid YAML: ...`;
    - a name not matching `^[a-z0-9][a-z0-9-]*$` (e.g. `../x`, `a/b`) is refused as `profile show: invalid profile name '<repr>'`
      without touching the filesystem (no path traversal);
    - no profiles root found at all: `profile show: no build profiles found (looked in: <dirs>)`.
- **AC-6** Given `build-profiles/python-uv/agent-notes.md`, then it documents pytest idioms, AC tagging (`ac:<KEY>:AC-n`), and fixture conventions, and the unit-test-generator agent definition references it.
  - Sections: pytest idioms, AC tagging, fixture conventions. The reference in
    `plugins/idp-agentic/agents/unit-test-generator.md` is body-only (frontmatter unchanged). ASSUMPTION A13.

## Edge cases and assumptions
- A tenant that lists `sbom` or `sca` in `.PHONY` without defining it gets no default: GNU make skips implicit-rule
  search for phony targets, and `defaults.mk` provides defaults through a pattern rule (see plan). Documented in
  service-contract.md; `defaults.mk` itself does not mark `sbom`/`sca` phony. ASSUMPTION A10.
- A tenant that defines its own match-anything rule (`%:`) may conflict with the defaults; documented limitation.
- A tenant rule with prerequisites but no recipe (`sca: lint`) still gets the default recipe (implicit rule supplies the
  recipe); documented behaviour.
- A file named `sbom` or `sca` in the tenant directory does not make the default "up to date": the default rule depends
  on a phony `idp-default-<t>` target, so it always runs.
- `make lnt` (a typo) still fails with make's usual "No rule to make target" error; the fallback rule only applies when
  `idp-default-<target>` exists.
- IDP-17 interaction: `idp validate` follows only literal includes and rejects includes outside the service directory.
  `include $(IDP_PROFILE_DIR)/defaults.mk` contains `$` and is skipped by that scanner (fine: `sbom`/`sca` are not
  required targets). A literal absolute include of the installed `defaults.mk` would be reported as
  `include '...' is outside the service directory`, so docs recommend the variable form. ASSUMPTION A11.
- Pytest is run by `make test`, so `MAKEFLAGS`, `MAKELEVEL` and `MFLAGS` are removed from the environment of the
  make-level test subprocesses (otherwise flags/jobserver from the outer make leak in and output changes).
- Profile directory without `profile.yaml` is treated as not found.
- ASSUMPTION A1: schema field names and shapes as listed under AC-1.
- ASSUMPTION A2: `name` must equal the directory name (checked in code after the schema).
- ASSUMPTION A3: `defaultTargets` ↔ `defaults.mk` consistency is a repo test, not a runtime check.
- ASSUMPTION A4: default tool commands run exact-pinned tools via `uv tool run --from <spec>` (overridable `*_SPEC`
  variables), so tenants need not add the tools to their dev deps, against the project's locked dependencies exported
  with `uv export --frozen` (uv.lock and the project environment are not changed). Network is only used when the recipe
  runs. Flags confirmed by a real run against this repo (Q4, resolved).
- ASSUMPTION A5: `defaults.mk` preserves the tenant's `.DEFAULT_GOAL`.
- ASSUMPTION A6: resolved profile = document + `dir`; the printed object is therefore not itself schema-valid
  (`dir` is not a schema field).
- ASSUMPTION A7: packaged root first, checkout root second; first existing root wins, no merging.
- ASSUMPTION A8: exit-2 cases print nothing on stdout, also with `--json`.
- ASSUMPTION A9: message formats as listed under AC-5.
- ASSUMPTION A10: tenants must not list un-defined `sbom`/`sca` in `.PHONY`.
- ASSUMPTION A11: tenants include `defaults.mk` through a variable, not a literal absolute path.
- ASSUMPTION A12: no `apiVersion`/`kind` keys in `profile.yaml`; the schema id carries the version.
- ASSUMPTION A13: the AC-6 reference in `plugins/idp-agentic/agents/unit-test-generator.md` names the literal path
  `build-profiles/python-uv/agent-notes.md` and explains that, in a tenant repo, the file is in the `dir` printed by
  `idp profile show <profile>` (profile from `spec.build.profile` in `idp.yaml`).

## Non-functional requirements
- No network at make parse time: `defaults.mk` contains only `?=` (lazily expanded) assignments, rules and
  `.DEFAULT_GOAL` handling; no `$(shell ...)`, no `!=`, no `:=` that runs commands. Verified by a test asserting
  `$(shell` and `!=` do not occur in `defaults.mk`, and by `make -n sbom` succeeding with `UV=/nonexistent/uv` (dry
  run parses and prints without executing tools).
- No secrets in any profile file; `profile.yaml`, `defaults.mk` and `agent-notes.md` contain no credentials, tokens
  or URLs with credentials (code review; existing gitleaks pre-commit hook).
- Discoverable from the installed package: the `idp-gate` wheel contains `idp_gate/build_profiles/python-uv/`
  (`profile.yaml`, `defaults.mk`, `agent-notes.md`). Verified by a test of the wheel build config and a test that
  builds the wheel (`uv build --wheel --offline`) and lists its contents (skipped if `uv` is absent), plus resolver
  unit tests for both roots.
- No new runtime dependencies (stdlib + existing `pyyaml`, `jsonschema`); `uv.lock` unchanged. No protected path
  (root `Makefile`, root `pyproject.toml`, `.github/**`, `infra/**`, plugin hooks, `.claude-plugin/**`) changes.
- Quality bars unchanged: mypy strict, ruff, coverage ≥ 85 %, diff-cover ≥ 80 %.

## Out of scope
- The `dockerfile` profile (later).
- The CI setup action `actions/setup-profile` (S5), including running `setup` steps.
- A dedicated `idp profile path` / `idp profile list` command (see Q2).
- Checking in `idp validate` that `spec.build.profile` names an existing profile.
- Executing the real SBOM/SCA tools in tests; SARIF output for SCA.
- Changes to the root `Makefile` / root `pyproject.toml` (not needed).

## Open questions
- Q1: Meaning of "resolved profile" in AC-4. Proposed default: the validated document as loaded plus a `dir` key with
  the absolute profile directory (A6). Alternatives: the document only; or the document with schema defaults merged in
  (the v1 schema has no defaults, so this equals the document).
- Q2: How does a tenant Makefile locate `defaults.mk` in CI? Proposed default: tenants set `IDP_PROFILE_DIR` (in CI by
  the S5 setup action, locally by hand or from the `dir` printed by `idp profile show python-uv --json`) and use
  `include $(IDP_PROFILE_DIR)/defaults.mk`. Alternative: add `idp profile path <name>` now (small, but beyond the ACs).
- Q3: With `--json`, should exit-2 cases print a JSON error object (as `spec-trace --json` does for a missing spec)
  instead of stderr only? Proposed default: stderr only, stdout empty, matching `idp validate` (A8).
- Q4: Exact default commands and output files for `sbom`/`sca` (A4): `cyclonedx-py environment` vs `cyclonedx-py
  requirements` from `uv export`; `pip-audit` against the environment vs `uv export | pip-audit -r -`; output paths
  `reports/sbom.cdx.json` and `reports/sca.json`. RESOLVED (IDP-18 review round 1): `cyclonedx-py requirements` and
  `pip-audit --disable-pip --requirement` on a hashed `uv export --frozen --all-packages` file in `$(REPORTS_DIR)`,
  tools pinned to `cyclonedx-bom==7.5.0` / `pip-audit==2.10.1` and run with `uv tool run --from`; outputs
  `reports/sbom.cdx.json` and `reports/sca.json`. Verified by one real run against this repo (not in tests; tests stub
  the commands and assert the full default lines with `make -n`).
- Q5: Should ADR-0012 move from "Proposed" to "Accepted" with this ticket? Proposed default: keep "Proposed" and add an
  "Implementation notes (IDP-18)" section; acceptance is a human decision.
- Q6: Is a test that builds the wheel with `uv build --wheel --offline` acceptable in `make verify` (a few seconds;
  relies on hatchling being in the uv cache, which `uv sync` guarantees)? Proposed default: yes, skipped if `uv` is not
  on PATH.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_profiles.py::test_build_profile_schema_ships_in_idp_gate, packages/idp-gate/tests/test_profiles.py::test_python_uv_profile_validates_against_build_profile_schema, packages/idp-gate/tests/test_profiles.py::test_invalid_profile_documents_are_rejected, packages/idp-gate/tests/test_profiles.py::test_profile_name_must_match_directory, packages/idp-gate/tests/test_profiles.py::test_default_targets_have_recipes_in_defaults_mk |
| AC-2 | packages/idp-gate/tests/test_profiles.py::test_make_sbom_and_sca_run_profile_defaults, packages/idp-gate/tests/test_profiles.py::test_default_commands_use_profile_tools_in_dry_run, packages/idp-gate/tests/test_profiles.py::test_defaults_mk_keeps_tenant_default_goal, packages/idp-gate/tests/test_profiles.py::test_defaults_mk_needs_no_commands_at_parse_time |
| AC-3 | packages/idp-gate/tests/test_profiles.py::test_tenant_target_overrides_default_without_warnings |
| AC-4 | packages/idp-gate/tests/test_profiles.py::test_profile_show_prints_yaml_and_exits_0, packages/idp-gate/tests/test_profiles.py::test_profile_show_json_prints_one_json_line, packages/idp-gate/tests/test_profiles.py::test_profiles_resolve_from_checkout_in_workspace, packages/idp-gate/tests/test_profiles.py::test_packaged_profiles_take_precedence_over_checkout, packages/idp-gate/tests/test_profiles.py::test_wheel_config_force_includes_build_profiles, packages/idp-gate/tests/test_profiles.py::test_built_wheel_contains_build_profiles |
| AC-5 | packages/idp-gate/tests/test_profiles.py::test_profile_show_unknown_name_exits_2_with_name_and_reason, packages/idp-gate/tests/test_profiles.py::test_profile_show_schema_violation_exits_2_with_name_and_reason, packages/idp-gate/tests/test_profiles.py::test_profile_show_invalid_yaml_exits_2, packages/idp-gate/tests/test_profiles.py::test_profile_show_refuses_path_like_names, packages/idp-gate/tests/test_profiles.py::test_profile_show_without_profiles_root_exits_2 |
| AC-6 | packages/idp-gate/tests/test_profiles.py::test_python_uv_agent_notes_document_idioms_tagging_and_fixtures, packages/idp-gate/tests/test_profiles.py::test_unit_test_generator_references_agent_notes |
