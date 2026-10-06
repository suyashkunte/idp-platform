#!/usr/bin/env python3
"""PreToolUse guard for Edit/Write/MultiEdit/NotebookEdit: block edits to protected paths (exit 2 = block).

Protected globs = built-in defaults + one glob per line in <repo>/.claude/idp-protected-paths.txt.
Stdlib only, Python 3.9+: hooks run before any project virtualenv exists.
"""

import fnmatch
import json
import os
import subprocess
import sys

DEFAULTS = [
    ".git/**",
    ".github/**",
    ".claude/settings.json",
    ".claude/idp-protected-paths.txt",
    "specs/*/APPROVED",
]
PROTECTED_LIST = os.path.join(".claude", "idp-protected-paths.txt")


def repo_root(cwd):
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def protected_globs(root):
    globs = list(DEFAULTS)
    path = os.path.join(root, PROTECTED_LIST)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    globs.append(line)
    return globs


def matches(rel, globs):
    rel = rel.replace(os.sep, "/")
    for g in globs:
        if fnmatch.fnmatchcase(rel, g) or (g.endswith("/**") and rel == g[:-3]):
            return g
    return None


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    root = repo_root(cwd)
    absolute = os.path.realpath(os.path.join(cwd, target))
    rel = os.path.relpath(absolute, os.path.realpath(root))
    if rel.startswith(".."):
        return 0  # outside the repository: not ours to police
    hit = matches(rel, protected_globs(root))
    if hit:
        sys.stderr.write(
            "BLOCKED by idp-agentic: '{}' is protected (matches '{}'). A human must change it through a reviewed PR "
            "(see CODEOWNERS). If the ticket genuinely requires this change, stop and tell the user.\n".format(rel, hit)
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
