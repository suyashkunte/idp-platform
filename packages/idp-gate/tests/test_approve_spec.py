import hashlib
import json
from pathlib import Path

import pytest

from idp_gate import approve_spec
from idp_gate.cli import main


def _spec(root: Path, key: str = "IDP-42") -> Path:
    folder = root / "specs" / key
    folder.mkdir(parents=True)
    spec = folder / "spec.md"
    spec.write_text("- **AC-1** something\n")
    return spec


@pytest.mark.ac("IDP-8:AC-3")
def test_refused_inside_agent_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _spec(tmp_path)
    monkeypatch.setenv("CLAUDECODE", "1")
    assert main(["approve-spec", "IDP-42", "--root", str(tmp_path)]) == 2
    assert not (tmp_path / "specs" / "IDP-42" / "APPROVED").exists()


@pytest.mark.ac("IDP-8:AC-4")
def test_human_approval_records_identity_time_and_hash(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    marker = approve_spec.approve("IDP-42", tmp_path, env={})
    record = json.loads(marker.read_text())
    assert record["ticket"] == "IDP-42"
    assert record["spec_sha256"] == hashlib.sha256(spec.read_bytes()).hexdigest()
    assert set(record["approver"]) == {"name", "email"}
    assert record["approved_at"].endswith("+00:00")
    assert approve_spec.is_current("IDP-42", tmp_path)


@pytest.mark.ac("IDP-8:AC-4")
def test_editing_spec_after_approval_invalidates_it(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    approve_spec.approve("IDP-42", tmp_path, env={})
    spec.write_text("- **AC-1** something else\n")
    assert not approve_spec.is_current("IDP-42", tmp_path)


def test_missing_spec_is_refused(tmp_path: Path) -> None:
    with pytest.raises(approve_spec.ApprovalRefused, match="spec not found"):
        approve_spec.approve("IDP-9", tmp_path, env={})


def test_agent_markers_detected() -> None:
    assert approve_spec.in_agent_session({"CLAUDE_CODE_ENTRYPOINT": "cli"})
    assert not approve_spec.in_agent_session({"HOME": "/x"})
