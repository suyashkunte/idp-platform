---
ticket: IDP-22
status: DRAFT        # DRAFT | APPROVED | IMPLEMENTED
risk: low
mode: guided
---

# IDP-22: idp validate/conformance: close Makefile contract-check bypasses

## Context
Follow-up from the IDP-19 review (PR #7). `idp validate` (IDP-17) checks only the file named `Makefile` beside
`idp.yaml`, but GNU make reads `GNUmakefile`, then `makefile`, then `Makefile` and uses the first one it finds. So a
service can pass the contract check with a valid `Makefile` while `make verify` runs a `GNUmakefile` whose `verify` is
`@true`. Separately, `idp conformance` (IDP-19) discovers `examples/<x>` with `Path.is_dir()`, which follows symlinks,
so a symlinked example directory can point the runner (and make) outside `examples/`. Parent epic IDP-16; depends on
IDP-19 (Done).

Facts checked in the repository (2026-10-10, branch `feature/IDP-22-makefile-contract-bypasses`):
- `packages/idp-gate/src/idp_gate/contract.py`: `check_make_contract(doc, makefile)` returns the single violation
  `Makefile not found` when `makefile.is_file()` is false, else scans it (`makefile_targets`). Nothing looks at other
  entries of the service directory. `validate_service(path)` parses `idp.yaml` with the private `_load_yaml`.
- `packages/idp-gate/src/idp_gate/conformance.py`: `find_examples(root)` keeps non-dot entries with `p.is_dir()` and
  `(p / "idp.yaml").is_file()` (both follow symlinks). `check_example(directory, make)` calls
  `contract.validate_service(path)` and then parses `idp.yaml` a second time through `contract._load_yaml(path)` for
  profile resolution. `_run_make_verify` runs
  `[make, "--no-print-directory", "-C", <dir>, "verify", "IDP_PROFILE_DIR=<dir>"]` (no `-f`) with
  `Popen(start_new_session=True)` and `os.killpg` on timeout.
- `packages/idp-gate/src/idp_gate/cli.py` `_cmd_conformance` prints `"\n".join(result.lines())` per example; the
  example is shown as the path built from DIR, e.g. `PASS examples/minimal-service`, `FAIL examples/bad: ...`.
- Existing tests that pin current behaviour: `test_contract.py::test_missing_makefile_is_single_violation` and
  `::test_gnumakefile_is_not_recognised` (IDP-17 AC-6: only `GNUmakefile`, no `Makefile` -> exactly
  `Makefile: Makefile not found`); `test_conformance.py::test_conformance_reports_make_timeout` (IDP-19 AC-2) asserts
  `argv[1:5] == ["--no-print-directory", "-C", "examples/slow", "verify"]` and `argv[5]` starts with `IDP_PROFILE_DIR=`.
- `profiles.py` also calls `contract._load_yaml` (profile.yaml); `test_profiles.py` monkeypatches it. Not touched here.
- `examples/minimal-service/` contains only `Makefile` (no `GNUmakefile`/`makefile`) and is a real directory.
- The service-contract doc is `docs/platform/service-contract.md` (repository root `docs/`, not under
  `packages/idp-gate/` as the ticket's Interfaces line says); it currently states "`makefile` and `GNUmakefile` are not
  recognised". `idp conformance` is described in `docs/platform/onboarding.md`.
- Negative conformance fixtures live in `tests/conformance/fixtures/<name>/` and are used by
  `tests/conformance/test_examples.py`.

## Requirements
- **AC-1** Given a service directory containing a valid `Makefile` and also a `GNUmakefile` or `makefile`, when I run `idp validate`, then it exits 1 and reports a violation naming the extra file.
  - "Extra file": a directory entry, found by listing the service directory (the directory of the validated
    `idp.yaml`) and comparing the stored entry names, not by `Path.exists()`/`is_file()` (which would match
    `Makefile` itself on a case-insensitive filesystem). An entry is extra when its name is not exactly `Makefile` and
    its name compared case-insensitively (`str.casefold()`) equals `gnumakefile` or `makefile`. So `GNUmakefile`,
    `makefile`, and on any filesystem also `gnumakefile`, `MAKEFILE`, `MakeFile` are extra; `Makefile.bak`,
    `GNUmakefile.orig`, `common.mk` are not. The entry type does not matter (file, directory, symlink, dangling
    symlink). ASSUMPTION A1, see Q2.
  - Each extra entry gives one violation with `path` = the entry name as stored (e.g. `GNUmakefile`) and message
    `GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it`. Text output:
    `idp.yaml: GNUmakefile: GNU make reads this file before Makefile, but only Makefile is validated; remove or rename it`.
    `--json`: `{"path": "GNUmakefile", "message": "..."}`. ASSUMPTION A2, see Q4.
  - Extra-file violations come first among the Make violations, sorted by entry name, followed by whatever the
    existing Makefile scan reports (read/confinement problems, or missing targets). They are reported even if the
    `Makefile` itself is otherwise valid (that is the AC) and also if it has other problems.
  - The check runs only when the Makefile check runs today (the YAML parsed into a mapping) and only when `Makefile`
    is present (`(dir / "Makefile").is_file()`). With no `Makefile`, the result stays the single IDP-17 AC-6 violation
    `Makefile not found`. ASSUMPTION A3, see Q3.
  - If the service directory cannot be listed (`OSError`), the check fails closed with one violation
    `Makefile: cannot list the service directory` (in place of the extra-file violations).
  - Exit code 1 comes from the existing rule (any violation -> 1); no CLI change.
  - Verified with `tmp_path` unit tests in `test_contract.py` and end to end with the negative conformance fixture
    `tests/conformance/fixtures/gnumakefile-bypass/` (valid `idp.yaml`, valid `Makefile` whose `verify` fails, and a
    `GNUmakefile` whose `verify` is `@true`): `idp conformance` reports it `FAIL ... idp validate: 1 violation(s)`
    naming `GNUmakefile` instead of `PASS`.
- **AC-2** Given `idp conformance` runs `make verify` for an example, then make is invoked with `-f Makefile`, so only the validated file is read.
  - argv becomes `[make, "--no-print-directory", "-C", <dir>, "-f", "Makefile", "verify", "IDP_PROFILE_DIR=<dir>"]`.
    `-f Makefile` is relative: GNU make processes `-C` before reading makefiles, so it names `<dir>/Makefile`, the
    file `idp validate` checked (`contract.MAKE_PATH`).
  - Everything else in `_run_make_verify` is unchanged: list-form argv, no shell, stripped make variables
    (`MAKEFLAGS`, `GNUMAKEFLAGS`, `MAKELEVEL`, `MFLAGS`, `MAKEFILES`), `Popen(start_new_session=True)`,
    `communicate(timeout=MAKE_TIMEOUT_S)` and `os.killpg(proc.pid, SIGKILL)` on timeout.
  - "Only the validated file is read" refers to the top-level makefile choice. Files the `Makefile` itself `include`s
    are read by make as before (make include-following is out of scope; `idp validate` already confines and scans
    literal includes).
  - Verified by an argv test (fake `Popen`, no make) and by a real-make test calling `_run_make_verify` on a
    directory whose `Makefile` `verify` exits 3 and whose `GNUmakefile` `verify` is `@true`: the result is
    `FAIL ...: make verify exited 2` (make never reads the `GNUmakefile`).
  - The IDP-19 test `test_conformance_reports_make_timeout` asserts the old argv slice; it is updated to the new argv
    (same intent, stronger assertion). ASSUMPTION A4, see Q7.
- **AC-3** (edge) Given `examples/<x>` is a symlink, or an `examples/<x>` whose resolved path is outside DIR, when I run `idp conformance`, then that entry is reported `FAIL <x>: outside examples directory` and make is not run for it.
  - The ticket writes the edge marker after the bold id; it stays outside the bold so `idp spec-trace` (regex
    `- **AC-n**`) parses it. Meaning unchanged.
  - `<x>` is shown the same way as on every other result line: the example path as built from DIR, e.g.
    `FAIL examples/linked: outside examples directory` (no detail lines). The reason text is literally
    `outside examples directory` whatever DIR is called. ASSUMPTION A5, see Q1.
  - Which entries: discovery (`find_examples`) is unchanged, so the check applies to every entry that is listed as an
    example today (non-dot, a directory after following links, containing `idp.yaml`). For each, before anything
    else: if `entry.is_symlink()`, or `entry.resolve(strict=True)` is not inside `DIR.resolve(strict=True)`, or
    resolving raises `OSError`/`RuntimeError`, the result is `FAIL <x>: outside examples directory`. A symlink is
    reported even when its target is inside DIR (for example `examples/alias -> minimal-service`). ASSUMPTION A6,
    see Q5 and Q6.
  - For such an entry neither `idp validate` nor profile resolution nor make runs: `idp.yaml` behind the link is not
    read. It counts as failed in the summary and makes the exit code 1.
  - DIR itself may be a symlink (for example `examples -> ../shared/examples`): entries are compared with the
    resolved DIR, so real subdirectories still pass.
  - The non-symlink "resolved outside DIR" branch is defence in depth (for example a mount point or an entry replaced
    between listing and checking); it is tested by monkeypatching the resolution of one entry.
- **AC-4** Given a valid example, then `idp.yaml` is parsed once and the same document is validated and used for profile resolution (no private `contract._load_yaml` call from `conformance.py`).
  - New public `contract.load_service(path) -> tuple[Any, list[Violation]]`: parses `idp.yaml` once and returns the
    parsed document together with the same violations `validate_service(path)` returns today (schema, then Make
    contract, including AC-1). `validate_service(path)` becomes `load_service(path)[1]`, so `idp validate` output is
    unchanged. ASSUMPTION A7, see Q8.
  - `conformance.check_example` calls `contract.load_service(path)` once; if there are violations it fails as today,
    otherwise it resolves `doc["spec"]["build"]["profile"]` from that same document.
  - "No private call": `conformance.py` contains no attribute access to a `contract` member whose name starts with
    `_` (checked with `ast` on the module source).
  - Verified by a test that wraps `contract._load_yaml` to count parses of `idp.yaml` (exactly 1 for a valid example)
    and records the profile name passed to `profiles.resolve` (equal to the one in the parsed document), with
    `_run_make_verify` stubbed (no make needed), plus the `ast` test.

## Edge cases and assumptions
- Case-insensitive filesystems (macOS APFS default): `Makefile` and `makefile` cannot both exist. A directory holding
  only `makefile` (stored lowercase) has `Path("Makefile").is_file()` true there, so validation reads it as
  `Makefile` and AC-1 reports `makefile` as extra (exit 1). On a case-sensitive filesystem (Linux CI) the same
  directory gives `Makefile not found` (exit 1). Both fail; the message differs. Accepted (see Q3).
- `Makefile` is a symlink to a `GNUmakefile` in the same directory: the `GNUmakefile` entry is still reported
  (fail closed; the contract file must be named `Makefile` and be the only candidate).
- An extra entry that is a directory or a dangling symlink is reported too (make would try to read it, or the next
  checkout may fill it).
- Many directory entries: the listing reads only names (`os.listdir`), O(n), no file is opened; no new cap.
- `idp validate path/to/service.yaml`: the directory listed is `path/to/` (same rule as the Makefile, IDP-17 A1).
- A symlinked `idp.yaml` or `Makefile` inside a real example directory is not an AC-3 case; `Makefile` confinement is
  already enforced by `idp validate` (`Makefile resolves outside the service directory`). A symlinked `idp.yaml` is
  out of scope here (see Out of scope).
- Symlinks in DIR that are not discovered as examples (dangling, pointing to a file, or to a directory without
  `idp.yaml`) stay ignored, as today (see Q5).
- TOCTOU: an entry swapped for a symlink after the check is not prevented (examples/ is platform-owned and reviewed
  like code; sandboxing is IDP-23).
- ASSUMPTION A1: case-insensitive matching of extra names on every platform (portable result; a repository checked
  out on macOS would otherwise be bypassable with `GNUMakefile`-style spellings).
- ASSUMPTION A2: violation `path` is the extra entry name; message as in AC-1.
- ASSUMPTION A3: extra-file check only when `Makefile` is present, keeping IDP-17 AC-6 and its two tests unchanged.
- ASSUMPTION A4: updating the IDP-19 timeout test's argv assertion in place is acceptable (its `IDP-19:AC-2` tag is
  kept; a separate new test carries `IDP-22:AC-2`).
- ASSUMPTION A5: `<x>` in AC-3 means the displayed example path (`examples/<x>` when DIR is `examples`).
- ASSUMPTION A6: every symlinked example entry fails, including links to another example inside DIR.
- ASSUMPTION A7: the new public API name is `contract.load_service`; `contract._load_yaml` stays (used by
  `profiles.py` and monkeypatched in `test_profiles.py`).
- ASSUMPTION A8: docs to update are `docs/platform/service-contract.md` (as the ticket says, at its real path) and one
  sentence in `docs/platform/onboarding.md` (conformance behaviour); CHANGELOG entry under `[Unreleased]` /
  `### Changed`.

## Non-functional requirements
- No new dependencies: stdlib only (`os.listdir`, `pathlib`, `ast` in tests). `packages/idp-gate/pyproject.toml` and
  `uv.lock` unchanged.
- `examples/minimal-service` still passes: `test_platform_examples_pass_conformance_within_60_seconds` and
  `test_minimal_service_passes_idp_validate_and_make_verify` (IDP-19) stay green unchanged; `make verify` (which runs
  `make conformance`) is green locally and in CI.
- The conformance runner keeps `Popen(start_new_session=True)` + `os.killpg` on timeout; the IDP-19 timeout and
  child-kill tests stay green.
- `idp validate` output for services without extra makefiles is byte-for-byte unchanged (existing IDP-17 tests pass
  unchanged); the IDP-17 AC-6 tests pass unchanged.
- Tests are deterministic on case-sensitive (Linux CI) and case-insensitive (macOS) filesystems: tests that need two
  spellings of `makefile` detect the filesystem's case sensitivity in `tmp_path` and build the matching setup; no
  committed fixture contains two names that differ only in case.
- Protected paths unchanged: root `Makefile`, root `pyproject.toml`, `.github/**`, `.pre-commit-config.yaml`,
  `infra/**`, plugin hooks, `.claude-plugin/**`. No human task needed.
- Quality bars unchanged: mypy strict, ruff, bandit, coverage >= 85 %, diff-cover >= 80 %; `idp spec-trace IDP-22`
  green.

## Out of scope
- Sandboxing make / an environment allow-list for `idp conformance` (IDP-23).
- Changes to make include-following (what `include` lines in `Makefile` pull in at run time).
- Symlinked `idp.yaml` inside a real example directory; `profiles.py`'s use of `contract._load_yaml`.
- Preventing TOCTOU swaps of example entries; Windows junctions.
- Detecting makefiles selected by `MAKEFILES` or `-f` in tenant CI (the runner already strips `MAKEFILES`).

## Open questions
- Q1: AC-3 says `FAIL <x>: outside examples directory`. Every other result line shows the path built from DIR
  (`FAIL examples/bad: ...`). Proposed: same display, so the line is `FAIL examples/<x>: outside examples directory`
  (A5). Alternative: bare entry name `FAIL <x>: ...`, which would be the only line formatted that way.
- Q2: Match extra names case-insensitively on all platforms (`gnumakefile`, `MAKEFILE`, `MakeFile` are also flagged,
  even on Linux where GNU make would not read them)? Proposed: yes; the same tree gives the same result on macOS and
  Linux, and false positives are trivially fixed by renaming (A1). Alternative: exact names `GNUmakefile` and
  `makefile` only, which leaves `GNUMakefile` (read by make on macOS) undetected.
- Q3: Should extra files also be reported when there is no `Makefile`? Proposed: no; keep IDP-17 AC-6 ("single
  violation `Makefile not found`") and its tests unchanged (A3). Consequence: on macOS a lone `makefile` is reported
  as extra, on Linux as `Makefile not found`; both exit 1.
- Q4: Violation format. Proposed: `path` = extra entry name, message `GNU make reads this file before Makefile, but
  only Makefile is validated; remove or rename it` (A2). Alternative: `path` = `Makefile` with the name in the
  message, matching "Make violations use `Makefile`" in today's doc.
- Q5: Symlinks in DIR that today are not discovered (dangling, to a file, to a directory without `idp.yaml`): keep
  ignoring them? Proposed: yes, discovery unchanged; AC-3 applies to entries that would be run. Alternative: report
  every non-dot symlink in DIR as `outside examples directory`.
- Q6: A symlink whose target is another directory inside DIR (alias of a real example): FAIL too? Proposed: yes, the
  AC says "is a symlink" (A6); it also avoids running the same example twice.
- Q7: The IDP-19 test `test_conformance_reports_make_timeout` must change its `argv[1:5]` / `argv[5]` assertions to
  the new argv. Proposed: update it in place (keep its `IDP-19:AC-2` tag) and add a separate `IDP-22:AC-2` argv test
  (A4).
- Q8: Public API name for "parse once, return doc and violations". Proposed: `contract.load_service(path)`, with
  `validate_service` delegating to it (A7). Alternative: make `_load_yaml` public and add
  `validate_service_document(doc, directory)`.
- Q9: Docs placement. The ticket names `service-contract.md` "under packages/idp-gate/", but it lives at
  `docs/platform/service-contract.md`. Proposed: edit that file, plus one sentence in `docs/platform/onboarding.md`
  for the conformance changes (`-f Makefile`, symlinked entries FAIL) (A8).
- Q10: Should `profiles.py`'s own `contract._load_yaml` call move to the new public API in this ticket? Proposed: no
  (not in the AC, and `test_profiles.py` monkeypatches `_load_yaml`); a follow-up if wanted.

## Traceability
| AC | Planned tests |
|----|---------------|
| AC-1 | packages/idp-gate/tests/test_contract.py::test_extra_gnumakefile_or_makefile_beside_valid_makefile_is_a_violation, packages/idp-gate/tests/test_contract.py::test_extra_makefile_names_match_case_insensitively, packages/idp-gate/tests/test_contract.py::test_extra_makefile_check_fails_closed_when_directory_cannot_be_listed, packages/idp-gate/tests/test_contract.py::test_extra_makefile_violation_in_json_output, tests/conformance/test_examples.py::test_conformance_fails_example_with_gnumakefile_bypass |
| AC-2 | packages/idp-gate/tests/test_conformance.py::test_make_verify_is_invoked_with_f_makefile, packages/idp-gate/tests/test_conformance.py::test_make_verify_ignores_gnumakefile_and_makefile |
| AC-3 | packages/idp-gate/tests/test_conformance.py::test_conformance_fails_symlinked_example_without_running_make, packages/idp-gate/tests/test_conformance.py::test_conformance_fails_example_resolving_outside_dir, packages/idp-gate/tests/test_conformance.py::test_conformance_accepts_real_examples_under_symlinked_dir |
| AC-4 | packages/idp-gate/tests/test_conformance.py::test_check_example_parses_idp_yaml_once_for_validation_and_profile, packages/idp-gate/tests/test_conformance.py::test_conformance_module_uses_no_private_contract_members |
