"""Human spec approval (design doc §21.7 step 4). Agents must never create the APPROVED marker.

Defence in depth: the plugin's permission deny-list and PreToolUse hook block agents from running this, and the
command itself refuses inside a Claude Code session (``CLAUDECODE=1`` is set in its Bash tool environment).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess  # nosec B404 - only fixed git commands, no shell
from datetime import UTC, datetime
from pathlib import Path

AGENT_ENV_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")


class ApprovalRefused(Exception):
    """Raised when approval is attempted from an agent session or without a spec."""


def in_agent_session(env: dict[str, str] | None = None) -> bool:
    env = dict(os.environ) if env is None else env
    return any(env.get(k) for k in AGENT_ENV_MARKERS)


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607  # nosec B603 B607
    return out.stdout.strip()


def approve(ticket: str, repo_root: Path = Path(), env: dict[str, str] | None = None) -> Path:
    if in_agent_session(env):
        raise ApprovalRefused("approve-spec is a human checkpoint and is refused inside an agent session")
    spec = repo_root / "specs" / ticket / "spec.md"
    if not spec.is_file():
        raise ApprovalRefused(f"spec not found: {spec}")
    record = {
        "ticket": ticket,
        "approver": {"name": _git("config", "user.name"), "email": _git("config", "user.email")},
        "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
        "head_commit": _git("rev-parse", "HEAD"),
    }
    marker = spec.parent / "APPROVED"
    marker.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return marker


def is_current(ticket: str, repo_root: Path = Path()) -> bool:
    """True when an APPROVED marker exists and still matches the spec content (spec unchanged since approval)."""
    folder = repo_root / "specs" / ticket
    marker, spec = folder / "APPROVED", folder / "spec.md"
    if not (marker.is_file() and spec.is_file()):
        return False
    recorded = json.loads(marker.read_text(encoding="utf-8")).get("spec_sha256")
    return bool(recorded == hashlib.sha256(spec.read_bytes()).hexdigest())
