"""Conformance runner (IDP-19): `idp validate` and `make verify` for every example directory with an `idp.yaml`."""

from __future__ import annotations

import os
import subprocess  # nosec B404 - only a fixed make invocation, no shell
from dataclasses import dataclass
from pathlib import Path

from idp_gate import contract, profiles

MAKE_TIMEOUT_S = 60
OUTPUT_TAIL_LINES = 40
EXAMPLE_FILE = "idp.yaml"
# Inherited make state must not change the example's run (outer `make -n/-k/-j`, MAKEFILES).
_MAKE_ENV_STRIPPED = frozenset({"MAKEFLAGS", "GNUMAKEFLAGS", "MAKELEVEL", "MFLAGS", "MAKEFILES"})


@dataclass(frozen=True)
class Result:
    example: Path
    ok: bool
    reason: str = ""
    details: tuple[str, ...] = ()

    def lines(self) -> list[str]:
        """`PASS <example>`, or `FAIL <example>: <reason>` followed by the details indented by 4 spaces."""
        if self.ok:
            return [f"PASS {self.example}"]
        return [f"FAIL {self.example}: {self.reason}", *(f"    {d}" for d in self.details)]


def find_examples(root: Path) -> list[Path]:
    """Sorted immediate subdirectories of `root` that contain an `idp.yaml`; dot-directories are skipped."""
    return sorted(
        p for p in root.iterdir() if not p.name.startswith(".") and p.is_dir() and (p / EXAMPLE_FILE).is_file()
    )


def _make_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _MAKE_ENV_STRIPPED}


def _run_make_verify(directory: Path, make: str, profile_dir: str) -> Result:
    argv = [make, "--no-print-directory", "-C", str(directory), "verify", f"IDP_PROFILE_DIR={profile_dir}"]
    try:
        # Fixed argv (no shell); `make` is an absolute path from shutil.which.
        out = subprocess.run(  # noqa: S603  # nosec B603
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=_make_env(),
            timeout=MAKE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(directory, ok=False, reason=f"make verify timed out after {MAKE_TIMEOUT_S} s")
    if out.returncode != 0:
        tail = tuple(out.stdout.splitlines()[-OUTPUT_TAIL_LINES:])
        return Result(directory, ok=False, reason=f"make verify exited {out.returncode}", details=tail)
    return Result(directory, ok=True)


def check_example(directory: Path, make: str) -> Result:
    """Validate the contract, resolve the build profile, then run `make verify`; the first failing step decides."""
    path = directory / EXAMPLE_FILE
    violations = contract.validate_service(path)
    if violations:
        reason = f"idp validate: {len(violations)} violation(s)"
        return Result(directory, ok=False, reason=reason, details=tuple(str(v) for v in violations))
    doc, _ = contract._load_yaml(path)
    try:
        profile_dir = str(profiles.resolve(doc["spec"]["build"]["profile"])["dir"])
    except profiles.ProfileError as exc:
        return Result(directory, ok=False, reason="profile: " + "; ".join(exc.lines))
    return _run_make_verify(directory, make, profile_dir)
