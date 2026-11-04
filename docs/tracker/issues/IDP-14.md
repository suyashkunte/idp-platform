---
key: IDP-14
type: Bug
status: Done
summary: "guard_bash false positive: blocks commands that only mention approve-spec or APPROVED as text"
parent:
labels: [component:ai-tooling, repo:idp-platform, risk:medium, spec:guided]
priority: Medium
resolution: Done
reporter: "Suyash Kunte"
assignee: ""
created: 2026-10-07T01:49:32.669+0530
updated: 2026-10-20T21:13:16.073+0530
resolved: 2026-10-20T21:13:16.053+0530
links:
  - {type: "relates to", key: IDP-39}
  - {type: "relates to", key: IDP-40}
  - {type: "relates to", key: IDP-41}
  - {type: "relates to", key: IDP-42}
  - {type: "relates to", key: IDP-43}
  - {type: "relates to", key: IDP-44}
jira_url: https://suyashkunte.atlassian.net/browse/IDP-14
---

# IDP-14: guard_bash false positive: blocks commands that only mention approve-spec or APPROVED as text

Links: relates to [IDP-39](IDP-39.md); relates to [IDP-40](IDP-40.md); relates to [IDP-41](IDP-41.md); relates to [IDP-42](IDP-42.md); relates to [IDP-43](IDP-43.md); relates to [IDP-44](IDP-44.md)

## Description

## Context / why

Found in the IDP-13 dry run. The Bash guard matched `approve-spec` and `specs/*/APPROVED` anywhere in a command, so it blocked the PR composer from saving a PR body that _mentions_ the approval command (heredoc) and blocked a notes update. The agent worked around it with Write/Edit, which is legitimate here, but false positives teach agents to route around guards. Separately, the `pr-generate` skill prescribes the trailer `Co-Authored-By: Claude <noreply@anthropic.com>`, while the environment supplies a model-specific one; the skill should defer to the environment.

## Acceptance criteria

* AC-1 Given a command that _executes_ `make approve-spec`, `uv run idp approve-spec` or `idp approve-spec` (at command start, or after `;`, `&&`, `||`, `|` or `$(`), when guard_bash runs, then it blocks.
* AC-2 Given a command that writes, copies, moves, tees or redirects INTO `specs/<KEY>/APPROVED`, when guard_bash runs, then it blocks.
* AC-3 Given a heredoc or quoted string that only mentions `make approve-spec` or `APPROVED` as text (e.g. `cat > pr.md <<'EOF' ... run make approve-spec ... EOF`, `git commit -m "... APPROVED ..."`), when guard_bash runs, then it is allowed.
* AC-4 Given the existing blocked/allowed command lists in `tests/plugin/test_hooks.py`, then they all still pass.
* AC-5 Given the `pr-generate` skill, then it tells the agent to use the Co-Authored-By trailer supplied by the environment/harness, not a hard-coded one.

## Non-functional criteria

Hook stays stdlib-only Python 3.9+, runs in under 1 s.

## Out of scope

Full shell parsing.

## Dependencies

`plugins/idp-agentic/hooks/**` is a protected path: this change needs a human-led session (the agent may not edit hooks).

Found in phase: DEV (iteration 1 dry run, IDP-13).

## Comments (4)

### Suyash Kunte, 2026-10-20T14:52:18.035+0530

**Spec drafted** (branch `feature/IDP-14-guard-bash-false-positive`, commit 3dc6874, `specs/IDP-14/`). Guided mode: waiting for spec approval.

**Approach:** guard_bash keeps every other rule unchanged; it replaces only the two approval rules with a small stdlib lexer. The lexer masks heredoc bodies and quoted text, then blocks (AC-1) `make`/`gmake`/`idp` running `approve-spec` in command position, and (AC-2) redirects or writers (cp, mv, tee, touch, install, ln, dd, truncate, sed -i, git add/rm/…) aimed at the marker. When it is unsure (unterminated quotes, backticks, `sh -c`/`eval`/`xargs`/interpreters, quoted text sent to a non-printer), it falls back to the old "any mention blocks" check. Reading the marker (cat, ls, git status/diff/log, test -f) is allowed.

**Human task H1:** the hook is a protected path. Right after approval, paste the replacement code from plan.md "H1" and commit it. Then tests (T1), the pr-generate trailer wording (T2, AC-5) and docs (T3) are agent tasks.

**Pre-check:** I ran the H1 code from plan.md against 80 cases with system Python 3.9.6: 55 block cases (including bypass attempts) and 25 mention-only allow cases. All 80 were correct. A 270 KB heredoc took 0.16 s. The current hook gets 16 of the allow cases wrong.

**Open questions (recommendation in brackets):**

* Q1: the protected-path and other raw rules still block heredocs that only mention them, such as `.github/` text after `cat >` \[follow-up ticket; keep this one to the approval rules\]
* Q2: confirm the interpreter, printer and writer lists \[accept\]
* Q3: when unsure, fall back to the old mention check \[yes\]
* Q4: check that the installed plugin copy matches the repo copy \[not here; possible SessionStart drift warning as a follow-up\]
* Q5: bump the plugin version so installed copies refresh (protected marketplace.json, so human work) \[yes, optional H1 step\]
* Q6: add no trailer when the environment supplies none \[yes\]

### Suyash Kunte, 2026-10-20T15:46:31.803+0530

**Review loop 1 → spec amendment 1** (commit d01ab4d; re-approval needed).

The independent code and security reviews found **14 confirmed regressions** in the H1 hook: commands that main blocks, that really run the approval or write the marker, and that H1 allowed. They include `\ #` read as a comment, `(( x << n ))` read as a heredoc, an empty quoted redirect target, `touch -m`, `sort -o`, `git diff --output=`, `| $SHELL`, `| sudo -s`, `curl -o`, `patch` and `git commit -- <marker>`.

**Decision (human):** relax-only design. Every raw mention of the approval target or the marker blocks, as on main. The lexer may only _relax_ a mention it places in a DATA span (quoted text or a heredoc given to a narrow printer, with no output options and no shell downstream) or a READ span (a plain marker path given to cat/ls/test/git status…). When it is unsure, nothing is relaxed.

**Pre-check of the H2 code:** ruff is clean and it parses as Python 3.9. It got all 115 committed test cases right. All 17 review payloads block, except the `$'\x61…'` residual, which main allows too. The large-input cases ran in at most 0.23 s.

**New questions:**

* Q7: should unquoted plain words given to printers be relaxed (`grep -n approve-spec Makefile`)? \[no: quote it\]
* Q8: relax DATA only when every command in the line is inert, so `make verify && git commit -m "…approve-spec…"` still blocks, as on main \[yes\]
* A9: backticks inside single quotes or quoted-delimiter heredocs count as data (markdown code spans in PR bodies)

### Suyash Kunte, 2026-10-20T16:53:43.651+0530

**Review loop 2 → spec amendment 2** (re-approval needed).

The H2 relax-only hook closed all 14 loop-1 regressions. Probing the new invariant found 5 more bypasses: bash evaluates array subscripts such as `'a[$(make approve-spec)]'` inside `[[ … -eq … ]]`, `test`/`[`/`[[ -v` (bash ≥ 4.2) and `printf -v`, so quoted text given to them runs code. Confirmed with a fake make on bash 3.2 (macOS) and bash 5.2 (Debian).

**Decision (human):** fix in this PR. `test`, `[` and `[[` are no longer printers or inert; their `-f/-e/-s <marker>` read form stays allowed through READ. `printf -v` gives no relaxation. The H3 diff from H2 is 3 small changes.

**Pre-check of H3:** ruff is clean and it parses as Python 3.9. It gets all 192 cases right: 166 committed, 16 new T5 and 17 review payloads.

**Left as minor follow-ups** (main has the same gaps): split-word forms like `appr"ove"-spec` and `$'\x61…'` evade the raw-mention regex; `git commit -F - <<EOF` with approval text is a false positive; the legacy protected-path regex takes 0.5 s on adversarial input.

### Suyash Kunte, 2026-10-20T20:48:55.521+0530

**Draft PR opened:** https://github.com/suyashkunte/idp-platform/pull/15

H3 (relax-only guard plus amendment 2) is in. `make verify` passes (756 tests, coverage 98.23%) and spec-trace shows AC-1..AC-5 OK. Red-first evidence and both review loops are in the PR body.

**Open for the human reviewer:**

* The independent security confirmation of H3 did not finish. The orchestrator's static pass and shell probes found nothing new.
* 6 minor follow-ups, all gaps main also has: split-word evasion, the `git commit -F -` false positive, the quadratic legacy regex, rg `--hostname-bin`, the py39 test scope, and the script-indirection residual risk.
* Q5: bump the plugin version (human edit to marketplace.json).
