---
key: IDP-30
type: Story
status: To Do
summary: "idp conformance: bound make output and fail examples whose includes make would look up outside the service directory"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T12:53:13.925+0530
updated: 2026-10-20T13:02:00.458+0530
resolved:
links:
  - {type: "relates to", key: IDP-23}
  - {type: "relates to", key: IDP-28}
  - {type: "relates to", key: IDP-31}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-30
---

# IDP-30: idp conformance: bound make output and fail examples whose includes make would look up outside the service directory

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-23](IDP-23.md); relates to [IDP-28](IDP-28.md); relates to [IDP-31](IDP-31.md)

## Description

## Context / why

Follow-up from the IDP-28 review (PR #12). Two conformance gaps remain that the static scanner cannot close:

* **make's include search path:** a literal include word whose file is missing from the service directory is skipped by the scanner. When make cannot find a relative include, it searches `-I` directories and its defaults (`/usr/local/include`, `/usr/gnu/include`, `/usr/include`) and reads whatever it finds there, unscanned. On macOS runners `/usr/local/include` is often writable (Homebrew). A missing include can never be legitimately generated during conformance, because every include word is pinned with `--assume-old`.
* **Unbounded make output:** `_run_make_verify` buffers all of make's output with `communicate()`, and `_tail` keeps 40 lines of any length. make echoes untrusted names (for example "No rule to make target `<1 MB name>`"), so one example can use a lot of memory and print very long lines in the conformance report.

## Acceptance criteria

* **AC-1** Given an example whose `Makefile` has `-include missing.mk` (also `include missing.mk`), where `missing.mk` does not exist in the example directory, when I run `idp conformance`, then that example is reported `FAIL <x>: include 'missing.mk' is not in the service directory` and make is not run, even if a file `missing.mk` exists in a directory on make's include search path.
* **AC-2** (edge) Given an example whose included files all exist in the example directory, when I run `idp conformance`, then the example still passes, and `examples/minimal-service` (whose profile include is pinned as `<profile dir>/defaults.mk`) still passes.
* **AC-3** (edge) Given an example whose `make verify` writes more than 10 MiB of output, including a line longer than 1 MiB, when I run `idp conformance`, then the FAIL report shows at most the last 40 lines, each at most 200 characters (truncated with `…`), and conformance never holds more than a fixed, documented number of bytes of that example's output in memory.

## Non-functional criteria

* No new dependencies.
* The example still times out at the existing limit; output bounding must not deadlock the child process.
* The real-make tests pass on GNU Make 3.81 (macOS) and 4.x (CI).

## Out of scope

* A minimal environment, process-group cleanup and sandboxing of example runs (IDP-23).
* Replacing static parsing with `make -pn` (ADR candidate after IDP-23).
* `MAKEFLAGS += -I<dir>` set inside a Makefile on make 4.4: verify during spec; if it is a separate bypass, record it as a question.

## Interfaces / dependencies

* Depends on IDP-28 (merged, 88c2d63). Relates to IDP-23 (both change how conformance runs make); whichever lands second rebases.
* Touches `idp_gate/conformance.py` (`check_example`, `_run_make_verify`, `_tail`) and possibly the scan result in `idp_gate/contract.py` (which literal words were missing), plus `docs/platform/onboarding.md`.

## Test approach

* Unit tests with a fake `Popen` for output bounding: a huge single line, many lines, and output followed by a non-zero exit code.
* A real-make conformance test that puts `missing.mk` in a temporary directory passed as an include directory, and checks that make is not run; explicit `os.utime`, no sleeps.
* Run `tests/conformance/test_examples.py` to check `minimal-service` still passes.

## Definition of Done

* All ACs traced; `make verify` green.
* `onboarding.md` and `service-contract.md` residual-risk notes for the include search path and output size removed or adjusted.
* CHANGELOG entry.

## Comments (1)

### Suyash Kunte, 2026-10-20T13:01:42.146+0530

**Parked (2026-10-20, agreed with the human).** The static Makefile scanner is a correctness check, not a security boundary. The security boundary is IDP-23 plus least-privilege roles; see IDP-31 (ADR-0013). The output-bounding part (AC-3) is a robustness item: take it back up with or after IDP-23 if conformance output becomes a problem.
