#!/usr/bin/env python3
"""PreToolUse guard for Bash: block commands that bypass human checkpoints or change shared state (exit 2 = block).

Defence in depth behind the permission deny-list and GitHub rulesets. Stdlib only, Python 3.9+.
"""

import json
import re
import sys

RULES = [
    (r"\bgit\s+push\b[^;&|]*\s(--force(-with-lease)?|-f)\b", "force-push is never allowed"),
    (r"\bgit\s+push\b[^;&|]*\b(HEAD:|refs/heads/)?(main|master)\b", "push to main: changes reach main only via a PR"),
    (r"\bgit\s+(commit|push)\b[^;&|]*--no-verify\b", "skipping git hooks is not allowed"),
    (r"\bgit\s+config\b[^;&|]*core\.hooksPath", "changing git hook configuration is not allowed"),
    (r"\bgh\s+pr\s+merge\b", "merging is a human decision (checkpoint B)"),
    (r"\bgh\s+pr\s+review\b[^;&|]*(--approve|\s-a\b)", "approving PRs is a human decision"),
    (
        r"\bgh\s+api\b[^;&|]*(/merge\b|/reviews\b|/rulesets\b|/branches/[^ ]+/protection)",
        "merge/approve/protection via API",
    ),
    (r"\b(make|uv\s+run\s+make)\s+approve-spec\b|\bidp\s+approve-spec\b", "spec approval is a human checkpoint (A)"),
    (r"specs/[^/\s]+/APPROVED", "the APPROVED marker is written only by `make approve-spec`, run by a human"),
    (
        r"\bterraform\s+(apply|destroy|import|state\s+(rm|mv|push|replace-provider))\b",
        "infrastructure changes run in CI",
    ),
    (
        r"\bkubectl\s+(apply|create|delete|edit|patch|replace|scale|label|annotate|drain|cordon|"
        r"rollout\s+(restart|undo))\b",
        "cluster changes are made by the pipeline, not the agent",
    ),
    (r"\bhelm\s+(install|upgrade|uninstall|delete|rollback)\b", "deployments are made by the pipeline"),
    (
        r"\baws\s+\S+\s+(create|delete|put|update|terminate|modify|attach|detach|run|start|stop|reboot|remove|add|"
        r"associate|disassociate|enable|disable|tag|untag)-",
        "mutating AWS calls are made by the pipeline",
    ),
    (r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(/|~|\$HOME|\.)(\s|$)", "recursive delete of a root, home or repo directory"),
    (r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z)?sh\b", "piping downloads into a shell"),
    (
        r"(>|\btee\b|\bsed\s+-i|\bcp\b|\bmv\b|\brm\b)[^;&|]*"
        r"(\.github/|\.claude/settings\.json|\.claude/idp-protected-paths)",
        "writing protected paths via the shell",
    ),
]
COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in RULES]


def check(command):
    for rx, why in COMPILED:
        if rx.search(command):
            return why
    return None


def main():
    data = json.load(sys.stdin)
    command = (data.get("tool_input") or {}).get("command") or ""
    why = check(command)
    if why:
        sys.stderr.write(
            "BLOCKED by idp-agentic: {}.\nCommand: {}\nAgents prepare work; people merge, approve and deploy. "
            "Explain to the user what you wanted to do instead.\n".format(why, command)
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
