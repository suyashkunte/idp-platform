# IDP-18: plan

## Approach
Add the profile as plain files under `build-profiles/python-uv/` (`profile.yaml`, `defaults.mk`, `agent-notes.md`),
the `build-profile.v1` JSON schema next to `idp-service.v1.json`, one new module `idp_gate/profiles.py` (discovery,
load, validate, resolve) and an `idp profile show NAME [--json]` subcommand in `cli.py`. The wheel ships the profiles
via hatch `force-include`; the resolver falls back to the repo checkout for the editable workspace install. No root
`Makefile` or root `pyproject.toml` change; no human step needed.

### Packaging and discovery (chosen: hatch `force-include` + checkout fallback)
- `packages/idp-gate/pyproject.toml` (not protected) gains
  `[tool.hatch.build.targets.wheel.force-include]` `"../../build-profiles" = "idp_gate/build_profiles"`. The wheel then
  contains `idp_gate/build_profiles/python-uv/{profile.yaml,defaults.mk,agent-notes.md}`.
- `profiles.profiles_root()` returns the first existing directory of:
  1. `_PACKAGED_DIR = Path(__file__).resolve().parent / "build_profiles"` (installed wheel; tenants in CI),
  2. `_CHECKOUT_DIR = _checkout_dir(Path(__file__).resolve())` (editable install via `uv sync --all-packages`:
     `idp_gate` is imported from `packages/idp-gate/src/`, where no `build_profiles/` exists, so the checkout copy is
     used). `_checkout_dir()` returns `parents[4] / "build-profiles"` only if the path has at least five parents and
     `parents[4]/packages/idp-gate/pyproject.toml` exists (this repo's source tree); otherwise `None`, so shallow
     layouts (`pip install --target`) do not crash at import and installed layouts never pick up an unrelated
     `build-profiles/` (review round 1).
  Neither exists → `ProfileError("no build profiles found (looked in: ...)")` → exit 2; only real candidates are listed.
- Why: keeps one source of truth at the path the ACs name (`build-profiles/python-uv/...`), needs no copy step (a copy
  step would live in the protected root Makefile), no symlinks (fragile on Windows and in sdists), and no duplicated
  package data that could drift. The fallback is two lines and only used when the packaged directory is absent.
- Caveat: a wheel built *from an sdist* would not see `../../build-profiles`. Wheels must be built directly from the
  source tree (`uv build --wheel`), which is what the test does. Publishing is not part of this ticket; recorded as a
  risk for the release work.

### Make defaults without override warnings (chosen: `idp-default-<t>` rules + match-anything fallback)
GNU make warns "overriding recipe for target" only when two *explicit* rules give the same target a recipe. Implicit
(pattern) rules are only consulted for targets that have no explicit recipe, and an explicit rule beats them silently.
So `defaults.mk` never defines `sbom`/`sca` explicitly:

```make
# Build profile python-uv: default Make targets (ADR-0012, IDP-18). Use: include $(IDP_PROFILE_DIR)/defaults.mk
# A target the tenant does not define (sbom, sca) runs idp-default-<target>; defining it yourself overrides the
# default without warnings. Caveats: listing sbom/sca in .PHONY without a recipe, or your own `%:` rule, bypasses the
# fallback. Reserved names: idp-default-*, _idp_*. No commands run at parse time.
# Include guard: a second include is a no-op (no duplicate rules, no override warnings).
ifndef _idp_python_uv_defaults
_idp_python_uv_defaults := 1
# Never pass the guard to sub-makes (a tenant's bare `export` would otherwise hide the defaults in `$(MAKE) sca`).
unexport _idp_python_uv_defaults
_idp_saved_goal := $(.DEFAULT_GOAL)
UV ?= uv
REPORTS_DIR ?= reports
# Tools are pinned (override the *_SPEC variables to upgrade) and run in uv's isolated tool environments. Both scan
# the project's locked dependencies, exported with hashes from uv.lock using --locked: the export fails if uv.lock is
# stale (out of date with pyproject.toml) and never writes uv.lock or the project environment. Network is needed only
# when the recipes run (tool download, vulnerability database).
IDP_CYCLONEDX_SPEC ?= cyclonedx-bom==7.5.0
IDP_PIP_AUDIT_SPEC ?= pip-audit==2.10.1
IDP_REQUIREMENTS ?= $(REPORTS_DIR)/requirements.locked.txt
IDP_EXPORT_CMD ?= $(UV) export --quiet --locked --all-packages --no-emit-project --no-emit-workspace --format requirements-txt --output-file $(IDP_REQUIREMENTS)
IDP_SBOM_CMD ?= $(IDP_EXPORT_CMD) && $(UV) tool run --from $(IDP_CYCLONEDX_SPEC) cyclonedx-py requirements --output-format JSON --output-file $(REPORTS_DIR)/sbom.cdx.json $(IDP_REQUIREMENTS)
IDP_SCA_CMD ?= $(IDP_EXPORT_CMD) && $(UV) tool run --from $(IDP_PIP_AUDIT_SPEC) pip-audit --disable-pip --requirement $(IDP_REQUIREMENTS) --format json --output $(REPORTS_DIR)/sca.json

.PHONY: idp-default-sbom idp-default-sca
# An empty command fails (fail closed) instead of silently producing no evidence.
idp-default-sbom:
	$(if $(strip $(IDP_SBOM_CMD)),,$(error IDP_SBOM_CMD is empty: set it or define your own sbom target))
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SBOM_CMD)
idp-default-sca:
	$(if $(strip $(IDP_SCA_CMD)),,$(error IDP_SCA_CMD is empty: set it or define your own sca target))
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SCA_CMD)

# A target with no recipe of its own runs idp-default-<target> when that exists; tenant rules win without warnings.
%: idp-default-%
	@:

.DEFAULT_GOAL := $(_idp_saved_goal)
endif
```

- Works the same in GNU make 3.81 and 4.x (pattern rules, `?=`, `.PHONY`, `.DEFAULT_GOAL`, `ifndef`, `$(if)`/`$(error)`
  all exist in 3.81).
- Default commands (review round 1, resolves spec Q4): tools are exact-pinned (`cyclonedx-bom==7.5.0`,
  `pip-audit==2.10.1`, the current releases resolved from PyPI with `uv pip compile`) behind `IDP_CYCLONEDX_SPEC` /
  `IDP_PIP_AUDIT_SPEC`, and run with `uv tool run --from <spec>` in uv's isolated tool environments. Both scan the
  project's locked dependencies: `uv export --locked --all-packages` (hashed, without the project/workspace members)
  into `$(IDP_REQUIREMENTS)`, then `cyclonedx-py requirements` and `pip-audit --disable-pip --requirement` on that
  file. `--locked` (review round 2; `--frozen` silently scanned a stale lock) fails when uv.lock is out of date with
  `pyproject.toml` and never writes uv.lock; `uv export` never syncs the environment. The export is part of
  `IDP_SBOM_CMD`/`IDP_SCA_CMD`, so a stubbed command runs nothing real. Verified by one real run of `make sbom` /
  `make sca` against this repo (CycloneDX 1.6 SBOM, pip-audit JSON, uv.lock unchanged).
- Fail closed: an empty `IDP_SBOM_CMD`/`IDP_SCA_CMD` stops make with an error naming the variable (exit 2) instead of
  exiting 0 without evidence. A failing command fails the target.
- Include guard (`ifndef _idp_python_uv_defaults`, then `unexport _idp_python_uv_defaults` so a tenant's bare `export`
  does not hide the defaults from `$(MAKE) sca` sub-makes): including `defaults.mk` twice is a no-op, so no duplicate-recipe
  warnings.
- `.DEFAULT_GOAL` save/restore keeps the tenant's first target as the default goal when the include is at the top
  (an empty restored value makes make pick the next explicit target, as documented for 3.81+).
- The prerequisite is a phony explicit target, so the default always runs even if a file named `sbom` exists, and a
  typo target (`make lnt`) still fails normally because `idp-default-lnt` does not exist.
- Rejected alternatives: `.DEFAULT:` (hijacks every missing target and prerequisite, needs recursive make);
  double-colon rules (run both recipes, and mixing `:`/`::` with a tenant's `sca:` is a fatal error); variable guards
  (`ifndef IDP_TENANT_SCA`) would force tenants to set a flag in addition to defining the target, changing AC-3.
- Parse time: only `?=`/`:=` of literals and variables, no `$(shell)`/`!=` (NFR). Tools run only inside recipes.

## Changes
| File | Change |
|------|--------|
| build-profiles/python-uv/profile.yaml | New. `name: python-uv`, `description`, `setup` (`{name, run}` steps: install Python via `uv python install`, `uv sync --frozen`), `defaultTargets: [sbom, sca]`, `coverage: {format: cobertura}`, `sbom: {tool: cyclonedx-py, format: cyclonedx-json}`, `sca: {tool: pip-audit}`. (AC-1) |
| build-profiles/python-uv/defaults.mk | New, as sketched above. (AC-2, AC-3) |
| build-profiles/python-uv/agent-notes.md | New. Sections `## pytest idioms` (layout `tests/` per package, `test_*.py`, plain asserts with literal expected values, `pytest.raises`, `parametrize`, `capsys`, no sleeps/network), `## AC tagging` (`@pytest.mark.ac("<KEY>:AC-n")`, which evidence reports as `ac:<KEY>:AC-n`; marker registered in `pyproject.toml`, `--strict-markers`; `idp spec-trace <KEY>` checks it; `p0`/`p1`/`critical`/`smoke`/`quarantine` markers), `## Fixture conventions` (`tmp_path`, `monkeypatch`, `conftest.py` at the narrowest scope, factories over shared mutable fixtures, independent data, `make test` writes JUnit + Cobertura to `$(REPORTS_DIR)`). (AC-6) |
| packages/idp-gate/src/idp_gate/schemas/build-profile.v1.json | New JSON Schema (draft 2020-12), `$id` `https://github.com/suyashkunte/idp-platform/schemas/build-profile.v1.json`, fields per spec A1, `additionalProperties: false` at every object level. (AC-1) |
| packages/idp-gate/src/idp_gate/contract.py | `load_schema(name: str = SCHEMA_NAME)`: add an optional parameter (default keeps today's behaviour). No other change. (AC-1) |
| packages/idp-gate/src/idp_gate/profiles.py | New. Constants `PROFILE_SCHEMA_ID = "build-profile.v1"`, `PROFILE_SCHEMA_NAME`, `PROFILE_FILE = "profile.yaml"`, `_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")`, `_PACKAGED_DIR`, `_CHECKOUT_DIR`. `class ProfileError(Exception)` with `lines: list[str]` (reason lines without the `profile show:` prefix). `profiles_root() -> Path`. `available(root: Path) -> list[str]` (sorted subdirectories containing `profile.yaml`). `validate_profile_document(doc: Any, dirname: str) -> list[contract.Violation]` (schema via `Draft202012Validator(contract.load_schema(PROFILE_SCHEMA_NAME))`, sorted like `contract.validate_document`; then the name/directory check when `doc` is a dict with a string `name`). `load(name: str) -> tuple[Path, dict[str, Any]]`: refuse names not matching `_NAME` (`invalid profile name '<repr>'`) before any filesystem access; resolve root; missing `<root>/<name>/profile.yaml` → `'<name>' not found (available: ...)`; parse with `contract._load_yaml` (`OSError`/`UnicodeDecodeError` → `cannot read '<name>': <error>`); violations → one line each `'<name>' is invalid (build-profile.v1): <violation>`. `resolve(name: str) -> dict[str, Any]` = document + `dir` (absolute path string). (AC-1, AC-4, AC-5) |
| packages/idp-gate/src/idp_gate/cli.py | Import `profiles`. New `_cmd_profile_show(args)`: `try: resolved = profiles.resolve(args.name)` / `except profiles.ProfileError as exc:` print each `profile show: <line>` to stderr, return 2; else print `json.dumps(resolved)` if `args.json` else `yaml.safe_dump(resolved, sort_keys=False)` (without an extra trailing newline), return 0. Parser: `profile` subparser (help "inspect build profiles (ADR-0012)") with a required nested subparser `show` (`name`, `--json` "print a JSON object instead of YAML"). (AC-4, AC-5) |
| packages/idp-gate/pyproject.toml | Add `[tool.hatch.build.targets.wheel.force-include]` `"../../build-profiles" = "idp_gate/build_profiles"`. Dependencies unchanged; `uv.lock` unchanged. (AC-4 NFR) |
| packages/idp-gate/tests/test_profiles.py | New; tests tagged `@pytest.mark.ac("IDP-18:AC-n")` per the spec traceability. Schema tests on the real profile and on in-memory invalid documents (parametrized: missing `name`, unknown top-level key, `coverage.format: xml`, empty `setup`, duplicate `defaultTargets`, bad `name` pattern). Resolver tests with `monkeypatch.setattr(profiles, "_PACKAGED_DIR"/"_CHECKOUT_DIR", tmp dirs)`. CLI tests via `cli.main([...])` + `capsys`. Static test: `tomllib` reads `packages/idp-gate/pyproject.toml` and asserts the force-include mapping. Wheel test: `uv build --wheel --offline --out-dir <tmp_path> packages/idp-gate`, then `zipfile` lists `idp_gate/build_profiles/python-uv/{profile.yaml,defaults.mk,agent-notes.md}` and `idp_gate/schemas/build-profile.v1.json`; skipped if `shutil.which("uv")` is None. Make tests: write a tenant `Makefile` into `tmp_path` with `include $(IDP_PROFILE_DIR)/defaults.mk`, run `make --no-print-directory -C <tmp> <target> IDP_PROFILE_DIR=<repo>/build-profiles/python-uv IDP_SBOM_CMD='echo default-sbom' IDP_SCA_CMD='echo default-sca'` with `MAKEFLAGS`/`MAKELEVEL`/`MFLAGS` (and the profile variables) removed from `env`, `timeout=60`; skipped if `shutil.which("make")` is None; assert literal stdout and empty stderr; AC-3 parametrized over include-before/include-after. Dry-run test: `make -n sca UV=/nonexistent/uv` prints the full default command line (export + `/nonexistent/uv tool run --from pip-audit==2.10.1 pip-audit ...`, and the analogous `cyclonedx-bom==7.5.0` line for `sbom`), exit 0. Review round 1 adds: overridable pins, empty command fails closed, failing command fails the target, double include without warnings, `_checkout_dir()` (3-level path, repo marker), unreadable `profile.yaml`, and an installed-wheel test (`python -I` with the unzipped wheel first on `sys.path`, `profile show python-uv --json` resolves `dir` inside it); make tests also strip `REPORTS_DIR`, `UV`, `IDP_*_CMD`, `IDP_*_SPEC`, `IDP_REQUIREMENTS` from `env`. Consistency test: `contract.makefile_targets(defaults.mk).targets` ⊇ `{f"idp-default-{t}" for t in defaultTargets}`. AC-6 tests: headings and literal strings (`ac:<KEY>:AC-n`, `@pytest.mark.ac(`) in `agent-notes.md`; `build-profiles/python-uv/agent-notes.md` in `unit-test-generator.md`. (AC-1 … AC-6) |
| plugins/idp-agentic/agents/unit-test-generator.md | Add to the Inputs line: the build profile's `agent-notes.md` for stack idioms: `build-profiles/python-uv/agent-notes.md` in the platform repo; in a tenant repo, the `dir` printed by `idp profile show <profile>` where `<profile>` is `spec.build.profile` in `idp.yaml`. Frontmatter unchanged (existing structure tests keep passing). (AC-6) |
| docs/adr/0012-build-profiles.md | Add an "Implementation notes (IDP-18)" section: layout, `build-profile.v1` schema, `defaults.mk` technique (pattern-rule fallback, override without warnings, `.PHONY` caveat), discovery order (packaged, then checkout), `idp profile show`. Status left as is (spec Q5). |
| docs/platform/service-contract.md | In the Make contract table, `sbom`/`sca` row: "the build profile provides defaults (`defaults.mk`)". New subsection "### Build profile defaults" after "How `idp validate` checks it": the `include $(IDP_PROFILE_DIR)/defaults.mk` line (fenced as `make`, after the existing YAML example so `_doc_example()` still finds StudyTimer first), overriding by defining the target, `IDP_SBOM_CMD`/`IDP_SCA_CMD`/`UV`/`REPORTS_DIR` variables, outputs, the `.PHONY` and `%:` caveats, why a literal absolute include fails `idp validate`, and `idp profile show <name> [--json]` with exit codes 0/2. |
| CHANGELOG.md | Under `[Unreleased]` / `### Added`: `- IDP-18: build profile \`python-uv\` (\`profile.yaml\`, \`defaults.mk\` with overridable \`sbom\`/\`sca\` defaults, \`agent-notes.md\`), schema \`build-profile.v1\` shipped in \`idp-gate\` (profiles included in the wheel), and \`idp profile show <name> [--json]\`.` |

No protected paths change (root `Makefile`, root `pyproject.toml`, `.github/**`, `infra/**`,
`plugins/idp-agentic/hooks/**`, `.claude-plugin/**`). Existing tests are not modified.

## Interfaces and data
- CLI (additive): `idp profile show NAME [--json]`. Exit codes: `0` printed; `2` invalid name, unknown profile, invalid
  profile (schema, YAML or name/directory mismatch), no profiles root, or usage error (argparse). Stdout is empty on
  exit 2; reasons on stderr prefixed `profile show: `.
- YAML output example (paths vary):
  ```
  name: python-uv
  description: ...
  setup:
  - name: Sync dependencies
    run: uv sync --frozen
  defaultTargets:
  - sbom
  - sca
  coverage:
    format: cobertura
  sbom:
    tool: cyclonedx-py
    format: cyclonedx-json
  sca:
    tool: pip-audit
  dir: /…/site-packages/idp_gate/build_profiles/python-uv
  ```
- JSON output: the same object on one line, e.g. `{"name": "python-uv", ..., "dir": "/…/python-uv"}`.
- Schema: new `build-profile.v1` (no change to `idp-service.v1`).
- Make interface for tenants: `include $(IDP_PROFILE_DIR)/defaults.mk`; variables `IDP_SBOM_CMD`, `IDP_SCA_CMD`,
  `IDP_EXPORT_CMD`, `IDP_REQUIREMENTS`, `IDP_CYCLONEDX_SPEC`, `IDP_PIP_AUDIT_SPEC`, `UV`, `REPORTS_DIR` (all `?=`);
  reserved names `idp-default-*` and `_idp_*`.
- Python API: `contract.load_schema(name=...)` (backward compatible); new module `profiles` (`profiles_root`,
  `available`, `validate_profile_document`, `load`, `resolve`, `ProfileError`, constants).
- Wheel contents: adds `idp_gate/build_profiles/**`. No dependency or lockfile change.

## Telemetry
None. Local CLI and Make include without runtime telemetry. The SBOM/SCA outputs (`reports/sbom.cdx.json`,
`reports/sca.json`) are evidence artefacts for later gates.

## Risks, rollout and rollback
- Risk: hatch rejects or mishandles the `../../build-profiles` force-include path, or a future release builds the
  wheel from an sdist (the relative path would then be missing). Detection: `test_built_wheel_contains_build_profiles`
  fails. Mitigation: build wheels directly from the source tree; if needed, add a matching sdist force-include in the
  release ticket.
- Risk: the wheel-build test is slow or fails offline in CI if hatchling is not cached. Mitigation: `--offline` relies on
  the cache populated by `uv sync`; skipped without `uv`; open question Q6.
- Risk: make-version differences (3.81 vs 4.x) in pattern-rule or `.DEFAULT_GOAL` handling. Detection: make-level tests
  run on macOS locally and on Linux CI (ubuntu-24.04, make 4.3).
- Risk: the match-anything rule surprises tenants (phony-listed `sbom`, own `%:` rules). Mitigation: documented caveats
  in service-contract.md and comments in `defaults.mk`.
- Risk: default tool flags (`cyclonedx-py`, `pip-audit`) are wrong. Detection: only by a real run (not in tests); one
  real run against this repo confirmed them for the pinned versions; mitigated by the overridable variables.
- Risk: pinned tool versions age (missed fixes, stale vulnerability matching logic). Mitigation: bump the `*_SPEC`
  defaults deliberately in a ticket; tenants can override them meanwhile.
- Risk: checkout fallback picks up an unrelated `build-profiles/` four levels above an installed module. Mitigated: the
  candidate is used only when that directory is this repo's source tree (`packages/idp-gate/pyproject.toml`).
- Rollout: ships with the next `idp-gate` build via the workspace; tenants opt in by including `defaults.mk`.
- Rollback: revert the PR; no data or state to migrate. Tenants that included `defaults.mk` must drop the include.
