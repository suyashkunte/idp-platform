---
name: spec-author
description: How to write specs/<KEY>/spec.md, plan.md and tasks.md from a Ready ticket. Use when drafting or updating a spec, plan or task list.
---

# Spec authoring rules

Templates are in this skill's `templates/` folder. Write to `specs/<KEY>/`.

## spec.md (the "what": precise and testable)
- Front matter: `ticket`, `status: DRAFT`, `risk`, `mode` (auto/guided).
- **Requirements**: every ticket AC copied with the SAME id as a bullet `- **AC-n** ...`. The spec-trace tool parses exactly
  this form. You may sharpen the wording but never change the meaning; put clarifications under it as sub-bullets.
- Edge cases and assumptions (each assumption flagged so the reviewer can confirm it).
- Non-functional requirements, copied and made measurable.
- Out of scope.
- **Open questions**: list them instead of guessing. Resolved answers stay, marked "(resolved: ...)".
- Traceability table `AC → planned test(s)`, filled in now and kept current.

## plan.md (the "how")
Files to touch, data and interface changes, telemetry, risks, rollout and rollback. Read the existing code first and keep
the plan the smallest design that meets the ACs.

## tasks.md
Small ordered tasks (each ≤ ~1 hour, each leaves tests green), each citing the AC ids it serves.

## After approval
Never silently edit an approved spec. If implementation shows a gap: update the spec, set `status: DRAFT`, and tell the
user that re-approval is needed (the APPROVED marker records the spec hash, so the change is detectable).
