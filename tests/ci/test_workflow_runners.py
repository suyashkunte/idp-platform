"""IDP-12: every GitHub Actions job must run on a pinned ``ubuntu-24.04`` runner (no ``*-latest`` labels)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_RUNNERS = {"ubuntu-24.04"}
USE = "use 'ubuntu-24.04'"


def workflow_files(root: Path) -> list[Path]:
    """Workflow files GitHub runs: ``*.yml`` / ``*.yaml`` directly under ``.github/workflows/`` (not recursive)."""
    wf = root / ".github" / "workflows"
    return sorted(p for p in wf.glob("*") if p.is_file() and p.suffix in {".yml", ".yaml"})


def _labels_ok(value: Any) -> bool:
    if isinstance(value, str):
        return "${{" not in value and value in ALLOWED_RUNNERS
    if isinstance(value, list):
        return bool(value) and all(isinstance(v, str) and _labels_ok(v) for v in value)
    return False


def runs_on_problem(job: dict[str, Any]) -> str | None:
    """Return the problem with a job's ``runs-on`` (without file/job prefix), or None if it is allowed."""
    if "uses" in job:
        return None
    if "runs-on" not in job:
        return f"runs-on is missing; {USE}"
    value = job["runs-on"]
    labels = value.get("labels") if isinstance(value, dict) else value
    if _labels_ok(labels):
        return None
    return f"runs-on {value!r} is not allowed; {USE}"


def runner_violations(root: Path) -> list[str]:
    """Every violating job across all workflow files, as ``<rel path>: job '<id>': <problem>``, sorted."""
    out: list[str] = []
    for path in workflow_files(root):
        rel = path.relative_to(root).as_posix()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, dict):
            out.append(f"{rel}: jobs is missing or not a mapping")
            continue
        for job_id, job in jobs.items():
            problem = runs_on_problem(job if isinstance(job, dict) else {})
            if problem:
                out.append(f"{rel}: job '{job_id}': {problem}")
    return sorted(out)


def _write_workflow(root: Path, name: str, jobs: str) -> None:
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(f"name: t\non: push\njobs:\n{jobs}", encoding="utf-8")


# --- synthetic inputs (T1) -------------------------------------------------------------------------------------------


@pytest.mark.ac("IDP-12:AC-1")
@pytest.mark.ac("IDP-12:AC-2")
@pytest.mark.parametrize(
    ("job", "expected"),
    [
        ({"runs-on": "ubuntu-24.04"}, None),
        ({"runs-on": ["ubuntu-24.04"]}, None),
        ({"runs-on": {"labels": "ubuntu-24.04"}}, None),
        ({"runs-on": {"group": "g", "labels": ["ubuntu-24.04"]}}, None),
        ({"uses": "org/repo/.github/workflows/x.yml@v1"}, None),
        ({"runs-on": "ubuntu-latest"}, "runs-on 'ubuntu-latest' is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": ["ubuntu-latest"]}, "runs-on ['ubuntu-latest'] is not allowed; use 'ubuntu-24.04'"),
        (
            {"runs-on": ["ubuntu-24.04", "ubuntu-latest"]},
            "runs-on ['ubuntu-24.04', 'ubuntu-latest'] is not allowed; use 'ubuntu-24.04'",
        ),
        ({"runs-on": "macos-latest"}, "runs-on 'macos-latest' is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": "windows-latest"}, "runs-on 'windows-latest' is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": "ubuntu-22.04"}, "runs-on 'ubuntu-22.04' is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": "self-hosted"}, "runs-on 'self-hosted' is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": "${{ matrix.os }}"}, "runs-on '${{ matrix.os }}' is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": {"group": "g"}}, "runs-on {'group': 'g'} is not allowed; use 'ubuntu-24.04'"),
        (
            {"runs-on": {"labels": "ubuntu-latest"}},
            "runs-on {'labels': 'ubuntu-latest'} is not allowed; use 'ubuntu-24.04'",
        ),
        ({"runs-on": []}, "runs-on [] is not allowed; use 'ubuntu-24.04'"),
        ({"runs-on": 42}, "runs-on 42 is not allowed; use 'ubuntu-24.04'"),
        ({"timeout-minutes": 5}, "runs-on is missing; use 'ubuntu-24.04'"),
    ],
)
def test_runs_on_rule_accepts_pinned_and_rejects_others(job: dict[str, Any], expected: str | None) -> None:
    assert runs_on_problem(job) == expected


@pytest.mark.ac("IDP-12:AC-2")
def test_ubuntu_latest_is_reported_with_file_and_job(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "bad.yml", "  build:\n    runs-on: ubuntu-latest\n    steps: []\n")
    assert runner_violations(tmp_path) == [
        ".github/workflows/bad.yml: job 'build': runs-on 'ubuntu-latest' is not allowed; use 'ubuntu-24.04'"
    ]


@pytest.mark.ac("IDP-12:AC-2")
def test_all_violations_reported_in_one_run(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "a.yml", "  ok:\n    runs-on: ubuntu-24.04\n  lint:\n    runs-on: 'ubuntu-latest'\n")
    _write_workflow(tmp_path, "b.yaml", "  test:\n    runs-on: [macos-latest]\n")
    nested = tmp_path / ".github" / "workflows" / "sub"
    nested.mkdir()
    (nested / "ignored.yml").write_text("jobs:\n  x:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
    assert runner_violations(tmp_path) == [
        ".github/workflows/a.yml: job 'lint': runs-on 'ubuntu-latest' is not allowed; use 'ubuntu-24.04'",
        ".github/workflows/b.yaml: job 'test': runs-on ['macos-latest'] is not allowed; use 'ubuntu-24.04'",
    ]


@pytest.mark.ac("IDP-12:AC-2")
def test_workflow_without_jobs_mapping_is_reported_by_file(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "list.yml").write_text("- not\n- a mapping\n", encoding="utf-8")
    (wf / "nojobs.yml").write_text("name: t\njobs: [build]\n", encoding="utf-8")
    assert runner_violations(tmp_path) == [
        ".github/workflows/list.yml: jobs is missing or not a mapping",
        ".github/workflows/nojobs.yml: jobs is missing or not a mapping",
    ]


# --- real repository (T3) --------------------------------------------------------------------------------------------


@pytest.mark.ac("IDP-12:AC-1")
def test_every_workflow_job_runs_on_ubuntu_24_04() -> None:
    assert workflow_files(ROOT) != [], "no workflow files found under .github/workflows/"
    violations = runner_violations(ROOT)
    assert violations == [], "\n".join(violations)


@pytest.mark.ac("IDP-12:AC-3")
def test_required_and_smoke_jobs_exist_and_are_pinned() -> None:
    wf = ROOT / ".github" / "workflows"
    ci = yaml.safe_load((wf / "platform-ci.yml").read_text(encoding="utf-8"))
    smoke = yaml.safe_load((wf / "oidc-smoke.yml").read_text(encoding="utf-8"))
    assert [
        ("platform-ci.yml", "verify", ci["jobs"]["verify"]["runs-on"]),
        ("oidc-smoke.yml", "assume-role", smoke["jobs"]["assume-role"]["runs-on"]),
    ] == [
        ("platform-ci.yml", "verify", "ubuntu-24.04"),
        ("oidc-smoke.yml", "assume-role", "ubuntu-24.04"),
    ]
