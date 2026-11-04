---
key: IDP-29
type: Story
status: To Do
summary: "idp validate/conformance: fail closed on archive-syntax includes and top-level tab define; strip pin spelling like make"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T12:53:01.598+0530
updated: 2026-10-20T13:01:59.042+0530
resolved:
links:
  - {type: "relates to", key: IDP-28}
  - {type: "relates to", key: IDP-31}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-29
---

# IDP-29: idp validate/conformance: fail closed on archive-syntax includes and top-level tab define; strip pin spelling like make

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-28](IDP-28.md); relates to [IDP-31](IDP-31.md)

## Description

## Context / why

Follow-up from the IDP-28 review (PR #12). The static Makefile scanner still disagrees with GNU make in three places that were left open:

* **Archive syntax:** `-include lib(x.mk y.mk)`. The scanner splits on blanks and records `lib(x.mk` and `y.mk)`. make's `parse_file_seq` expands archive syntax, so it reads `lib(x.mk)` and `lib(y.mk)`, which nobody scanned. This already happened before IDP-28 and was reproduced on make 3.81: validation passed and an injected recipe ran.
* **Top-level tab-indented** `define` before any rule: make treats a tab line as a directive while no rule has been seen yet, so `\tdefine A` opens a block. The scanner never opens a block on a tab line, so it credits targets inside the body that make never defines. This fails open only for the required-target check, not for include pinning.
* **Pin spelling:** `conformance._assume_old` strips only one leading `./`. For `.//gen.mk` it emits `--assume-old=/gen.mk`, which pins nothing. make strips leading `./` runs (`./`, `.//`, `././`) the way `_LEADING_DOT_SLASH` does. This is harmless on make 3.81 (the include was not remade there) but unverified on 4.x.

## Acceptance criteria

* **AC-1** Given a `Makefile` or scanned include with an include word containing `(` or `)` (for example `-include lib(x.mk y.mk)` or `include a(b).mk`), when I run `idp validate`, then it exits 1 with a violation naming the file and the word, and `idp conformance` reports that example `FAIL <x>: idp validate: 1 violation(s)` without running make.
* **AC-2** (edge) Given a `Makefile` whose first non-blank, non-comment lines are `X = 1`, then a tab-indented `define A`, a body line `verify:` and `endef`, with no other `verify` rule, when I run `idp validate`, then `verify` is not credited and the output reports `missing required target 'verify'` (or a violation naming the file); a tab-indented recipe line containing the word `define` after a rule is still accepted.
* **AC-3** Given an example whose `Makefile` has `-include .//gen.mk` (also `././gen.mk`) and a rule that generates `gen.mk`, when I run `idp conformance`, then make is called with `--assume-old=gen.mk`, no `--assume-old=/gen.mk` argument is passed, make does not create `gen.mk`, and the validated `verify` recipe runs.

## Non-functional criteria

* No new dependencies.
* Scanning stays linear, with the size, file-count, include-word and problem caps unchanged.
* The real-make tests pass on GNU Make 3.81 (macOS) and 4.x (CI).
* `examples/minimal-service` still passes.

## Out of scope

* Replacing static parsing with make's own database (`make -pn` in a sandbox): ADR candidate after IDP-23.
* make's default include search path and bounding make output (separate follow-up).
* `.RECIPEPREFIX`, `load` and `guile` (IDP-28 spec Q27).

## Interfaces / dependencies

* Depends on IDP-28 (merged, 88c2d63).
* Touches `idp_gate/contract.py` (include-word checks, `_parsed_lines` define handling) and `idp_gate/conformance.py` (`_assume_old`), plus `docs/platform/service-contract.md` and `onboarding.md` (residual-risk notes).

## Test approach

* Unit tests for archive-syntax words (in the Makefile and in an include) and the accepted literal words around them.
* Unit tests for the tab-indented `define` before and after the first rule (LF and CRLF).
* A real-make conformance test for the archive repro and for `.//gen.mk` with a FORCE rule, using explicit `os.utime` and no sleeps; an argv test for the pin spelling.

## Definition of Done

* All ACs traced; `make verify` green.
* `service-contract.md` and `onboarding.md` residual-risk notes for these three items removed or adjusted.
* CHANGELOG entry.

## Comments (1)

### Suyash Kunte, 2026-10-20T13:01:41.440+0530

**Parked (2026-10-20, agreed with the human).** The static Makefile scanner is a correctness check, not a security boundary. The security boundary is IDP-23 plus least-privilege roles; see IDP-31 (ADR-0013). Take this ticket back up only if one of these items becomes a regression, or a bypass in a job that holds credentials or runs code it didn't write, or if the `make -pn` re-evaluation after IDP-23 doesn't supersede it.
