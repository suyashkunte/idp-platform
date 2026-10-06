# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-10-06
- **Deciders:** Suyash Kunte

## Context
The project needs a durable record of why things are the way they are, readable by humans and agents.
## Decision
Use MADR-style ADRs in `docs/adr/`, numbered sequentially. Any change to an Accepted ADR needs a new ADR that supersedes it. Agents may draft ADRs (doc-upkeeper); humans accept them in PR review.
## Consequences
Design rationale lives next to the code; `CLAUDE.md` points agents here before design work.
