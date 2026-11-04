---
key: IDP-39
type: Story
status: To Do
summary: "Guard catches split-word approval runs (appr\"ove\"-spec, appr\\ove-spec, $'\\x61…')"
parent: IDP-16
labels: [component:ai-tooling, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution:
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-20T21:12:01.470+0530
updated: 2026-10-20T21:13:01.981+0530
resolved:
links:
  - {type: "relates to", key: IDP-14}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-39
---

# IDP-39: Guard catches split-word approval runs (appr"ove"-spec, appr\ove-spec, $'\x61…')

Epic/parent: [IDP-16](IDP-16.md)

Links: relates to [IDP-14](IDP-14.md)

## Description

## Context / why

Follow-up from the IDP-14 review (PR #15). The relax-only guard in `plugins/idp-agentic/hooks/scripts/guard_bash.py` looks for raw text mentions. `make appr"ove"-spec`, `make appr\ove-spec` and `make $'\x61pprove-spec'` all run the approval target without a raw mention: a fake make confirmed it. Both main and the IDP-14 hook allow them. The hook's lexer already computes the de-quoted text of each word, so the guard can also check that text.

## Acceptance criteria

* **AC-1** Given `make appr"ove"-spec KEY=X`, `make appr\ove-spec KEY=X` or `idp 'appr'ove-spec X`, when guard_bash runs, then it blocks with the spec-approval reason.
* **AC-2** (edge) Given an ANSI-C `$'…'` word containing a backslash escape in a command that is not a printer, when guard_bash runs, then it fails closed: it blocks if the decoded text could be a mention, or treats the input as unsure.
* **AC-3** Given the existing IDP-14 lists in `tests/plugin/test_hooks.py` (RUNS_APPROVAL, WRITES_MARKER, MENTIONS_ONLY, UNSURE_MENTIONS, COMMENTED_MENTIONS) and the IDP-10 lists, then they all still pass. In particular, quoted text given to printers gets no new false positives.

## Non-functional criteria

Hook stays stdlib-only, Python 3.9+, and runs in under 1 s on the IDP-14 large inputs.

## Out of scope

Variable, alias, function and script indirection. `m=make; $m …` already blocks; a script file written earlier and run later is accepted residual risk (IDP-14 spec).

## Interfaces / dependencies

`plugins/idp-agentic/hooks/**` is a protected path: the agent writes the code in plan.md and the human places it after spec approval. No blocking tickets (IDP-14 Done).

## Test approach

New RUNS_APPROVAL cases, shown red against the IDP-14 hook (fa948a5) and green after. Confirm each with a fake make in a throwaway dir on bash 3.2, bash 5.2 (Docker) and zsh.

## Definition of Done

Spec approved; hook placed by the human; `make verify` green; spec-trace OK; independent review done; CHANGELOG updated.

## Comments (0)
