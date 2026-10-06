---
name: create-story
description: Help a human write a hardened, Ready tracker ticket (context, Given/When/Then ACs with an edge case, NFRs, out of scope, dependencies, test approach, labels) and create it via MCP after confirmation. Use when the user wants to create a story, task or bug.
---

# Create a hardened ticket

1. Ask for or derive: goal, user, the behaviour change, constraints.
2. Draft using the hardened template: Context/why · Acceptance criteria (`AC-n`, Given/When/Then, ≥ 1 negative or edge
   case) · Non-functional criteria · Out of scope · Interfaces/dependencies · Test approach · Definition of Done ·
   Labels (`repo:*`, `component:*`, `risk:*`, `spec:auto|guided`).
3. Show the draft and get the user's confirmation, then create it with the Atlassian MCP (`createJiraIssue`, parent epic if
   given). Report the key.
