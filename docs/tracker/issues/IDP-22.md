---
key: IDP-22
type: Story
status: Done
summary: "idp validate/conformance: close Makefile contract-check bypasses"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T17:02:02.352+0530
updated: 2026-10-10T12:29:39.902+0530
resolved: 2026-10-10T12:29:39.886+0530
links:
  - {type: "relates to", key: IDP-28}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-22
---

# IDP-22: idp validate/conformance: close Makefile contract-check bypasses

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-28](IDP-28.md)

## Description

## Context / why

Follow-up from the IDP-19 review (PR #7). Two ways an example or tenant can pass the contract check while make runs something else:

* GNU make reads `GNUmakefile` or `makefile` before `Makefile`, but only `Makefile` is validated.
* `idp conformance` follows a symlinked example directory out of `examples/`.

## Acceptance criteria

* **AC-1** Given a service directory containing a valid `Makefile` and also a `GNUmakefile` or `makefile`, when I run `idp validate`, then it exits 1 and reports a violation naming the extra file.
* **AC-2** Given `idp conformance` runs `make verify` for an example, then make is invoked with `-f Makefile`, so only the validated file is read.
* **AC-3** (edge) Given `examples/<x>` is a symlink, or an `examples/<x>` whose resolved path is outside DIR, when I run `idp conformance`, then that entry is reported `FAIL <x>: outside examples directory` and make is not run for it.
* **AC-4** Given a valid example, then `idp.yaml` is parsed once and the same document is validated and used for profile resolution (no private `contract._load_yaml` call from `conformance.py`).

## Non-functional criteria

No new dependencies; `examples/minimal-service` still passes.

## Out of scope

Sandboxing / environment allow-list (separate story); changes to make include-following.

## Interfaces / dependencies

Depends on IDP-19 (Done). Touches `idp_gate/contract.py`, `idp_gate/conformance.py`, `docs/platform/service-contract.md`.

## Test approach

Unit tests with tmp_path fixtures for each bypass; a negative fixture with a `GNUmakefile` whose `verify` is `@true`.

## Definition of Done

ACs traced; `make verify` green; `service-contract.md` lists the new violation; CHANGELOG entry.

Labels: repo:idp-platform, component:pipeline, layer:test, risk:low, spec:guided

## Comments (5)

### Suyash Kunte, 2026-10-10T10:49:17.682+0530

**Spec drafted** (guided mode). Branch `feature/IDP-22-makefile-contract-bypasses`, commit 815bc20: `specs/IDP-22/spec.md`, `plan.md`, `tasks.md`.

**Design**

* AC-1: `idp validate` lists the service directory by exact entry name, so a case-insensitive filesystem cannot confuse `Makefile` with `makefile`. It reports one violation per `GNUmakefile`/`makefile` that sits next to `Makefile`.
* AC-2: conformance runs `make --no-print-directory -C <dir> -f Makefile verify …`. The Popen and killpg handling stays as it is.
* AC-3: `check_example(dir, root)` first rejects any entry that is a symlink, resolves outside DIR, or cannot be resolved. It reports `FAIL … outside examples directory` and does not run validate or make.
* AC-4: new public `contract.load_service(path) -> (doc, violations)`. `validate_service` and conformance both use it, so `idp.yaml` is parsed once.
* No new dependencies and no protected-path edits. Tasks T1–T6 are all agent tasks.

**Open questions (proposed default in brackets)**

* Q1: Show the FAIL line as the DIR-relative path `examples/<x>` \[yes\]
* Q2: Match extra names case-insensitively on every platform \[yes\]
* Q3: Report extra files only when `Makefile` exists, so IDP-17 AC-6 is unchanged \[yes\]
* Q4: Use the extra file's name as the violation path \[yes\]
* Q5: Keep ignoring symlinks that are not discovered as examples today \[yes\]
* Q6: Also fail a symlink that points to another example inside DIR \[yes\]
* Q7: Update the IDP-19 timeout test's argv assertion in place \[yes\]
* Q8: Name the API `load_service` \[yes\]
* Q9: Docs go to `docs/platform/service-contract.md` plus the `onboarding.md` sentence \[yes\]
* Q10: Leave the `profiles.py` `_load_yaml` call alone \[yes\]

Waiting for spec approval.

### Suyash Kunte, 2026-10-10T11:15:40.344+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/11

* All 4 ACs are traced to tests (spec-trace OK). `make verify` is green: 337 tests passed, coverage 97.91%, `examples/minimal-service` passes conformance.
* Review loop 1: no BLOCKERs. The one MAJOR (missing docs) is fixed.
* **Decision needed:** security M1. A Makefile can rebuild itself, so `-f Makefile` alone doesn't guarantee that only the validated file runs. Options: add `-o Makefile` in this PR (needs spec re-approval), or handle it in a follow-up ticket.
* Other minors are listed in the PR body.

### Suyash Kunte, 2026-10-10T11:39:49.656+0530

**Spec amended after review loop 1** (commit 7a9d3a2, on PR #11), at the human's request to fix M1 and the other important findings in this PR. **Needs re-approval.**

* **AC-5 (security M1):** `idp conformance` passes `--assume-old=` for `Makefile` and for every literal include word the scan saw, so make can't remake a validated makefile and restart with content that wasn't checked. Dynamic `$(...)` includes remain a documented residual risk (outside this ticket's scope).
* **AC-6 (security M3):** if `idp.yaml` can't be read or isn't valid UTF-8, `idp validate` and `idp conformance` report a violation instead of crashing with a traceback.
* **Test hardening:** a `FileNotFoundError` case for the symlink check (AC-3), and the AST test now also catches `from … import _x` (AC-4).
* **Not changed:** D1 (the test helper copied in two files), D2 (`status: DRAFT`), D3 (no scanner violation for rules that target `Makefile`).
* New tasks T7–T11. New open questions Q11–Q18, defaults in spec.md.

### Suyash Kunte, 2026-10-10T12:01:55.541+0530

**Review loop 2 and spec amendment 2** (commit 3b9db88, PR #11). **Needs re-approval.**

* **Done since the last approval:**

    * T7 (AC-6, unreadable `idp.yaml`), T8 (scanner records include words) and T9 (`--assume-old` in conformance).
    * The IDP-17 cap test was adjusted per the human's decision (D4).
    * `make verify` passes (351 tests). CI passes on make 4.x, and the real-make tests pass on make 3.81.

* **Loop 2 findings:** both reviewers reproduced an AC-5 bypass through include lines the scanner misreads: a continuation (`-include a.mk \` + `gen.mk`) and an escape (`gen\#.mk`).
* **New AC-7 (edge):** `idp validate` and `idp conformance` reject any include line that contains a backslash, and make is not run (fail closed).
* **AC-6 extended:** a deeply nested `idp.yaml` is reported as `cannot parse: nesting too deep` instead of a traceback.
* **Not fixed, follow-up suggested (Q23):**

    * D5: includes built from `$(...)` are not pinned.
    * D6: the second Makefile scan is not compared with the one that was validated.
    * D7: a comment ending in `# \` makes the scanner count targets that make never defines (pre-existing IDP-17).

* New tasks T12–T15 and open questions Q19–Q23, defaults in spec.md.

### Suyash Kunte, 2026-10-10T12:17:08.604+0530

**Amendment 2 implemented.** PR #11 is updated and CI `verify` passes on head a5454d6.

* **Done:** T12 (deeply nested `idp.yaml` is a violation), T13 (typing), T14 (include lines with a backslash are rejected), and the docs and CHANGELOG.
* **Checks:** 360 tests pass, coverage 97.7%, all 7 ACs traced. The real-make tests pass on make 3.81 and 4.x.
* **Security confirmation check:** MJ1, MJ2 and deep nesting are confirmed fixed.
* **New MAJOR, left open:** the scanner and make can disagree about which lines are inside a `define`, because the scanner neither joins `\` continuations nor splits lines the way make does. That lets an include be hidden. Details and a suggested fix are in the PR body.
* **Suggested follow-up (Q23):** one "make include/continuation hardening" ticket covering that MAJOR plus D5 (`$(...)` includes), D6 (single shared scan) and D7 (`# \` comments).
