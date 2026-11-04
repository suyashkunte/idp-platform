---
key: IDP-42
type: Task
status: To Do
summary: "guard_bash hardening: rg --hostname-bin as output option, real Python 3.9 test run"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:low, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T21:12:33.133+0530
updated: 2026-10-20T21:13:06.179+0530
resolved:
links:
  - {type: "relates to", key: IDP-14}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-42
---

# IDP-42: guard_bash hardening: rg --hostname-bin as output option, real Python 3.9 test run

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-14](IDP-14.md)

## Description

## Context / why

Two small follow-ups from the IDP-14 review (PR #15).

1. ripgrep's `--hostname-bin=<prog>` runs a program, but it is not in the guard's output-option list (`_OUTPUT`). It can only run a bare binary name with no arguments, so it can't run the approval target. A command that runs programs should still get no DATA relaxation.
2. `test_hook_parses_as_python_39` only checks syntax (`ast.parse(feature_version=(3, 9))`). It misses 3.10+-only standard-library calls such as `str.removeprefix` or `zip(strict=)`. Hooks must run on macOS's system Python 3.9.

## Acceptance criteria

* **AC-1** Given an `rg` command with `--hostname-bin=<x>` (or `--hostname-bin <x>`) and quoted text mentioning the approval target, when guard_bash runs, then it blocks (no DATA relaxation).
* **AC-2** Given the plugin tests, then guard_bash's `check()` (and `main()` via stdin) runs under a real Python 3.9 interpreter on a representative block/allow set, and the test fails if the hook uses an API that 3.9 lacks.
* **AC-3** (edge) Given no Python 3.9 interpreter is available (locally or in CI), then that test fails with a clear message naming how to get one (e.g. `uv python install 3.9`); it is never skipped silently.

## Non-functional criteria

The suite stays under its current runtime + 10 s.

## Out of scope

Other hooks' 3.9 checks (could reuse the helper later).

## Interfaces / dependencies

`plugins/idp-agentic/hooks/**` is protected (AC-1 hook edit placed by the human). CI image ubuntu-24.04 has no 3.9 by default: the spec must decide how CI gets one (uv-managed Python), and any `.github/**` change is human-placed. Related: IDP-14.

## Test approach

AC-1: block-list case, red on the current hook. AC-2: a test that shells out to the 3.9 interpreter; prove it red by temporarily running it against a scratch copy of the hook that uses `str.removeprefix`.

## Definition of Done

Spec approved; hook placed; `make verify` green locally and in CI; spec-trace OK; review; CHANGELOG.

## Comments (0)
