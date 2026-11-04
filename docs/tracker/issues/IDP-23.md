---
key: IDP-23
type: Story
status: To Do
summary: "idp conformance: minimal environment and guaranteed process cleanup for example runs"
parent: IDP-16
labels: [component:pipeline, layer:test, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T17:02:10.277+0530
updated: 2026-10-20T13:02:03.116+0530
resolved:
links:
  - {type: "relates to", key: IDP-28}
  - {type: "relates to", key: IDP-30}
  - {type: "relates to", key: IDP-31}
  - {type: "relates to", key: IDP-34}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-23
---

# IDP-23: idp conformance: minimal environment and guaranteed process cleanup for example runs

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-28](IDP-28.md); relates to [IDP-30](IDP-30.md); relates to [IDP-31](IDP-31.md); relates to [IDP-34](IDP-34.md)

## Description

## Context / why

Follow-up from the IDP-19 review (PR #7, security finding M1 and code-review minors). `idp conformance` runs example Makefiles with the full environment, minus 5 `MAKE*` variables. In CI that gives an example's recipes access to `GITHUB_ENV`, `GITHUB_PATH`, the checkout token and the network. This is acceptable only while the platform team owns `examples/`, and it must be fixed before any tenant contributes an example. Process cleanup also has gaps:

* the second `communicate()` call after a kill has no time limit;
* an interrupt (Ctrl-C) can leave make running;
* background children left over after a normal exit are never killed.

## Acceptance criteria

* **AC-1** Given `idp conformance` runs an example, then the child environment contains only an allow-list (`PATH`, `HOME`, `LANG`, `LC_*`, `TMPDIR`, `TERM`, plus `IDP_PROFILE_DIR` passed on the command line). In particular, no `GITHUB_*`, `ACTIONS_*`, `*_TOKEN`, `AWS_*` or `MAKE*` variables reach it.
* **AC-2** Given an example's `verify` leaves a background process running after make exits successfully, then that process group is killed before the next example starts.
* **AC-3** (edge) Given a recipe child that holds stdout open after a timeout kill, or a KeyboardInterrupt during a run, then `idp conformance` returns within timeout + 5 s, kills the process group, and reports FAIL (or exits 130 on interrupt). It never hangs.
* **AC-4** Given the platform CI `verify` job, then checkout uses `persist-credentials: false`. This is a human-placed `.github` edit (agents cannot edit `.github/**`).

## Non-functional criteria

Conformance still under 60 s; behaviour unchanged on macOS and on Linux with GNU make 4.x.

## Out of scope

Network isolation or container sandboxing. Record this as a prerequisite in `docs/platform/onboarding.md` before tenant-contributed examples are accepted, and give it its own story later.

## Interfaces / dependencies

Depends on IDP-19 (Done). AC-4 needs a human edit to `.github/workflows/platform-ci.yml`. Touches `idp_gate/conformance.py`.

## Test approach

Real-process tests with short timeouts (an env-dump recipe, a background `sleep`, and a child that ignores closing stdout); the AC-4 test parses `platform-ci.yml`.

## Definition of Done

ACs traced; `make verify` green; trust assumption documented in `onboarding.md`; CHANGELOG entry.

Labels: repo:idp-platform, component:pipeline, layer:test, risk:medium, spec:guided

## Comments (0)
