# Backlog: Jira setup, epics and seed stories

These are seed tickets to create in Jira (scripted later by `tools/jira_bootstrap.py`, run by a human).
Every story follows the **hardened ticket template** (design doc §21.3), so it passes the Definition of Ready and
`/implement-ticket` can run it without guessing.

## 1. Jira configuration

| Item | Value |
|---|---|
| Project | `IDP` on suyashkunte.atlassian.net (free plan). Tickets are referenced as `IDP-<n>`; IDs below (ST-n, IDP-En) are planning aliases |
| Issue types | Epic, Story, Task, Bug, **Gate Hold** (created by pipeline) |
| Workflow | To Do → **Ready** (DoR passed) → In Progress → In Review → Done. Agent may transition only to *In Progress* and *In Review*; *Done* is set by the pipeline after merge + G0 PASS |
| Components | modelled as labels `component:studytimer`, `component:gatekeeper`, `component:pipeline`, `component:infra`, `component:observability`, `component:ai-tooling` |
| Labels | `risk:low` / `risk:medium` / `risk:high`, `spec:auto` / `spec:guided`, `gate:G0`…`gate:G5`, `layer:app` / `layer:policy` / `layer:infra` / `layer:test`, `ai-assisted` |
| Custom fields | **Found in phase** (Bug): DEV, G0, G1, G2, G3, G5, PROD; **Severity** (Bug, Gate Hold): P0–P3 |
| Live IDs (verified 2026-10-06 via MCP) | cloudId `9fd93ad3-325d-4bb0-8628-f4620d592cd2`; work types Epic `10001`, Subtask `10002`, Task `10003`, Story `10004`, Bug `10038`, Gate Hold `10039`; fields Severity `customfield_10077` (P0–P3), Found in phase `customfield_10078` (DEV, G0–G5, PROD); global transitions (any status → target): To Do `11`, Ready `2`, In Progress `21`, In Review `31`, Done `41` |
| Description template | Sections below, as headings in the description (the `ticket-intake` skill parses them) |

### Hardened ticket template
```
## Context / why
## Acceptance criteria          (AC-n, Given / When / Then, independently testable; ≥1 negative/edge case)
## Non-functional criteria      (performance, security, observability, or "none")
## Out of scope
## Interfaces / dependencies    (APIs, schemas, tickets)
## Test approach
## Definition of Done           (checklist; defaults from docs/process/definition-of-done.md)
Labels: component, risk, spec mode, layer
```

## 2. Epics

Every ticket carries `repo:idp-platform` or `repo:studytimer` so `/implement-ticket` knows where it runs.

| Epic | Repo | Iteration | Purpose |
|---|---|---|---|
| E1 Setup & bootstrap | platform | 0 | Toolchain, AWS/GitHub/Jira connectivity, Terraform bootstrap (hand-built) |
| E2 Platform skeleton & agentic plugin | platform | 1 | Workspace, `idp-agentic` plugin + marketplace, schemas v0 (hand-built) |
| E3 Contract, template & PR pipeline | both | 2 | `idp validate`, python-uv profile, template, `service-pipeline.yml`; StudyTimer generated |
| E4 Gate engine & G0 | platform | 3 | Policy profiles, multi-tenant Gatekeeper, catalog + onboarding module, G0 |
| E5 Cluster, generic chart & G1 | platform | 4 | EKS, add-ons, `idp-service` chart, env-up/down, G1 |
| E6 G2 | both | 5 | idp-testkit, platform suites, release manifest, hold tickets; StudyTimer API tests |
| E7 Observability | platform | 6 | Telemetry plane, dashboards templated by service, SLO alerts from contract |
| E8 G3 | both | 7 | Regression/E2E, load/soak, resilience, rehearsals, readiness score |
| E9 G4/G5 | platform | 8 | Decision records, Kyverno enforce, Rollouts per service type, waivers |
| E10 Metrics & AI validation | platform | 9 | Scorecard, mutation, flake registry, triage assistant |
| E11 StudyTimer MVP | studytimer | 10 | Product stories below |
| E12 Prove "any app" | new repo + platform release | 11 | Tenant #2 (different type and stack) with 0 platform changes; v1.0.0; upgrade drill |

Platform tickets for E3–E10 are written in full at the start of each iteration with the `create-story` skill, so they reflect what
we learned in the previous iteration.

## 3. StudyTimer MVP stories (Epic IDP-E10)

> Default labels: `repo:studytimer`, `component:studytimer`, `layer:app`. Default NFRs: p95 < 300 ms reads / < 800 ms writes at G3 load; every new endpoint
> emits RED metrics and spans; no PII in logs. Default DoD: see `docs/process/definition-of-done.md`.

### ST-1 Account sign-up and sign-in — `risk:medium`, `spec:guided`
**Context:** students need a private space for their data; all later features are per-user.
- **AC-1** Given a new email and a password of ≥ 12 chars, when I submit sign-up, then an account is created, I am signed in, and I land on the dashboard.
- **AC-2** Given an email that already exists, when I sign up, then I see "account already exists" and no second account is created.
- **AC-3** Given valid credentials, when I sign in, then a session cookie (HttpOnly, Secure, SameSite=Lax) is set and expires after 7 days of inactivity.
- **AC-4** Given wrong credentials, when I sign in 5 times within 10 minutes, then further attempts are rejected for 10 minutes (no user enumeration in messages).
- **AC-5** Given I am signed out, when I request any page other than sign-in/sign-up/health, then I am redirected to sign-in.
- **NFR:** passwords hashed with argon2id; CSRF protection on forms. **Out of scope:** password reset, OAuth.

### ST-2 Manage subjects — `risk:low`, `spec:auto`
- **AC-1** Given I am signed in, when I create a subject with a name (1–40 chars) and a colour, then it appears in my subject list.
- **AC-2** Given a subject name I already use (case-insensitive), when I create it again, then I get a validation error.
- **AC-3** Given an existing subject, when I rename it, then the new name shows everywhere, including past sessions.
- **AC-4** Given a subject, when I archive it, then it is hidden from the timer picker but its history still counts in reports.
- **AC-5** Given another user's subject id, when I request or modify it, then I get 404.

### ST-3 Study timer — `risk:medium`, `spec:guided`
- **AC-1** Given a subject and no active session, when I press Start, then a session starts with server-side start time.
- **AC-2** Given an active session, when I press Start on any subject, then I am told one session is already running and nothing changes.
- **AC-3** Given an active session, when I Pause and later Resume, then paused time is excluded from the duration.
- **AC-4** Given an active session, when I press Stop, then the session is saved with duration = elapsed − paused, rounded down to the minute.
- **AC-5** Given I reload the page or open another tab, then the running timer shows the correct elapsed time (state is on the server).
- **AC-6** Given a session running > 12 hours, then it is auto-stopped at 12 hours and flagged "auto-stopped".

### ST-4 Manual session log and edit — `risk:low`, `spec:auto`
- **AC-1** Given a subject, when I log a session with date, start and duration (1–720 min), then it is saved and counted in totals.
- **AC-2** Given a manual session that overlaps an existing one, when I save it, then I get a validation error naming the overlap.
- **AC-3** Given a past session, when I edit its duration or subject, then totals update accordingly.
- **AC-4** Given a past session, when I delete it and confirm, then it is removed and totals update.

### ST-5 Dashboard: today and this week — `risk:low`, `spec:auto`
- **AC-1** Given sessions today, when I open the dashboard, then I see total minutes today and a per-subject breakdown.
- **AC-2** Given sessions this ISO week, then I see a 7-day bar breakdown (Mon–Sun) in my configured timezone.
- **AC-3** Given no sessions, then I see an empty state with a "Start studying" call to action.
- **AC-4** Given a session crossing midnight, then minutes are split across the two days.

### ST-6 Daily goal — `risk:low`, `spec:auto`
- **AC-1** Given I set a daily goal (15–720 min), then the dashboard shows progress = today's minutes / goal, capped at 100 % visually.
- **AC-2** Given I reach the goal, then the progress bar shows "Goal reached" for the rest of the day.
- **AC-3** Given no goal set, then the progress widget prompts me to set one.
- **AC-4** Given a goal outside 15–720, then I get a validation error.

### ST-7 Weekly plan — `risk:medium`, `spec:guided`
- **AC-1** Given a subject, when I add a planned block (weekday, start, duration), then it appears on the week view.
- **AC-2** Given planned blocks and actual sessions, then the week view shows planned vs actual minutes per subject.
- **AC-3** Given overlapping planned blocks, then I get a validation error.
- **AC-4** Given I copy last week's plan, then all blocks are duplicated into the current week without duplicates if run twice (idempotent).

### ST-8 Pomodoro mode — `risk:low`, `spec:auto`
- **AC-1** Given Pomodoro mode on, when I start, then a 25-minute focus interval runs, followed by a 5-minute break (both configurable 5–90 / 1–30).
- **AC-2** Given a focus interval completes, then its minutes are recorded as a session; break minutes are not.
- **AC-3** Given I stop mid-interval, then only elapsed focus minutes are recorded.

### ST-9 CSV export — `risk:low`, `spec:auto`
- **AC-1** Given a date range, when I export, then I download a CSV with date, subject, start, end, minutes, source (timer/manual/pomodoro).
- **AC-2** Given a range > 366 days, then I get a validation error.
- **AC-3** Given subject names containing commas, quotes or a leading `=`, then the CSV is correctly escaped and formula-injection safe.

## 4. Seed platform stories (examples of the template; full set written per iteration)

### IDP-? Add quarantine-share criterion X16 to G3 — `component:gatekeeper`, `layer:policy`, `risk:medium`, `spec:guided`
Mirrors design doc §21.3 (IDP-214) verbatim. It proves that policy changes go through the same flow, with the customer-reviewer rule
replaced by the CODEOWNER on `policy/`.

### IDP-? Seeded-defect drill — `component:pipeline`, `risk:low`
A story that intentionally introduces an N+1 query behind a flag. It is used to demonstrate that G3 holds the release with trace evidence (S4).
