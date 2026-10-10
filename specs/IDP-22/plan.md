# IDP-22: plan

## Approach
Smallest design: one directory-listing check in `contract.py`, one public "parse once" function in `contract.py`,
and three small changes in `conformance.py` (confinement check, `-f Makefile`, use the new function). CLI passes DIR
to `check_example`. No protected path changes, no human task.

1. **Extra makefiles (AC-1)**, `contract.py`:
   - Constant `_SHADOWING_MAKEFILES = frozenset({"gnumakefile", "makefile"})` (casefolded names GNU make reads before
     `Makefile`).
   - Helper `_extra_makefiles(directory: Path) -> list[Violation]`: `names = os.listdir(directory)`; on `OSError`
     return `[Violation(MAKE_PATH, "cannot list the service directory")]`; otherwise one
     `Violation(name, "GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it")`
     per `name` in `sorted(names)` with `name != MAKE_PATH and name.casefold() in _SHADOWING_MAKEFILES`.
   - `check_make_contract(doc, makefile)`: keep the `Makefile not found` early return unchanged; after it compute
     `extra = _extra_makefiles(makefile.parent)` and prepend `extra` to both existing return paths (scan problems,
     or missing targets).
   - Listing compares stored names, so on a case-insensitive filesystem `Makefile` is never mistaken for `makefile`,
     and a lone stored `makefile` is reported (spec edge case, Q3).
2. **Parse once (AC-4)**, `contract.py`:
   - `load_service(path: Path) -> tuple[Any, list[Violation]]`: the current body of `validate_service`, returning
     `(doc, violations)` (on a YAML error: `(None, errors)`).
   - `validate_service(path)` returns `load_service(path)[1]`. `_load_yaml` stays (profiles.py, test_profiles.py).
   - `conformance.check_example`: `doc, violations = contract.load_service(path)`; the second parse
     (`contract._load_yaml`) is removed.
3. **`-f Makefile` (AC-2)**, `conformance._run_make_verify`: argv
   `[make, "--no-print-directory", "-C", str(directory), "-f", contract.MAKE_PATH, "verify", f"IDP_PROFILE_DIR={profile_dir}"]`.
   Popen call, env stripping, `start_new_session=True`, timeout and `killpg` untouched.
4. **Confinement (AC-3)**, `conformance.py` + `cli.py`:
   - Helper `_outside(directory: Path, root: Path) -> bool`: true if `directory.is_symlink()`; else
     `directory.resolve(strict=True).is_relative_to(root.resolve(strict=True))` negated; `OSError`/`RuntimeError`
     from resolving -> true (fail closed).
   - `check_example(directory: Path, make: str, root: Path) -> Result`: first step
     `if _outside(directory, root): return Result(directory, ok=False, reason="outside examples directory")`; then
     load/validate, profile, make as today.
   - `cli._cmd_conformance`: `conformance.check_example(example, make, root)`. `find_examples` unchanged.
5. **Negative fixture (AC-1, ticket test approach)**: `tests/conformance/fixtures/gnumakefile-bypass/` with
   `idp.yaml` (valid, `metadata.name: gnumakefile-bypass`, copied from `missing-target/idp.yaml` with the name
   changed), `Makefile` (all required targets; `verify: ; @echo "Makefile verify must not pass"; exit 1`-style
   recipe, header comment explaining the fixture) and `GNUmakefile` (header comment; `verify:` with recipe `@true`
   and the other required targets as `@true`). Before the fix, conformance prints `PASS` for it (make picks the
   `GNUmakefile`); after it, `FAIL ... idp validate: 1 violation(s)` naming `GNUmakefile`.
6. **Docs**: service-contract.md, onboarding.md, CHANGELOG (see Changes).

### Tests (all new tests tagged `@pytest.mark.ac("IDP-22:AC-n")`)
`packages/idp-gate/tests/test_contract.py` (reuse `_write_idp`, `_write_makefile`, `_run`, `ALL_TARGETS`):
- `test_extra_gnumakefile_or_makefile_beside_valid_makefile_is_a_violation` (AC-1), parametrized `GNUmakefile` /
  `makefile`. Setup by filesystem: a small helper `_case_sensitive(tmp_path)` writes `probe` and checks whether
  `PROBE` exists. Case-sensitive: write the valid `Makefile` and the extra file. Case-insensitive and extra is
  `makefile`: write the valid content, then rename `Makefile` -> `makefile` (stored name lowercase; it is still what
  `Makefile` opens). Assert exit 1 and exact stdout
  `idp.yaml: <name>: GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it\n`.
- `test_extra_makefile_names_match_case_insensitively` (AC-1): with a valid `Makefile`, `gnumakefile` and a
  directory named `GNUmakefile` are each reported by stored name (sorted); `Makefile.bak`, `GNUmakefile.orig`,
  `common.mk` are not. Spellings that collide with `Makefile` on a case-insensitive filesystem (`MAKEFILE`) are only
  exercised when `_case_sensitive` is true; a direct `contract._extra_makefiles` unit check with a monkeypatched
  `contract.os.listdir` returning `["Makefile", "MAKEFILE", "MakeFile"]` covers them on every platform.
- `test_extra_makefile_check_fails_closed_when_directory_cannot_be_listed` (AC-1): monkeypatch
  `contract.os.listdir` to raise `PermissionError`; one violation `Makefile: cannot list the service directory`.
- `test_extra_makefile_violation_in_json_output` (AC-1): `--json` lists `{"path": "GNUmakefile", ...}` first, then
  a missing-target violation from the same `Makefile` (ordering rule).
- Existing `test_missing_makefile_is_single_violation` and `test_gnumakefile_is_not_recognised` (IDP-17 AC-6) pass
  unchanged.

`packages/idp-gate/tests/test_conformance.py` (reuse `_write_example`, `_doc`, `_run`, `needs_make`):
- `test_make_verify_is_invoked_with_f_makefile` (AC-2): fake `Popen` as in the timeout test; returncode 0;
  argv equals `[make, "--no-print-directory", "-C", "examples/ok", "-f", "Makefile", "verify", "IDP_PROFILE_DIR=..."]`
  (the last element checked by prefix/suffix) and `start_new_session is True`.
- `test_make_verify_ignores_gnumakefile_and_makefile` (AC-2, `needs_make`): directory with a `Makefile` whose
  `verify` exits 3 and a `GNUmakefile` with `verify: ; @true` (and `makefile` with `@true` on case-sensitive
  filesystems only); `conformance._run_make_verify(dir, make, profile_dir)` returns
  `FAIL ...: make verify exited 2`. Called directly because `check_example` would stop at AC-1.
- `test_conformance_fails_symlinked_example_without_running_make` (AC-3, `needs_make`): `examples/real` (valid,
  default `verify`, PASS), `examples/linked -> <tmp>/outside/svc` (valid example whose `verify` touches `make-ran`)
  and `examples/alias -> real` (relative link). Exact stdout `FAIL examples/alias: outside examples directory\nFAIL
  examples/linked: outside examples directory\nPASS examples/real\nconformance: 1 passed, 2 failed\n`; exit 1; no
  `make-ran` in `<tmp>/outside/svc`.
- `test_conformance_fails_example_resolving_outside_dir` (AC-3): a real directory `examples/odd`; monkeypatch
  `Path.resolve` so that only that entry resolves to `<tmp>/elsewhere/odd` (others delegate to the original); and a
  second case where its resolution raises `RuntimeError`. Both report `outside examples directory`; make not run
  (fake `Popen` asserting it is never called).
- `test_conformance_accepts_real_examples_under_symlinked_dir` (AC-3, `needs_make`): `linkdir -> examples`; running
  `conformance linkdir` prints `PASS linkdir/real`.
- `test_check_example_parses_idp_yaml_once_for_validation_and_profile` (AC-4): wrap `contract._load_yaml` (record
  paths, call the original), wrap `profiles.resolve` (record names, call the original), stub
  `conformance._run_make_verify` to return `Result(directory, ok=True)`. `check_example(dir, make, root)` is PASS,
  `idp.yaml` parsed exactly once, `profiles.resolve` called once with `python-uv`.
- `test_conformance_module_uses_no_private_contract_members` (AC-4): `ast.parse` of
  `inspect.getsourcefile(conformance)`; no `ast.Attribute` with `value` `Name(id="contract")` and `attr` starting
  with `_`.
- Existing `test_conformance_reports_make_timeout` (IDP-19 AC-2): update the argv assertion to
  `argv[1:7] == ["--no-print-directory", "-C", "examples/slow", "-f", "Makefile", "verify"]` and `argv[7]` for
  `IDP_PROFILE_DIR=` (spec Q7). All other assertions unchanged.

`tests/conformance/test_examples.py`:
- `test_conformance_fails_example_with_gnumakefile_bypass` (AC-1, `needs_make`): copy `minimal-service` and
  `FIXTURES / "gnumakefile-bypass"` into `tmp_path/examples` (existing `_copy_into`); exact stdout
  `PASS examples/minimal-service\nFAIL examples/gnumakefile-bypass: idp validate: 1 violation(s)\n    GNUmakefile:
  GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it\nconformance: 1
  passed, 1 failed\n`; exit 1.

## Changes
| File | Change |
|------|--------|
| packages/idp-gate/src/idp_gate/contract.py | `_SHADOWING_MAKEFILES`, `_extra_makefiles`; `check_make_contract` prepends extra-file violations when `Makefile` exists; new public `load_service`; `validate_service` delegates to it. (AC-1, AC-4) |
| packages/idp-gate/src/idp_gate/conformance.py | `_outside`; `check_example(directory, make, root)` fails `outside examples directory` first, then uses `contract.load_service` (no `_load_yaml`); `_run_make_verify` argv gains `-f Makefile`. Module docstring mentions IDP-22. (AC-2, AC-3, AC-4) |
| packages/idp-gate/src/idp_gate/cli.py | `_cmd_conformance` passes `root` to `check_example`. (AC-3) |
| packages/idp-gate/tests/test_contract.py | Four new AC-1 tests and the `_case_sensitive` helper. (AC-1) |
| packages/idp-gate/tests/test_conformance.py | Seven new tests (AC-2, AC-3, AC-4); argv assertion of `test_conformance_reports_make_timeout` updated. |
| tests/conformance/fixtures/gnumakefile-bypass/{idp.yaml,Makefile,GNUmakefile} | New negative fixture. (AC-1) |
| tests/conformance/test_examples.py | `test_conformance_fails_example_with_gnumakefile_bypass`. (AC-1) |
| docs/platform/service-contract.md | "How `idp validate` checks it": replace "(`makefile` and `GNUmakefile` are not recognised)" with the extra-file rule (case-insensitive names other than exactly `Makefile`, only when `Makefile` exists, one violation per entry with `path` = entry name, message text, `cannot list the service directory`); mention it in the check order and in the `--json` `path` description; one example line. (AC-1, DoD) |
| docs/platform/onboarding.md | Conformance paragraph: make runs as `make -f Makefile verify`; a symlinked example entry, or one resolving outside DIR, is reported `FAIL <x>: outside examples directory` without running make. (AC-2, AC-3) |
| CHANGELOG.md | Under `[Unreleased]` / `### Changed`: `- IDP-22: idp validate reports a GNUmakefile/makefile (any case) beside Makefile as a violation (GNU make would read it instead of the validated Makefile); idp conformance runs make -f Makefile, fails symlinked or out-of-DIR example entries without running make, and parses idp.yaml once.` (DoD) |

Unchanged: root `Makefile`, root `pyproject.toml`, `.github/**`, `profiles.py`, `examples/minimal-service/**`,
`find_examples`, `Result`, the CLI output format and exit codes.

## Interfaces and data
- `idp validate` (text and `--json`): new violation kind, `path` = extra entry name (e.g. `GNUmakefile`), and
  `Makefile: cannot list the service directory`. Services without such entries see no change. Tenants with a stray
  `GNUmakefile`/`makefile` now fail validation (intended).
- `idp conformance`: new result reason `outside examples directory`; make argv gains `-f Makefile`.
- Python API: new `contract.load_service(path) -> tuple[Any, list[Violation]]`; `conformance.check_example` gains a
  required `root: Path` parameter (only caller: `cli._cmd_conformance`). `validate_service` signature unchanged.
- No schema, dependency or config change.

## Telemetry
None (CLI-only, no service). Operator signals are the new violation lines and the `FAIL <x>: outside examples
directory` result line.

## Risks, rollout and rollback
- Risk: a tenant legitimately keeps a `GNUmakefile` that includes `Makefile` (a known GNU make pattern). Detection:
  `idp validate` fails with the new violation naming the file. Mitigation: documented remedy (move the content into
  `Makefile`); the contract requires a single top-level `Makefile`.
- Risk: case-insensitive matching flags a harmless `MAKEFILE`-style name on Linux (spec Q2). Mitigation: rename.
- Risk: tests behave differently on macOS and Linux. Mitigation: `_case_sensitive(tmp_path)` setup branches and a
  `listdir`-monkeypatched unit check that covers all spellings on both; no committed case-colliding fixture.
- Risk: `-f Makefile` changes behaviour for an example relying on make's default makefile search. Detection: the
  IDP-19 conformance test over `examples/` (`minimal-service` has only `Makefile`). None expected.
- Risk: monkeypatching `Path.resolve` in the AC-3 defence-in-depth test leaks into other tests. Mitigation:
  `monkeypatch` fixture scope (restored after the test), delegate to the original for every other path.
- Rollout: lands with the PR; CI runs `make verify` (includes `make conformance`). No migration.
- Rollback: revert the PR; no data or config to undo.
