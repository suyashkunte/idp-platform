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
  1. packaged: `idp_gate/build_profiles/` inside the installed `idp-gate` wheel (hatch `force-include` of
     `build-profiles/`);
  2. checkout: `<repo>/build-profiles/`, used only for the editable workspace install, and only when the module sits in
     this repository's own source tree (`<repo>/packages/idp-gate/pyproject.toml` exists). Any other layout yields no
     checkout candidate, so an unrelated `build-profiles/` directory is never picked up.
- Profile names must match `^[a-z0-9][a-z0-9-]*$` and are checked before any filesystem access (no path traversal).
- **Invariant:** profiles come only from the trusted packaged root or the guarded checkout root. They are never loaded
  from tenant-supplied paths (no path argument, no environment variable, no lookup relative to the tenant repo).
  Changing this would make tenant input part of the trusted toolchain and needs a new decision.
- Caveat: a wheel built from an sdist would not contain `build-profiles/`; build wheels from the source tree.

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
  (`uv export --frozen`), so uv.lock and the project environment are not changed.
- Pins do not move by themselves: upgrading (for fixes or newer vulnerability matching) is a deliberate change in a
  ticket. Tenants can override the `*_SPEC` variables in the meantime.
