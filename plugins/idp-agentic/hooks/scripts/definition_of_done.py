#!/usr/bin/env python3
"""Stop hook: while working a ticket, the agent may not declare victory until the Definition of Done checks pass.

Active only on a branch `feature/<KEY>-...` with `specs/<KEY>/spec.md` and work not yet pushed. Runs the Make
contract (`make spec-trace KEY=...`, then `make verify-fast` if defined). On failure it blocks once (exit 2) with the
output; if Claude is already continuing because of this hook (`stop_hook_active`), it never blocks again (no loops).
Stdlib only, Python 3.9+.
"""

import json
import os
import re
import subprocess
import sys

BRANCH = re.compile(r"^feature/([A-Z][A-Z0-9]+-\d+)")
MAX_OUTPUT = 4000


def sh(args, cwd, timeout=540):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def has_unpushed_work(root):
    code, out = sh(["git", "status", "--porcelain"], root, 10)
    if code == 0 and out.strip():
        return True
    code, out = sh(["git", "rev-list", "--count", "@{upstream}..HEAD"], root, 10)
    return code != 0 or out.strip() != "0"  # no upstream yet, or commits ahead


def make_has(root, target):
    try:
        with open(os.path.join(root, "Makefile"), encoding="utf-8") as fh:
            return re.search(r"^{}:".format(re.escape(target)), fh.read(), re.MULTILINE) is not None
    except OSError:
        return False


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    code, root = sh(["git", "rev-parse", "--show-toplevel"], cwd, 10)
    if code != 0:
        return 0
    root = root.strip()
    _, branch = sh(["git", "branch", "--show-current"], root, 10)
    m = BRANCH.match(branch.strip())
    if not m or not os.path.isfile(os.path.join(root, "specs", m.group(1), "spec.md")):
        return 0
    if not has_unpushed_work(root):
        return 0
    key = m.group(1)
    checks = [["make", "-s", "spec-trace", "KEY=" + key]]
    if make_has(root, "verify-fast"):
        checks.append(["make", "-s", "verify-fast"])
    for cmd in checks:
        try:
            code, out = sh(cmd, root)
        except subprocess.TimeoutExpired:
            sys.stderr.write("Definition of Done check timed out: {}\n".format(" ".join(cmd)))
            return 2
        if code != 0:
            sys.stderr.write(
                "Definition of Done NOT met for {} (`{}` failed). Keep working; do not lower thresholds or skip "
                "tests.\n{}\n".format(key, " ".join(cmd), out[-MAX_OUTPUT:])
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
