---
key: IDP-28
type: Story
status: Done
summary: "idp validate/conformance: read Makefiles as make does (logical lines) and pin dynamic includes"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-10T12:27:26.744+0530
updated: 2026-10-20T12:53:25.102+0530
resolved: 2026-10-20T12:52:33.394+0530
links:
  - {type: "relates to", key: IDP-22}
  - {type: "relates to", key: IDP-23}
  - {type: "relates to", key: IDP-29}
  - {type: "relates to", key: IDP-30}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-28
---

# IDP-28: idp validate/conformance: read Makefiles as make does (logical lines) and pin dynamic includes

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-22](IDP-22.md); relates to [IDP-23](IDP-23.md); relates to [IDP-29](IDP-29.md); relates to [IDP-30](IDP-30.md)

## Description

## Context / why

This is the follow-up from the IDP-22 review (PR #11). IDP-22 pins every literal include with `--assume-old` (AC-5) and rejects include lines containing a backslash (AC-7). But the static scanner still reads lines differently from GNU make, so an example can hide an include and make runs content that was never checked:

* **Open security MAJOR:** `_parsed_lines` splits with `str.splitlines()` and doesn't join backslash-newline continuations before it tracks `define`/`endef`.

    * With `X = \` followed by `define Y`, make reads `X = define Y`, but the scanner skips everything after it as a define body. A `-include gen.mk` and the rule that generates it then go unscanned and unpinned.
    * The same happens with separators Python splits on and make doesn't: `\x0b`, `\x0c`, `\x85`, a lone `\r`, U+2028/2029.
    * Reproduced on make 3.81.

* **D5:** include words containing `$` (for example `$(IDP_PROFILE_DIR)/defaults.mk`) are neither scanned nor pinned, so a rule can generate them.
* **D6:** conformance scans the Makefile a second time and pins from that scan, which is never compared with the one that was validated.
* **D7:** a comment ending in `\` continues onto the next line in make, so the scanner counts targets there that make never defines.

## Acceptance criteria

* **AC-1** Given an example whose `Makefile` has `X = \` followed by `define Y`, a `-include gen.mk` line, a rule that generates `gen.mk`, and a later `define Z`/`endef` pair, when I run `idp conformance`, then `gen.mk` is recorded in the scan's include words and pinned with `--assume-old`, make does not create `gen.mk`, and the validated `verify` recipe runs.
* **AC-2** (edge) Given a `Makefile` or scanned include that contains a line separator make does not use (`\r` not followed by `\n`, `\x0b`, `\x0c`, `\x1c`–`\x1e`, `\x85`, U+2028, U+2029), when I run `idp validate`, then it exits 1 with a violation naming that file, and a file with CRLF line endings is still accepted.
* **AC-3** Given a `Makefile` where a comment line ends in `\` and the next line defines `verify:`, when I run `idp validate`, then `verify` is not credited and the output reports `missing required target 'verify'`.
* **AC-4** (edge) Given an example whose Makefile has an include word containing `$` that does not start with exactly `$(IDP_PROFILE_DIR)/`, when I run `idp conformance`, then that example is reported `FAIL <x>: dynamic include '<word>' cannot be pinned` and make is not run. A word starting with `$(IDP_PROFILE_DIR)/` is pinned as `--assume-old=<resolved profile dir>/<rest>`, and `examples/minimal-service` still passes.
* **AC-5** Given a valid example, when I run `idp conformance`, then the Makefile is scanned exactly once, and the `--assume-old` words come from the same scan whose result was validated (no second `makefile_targets` call).

## Non-functional criteria

* No new dependencies.
* Scanning stays linear, with the existing size, file-count, include-word and problem caps unchanged.
* The real-make tests pass on GNU Make 3.81 (macOS) and 4.x (CI).
* `examples/minimal-service` still passes.

## Out of scope

* Replacing static parsing with make's own database (`make -pn` in a sandbox). Record it as an ADR candidate once IDP-23 lands.
* An environment allow-list or sandboxing (IDP-23).
* Tenant CI pipelines that run plain `make verify` without conformance.

## Interfaces / dependencies

* Depends on IDP-22 (PR #11) being merged.
* Touches `idp_gate/contract.py` (`_parsed_lines`, the scanner, the `load_service`/scan result) and `idp_gate/conformance.py`, plus `docs/platform/service-contract.md` and `onboarding.md`.

## Test approach

* Real-make conformance tests for the reviewer's repros: the continuation case, `\x0b`, and `\x85`, all with explicit `os.utime` and no sleeps.
* Unit tests for logical-line parsing: continuations, comment continuations, CRLF, and each rejected separator.
* A conformance test with a fake `makefile_targets` that counts calls, to check there is a single scan.
* A dynamic-include test, checking both the allowed profile prefix and the rejected form.

## Definition of Done

* All ACs traced; `make verify` green.
* `service-contract.md` and `onboarding.md` updated, and the IDP-22 residual-risk notes for D5–D7 and the define/continuation MAJOR removed or adjusted.
* CHANGELOG entry.

Labels: repo:idp-platform, component:pipeline, layer:test, risk:medium, spec:guided

## Comments (3)

### Suyash Kunte, 2026-10-10T22:32:36.929+0530

**Spec drafted (guided mode, awaiting approval)**: branch `feature/IDP-28-makefile-logical-lines`, commit 5016dc3, `specs/IDP-28/{spec,plan,tasks}.md`.

**Design**

* Logical lines: split on `\n` only, drop the `\r` of CRLF, and join lines ending in an odd number of backslashes _before_ comment stripping and define/endef tracking (AC-1, AC-3). IDP-22 AC-7 still holds: a continued include line is still rejected.
* Separators make does not use (lone `\r`, `\x0b`, `\x0c`, `\x1c`–`\x1e`, `\x85`, U+2028/2029) are rejected in `_load_makefile` (AC-2).
* Include words containing `$` go into a new `MakefileScan.dynamic_include_words` field. Conformance pins `$(IDP_PROFILE_DIR)/<literal rest>` as `<profile dir>/<rest>` and fails the rest as "cannot be pinned" (AC-4).
* `load_service` returns `(doc, violations, scan)`, and conformance's second scan is removed (AC-5).

**Tasks:** T1 logical lines → T2 real-make continuation test → T3 separator rejection → T4 single scan → T5 record dynamic words → T6 pin/reject dynamic includes → T7 docs/CHANGELOG/verify. All are agent tasks; none touches a protected path.

**Open questions needing a decision**

* **Q7:** a word that starts with `$(IDP_PROFILE_DIR)/` but whose rest contains `$` or a glob character, or is empty, fails as "cannot be pinned". This narrows AC-4's second sentence.
* **Q16 (new finding):** make and the scanner disagree on `define` nesting. Make only nests on a bare `define` and ignores tab-prefixed lines in a body. The scanner also nests on `override define` and `export define` and on tab lines, so `define A` / `override define B` / `endef` hides every later line (the same kind of bypass as AC-1). Proposed: confirm it with real make in T1, then handle it in a follow-up ticket or an amendment with a new AC.
* Other defaults (Q1–Q6, Q8–Q15, Q17) are proposed in spec.md, including: `$$` counts as dynamic (Q10), NUL bytes are not rejected here (Q15), and the IDP-22 two-scan test is replaced (Q14).

### Suyash Kunte, 2026-10-10T23:41:06.223+0530

**Progress + spec amendment 1 (awaiting re-approval)**

Implemented AC-1..AC-5: T1–T6 are in commits 265eefb…429b6a2. `make verify` is green (411 tests, 100% diff coverage).

Review loop 1 found more ways an example can make GNU make read content the scanner never saw. All were reproduced with make 3.81:

* **Regression from this branch:** a line holding only `\`, followed by `-include` or `endef`, hides an include.
* **Unscanned file read:** `$(IDP_PROFILE_DIR)/../…` reads a file outside the profile directory that nothing scanned.
* **Already on main:** `define#` inside a define body; characters that are whitespace to Python but not to make (`\x1f`, U+00A0, …); `private`/`export define X = 1`; `override define` or a tab-prefixed `define` nested in a body (Q16); and `~` include words.

Following the human's decision, amendment 1 (commit 22c612c) adds **AC-6..AC-14** and supersedes Q2, Q7, Q15 and Q16. AC-1..AC-5 are unchanged. New tasks T8–T14; T7 (docs) runs last.

Follow-ups (not in this ticket): make's default include search path; bounding make output; time-of-check/time-of-use between the scan and the make run (IDP-23); `.RECIPEPREFIX`/`load`/`guile` (Q27); replacing the scanner with `make -pn` (ADR candidate after IDP-23).

Decisions flagged for the reviewer: Q19, Q20, Q22, Q27, the rewrite of the IDP-17 test `test_define_bodies_are_skipped_including_nested_ones`, and the AC-10, AC-11 and AC-12 message texts.

### Suyash Kunte, 2026-10-12T22:03:57.902+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/12

* AC-1..AC-14 implemented and traced (spec approved; amendments 1 and 2 re-approved).
* `make verify` green: 575 tests, coverage 98.23%, diff coverage 100%, minimal-service conformance PASS.
* Real-make tests ran on GNU Make 3.81; key cases were also checked on 4.3 and 4.4.1.
* Two review loops plus a confirmation check; every blocker and major found is fixed.
* Findings left for the reviewer are listed in the PR body: archive syntax `lib(x.mk)`, top-level tab-indented `define`, `_assume_old` slash stripping, make's default include search path, unbounded make output, TOCTOU (IDP-23), and `make -pn` as an ADR candidate. Two follow-up tickets are proposed.
