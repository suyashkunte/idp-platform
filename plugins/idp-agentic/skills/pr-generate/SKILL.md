---
name: pr-generate
description: Push the feature branch and open a DRAFT pull request with the IDP PR body (spec link, AC-to-test table, evidence, risk, AI disclosure), then link it on the ticket and move the ticket to In Review. Use as the last step of implement-ticket.
---

# Open the draft PR

1. Make sure the work is committed in logical commits, titled `<KEY>: <imperative summary>`, each with the trailer
   `Co-Authored-By: Claude <noreply@anthropic.com>`.
2. `git push -u origin HEAD` (feature branch only).
3. Ask the `pr-composer` subagent for the body using `templates/pr-body.md` in this skill's folder: fill the AC→test
   table from `make spec-trace KEY=<KEY>` output and the evidence from the last `make verify` run.
4. `gh pr create --draft --base main --title "<KEY>: <summary>" --body-file <file>`, then
   `gh pr edit --add-label ai-assisted` (create the label if missing: `gh label create ai-assisted --color 5319E7`).
5. Comment the PR URL on the ticket and transition it to *In Review*.
