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

## Amendment (2026-10-10, after review loop 1): AC-5, AC-6 and test hardening
T1-T6 are done (PR #11). The additions below are agent work only; no protected path.

### AC-5: pin the validated makefiles with assume-old
- `contract.py`:
  - `MakefileScan` gains `include_words: tuple[str, ...] = ()` (default keeps existing constructions valid).
  - `_Scanner` gains `spellings: list[str]` and `seen_spellings: set[str]`. In `queue(word)`, before the existing
    normpath dedup: if `word` is a new spelling, then if `len(seen_spellings) >= MAX_INCLUDE_WORDS` call
    `stop(f"too many include words (limit {MAX_INCLUDE_WORDS})")` and return, else record it. The existing
    normpath dedup and cap stay as they are, so every file is still read once and existing messages are unchanged.
    Words for files not on disk are recorded too (they are queued today; `_locate` skips them later).
  - `makefile_targets` returns `MakefileScan(frozenset(targets), tuple(problems), tuple(spellings))`.
- `conformance.py`:
  - `MAX_ASSUME_OLD_BYTES = 64 * 1024`.
  - `_assume_old(words: tuple[str, ...]) -> list[str] | None`: names = `Makefile`, then each word, plus the word
    with leading `./` segments removed when it starts with `./` and the result is non-empty and different; dedup
    keeping order; returns `[f"--assume-old={n}" for n in names]`, or None when the summed UTF-8 length of those
    arguments exceeds `MAX_ASSUME_OLD_BYTES`.
  - `check_example`: after `load_service` reports no violations and the profile resolves:
    `scan = contract.makefile_targets(directory / contract.MAKE_PATH)`; if `scan.violations`, fail
    `idp validate: <n> violation(s)` with them as details (files changed between the scans); if `_assume_old`
    returns None, fail `include words exceed the make argument limit`; otherwise
    `_run_make_verify(directory, make, profile_dir, assume_old)`.
  - `_run_make_verify(directory, make, profile_dir, assume_old: list[str])`: argv
    `[make, "--no-print-directory", "-C", dir, "-f", "Makefile", *assume_old, "verify", "IDP_PROFILE_DIR=..."]`.
    Popen, env stripping, `start_new_session=True`, timeout and `killpg` untouched.
  - Module docstring: mention the assume-old pinning and the dynamic-include residual risk.
- Existing tests to adapt (assertions stay at least as strict):
  - `test_conformance_reports_make_timeout` (IDP-19): argv slice becomes
    `["--no-print-directory", "-C", "examples/slow", "-f", "Makefile", "--assume-old=Makefile", "verify"]`.
  - `test_make_verify_is_invoked_with_f_makefile` (IDP-22 AC-2): expected argv gains `--assume-old=Makefile`.
  - `test_make_verify_ignores_gnumakefile_and_makefile` (AC-2): passes `["--assume-old=Makefile"]` to the new
    parameter.
  - `test_check_example_parses_idp_yaml_once_for_validation_and_profile` (AC-4): `stub_make` takes the fourth
    argument; the assertion that `idp.yaml` is parsed once is unchanged (the extra scan reads only makefiles).

New AC-5 tests:
- `test_makefile_scan_records_literal_include_words_as_written` (test_contract.py): a Makefile with
  `include common.mk ./common.mk`, `-include gen.mk` (missing), `sinclude sub/x.mk`, `include $(V)/d.mk`,
  `include *.mk`, and `common.mk` including `gen.mk` again: `include_words == ("common.mk", "./common.mk", "gen.mk",
  "sub/x.mk")`; `targets`/`violations` as before.
- `test_makefile_scan_caps_recorded_include_spellings` (test_contract.py): 1025 distinct spellings of one file
  (`./a.mk`, `././a.mk`, ...) give the `too many include words (limit 1024)` violation; 1024 do not.
- `test_make_verify_pins_makefile_and_include_words_with_assume_old` (test_conformance.py, fake `Popen`, no make):
  example including `common.mk`, `./gen.mk` and `-x.mk` (a word starting with `-`); argv between `Makefile` and
  `verify` is exactly `--assume-old=Makefile`, `--assume-old=common.mk`, `--assume-old=./gen.mk`,
  `--assume-old=gen.mk`, `--assume-old=-x.mk`.
- `test_conformance_fails_when_include_words_exceed_make_argument_limit`: monkeypatch `MAX_ASSUME_OLD_BYTES` to a
  small value; `FAIL examples/<x>: include words exceed the make argument limit`; fake `Popen` never called.
- `test_conformance_fails_when_makefile_changes_between_scans`: monkeypatch `contract.makefile_targets` so the
  second call (from conformance) returns a scan with one violation; the example fails
  `idp validate: 1 violation(s)` with that detail; make not called.
- `test_make_cannot_remake_validated_makefiles` (`needs_make`, parametrized, run through `idp conformance` so
  validation passes first). The validated `verify` recipe touches `validated-ran`; injected content touches
  `evil-ran` (via a `verify` recipe or `$(shell touch evil-ran)` at parse time). Cases:
  - `self-remake`: `Makefile` has `Makefile: evil.txt` with recipe `cp evil.txt Makefile`; `evil.txt` holds a
    makefile whose `verify` touches `evil-ran`; `os.utime` makes `evil.txt` newer than `Makefile`.
  - `generated-include`: `Makefile` has `-include gen.mk` and `gen.mk:` with a recipe that writes
    `$$(shell touch evil-ran)` into `gen.mk`; `gen.mk` does not exist.
  - `stale-include`: `include common.mk` (existing, benign) and `common.mk: common.src` with recipe
    `cp common.src common.mk`; `common.src` is newer and injects `evil-ran`.
  - `dot-slash`: as `generated-include`, spelled `-include ./gen.mk` with rule `./gen.mk:` (confirms Q15).
  Each: stdout `PASS examples/<x>`, `validated-ran` exists, `evil-ran` does not, `Makefile` and `common.mk` are
  byte-for-byte unchanged, `gen.mk` still absent. Red before the fix (make remakes and restarts). If a case shows
  assume-old does not behave as spec A14 says on 3.81 or 4.x, stop and revise the spec.

### AC-6: unreadable or undecodable idp.yaml
- `contract.load_service`: wrap the `_load_yaml(path)` call in
  `try ... except OSError as exc` -> `return None, [Violation("", f"cannot read: {exc.strerror or exc}")]` and
  `except UnicodeDecodeError as exc` -> `return None, [Violation("", f"cannot read: not valid UTF-8 ({exc.reason}
  at byte {exc.start})")]`. `UnicodeDecodeError` is a `ValueError`, not an `OSError`, so the two handlers do not
  overlap. `_load_yaml` is unchanged (still raises), so `profiles.load` and its IDP-18 test are unaffected.
- `test_unreadable_or_undecodable_idp_yaml_is_a_violation` (test_contract.py, parametrized): (a) `idp.yaml` written
  as bytes `b"name: caf\xe9\n"` -> stdout `idp.yaml: <root>: cannot read: not valid UTF-8 (invalid continuation
  byte at byte 9)` (exact text checked against Python's reason string when implementing; the test asserts the
  full line), exit 1; (b) monkeypatched `contract._load_yaml` raising `PermissionError(13, "Permission denied",
  ...)` -> `idp.yaml: <root>: cannot read: Permission denied`, exit 1; plus `--json` for (b):
  `[{"path": "", "message": "cannot read: Permission denied"}]`.
- `test_conformance_reports_unreadable_idp_yaml_and_continues` (test_conformance.py, fake make on PATH and stubbed
  `_run_make_verify`, or `needs_make`): `examples/a` with non-UTF-8 `idp.yaml`, `examples/b` valid; stdout
  `FAIL examples/a: idp validate: 1 violation(s)`, the indented `<root>: cannot read: ...` detail, then
  `PASS examples/b` and `conformance: 1 passed, 1 failed`; exit 1; no traceback.
- Regression: `test_profiles.py::test_profile_show_unreadable_profile_exits_2` (IDP-18) passes unchanged.

### Test hardening (existing ACs)
- AC-3: `test_conformance_fails_example_resolving_outside_dir` gains a third mode `missing` where the fake
  `resolve` raises `FileNotFoundError` (id `resolve-oserror`); same expected output.
- AC-4: `test_conformance_module_uses_no_private_contract_members` also collects `ast.ImportFrom` nodes where
  (`module == "idp_gate.contract"` and `level == 0`) or (`module == "contract"` and `level >= 1`) and any alias
  `name` starts with `_`. Checked red-first by feeding the predicate a synthetic source string containing both
  forms (refactor the predicate into a small helper the test calls on the real module and on the synthetic text).

### Docs (amendment)
- `docs/platform/service-contract.md`: in "How `idp validate` checks it", an `idp.yaml` that cannot be read or is
  not UTF-8 is a `<root>: cannot read: ...` violation (exit 1). Note that `idp validate` does not reject rules that
  remake `Makefile` or includes (D3); the conformance runner pins them.
- `docs/platform/onboarding.md`: conformance runs `make -f Makefile --assume-old=Makefile --assume-old=<each literal
  include> verify`, so the validated makefiles are never remade; dynamic `$(...)` includes are not pinned (residual
  risk); an unreadable `idp.yaml` fails that example and the run continues.
- `CHANGELOG.md`: extend the IDP-22 line: conformance pins `Makefile` and literal includes with `--assume-old`
  (no self-remake), and an unreadable/undecodable `idp.yaml` is a violation instead of a traceback.

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

| packages/idp-gate/src/idp_gate/contract.py (amendment) | `MakefileScan.include_words`; `_Scanner` records distinct spellings (capped at `MAX_INCLUDE_WORDS`); `load_service` turns `OSError`/`UnicodeDecodeError` into a `<root>: cannot read: ...` violation. (AC-5, AC-6) |
| packages/idp-gate/src/idp_gate/conformance.py (amendment) | `MAX_ASSUME_OLD_BYTES`, `_assume_old`; `check_example` re-scans the Makefile, fails on scan violations or the argument budget; `_run_make_verify` takes and passes the `--assume-old=` list; docstring. (AC-5) |
| packages/idp-gate/tests/test_contract.py (amendment) | AC-5 scanner tests, AC-6 test. |
| packages/idp-gate/tests/test_conformance.py (amendment) | AC-5 argv, budget, changed-scan and real-make tests; AC-6 conformance test; argv/stub updates in four existing tests; AC-3 `OSError` case; AC-4 `ImportFrom` check. |
| docs/platform/service-contract.md, docs/platform/onboarding.md, CHANGELOG.md (amendment) | As in "Docs (amendment)". |

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
- Amendment: `MakefileScan` gains `include_words` (defaulted, backwards compatible). `_run_make_verify` gains a
  fourth parameter (private; only caller `check_example`). New conformance result reason
  `include words exceed the make argument limit`. make argv gains `--assume-old=` options. `idp validate` gains the
  `<root>: cannot read: ...` violation where it used to crash.

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
- Amendment risk: assume-old behaves differently across GNU Make versions (3.81 on macOS, 4.x on Linux CI), for
  example for missing files or `./` spellings (spec A14, Q15). Detection: the parametrized real-make test runs in
  both places. Mitigation: stop and revise the spec.
- Amendment risk (residual, accepted): dynamic includes, including `$(IDP_PROFILE_DIR)/defaults.mk`, are not pinned,
  so a rule targeting them can still be remade (spec Q16). Detection: none automatic. Mitigation: examples are
  platform-owned and reviewed; documented in onboarding.md; follow-up with IDP-23.
- Amendment risk: an example that legitimately generates an included makefile now fails (plain `include`) or runs
  without it (`-include`). Detection: conformance FAIL. Mitigation: commit the generated file; `minimal-service` is
  unaffected.
- Amendment risk: the second Makefile scan doubles static parse time per example. Bounded by the existing caps;
  negligible next to `make verify`.
- Rollout: lands with the PR; CI runs `make verify` (includes `make conformance`). No migration.
- Rollback: revert the PR; no data or config to undo.
