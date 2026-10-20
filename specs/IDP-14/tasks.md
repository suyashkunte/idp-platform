# IDP-14: tasks

Status:
- Done: spec approved (cb63815), H1 (d1c83f5), T1 (1b11b14), T2 (57c8532).
- Spec amended 2026-10-20 (amendment 1, relax-only, after review loop 1): `status: DRAFT`, so re-approval is needed.
- Open:
  - H2 is a HUMAN task on a protected path. It comes right after re-approval;
  - T4 updates the tests to the amended spec;
  - T3 (docs) comes last;
  - then verify and review loop 2.
- Between H2 and T4, the four changed MENTIONS_ONLY cases, the moved comment case and the changed timing case are
  red by design.
- If H2's checks fail, or any unchanged test case disagrees with H2, stop and revise the spec.

Test names and exact case lists are in plan.md ("Tests", and "Amendment 1" / "Tests (T4)").

- [x] H1 HUMAN, protected path, right after `make approve-spec KEY=IDP-14`.
  - Replace `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the complete file in plan.md ("H1").
  - Run the plan.md H1 checks: executable bit, `ruff format --check`, `ruff check`, the Python 3.9 `ast.parse`, the two
    smoke commands with `/usr/bin/python3`, and `make validate-plugin`.
  - Commit only that file.
  - (AC-1, AC-2, AC-3, AC-4) Files: plugins/idp-agentic/hooks/scripts/guard_bash.py.
  - Done d1c83f5. Superseded by H2 (amendment 1).
- [x] T1 Guard tests (after H1): the AC-1..AC-3 lists, the fail-closed, timing and large-heredoc tests, and the
  stacked `IDP-14:AC-4` marks.
  - (AC-1, AC-2, AC-3, AC-4) Files: tests/plugin/test_hooks.py.
  - Done 1b11b14. Extended by T4.
- [x] T2 `pr-generate` trailer: step 1 of SKILL.md and `test_pr_generate_uses_environment_co_author_trailer`.
  - (AC-5) Files: plugins/idp-agentic/skills/pr-generate/SKILL.md, tests/plugin/test_structure.py.
  - Done 57c8532.
- [ ] H2 HUMAN, protected path, right after re-approval of the amended spec.
  - Replace `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the complete file in plan.md ("Amendment 1" /
    "H2").
  - Run the plan.md H2 checks: the H1 checks, the two smoke commands, and the review payload check (p01, p15: both
    must exit 2).
  - Commit only that file as `IDP-14: relax-only approval guard (amendment 1)`.
  - (AC-1, AC-2, AC-3, AC-4) Files: plugins/idp-agentic/hooks/scripts/guard_bash.py.
- [ ] T4 Tests for the relax-only guard (after H2), in `tests/plugin/test_hooks.py`:
  - Add the review payloads: p01-p06, p09-p11 and p17 to `RUNS_APPROVAL`; p07, p08 and p13-p16 to `WRITES_MARKER`.
    p12 is not added (residual risk; a test would pin a bypass).
  - Turn `UNSURE_MENTIONS` into `(command, reason)` pairs and assert the reason. Add the three cases moved from
    MENTIONS_ONLY and the seven new fail-closed cases from plan.md.
  - Apply the four MENTIONS_ONLY changes and add the two new allowed cases.
  - Add `test_mentions_in_comments_block` (AC-1, AC-2) and `test_hook_parses_as_python_39` (AC-3, NFR).
  - Update the timing cases.
  - Do not edit any other existing case. If one fails with H2, stop and report.
  - Red-first evidence for the PR: run the new block cases against the H1 hook (`git show d1c83f5:<path>` into the
    scratchpad); the 14 regressions are allowed there.
  - Run `uv run pytest tests/plugin --no-cov`, `uv run ruff check tests/plugin`,
    `uv run ruff format --check tests/plugin` and `uv run idp test-quality-lint tests/plugin/test_hooks.py`.
  - (AC-1, AC-2, AC-3) Files: tests/plugin/test_hooks.py.
- [ ] T3 Docs and final checks (after T4).
  - Add the IDP-14 entry under a new `### Fixed` in `[Unreleased]` in `CHANGELOG.md`. Use the amendment 1 wording in
    plan.md ("Changes (amendment 1)"), including the "takes effect after the plugin is updated" note (spec Q4).
  - Run `make verify` (green, including `idp spec-trace IDP-14` with AC-1..AC-5 OK).
  - (AC-1..AC-5) Files: CHANGELOG.md.
- [ ] Review loop 2 (orchestrator) on the H2 hook and the T4 tests.
