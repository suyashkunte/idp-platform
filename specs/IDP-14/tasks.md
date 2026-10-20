# IDP-14: tasks

Status: awaiting human spec approval (guided mode).
- H1 is a HUMAN task on a protected path (`plugins/idp-agentic/hooks/**`). It comes first, right after approval, so
  the new tests are green as soon as they are written, and the Definition of Done Stop hook does not block every turn.
- T1-T3 are agent tasks.
- If H1's checks fail, or T1 finds a case where the hook disagrees with the spec, stop and revise the spec
  (re-approval needed, and a new H1 paste by the human).

Test names and exact case lists are in plan.md ("Tests").

- [ ] H1 HUMAN, protected path, right after `make approve-spec KEY=IDP-14`.
  - Replace `plugins/idp-agentic/hooks/scripts/guard_bash.py` with the complete file in plan.md ("H1").
  - Run the plan.md H1 checks: executable bit, `ruff format --check`, `ruff check`, the Python 3.9 `ast.parse`, the two
    smoke commands with `/usr/bin/python3` (expect `exit 0`, then `BLOCKED ...` and `exit 2`), and
    `make validate-plugin` (green).
  - Commit only that file as `IDP-14: judge spec approval by what a command runs or writes`.
  - Optional (spec Q5, if confirmed): bump the plugin version to 0.1.1 in `plugin.json` and `marketplace.json`.
  - (AC-1, AC-2, AC-3, AC-4) Files: plugins/idp-agentic/hooks/scripts/guard_bash.py (optionally
    plugins/idp-agentic/.claude-plugin/plugin.json, .claude-plugin/marketplace.json).
- [ ] T1 Guard tests (after H1).
  - Add the `bash()` helper, the case lists and the tests to `tests/plugin/test_hooks.py`:
    - `test_running_spec_approval_is_blocked` (AC-1);
    - `test_writing_the_approved_marker_is_blocked` (AC-2);
    - `test_mentioning_approval_as_text_is_allowed` (AC-3);
    - `test_approval_check_fails_closed_when_unsure` (AC-1, AC-2);
    - `test_large_command_is_checked_within_a_second` (AC-3, NFR);
    - `test_large_heredoc_is_allowed_by_the_hook` (AC-3).
  - Stack `@pytest.mark.ac("IDP-14:AC-4")` on the two existing guard tests. Their lists and bodies stay unchanged.
  - Red-first evidence, recorded for the PR:
    - write the pre-H1 hook to the scratchpad with `git show <commit before H1>:plugins/idp-agentic/hooks/scripts/guard_bash.py`;
    - pipe every new case into it in a scratchpad loop, without editing the hook;
    - expect the AC-3 cases (mention-only, reading the marker) to be blocked by the old hook, and bypass cases such as
      `make -s approve-spec`, `make 'approve-spec'`, `cd specs/IDP-1 && touch APPROVED` and
      `cat <(make approve-spec ...)` to be allowed by it.
  - Run `uv run pytest tests/plugin --no-cov`, `uv run ruff check tests/plugin`,
    `uv run ruff format --check tests/plugin` and `uv run idp test-quality-lint tests/plugin/test_hooks.py`.
  - If a case disagrees with the spec, stop (see Status).
  - (AC-1, AC-2, AC-3, AC-4) Files: tests/plugin/test_hooks.py.
- [ ] T2 `pr-generate` trailer.
  - Add `test_pr_generate_uses_environment_co_author_trailer` to `tests/plugin/test_structure.py` and see it fail.
  - Replace step 1 of `plugins/idp-agentic/skills/pr-generate/SKILL.md` with the plan.md text, and see the test pass.
  - Confirm that `test_every_skill_has_name_and_description` stays green.
  - (AC-5) Files: plugins/idp-agentic/skills/pr-generate/SKILL.md, tests/plugin/test_structure.py.
- [ ] T3 Docs and final checks.
  - Add the plan.md IDP-14 entry under a new `### Fixed` in `[Unreleased]` in `CHANGELOG.md`. It includes the
    "takes effect after the plugin is updated" note (spec Q4).
  - Run `make verify` (green, including `idp spec-trace IDP-14` with AC-1..AC-5 OK).
  - (AC-1..AC-5) Files: CHANGELOG.md.
