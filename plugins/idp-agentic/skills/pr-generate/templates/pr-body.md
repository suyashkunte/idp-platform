## Summary
<3 sentences: what and why>. Ticket: <KEY>

## Spec and traceability
Spec: `specs/<KEY>/spec.md` (approval: <approved by NAME at TIME | deferred to this PR review (auto mode): run `make approve-spec KEY=<KEY>` before merge>)

| AC | Tests |
|----|-------|
| AC-1 | `path::test_name` |

## Evidence
- `make verify`: <PASS/FAIL> (<n> tests, coverage <x>%, diff coverage <y>%)
- spec-trace: <n>/<n> ACs covered
- test-quality-lint: clean

## Risk and rollout
<blast radius, rollback, monitoring>

## Review findings left for the human reviewer
<none | list>

## AI assistance
- [x] ai-assisted (Claude Code, idp-agentic plugin): spec, tests and code drafted by agents
- Reviewer agents run: code-reviewer, security-reviewer
- Human reviewer, please focus on: <areas of least certainty>
