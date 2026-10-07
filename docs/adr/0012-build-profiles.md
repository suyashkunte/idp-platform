# 0012. Build profiles for language-agnostic pipelines

- **Status:** Proposed
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Decision
A build profile (`build-profiles/<name>/profile.yaml` + scripts) supplies toolchain setup, default make targets, SCA/SBOM settings, the coverage format and agent notes for one stack. v1 ships `python-uv` and `dockerfile` (generic: any stack that has a Dockerfile and implements the Make contract). Further profiles (`node-pnpm`, `go`, `java-gradle`) are additive.
## Consequences
+ The gate engine never branches on language; tenant #2 (iteration 11) proves the `dockerfile` path.
- Profile-specific quality signals (mutation testing) are optional per profile and reported as advisory where unsupported.

## Implementation notes (IDP-18)
Status stays Proposed; acceptance is a human decision (IDP-18 spec, Q5).

### Layout and schema
- One directory per profile, `build-profiles/<name>/`, with `profile.yaml` (the profile document), `defaults.mk`
  (default Make targets) and `agent-notes.md` (stack idioms for the test-generating agents). The first profile is
  [`python-uv`](../../build-profiles/python-uv/profile.yaml).
- `profile.yaml` is validated against the JSON Schema `build-profile.v1` (draft 2020-12), shipped inside `idp-gate` at
  `idp_gate/schemas/build-profile.v1.json`. Required top-level keys, no others allowed: `name`, `description`,
  `setup` (`{name, run}` steps), `defaultTargets`, `coverage` (`format`: `cobertura` | `lcov` | `jacoco`),
  `sbom` (`tool`, `format`: `cyclonedx-json`), `sca` (`tool`). Beyond the schema, `name` must equal the directory name.
  There is no `apiVersion`/`kind`; the schema id carries the version.
- `idp profile show <name> [--json]` prints the resolved profile: the document as loaded plus a `dir` key with the
  absolute profile directory (so tenants and agents can find `defaults.mk` and `agent-notes.md`). Exit `0` on success,
  `2` for an invalid name, unknown or invalid profile, or no profiles root (reason on stderr, stdout empty).

### Discovery
- Profiles are resolved from the first existing root, never merged:
  1. packaged: `idp_gate/build_profiles/` inside the installed `idp-gate` wheel (allow-listed copy of
     `build-profiles/`, added by a hatch build hook since IDP-21; see below);
  2. checkout: `<repo>/build-profiles/`, used only for the editable workspace install, and only when the module sits in
     this repository's own source tree (`<repo>/packages/idp-gate/pyproject.toml` exists). Any other layout yields no
     checkout candidate, so an unrelated `build-profiles/` directory is never picked up.
- Profile names must match `^[a-z0-9][a-z0-9-]*$` and are checked before any filesystem access (no path traversal).
- **Invariant:** profiles come only from the trusted packaged root or the guarded checkout root. They are never loaded
  from tenant-supplied paths (no path argument, no environment variable, no lookup relative to the tenant repo).
  Changing this would make tenant input part of the trusted toolchain and needs a new decision.

### Default Make targets (`%: idp-default-%`)
- `defaults.mk` never defines `sbom`/`sca` explicitly. It defines phony `idp-default-sbom`/`idp-default-sca` rules and
  one match-anything pattern rule `%: idp-default-%` with an empty recipe.
- Why: GNU make warns "overriding recipe for target" only when two explicit rules give a target a recipe; a pattern
  rule is consulted only for targets without an explicit recipe, and an explicit tenant rule beats it silently. So a
  tenant that defines `sca` gets only its own recipe, without warnings, whether the include is before or after the
  rule; a tenant that does not gets the default. Because the prerequisite is a phony target, the default always runs
  even if a file named `sca` exists, and a typo (`make lnt`) still fails normally since `idp-default-lnt` does not
  exist. Works with GNU make 3.81 and 4.x.
- Rejected: `.DEFAULT:` (hijacks every missing target), double-colon rules (run both recipes; mixing `:` and `::` is
  fatal), opt-out variables (tenants would need a flag in addition to the target).
- Known limits: a tenant listing `sbom`/`sca` in `.PHONY` without defining it gets no default (make skips implicit-rule
  search for phony targets); a tenant's own `%:` rule may conflict. `defaults.mk` has an include guard, keeps the
  tenant's `.DEFAULT_GOAL`, runs nothing at parse time (no `$(shell)`, no `!=`) and reserves the names `idp-default-*`
  and `_idp_*`. Tenant-facing details are in the
  [service contract](../platform/service-contract.md#build-profile-defaults).

### Pinned tool versions
- The python-uv defaults run exact-pinned tools, `IDP_CYCLONEDX_SPEC ?= cyclonedx-bom==7.5.0` and
  `IDP_PIP_AUDIT_SPEC ?= pip-audit==2.10.1`, with `uv tool run --from <spec>` against the project's locked dependencies
  (`uv export --locked`): the export fails if uv.lock is stale, and uv.lock and the project environment are not
  changed.
- Pins do not move by themselves: upgrading (for fixes or newer vulnerability matching) is a deliberate change in a
  ticket. Tenants can override the `*_SPEC` variables in the meantime.

### SBOM and SCA scope (reviewer decisions)
- SBOM = runtime dependencies: its export (`IDP_SBOM_EXPORT_CMD`) uses `--no-dev`, so the SBOM describes what ships.
  SCA = all dependency groups, dev included (`IDP_EXPORT_CMD`), because dev tools run in CI.
- `make sca` deliberately fails on any finding while no gate engine exists. When the policy/gate engine lands, `sca`
  becomes report-only and the gate decides, with severity thresholds and expiring waivers.
- SCA covers the CI platform only (Linux/CPython, matching the deploy target): dependencies that are conditional on
  other platforms (environment markers such as `sys_platform == 'win32'`) are not audited.

## Implementation notes (IDP-21)
Status stays Proposed (IDP-21 spec, Q6).

### Reproducible tool resolution
- The `*_SPEC` pins fix only the top-level tools. To freeze their transitive dependencies too, the python-uv
  [`defaults.mk`](../../build-profiles/python-uv/defaults.mk) passes `--exclude-newer '$(IDP_TOOLS_EXCLUDE_NEWER)'` to
  both `uv tool run` invocations (before `--from`, because uv reads options only before the command). `uv export` does
  not get the option: it reads the existing uv.lock and resolves nothing.
- `IDP_TOOLS_EXCLUDE_NEWER ?= 2026-10-06T00:00:00Z`: a fixed RFC 3339 UTC instant (the IDP-18 pin date), never
  relative or computed. A bare date is avoided because uv reads it in the local time zone, which would make resolution
  differ between a laptop and CI. Tenants can override it like any other profile variable; the explicit flag also
  takes precedence over a `UV_EXCLUDE_NEWER` environment variable.
- Fail closed: an empty (or whitespace-only) value stops `idp-default-sbom`/`idp-default-sca` with
  `IDP_TOOLS_EXCLUDE_NEWER is empty: ...` before anything runs. The guard is a recipe line, so parse time stays
  command-free and unrelated targets are unaffected. It applies even when `IDP_SBOM_CMD`/`IDP_SCA_CMD` is overridden;
  a tenant-defined `sbom`/`sca` target never runs it. A second guard line (PR #8 security review) also fails closed,
  with `IDP_TOOLS_EXCLUDE_NEWER must be a single value without spaces or single quotes ...`, when the value has more
  than one word or contains a single quote; the command lines pass it single-quoted. Together these stop the value
  from injecting extra uv options or shell commands. The date format itself is not checked by make; uv rejects a
  malformed date when the recipe runs.
- Bumping a `*_SPEC` pin requires moving `IDP_TOOLS_EXCLUDE_NEWER` forward in the same change; otherwise a pin
  released after that instant cannot resolve.

### Packaging via a build hook
- The static wheel `force-include` of `../../build-profiles` is replaced by a hatch custom build hook,
  [`packages/idp-gate/hatch_build.py`](../../packages/idp-gate/hatch_build.py) (`[tool.hatch.build.hooks.custom]`).
  Why: hatchling does not apply `exclude` patterns to force-included paths, so a static mapping cannot filter, and a
  static wheel mapping points at a path that does not exist next to an unpacked sdist.
- Allow-list: only regular, non-symlink files with suffix `.yaml`, `.mk` or `.md` and no dot-prefixed path component
  are packaged; everything else (`notes.txt`, `.env`, `.hidden.md`, `__pycache__/`) is left out silently.
- Targets: the sdist carries the profiles at `build-profiles/` in its root, the wheel at `idp_gate/build_profiles/`.
  The hook uses `<root>/build-profiles` first; inside an unpacked sdist (`PKG-INFO` present) it uses only that copy and
  never looks outside the sdist, otherwise it falls back to the checkout's `<root>/../../build-profiles`. A direct wheel
  build and a wheel built from the sdist therefore contain the same files with identical bytes.
- The sdist is allow-listed as well (PR #8 security review): `[tool.hatch.build.targets.sdist] only-include =
  ["src", "tests", "hatch_build.py", "pyproject.toml"]`, plus the hook's `build-profiles/` and the files hatchling
  always adds (`PKG-INFO`, and the nearest `.gitignore` up to the repository root). An untracked file next to
  `pyproject.toml` (`creds.yaml`, `id_rsa`) therefore never ships.
- Fail closed: the build stops with an error when no profiles source exists, when no `*/profile.yaml` is selected, or
  for an unknown build target, instead of producing a wheel without profiles.
- Install layout and discovery (above) are unchanged. `hatchling` is in idp-gate's dev dependency group only, so mypy
  strict checks the hook against real types; runtime dependencies are unchanged.
