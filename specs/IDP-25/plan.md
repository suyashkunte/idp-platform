# IDP-25: plan

## Approach
Smallest design: one setting, one test-side drift check, one ADR edit. No production code changes.

1. **Root setting (AC-1, human edit H1)**: add `build-constraint-dependencies` to the existing `[tool.uv]` table of
   the root `pyproject.toml` with the six `==` pins from `packages/idp-gate/build-constraints.txt`. Every
   `uv sync --all-packages` (CI `--frozen`, `make setup`) then resolves idp-gate's editable build backend to the locked
   versions. Hashes are not possible there (uv limitation, out of scope). Then `uv lock` so `uv.lock` records the
   setting if uv does that (spec Q3), and a rebuild of the local editable install.
2. **Three-way drift test (AC-1, AC-3)** in `packages/idp-gate/tests/test_profiles.py`, next to the IDP-24 helpers
   it reuses (`_locked_closure`, `_normalize`, `_REGENERATE_CONSTRAINTS`, `UV_LOCK`, `BUILD_CONSTRAINTS`). A pure
   comparison function takes already-parsed inputs and returns a list of human-readable problems, so every
   disagreement kind is unit-tested with synthetic data, and one test runs it on the real files.
3. **Installed WHEEL check (AC-2)**: read the editable install's `WHEEL` via `importlib.metadata`; no build.
4. **Docs (AC-4)**: replace the `uv sync` bullet in ADR-0012 "Known gaps", add "Implementation notes (IDP-25)", add a
   CHANGELOG entry, and a small text test on the ADR.

CI workflow and the root `Makefile` stay unchanged: both already call `uv sync --all-packages [--frozen]`, which reads
the root `[tool.uv]` table (spec A1, A5).

### H1: human edit right after spec approval (protected path)
The agent cannot edit the root `pyproject.toml`. Replace its existing `[tool.uv]` table (currently only
`package = false`) with:

```toml
[tool.uv]
package = false
# Build backend for every uv sync build of idp-gate (IDP-25, ADR-0012). Must equal
# packages/idp-gate/build-constraints.txt and the hatchling closure in uv.lock (drift test in test_profiles.py).
build-constraint-dependencies = [
  "hatchling==1.32.4",
  "packaging==26.3",
  "pathspec==1.1.1",
  "pluggy==1.6.0",
  "tomlkit==0.15.1",
  "trove-classifiers==2026.9.21.13",
]
```

Then, from the repository root:

```text
uv --version
uv lock --offline || uv lock
uv lock --check
git diff --stat -- pyproject.toml uv.lock
git diff -- uv.lock
uv sync --all-packages --frozen --reinstall-package idp-gate
grep '^Generator:' .venv/lib/python3.12/site-packages/idp_gate-0.1.0.dist-info/WHEEL
uv run --frozen pytest -q packages/idp-gate/tests/test_profiles.py -k "build_constraint or installed_idp_gate"
```

Expected: `uv lock --check` exits 0; the `uv.lock` diff, if any, only adds a record of the six build constraints
(no package version changes; if versions change, stop and report); `grep` prints `Generator: hatchling 1.32.4`.
Record for the PR description: the uv version, whether `uv.lock` changed and where (answers spec Q3), and whether
`uv lock --offline` was enough (spec Q6). Commit `pyproject.toml` and, if changed, `uv.lock` together (the human
commits). Until H1 lands, `test_root_build_constraint_dependencies_pin_build_constraints_file` and
`test_build_constraint_sources_agree` are red.

### Drift check design (test code, stdlib only)
uv.lock is the reference. Sketch (plain text, not code):

```text
_ROOT_PYPROJECT = REPO / "pyproject.toml"
_ADR_0012 = REPO / "docs" / "adr" / "0012-build-profiles.md"
_EXACT_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)$")   # no markers/extras/ranges

_root_build_constraints(pyproject_text) -> object | None
    tomllib.loads(text).get("tool", {}).get("uv", {}).get("build-constraint-dependencies")   # None if absent

_parse_exact_pins(entries, source) -> tuple[dict[name, version], list[problem]]
    problems for: value not a list of strings, entry not matching _EXACT_PIN (quotes the entry, e.g.
    "'hatchling>=1.25' is not an exact '==' pin"), duplicate normalized name

_compare(reference: dict[name, version], actual: dict[name, version]) -> list[difference]
    "missing hatchling==1.32.4", "extra setuptools==80.0", "hatchling: 1.33.0, uv.lock has 1.32.4"

_build_constraint_drift(locked: _Pins, constraints_text: str, root_entries: object | None,
                        lock_recorded: object | None = None) -> list[str]
    locked versions = {name: version for name, (version, _) in locked.items()}
    file: parse with the IDP-24 rules (as text, collecting a problem instead of asserting on a non-'==' line);
          compare names, versions and hash sets with `locked`
          -> "packages/idp-gate/build-constraints.txt is out of date with uv.lock: <differences>;
              regenerate: <_REGENERATE_CONSTRAINTS>"
    root: absent -> "root pyproject.toml has no [tool.uv] build-constraint-dependencies"
          else _parse_exact_pins + _compare(locked versions)
          -> "root pyproject.toml [tool.uv] build-constraint-dependencies is out of date with uv.lock: <differences>;
              a human must set it (protected path) to: [<expected entries, sorted>], then run: uv lock"
    lock_recorded (only if spec Q3 shows uv records it): compare with the root list
          -> "uv.lock is out of date with pyproject.toml build-constraint-dependencies; run: uv lock"
    any problem -> append "To bump hatchling on purpose: uv lock --upgrade-package hatchling, then update both
                           derived sources as above."
```

`_constraints()` (IDP-24) asserts on parse errors; it gets a text-taking core (`_parse_constraints(text)`) that
collects problems, and `_constraints()` keeps its behaviour by wrapping it, so the IDP-24 test is unchanged. The
expected root entries in the message are built from uv.lock (`f"{name}=={version}"`, sorted), so the human can paste
them.

### New tests (all `@pytest.mark.ac("IDP-25:AC-n")`, no subprocess, no network)
- `test_root_build_constraint_dependencies_pin_build_constraints_file` (AC-1): the root key exists, every entry is an
  exact pin, and `{name: version}` equals the names and versions parsed from `build-constraints.txt`. Red until H1.
- `test_build_constraint_sources_agree` (AC-1, AC-3): `_build_constraint_drift(_locked_closure(), file text, root
  value, lock_recorded)` on the real repository files returns `[]`; the assertion message is the joined problem list.
  Red until H1.
- `test_build_constraint_drift_names_stale_source_and_remedy` (AC-3): parametrized, synthetic inputs built from a
  small fixed `locked` closure (no repository files written). Cases and what the message must contain:
  - all three agree -> `[]`;
  - root list bumped only (`hatchling==1.33.0`) -> names the root list, `1.33.0` and `1.32.4`, `uv lock`, bump hint;
  - constraints file bumped only -> names `build-constraints.txt` and the `uv export` command;
  - uv.lock bumped only -> two problems, one per derived source, each with its remedy;
  - package missing from the root list / extra in the root list -> names the package;
  - package missing from / extra in the constraints file -> names the package;
  - range in the root list (`hatchling>=1.25`), and the other non-exact forms from spec AC-3 -> quotes the entry
    and says it is not an exact `==` pin;
  - range in the constraints file -> same, for `build-constraints.txt`;
  - duplicate entry in the root list -> names the duplicate;
  - key absent / not a list -> names the root list and the remedy;
  - hash set differs in the constraints file -> names `build-constraints.txt` (covered by IDP-24 too; kept so the
    combined function is complete).
- `test_installed_idp_gate_was_built_by_locked_hatchling` (AC-2): `dist = importlib.metadata.distribution("idp-gate")`;
  `json.loads(dist.read_text("direct_url.json"))` has `dir_info == {"editable": True}` and `url` equal to
  `PACKAGE_DIR.as_uri()` (comparison after `Path.resolve()` on both sides; otherwise fail with "run make setup");
  the `Generator:` lines of `dist.read_text("WHEEL")` equal `[f"Generator: hatchling {locked}"]` with `locked` from
  `_locked_closure()["hatchling"][0]`.
- `test_adr_0012_known_gaps_state_sync_build_limit` (AC-4): reads the ADR, takes the text from the heading line that
  starts with `### Known gaps` to the next heading; asserts it no longer contains the old phrase
  `still build idp-gate with an unconstrained` and does contain both `build-constraint-dependencies` and the phrase
  `pin versions but not hashes`.

## Changes
| File | Change |
|------|--------|
| pyproject.toml (root, PROTECTED) | HUMAN (H1): `[tool.uv] build-constraint-dependencies` with the six `==` pins and a one-line comment, snippet above. (AC-1) |
| uv.lock | HUMAN (H1), only if `uv lock` changes it: record of the build constraints; no version changes. (AC-1, NFR) |
| packages/idp-gate/tests/test_profiles.py | Module docstring mentions IDP-25. Constants `_ROOT_PYPROJECT`, `_ADR_0012`, `_EXACT_PIN`; helpers `_root_build_constraints`, `_parse_exact_pins`, `_parse_constraints` (text core of `_constraints`), `_compare`, `_build_constraint_drift`; five new tests above. Imports `re` and `importlib.metadata` (stdlib). (AC-1..AC-4) |
| docs/adr/0012-build-profiles.md | Replace the first "Known gaps (review of IDP-24)" bullet with the remaining limit (sync builds pin versions but not hashes; `uv sync` has no hash support for build constraints). Add "Implementation notes (IDP-25)": the root setting and why it lives there; the three sources and that uv.lock is the reference; drift test name; bump order (`uv lock --upgrade-package hatchling`, regenerate `build-constraints.txt`, human edit of the root list, `uv lock`); local rebuild with `uv sync --all-packages --reinstall-package idp-gate`; H1 findings on `uv.lock` (spec Q3). Status stays Proposed. (AC-4) |
| CHANGELOG.md | Under `[Unreleased]` / `### Changed`: `- IDP-25: uv sync builds of the editable idp-gate (CI, make setup) use the locked hatchling closure via [tool.uv] build-constraint-dependencies (versions pinned, not hashes); a drift test keeps uv.lock, build-constraints.txt and the root list in step.` |

Unchanged: `.github/workflows/platform-ci.yml`, root `Makefile`, `packages/idp-gate/pyproject.toml`,
`packages/idp-gate/build-constraints.txt`, `packages/idp-gate/hatch_build.py`, the IDP-24 fixtures and tests.

## Interfaces and data
- New workspace configuration `[tool.uv] build-constraint-dependencies` (root `pyproject.toml`). It narrows the build
  dependencies of every source build in the workspace; today only idp-gate is built from source.
- Possibly a new record in `uv.lock` written by uv (spec Q3). No version changes.
- No CLI, schema, runtime dependency, wheel content or Python API change. Wheels built by `uv sync` and by the
  fixtures still come from hatchling 1.32.4.

## Telemetry
None; build-time configuration and tests only. The drift test failure message is the operator signal (which source,
what differs, exact remedy).

## Risks, rollout and rollback
- Risk: uv does not apply the root setting to the editable member build (spec A1). Detection: H1 (`--reinstall-package`
  rebuild still works, but the setting cannot be proven effective while 1.32.4 is also the newest hatchling); AC-2 in
  CI once a newer hatchling is published. Mitigation: stop and revise the spec (for example move the setting or add
  `[tool.uv] constraint-dependencies`), needs re-approval.
- Risk: `uv.lock` goes stale relative to the root setting and `--frozen` does not notice (spec Q3); `make test`'s
  `uv run` then re-locks silently in CI. Detection: the optional fourth drift comparison if uv records the list;
  otherwise `uv lock --check` in H1. Mitigation: follow-up for `--frozen` in the Makefile (spec Q5).
- Risk: `uv lock` in H1 moves other versions. Detection: the `git diff -- uv.lock` review in H1 and the IDP-24 drift
  test. Mitigation: discard the lock change, retry with `uv lock --offline`, report.
- Risk: a future source-built dependency needs a newer `packaging`/`pluggy` for its build. Detection: its build
  fails during sync. Mitigation: deliberate bump through the documented order.
- Risk: the AC-4 text test is brittle against ADR rewording. Mitigation: it checks two short phrases only (spec Q4).
- Rollout: lands with the PR; developers run `make setup` (or the `--reinstall-package` command) to rebuild their
  editable install. No tenant-visible change.
- Rollback: revert the PR (human, because the root `pyproject.toml` is protected) and run `uv lock`. Builds return to
  the unconstrained `hatchling>=1.25`; nothing to migrate.
