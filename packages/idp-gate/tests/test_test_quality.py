from pathlib import Path

import pytest

from idp_gate.cli import main
from idp_gate.test_quality import lint_source

BAD = """
import time
def test_nothing():
    x = 1
def test_constant():
    assert True
def test_status_only(api):
    r = api.get("/x")
    assert r.status_code == 200
def test_sleepy():
    time.sleep(2)
    assert 1 + 1 == 2
def helper_not_a_test():
    pass
"""

GOOD = """
import pytest
def test_behaviour(api):
    r = api.get("/x")
    assert r.status_code == 200
    assert r.json()["total_cents"] == 9800
def test_raises():
    with pytest.raises(ValueError):
        int("x")
"""


@pytest.mark.ac("IDP-8:AC-2")
def test_flags_every_weak_test_pattern() -> None:
    messages = [p.message for p in lint_source(BAD, "bad.py")]
    assert messages == [
        "test_nothing: no assertions",
        "test_constant: constant-true assertion",
        "test_status_only: asserts status code only",
        "test_sleepy: sleep() used; use a condition-based wait",
    ]


@pytest.mark.ac("IDP-8:AC-2")
def test_meaningful_tests_pass_clean() -> None:
    assert lint_source(GOOD, "good.py") == []


@pytest.mark.ac("IDP-8:AC-2")
def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad, good = tmp_path / "test_bad.py", tmp_path / "test_good.py"
    bad.write_text(BAD)
    good.write_text(GOOD)
    assert main(["test-quality-lint", str(good)]) == 0
    assert main(["test-quality-lint", str(bad), str(good)]) == 1
    assert f"{bad}:3: test_nothing: no assertions" in capsys.readouterr().out
