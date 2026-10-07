# IDP-21: plan

## Approach
Two independent, small changes; no root `Makefile` or root `pyproject.toml` change, no human step.

1. **Reproducible tool resolution (AC-1, AC-4)** in `build-profiles/python-uv/defaults.mk`: one new `?=` variable,
   `--exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER)` on both `uv tool run` lines, and one recipe-time guard per default
   recipe, using the existing `$(if $(strip ...),,$(error ...))` pattern.
2. **Clean, sdist-safe packaging (AC-2, AC-3)**: replace the static wheel `force-include` of `../../build-profiles`
   with a hatch custom build hook, `packages/idp-gate/hatch_build.py`. The hook selects allow-listed profile files and
   adds them through `build_data["force_include"]`, for both the sdist target (`build-profiles/<rel>`) and the wheel
   target (`idp_gate/build_profiles/<rel>`). The hook looks for the source first inside the project root
   (`<root>/build-profiles`, which exists only in an unpacked sdist), then at `<root>/../../build-profiles` (the
   checkout). The same selection code therefore runs for the direct wheel, the sdist, and the wheel built from the
   sdist.
3. **Tests**: session-scoped fixtures build once from a temporary copy of the build tree that contains stray files.
   Fast unit tests import `hatch_build.py` directly (hatchling is a dev dependency).

### defaults.mk (diff sketch)
```make
# Transitive tool dependencies are resolved as of this fixed instant (uv --exclude-newer), so sbom/sca are
# reproducible. RFC 3339 UTC on purpose (a bare date is read in the local time zone). When you bump a *_SPEC pin,
# move this forward too, or the pin may not resolve.
IDP_TOOLS_EXCLUDE_NEWER ?= 2026-10-06T00:00:00Z
...
IDP_SBOM_CMD ?= $(IDP_SBOM_EXPORT_CMD) && $(UV) tool run --exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER) --from $(IDP_CYCLONEDX_SPEC) cyclonedx-py requirements ...
IDP_SCA_CMD ?= $(IDP_EXPORT_CMD) && $(UV) tool run --exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER) --from $(IDP_PIP_AUDIT_SPEC) pip-audit ...

idp-default-sbom:
	$(if $(strip $(IDP_SBOM_CMD)),,$(error IDP_SBOM_CMD is empty: set it or define your own sbom target))
	$(if $(strip $(IDP_TOOLS_EXCLUDE_NEWER)),,$(error IDP_TOOLS_EXCLUDE_NEWER is empty: set it to a fixed date (RFC 3339, e.g. 2026-10-06T00:00:00Z) so tool dependencies resolve reproducibly))
	@mkdir -p $(REPORTS_DIR)
	$(IDP_SBOM_CMD)
```
(`idp-default-sca` gets the same guard line.) GNU make expands the whole recipe before running its first line, so
the error fires before `mkdir`. Make also expands recipes under `-n`, so a dry run fails too. The new line has no
`$(shell)` and no `!=`, so parse time stays command-free. The guard is also unaffected by the existing `,` and `(`
characters in the message: `$(error ...)` takes everything up to the matching `)`. Note for the implementer: the
message text must not contain an unbalanced `)` or a top-level `,` inside the `$(if ...)` third argument, and the
sketch's `(RFC 3339, e.g. ...)` is balanced. If make 3.81 mis-splits the comma, drop the parenthetical; the tests
assert the prefix `IDP_TOOLS_EXCLUDE_NEWER is empty: set it to a fixed date`.

Default date (spec A1, Q1): `2026-10-06T00:00:00Z`. This is the IDP-18 pin date (ADR-0012), so both
`cyclonedx-bom==7.5.0` and `pip-audit==2.10.1` were published before it, and every transitive dependency is frozen at
that instant. It must be confirmed once by a real run (T4), because tests never run real tools.

### hatch_build.py (sketch)
```python
"""idp-gate build hook: ship allow-listed build profiles in the sdist and the wheel (IDP-21, ADR-0012)."""

from pathlib import Path
from typing import Any
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ALLOWED_SUFFIXES = frozenset({".yaml", ".mk", ".md"})
SDIST_DIR = "build-profiles"
WHEEL_DIR = "idp_gate/build_profiles"


def profiles_source(project_root: Path) -> Path:
    """`<root>/build-profiles` inside an unpacked sdist, else the checkout's `<root>/../../build-profiles`."""
    candidates = [project_root / SDIST_DIR, project_root.parent.parent / SDIST_DIR]
    for c in candidates:
        if c.is_dir():
            return c
    raise RuntimeError(f"idp-gate build: build profiles not found (looked in: {', '.join(map(str, candidates))})")


def select_profile_files(source: Path) -> list[Path]:
    """Sorted relative paths of regular, non-symlink *.yaml/*.mk/*.md files without dot-prefixed components."""
    ...  # rglob("*"); skip symlinks, non-files, dot components, other suffixes; raise if no */profile.yaml selected


class ProfilesBuildHook(BuildHookInterface):  # subscript if hatchling's class is generic
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        source = profiles_source(Path(self.root))
        prefix = WHEEL_DIR if self.target_name == "wheel" else SDIST_DIR
        for rel in select_profile_files(source):
            build_data["force_include"][str(source / rel)] = f"{prefix}/{rel.as_posix()}"
```
- Why a hook instead of static config (spec Q3): a static directory `force-include` cannot apply an allow-list,
  because hatchling does not apply `exclude` patterns to forced paths. A static wheel mapping also points at a missing
  path when the wheel is built from the sdist. The hook is about 40 lines and keeps one source of truth at
  `build-profiles/`. Rejected alternatives: a symlink `src/idp_gate/build_profiles -> ../../../../build-profiles`
  (fragile on Windows; rejected in IDP-18), and a copy step in the root Makefile (protected path).
- Order matters: inside the sdist, `<root>/build-profiles` is used, so a `build-profiles/` two levels above the
  unpack directory can never be picked up. In the checkout, `packages/idp-gate/build-profiles` does not exist, so the
  hook uses `../../build-profiles`.
- In the wheel built from the sdist, the sdist-root `build-profiles/` is not part of the wheel's normal file selection
  (`packages = ["src/idp_gate"]`), so it ships only once, via the hook mapping.
- mypy strict checks `packages/**`. No `type: ignore`: `hatchling>=1.25` is added to idp-gate's own
  `[dependency-groups] dev` in `packages/idp-gate/pyproject.toml` (editable; the root `pyproject.toml` is protected).
  `uv sync --all-packages` (Makefile `setup` and CI) installs member dev groups (verified locally during spec review),
  so mypy sees real hatchling types. `uv.lock` changes accordingly. ruff and bandit apply as usual.
- Editable install (`uv sync`): the hook also runs for `version == "editable"` and finds the checkout source, so the
  behaviour equals today's static `force-include`. Discovery in `profiles.py` is unchanged.

### How "direct wheel == sdist-built wheel" is verified
- Session fixture `profile_build_tree` (`tmp_path_factory`) copies `packages/idp-gate/{pyproject.toml,hatch_build.py,src}`
  (ignoring `__pycache__`/`*.pyc`) to `<tmp>/packages/idp-gate/` and `build-profiles/` to `<tmp>/build-profiles/`,
  then adds the stray files `python-uv/notes.txt`, `python-uv/.env`, `python-uv/.hidden.md` and
  `python-uv/sub/notes.txt`. Skipped when `uv` is absent.
- `built_wheel` (session): `uv build --wheel --offline --out-dir <tmp>/direct <tree>/packages/idp-gate`, run once.
- `sdist_built_wheel` (session): `uv build --offline --out-dir <tmp>/sdist <tree>/packages/idp-gate`, run once. uv's
  default builds the sdist and then the wheel from that sdist; the fixture returns `(sdist, wheel)`.
- Tests compare `{name: bytes}` of every member under `idp_gate/build_profiles/` in both wheels: they must be equal,
  and equal to exactly the three literal python-uv files. The sdist's `idp_gate-0.1.0/build-profiles/` members must be
  exactly those three files too. `profile show python-uv --json` must work from the unzipped sdist-built wheel.

## Changes
| File | Change |
|------|--------|
| build-profiles/python-uv/defaults.mk | Add `IDP_TOOLS_EXCLUDE_NEWER ?= 2026-10-06T00:00:00Z` with a comment (why, UTC, bump together with pins); `--exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER)` before `--from` in `IDP_SBOM_CMD` and `IDP_SCA_CMD`; a second guard line in `idp-default-sbom` and `idp-default-sca`. (AC-1, AC-4) |
| packages/idp-gate/hatch_build.py | New build hook as sketched: `profiles_source()`, `select_profile_files()`, `ProfilesBuildHook`. (AC-2, AC-3) |
| packages/idp-gate/pyproject.toml | Remove `[tool.hatch.build.targets.wheel.force-include]`; add `[tool.hatch.build.hooks.custom]` (default path `hatch_build.py`, applies to sdist and wheel). Add `[dependency-groups] dev = ["hatchling>=1.25"]` (typing for mypy strict). `[tool.hatch.build.targets.wheel] packages` and the runtime dependencies stay unchanged. (AC-2, AC-3) |
| packages/idp-gate/tests/test_profiles.py | Module docstring mentions IDP-21. Add `IDP_TOOLS_EXCLUDE_NEWER` to `_MAKE_ENV_STRIPPED`. Update the expected lines in the IDP-18 test `test_default_commands_use_profile_tools_in_dry_run` (now with `--exclude-newer 2026-10-06T00:00:00Z`). Replace `test_wheel_config_force_includes_build_profiles` with `test_hatch_config_packages_profiles_through_build_hook` (asserts the `hooks.custom` table, no wheel `force-include`, dependencies unchanged; tagged IDP-18:AC-4 and IDP-21:AC-2). Add the session fixtures `profile_build_tree`, `built_wheel` and `sdist_built_wheel`. Rewrite `test_built_wheel_contains_build_profiles` and `test_installed_wheel_resolves_packaged_python_uv` to use `built_wheel` (no own build), with a shared helper `_profile_show_from_wheel(wheel, tmp_path)`. Add the new IDP-21 tests listed in the spec traceability. Load the hook with `importlib.util.spec_from_file_location` (real hatchling from the dev group). Then test `select_profile_files`/`profiles_source` on `tmp_path` trees: allow-list, sdist copy preferred, error when missing or when there is no `profile.yaml`. |
| docs/adr/0012-build-profiles.md | Add "Implementation notes (IDP-21)": `--exclude-newer` (fixed UTC instant, overridable, fail closed when empty, bump with pins), packaging via the build hook (allow-list, sdist carries `build-profiles/`, sdist-built wheel identical). Remove the IDP-18 caveat line about sdists. Status stays Proposed (Q6). |
| docs/platform/service-contract.md | Add an `IDP_TOOLS_EXCLUDE_NEWER` row to the overridable-variables table (`2026-10-06T00:00:00Z`; passed as `--exclude-newer` to `uv tool run`; empty fails closed); show `--exclude-newer` in the pinned-tools rows; one sentence on bumping it together with the `*_SPEC` pins. |
| build-profiles/python-uv/agent-notes.md | One bullet under "Fixture conventions": build expensive artefacts (e.g. a wheel) once, in a `scope="session"` fixture using `tmp_path_factory` (Q7). The existing AC-6 heading test is unaffected. |
| CHANGELOG.md | Under `[Unreleased]` / `### Changed`: `- IDP-21: python-uv \`sbom\`/\`sca\` defaults pass \`--exclude-newer $(IDP_TOOLS_EXCLUDE_NEWER)\` (default \`2026-10-06T00:00:00Z\`, overridable; empty fails closed); \`idp-gate\` ships only \`*.yaml\`/\`*.mk\`/\`*.md\` profile files, and wheels built from the sdist include the profiles.` |

No protected path changes. `uv.lock` gains hatchling (dev only) for the idp-gate dev group.

## Interfaces and data
- Make (additive): new tenant-overridable variable `IDP_TOOLS_EXCLUDE_NEWER` (`?=`). The default `IDP_SBOM_CMD` /
  `IDP_SCA_CMD` lines gain `--exclude-newer <value>`. Tenants who override those commands are unaffected, apart from
  the AC-4 guard, which still requires a non-empty value.
- Packaging: wheel contents under `idp_gate/build_profiles/` narrow to the allow-list (the same three files today).
  The sdist gains `build-profiles/**` (allow-listed). The install layout and `profiles.py` discovery are unchanged.
- No CLI, schema or Python API change.

## Telemetry
None. Build-time and make-time behaviour only. The exclude-newer value appears in the command lines that make
echoes, so CI logs show which resolution instant was used.

## Risks, rollout and rollback
- Risk: the default date is older than a pinned tool's release, so `uv tool run` cannot resolve it. Detection: the
  one-time real run in T4 (network), and later the S5 CI run. Mitigation: overridable variable; documented "bump with
  the pins".
- Risk: the hatchling hook API (`build_data["force_include"]`, `self.target_name`, `self.root`) behaves differently
  for the sdist target in the hatchling version uv picks (`hatchling>=1.25`). Detection: the session build tests (sdist
  member list, identical wheels). Mitigation: pin a minimum hatchling version in `build-system.requires` if needed.
- Risk: `uv build --offline` for the sdist-to-wheel path needs hatchling in the uv cache. The direct build already
  relies on this (IDP-18 Q6). Skipped without `uv`.
- Risk: mypy strict rejects the hook. Mitigation: hatchling is a typed dev dependency; never `type: ignore`.
- Rollout: the next `idp-gate` build; tenants get `--exclude-newer` automatically through `defaults.mk`.
- Rollback: revert the PR. Static `force-include` returns, along with its known caveats. No data to migrate.
