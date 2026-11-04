# Tracker archive (Jira export)

The project tracked its work in Jira (site `suyashkunte.atlassian.net`, project `IDP`) until 2026-11-04, when the
Jira subscription ended. This folder is a complete export of that project, taken on 2026-11-04 through the
Atlassian MCP while the site was still reachable.

| Path | What it holds |
|---|---|
| [index.md](index.md) | All tickets in one table per epic, with type, status, risk label and summary |
| `issues/IDP-N.md` | One file per ticket: front matter (key, type, status, summary, parent, labels, priority, resolution, reporter, assignee, dates, links, original Jira URL), then the description and every comment, as Markdown |
| `raw/IDP-N.json` | **Local only, not in git** (`.gitignore`d, because it holds account e-mail addresses and IDs and this repo is public). The same ticket as Jira returned it (all fields, rich text in Atlassian Document Format), one compact JSON object per file, kept by the maintainer for any later import into another tracker |

## Export facts

- 40 tickets: IDP-5 to IDP-44. The search returned no IDP-1 to IDP-4.
- Status at export: Done 19, In Progress 1 (IDP-20), To Do 20.
- 42 comments, 46 issue links, 0 attachments. No ticket had more comments than were returned.

## Not included

- Status history (transition dates and who moved a ticket) and the field change log. Jira's search API does not return
  them, and they were not exported separately. Created, updated and resolved dates are in each file.
- Jira-only configuration: workflows, boards, sprints, filters.

## Links in older documents

Specs, PRs, memory notes and docs refer to tickets by key (e.g. `IDP-14`) and sometimes by Jira URL. Jira URLs no
longer resolve; find the ticket here as `issues/<KEY>.md`.
