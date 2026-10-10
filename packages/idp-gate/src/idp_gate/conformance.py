"""Conformance runner (IDP-19): `idp validate` and `make verify` for every example directory with an `idp.yaml`.

IDP-22: an example that is a symlink or resolves outside the examples directory fails before anything runs, and
`make verify` reads only the validated Makefile (`-f Makefile`). The Makefile and every literal include word the scan
saw are pinned with `--assume-old=<word>`, so make neither remakes them nor restarts with unvalidated content.
Residual risk: dynamic includes (`$(...)` words, e.g. `$(IDP_PROFILE_DIR)/defaults.mk`) are not pinned."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess  # nosec B404 - list-form argv for make (no shell); see _run_make_verify for the trust assumption
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from idp_gate import contract, profiles

MAKE_TIMEOUT_S = 60
MAX_ASSUME_OLD_BYTES = 64 * 1024  # summed UTF-8 length of the `--assume-old=` arguments
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


def _tail(output: str) -> tuple[str, ...]:
    return tuple(output.splitlines()[-OUTPUT_TAIL_LINES:])


def _assume_old(words: tuple[str, ...]) -> list[str] | None:
    """`--assume-old=` arguments for `Makefile` and each include word (plus its `./`-stripped spelling), in order
    and without duplicates; None if they exceed MAX_ASSUME_OLD_BYTES."""
    names = [contract.MAKE_PATH]
    for word in words:
        names.append(word)
        stripped = word
        while stripped.startswith("./"):
            stripped = stripped[2:]
        if word.startswith("./") and stripped:
            names.append(stripped)
    args = [f"--assume-old={n}" for n in dict.fromkeys(names)]
    return None if sum(len(a.encode("utf-8")) for a in args) > MAX_ASSUME_OLD_BYTES else args


def _invalid(directory: Path, violations: Sequence[contract.Violation]) -> Result:
    reason = f"idp validate: {len(violations)} violation(s)"
    return Result(directory, ok=False, reason=reason, details=tuple(str(v) for v in violations))


def _run_make_verify(directory: Path, make: str, profile_dir: str, assume_old: list[str]) -> Result:
    # `-f Makefile`: make reads only the validated Makefile, never a GNUmakefile/makefile beside it.
    argv = [
        make,
        "--no-print-directory",
        "-C",
        str(directory),
        "-f",
        contract.MAKE_PATH,
        *assume_old,
        "verify",
        f"IDP_PROFILE_DIR={profile_dir}",
    ]
    try:
        # List-form argv, no shell for argv; `make` is an absolute path from shutil.which. make itself runs the
        # example's recipes via /bin/sh: examples/ is platform-owned (reviewed like code), not tenant-contributed.
        # New session so a timeout can kill the whole process group (make and any recipe children, e.g. a server).
        proc = subprocess.Popen(  # noqa: S603  # nosec B603
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=_make_env(),
            start_new_session=True,
        )
    except OSError as exc:
        return Result(directory, ok=False, reason=f"make verify could not run: {exc}")
    try:
        output, _ = proc.communicate(timeout=MAKE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate()
        reason = f"make verify timed out after {MAKE_TIMEOUT_S} s"
        return Result(directory, ok=False, reason=reason, details=_tail(output or ""))
    if proc.returncode != 0:
        return Result(directory, ok=False, reason=f"make verify exited {proc.returncode}", details=_tail(output))
    return Result(directory, ok=True)


def _outside(directory: Path, root: Path) -> bool:
    """True if `directory` is a symlink or its real path is not under `root`'s; fails closed if resolution fails."""
    if directory.is_symlink():
        return True
    try:
        return not directory.resolve(strict=True).is_relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError):
        return True


def check_example(directory: Path, make: str, root: Path) -> Result:
    """Check `directory` is confined to `root`, validate the contract, resolve the build profile, then run
    `make verify`; the first failing step decides."""
    if _outside(directory, root):
        return Result(directory, ok=False, reason="outside examples directory")
    path = directory / EXAMPLE_FILE
    doc, violations = contract.load_service(path)
    if violations:
        return _invalid(directory, violations)
    try:
        profile_dir = str(profiles.resolve(doc["spec"]["build"]["profile"])["dir"])
    except profiles.ProfileError as exc:
        return Result(directory, ok=False, reason="profile: " + "; ".join(exc.lines))
    scan = contract.makefile_targets(directory / contract.MAKE_PATH)  # include words to pin; files may have changed
    if scan.violations:
        return _invalid(directory, scan.violations)
    assume_old = _assume_old(scan.include_words)
    if assume_old is None:
        return Result(directory, ok=False, reason="include words exceed the make argument limit")
    return _run_make_verify(directory, make, profile_dir, assume_old)
