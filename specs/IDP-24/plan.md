# IDP-24: plan

## Approach
Three small changes, all in non-protected files. No root `Makefile`, root `pyproject.toml` or `.github/**` change, so
there is no human edit after spec approval.

1. **Locked build backend (AC-1)**: a committed, generated, hashed constraints file
   `packages/idp-gate/build-constraints.txt`, used by every `uv build` the repository runs as
   `--build-constraint <file> --require-hashes`. The only such builds are the two session fixtures in
   `packages/idp-gate/tests/test_profiles.py`. CI reaches them through `make verify` -> `make test` -> pytest; the
   workflow and the root Makefile never call `uv build`, so they stay unchanged.
2. **Clean build environment (AC-2)**: one helper builds the environment for `uv build` by dropping `UV_*`/`PIP_*`
   (keep-list `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`), and `uv build` gets `--no-config`.
3. **Symlink handling in the build hook (AC-3, AC-4)**: in `packages/idp-gate/hatch_build.py`, `select_profile_files`
   walks with `os.walk(followlinks=False)`, and `profiles_source` fails closed when a candidate `build-profiles` is a
   symlink.

### Why hashed constraints and not `--exclude-newer` (spec Q1)
- `uv.lock` already records hatchling 1.32.4 and its closure (`packaging` 26.3, `pathspec` 1.1.1, `pluggy` 1.6.0,
  `tomlkit` 0.15.1, `trove-classifiers` 2026.9.21.13) with sha256 hashes, because hatchling is in idp-gate's dev
  group since IDP-21. Exporting exactly that closure gives a version pin plus an integrity check, and the build
  backend becomes the same one that mypy checks the hook against.
- `--exclude-newer` freezes only "whatever was newest at date X": no integrity check, a second source of truth next to
  `uv.lock`, and it would have to be bumped separately.
- One file, reusable: a future release workflow or Make target only has to add the same two flags (recorded in
  ADR-0012).
- Offline still works: `uv sync --all-packages` installs the dev group, so all six locked distributions are in the uv
  cache before pytest runs the offline builds (today the offline build takes whatever hatchling the cache happens to
  hold).

### Generating the constraints file
```text
uv export --frozen --package idp-gate --only-group dev --no-emit-project \
  --output-file packages/idp-gate/build-constraints.txt
```
uv writes its default header, which names the command, so the file documents how it was made. T1 confirms that this
exports exactly the hatchling closure with hashes (if it also emits environment markers, they are kept; the parser in
the drift test ignores them). The file is never edited by hand.

### test_profiles.py changes (sketch, plain text)
```text
BUILD_CONSTRAINTS = PACKAGE_DIR / "build-constraints.txt"
UV_LOCK = REPO / "uv.lock"
_UV_ENV_KEEP = frozenset({"UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"})
_POLLUTED_ENV = {"UV_INDEX_URL": "http://127.0.0.1:9/simple", "UV_NO_BUILD_ISOLATION": "1",
                 "PIP_INDEX_URL": "http://127.0.0.1:9/simple"}

_uv_build_env(base) -> dict[str, str]
    {k: v for k, v in base.items() if k in _UV_ENV_KEEP or not k.startswith(("UV_", "PIP_"))}

_uv_build_argv(tree, out_dir, *flags) -> list[str]
    ["uv", "build", *flags, "--offline", "--no-config",
     "--build-constraint", str(BUILD_CONSTRAINTS), "--require-hashes",
     "--out-dir", str(out_dir), str(tree / "packages" / "idp-gate")]

_Build gains: argv: tuple[str, ...], env_names: frozenset[str]   (names only, never values)

_uv_build(tree, out_dir, *flags):
    env = _uv_build_env(os.environ | _POLLUTED_ENV)   # spec A5: polluted on purpose, stripped here
    argv = _uv_build_argv(...)
    subprocess.run(argv, cwd=tree, env=env, ...) -> _Build(out_dir, rc, stderr, tuple(argv), frozenset(env))

_locked_closure(root="hatchling") -> dict[name, (version, frozenset[hashes])]   # tomllib on uv.lock, walk deps
_constraints() -> dict[name, (version, frozenset[hashes])]   # join "\" continuations, skip comments/blank
```
`built_wheel` and `sdist_built_wheel` keep their signatures and stay the only callers of `_uv_build`, so the build
count stays at two. The constraints file is referenced by its absolute repository path; it is not copied into the
temporary build tree and not added to the sdist `only-include` list.

New tests (names as in the spec traceability):
- `test_build_constraints_pin_locked_build_backend_with_hashes` (AC-1): `_constraints() == _locked_closure()`; every
  entry has at least one hash; the closure contains `hatchling`. Failure message names the regeneration command.
- `test_session_builds_use_hashed_build_constraints` (AC-1): for `built_wheel` and `sdist_built_wheel`, `argv`
  contains `--build-constraint` directly followed by `str(BUILD_CONSTRAINTS)`, plus `--require-hashes`, `--offline`
  and `--no-config`. Skipped without uv (inherited from the fixtures).
- `test_session_wheels_are_built_by_locked_hatchling` (AC-1): both wheels' `idp_gate-0.1.0.dist-info/WHEEL` contain
  the line `Generator: hatchling <locked version>`.
- `test_uv_build_env_strips_uv_and_pip_variables` (AC-2): `monkeypatch.setenv` the three AC-2 variables plus
  `UV_EXTRA_INDEX_URL`, `UV_EXCLUDE_NEWER`, `PIP_CONSTRAINT`, `UV_CACHE_DIR`; assert the stripped names are absent,
  `UV_CACHE_DIR` and an unrelated variable (`HOME`/`PATH`) are kept, and
  `_uv_build_env(os.environ | _POLLUTED_ENV) == _uv_build_env(clean)` where `clean` is `os.environ` without any
  `UV_*`/`PIP_*` except the keep-list.
- `test_session_builds_ran_without_uv_and_pip_variables` (AC-2): for both session builds, `returncode == 0` and
  `env_names` has no name starting with `UV_`/`PIP_` outside the keep-list, although `_POLLUTED_ENV` was in the base.
  The existing content tests (`test_wheel_build_profiles_contain_only_allowed_files`,
  `test_sdist_built_wheel_has_same_build_profiles_as_direct_wheel`, `test_profile_show_works_from_sdist_built_wheel`)
  are the "same result as a clean environment" evidence and stay unchanged.
- `test_profile_file_selection_does_not_follow_symlinked_directories` (AC-3): `tmp_path` tree with
  `build-profiles/python-uv/{profile.yaml,defaults.mk}`, an outside directory `outside/` with `x.md` and
  `nested/y.yaml`, `python-uv/linked -> outside`, `python-uv/sub/linked -> outside` and `python-uv/alias -> ../python-uv`;
  `select_profile_files` returns exactly `[python-uv/defaults.mk, python-uv/profile.yaml]`.
- `test_profiles_source_fails_closed_on_symlinked_source` (AC-4): parametrized over (checkout candidate, sdist
  candidate with `PKG-INFO`) x (symlink to a real profiles dir, dangling symlink); `pytest.raises(RuntimeError)` with
  the exact message `idp-gate build: build profiles source is a symlink, refusing to follow it: <path>`. Also: a
  symlinked `<root>/build-profiles` in the checkout does not fall back to the real `../../build-profiles`.
- `test_build_hook_fails_closed_on_symlinked_profiles_source` (AC-4): parametrized over `wheel`/`sdist`; the real
  `ProfilesBuildHook.initialize` (existing `_build_hook` helper) raises the same message and leaves
  `build_data == {"force_include": {}}`.

Existing IDP-21 tests stay green unchanged, including `test_profile_file_selection_applies_allow_list` (the file
symlink `link.md` is still rejected) and `test_profile_source_in_unpacked_sdist_never_falls_back_to_parent`.

### hatch_build.py changes (sketch, plain text)
```text
profiles_source(project_root):
    for candidate in candidates:
        if candidate.is_symlink():
            raise RuntimeError(f"idp-gate build: build profiles source is a symlink, refusing to follow it: {candidate}")
        if candidate.is_dir():
            return candidate
    raise RuntimeError("... not found (looked in: ...)")          # unchanged

select_profile_files(source):
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):   # never descends into dir symlinks
        for each name in filenames + symlinked entries of dirnames: path = Path(dirpath) / name; apply _is_allowed
    sorted; fail closed without */profile.yaml                       # unchanged
```
`os.walk` lists a directory symlink in `dirnames` but does not descend into it with `followlinks=False`; such an entry
is not a regular file, so `_is_allowed` rejects it anyway. Iterating only `filenames` is enough; file symlinks appear
there and are rejected by `path.is_symlink()`. Pruning dot-directories in `dirnames` is optional (the component rule
already rejects them) and not done, to keep the diff small. Docstrings mention IDP-24. mypy strict: `os.walk` on a
`Path` yields `str` tuples, so paths are rebuilt with `Path(dirpath)`.

## Changes
| File | Change |
|------|--------|
| packages/idp-gate/build-constraints.txt | New, generated by the `uv export` command above: `==` pins with all sha256 hashes for hatchling and its closure, as locked. (AC-1) |
| packages/idp-gate/hatch_build.py | `profiles_source`: fail closed on a symlinked candidate (new message). `select_profile_files`: `os.walk(followlinks=False)` instead of `rglob`. Module docstring mentions IDP-24. (AC-3, AC-4) |
| packages/idp-gate/tests/test_profiles.py | Docstring mentions IDP-24. Constants `BUILD_CONSTRAINTS`, `UV_LOCK`, `_UV_ENV_KEEP`, `_POLLUTED_ENV`; helpers `_uv_build_env`, `_uv_build_argv`, `_locked_closure`, `_constraints`; `_Build` gains `argv` and `env_names`; `_uv_build` uses them. Seven new tests listed above, tagged `@pytest.mark.ac("IDP-24:AC-n")`. (AC-1..AC-4) |
| docs/adr/0012-build-profiles.md | Add "Implementation notes (IDP-24)": hashed build constraints generated from uv.lock (regeneration command, drift test, bump procedure, any future CI/Make build must pass the same flags); clean env for `uv build` (prefix rule, keep-list, `--no-config`); symlinks are never followed (walk without following, symlinked source fails closed). Status stays Proposed (Q8). |
| CHANGELOG.md | Under `[Unreleased]` / `### Changed` (exists; IDP-21 entry is there): `- IDP-24: idp-gate builds use a hashed build-constraints file generated from uv.lock (hatchling pinned and hash-checked); test builds run without UV_*/PIP_* variables and user uv config; the build hook never follows symlinked profile directories and fails closed when build-profiles itself is a symlink.` |

Protected paths: none. `uv.lock`, `packages/idp-gate/pyproject.toml`, the root `Makefile`, the root `pyproject.toml`
and `.github/workflows/*.yml` are unchanged.

## Interfaces and data
- New repository file `packages/idp-gate/build-constraints.txt` (requirements format with hashes). It is not part of
  the sdist or the wheel.
- Build hook: a new failure mode (symlinked `build-profiles`) with a new message. Wheel and sdist contents for the real
  repository are unchanged (same three profile files, same bytes).
- No CLI, schema, runtime dependency or Python API change.

## Telemetry
None. Build-time and test-time behaviour only. The build hook's error messages are the operator signal; the uv build
argv is visible in assertion output when a session build fails.

## Risks, rollout and rollback
- Risk: uv cannot verify hashes for build dependencies taken from the cache with `--offline` (spec A9), so both
  session builds fail. Detection: T1, before any other change. Mitigation: the Q1 fallbacks (drop `--require-hashes`,
  then `--exclude-newer`), each requiring spec re-approval.
- Risk: a developer cache lacks the locked hatchling closure (never ran `uv sync --all-packages`), so the offline
  builds fail where they previously passed with another cached hatchling. Detection: the existing returncode
  assertions, whose stderr names the missing package. Mitigation: `make setup` (documented in ADR-0012 notes).
- Risk: CI's uv cache is reachable only through a `UV_*` variable other than the keep-list. Detection: the session
  builds fail in CI. Mitigation: extend the keep-list (Q2).
- Risk: `uv lock --upgrade` moves hatchling without regenerating the constraints file. Detection: the drift test
  fails with the regeneration command in its message.
- Risk: `os.walk` changes the selection order or set. Detection: the existing IDP-21 allow-list and wheel-content
  tests (output is sorted, and the set must stay the same three files).
- Rollout: lands with the PR; no tenant-visible change.
- Rollback: revert the PR. The fixtures return to the unconstrained, unfiltered `uv build`; nothing to migrate.
