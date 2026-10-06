---
name: review-self
description: Independent pre-PR review - run the read-only code-reviewer and security-reviewer subagents on the branch diff, fix blockers and majors, and report what remains. Use before opening a PR.
---

# Independent review loop

1. Run `code-reviewer` and `security-reviewer` (in parallel when possible). Both are read-only and review
   `git diff main...HEAD` against `specs/<KEY>/spec.md`.
2. Collect findings as BLOCKER / MAJOR / MINOR with file:line.
3. Fix BLOCKER and MAJOR findings (via `code-implementer`), then re-run `make verify`.
4. Repeat at most 2 loops. Anything still open goes into the PR body under "Review findings left for the human reviewer".
