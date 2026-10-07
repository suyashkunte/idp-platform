"""Build profiles (`build-profiles/<name>/profile.yaml`) validated against schema build-profile.v1 (ADR-0012)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from idp_gate import contract

PROFILE_SCHEMA_ID = "build-profile.v1"
PROFILE_SCHEMA_NAME = f"{PROFILE_SCHEMA_ID}.json"
PROFILE_FILE = "profile.yaml"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
_CHECKOUT_MARKER = ("packages", "idp-gate", "pyproject.toml")


def _checkout_dir(module_file: Path) -> Path | None:
    """`<repo>/build-profiles` when `module_file` is `<repo>/packages/idp-gate/src/idp_gate/<module>.py`, else None.

    Only this repository's own source tree qualifies (editable workspace install); shallow layouts
    (`pip install --target`) and site-packages never pick up an unrelated `build-profiles/` four levels up."""
    parents = module_file.parents
    if len(parents) < 5:
        return None
    repo = parents[4]
    return repo / "build-profiles" if repo.joinpath(*_CHECKOUT_MARKER).is_file() else None


# Installed wheel: profiles are force-included next to the package (see packages/idp-gate/pyproject.toml).
_PACKAGED_DIR = Path(__file__).resolve().parent / "build_profiles"
# Editable workspace install: `idp_gate` is imported from packages/idp-gate/src/, so use the repo checkout.
_CHECKOUT_DIR: Path | None = _checkout_dir(Path(__file__).resolve())


class ProfileError(Exception):
    """A profile could not be resolved; `lines` are the reasons, one per line."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__("\n".join(lines))
        self.lines = lines


def profiles_root() -> Path:
    """The first existing profiles directory: packaged, then checkout (roots are not merged)."""
    candidates = [c for c in (_PACKAGED_DIR, _CHECKOUT_DIR) if c is not None]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ProfileError([f"no build profiles found (looked in: {', '.join(str(c) for c in candidates)})"])


def available(root: Path) -> list[str]:
    """Sorted names of the subdirectories of `root` that contain a profile file."""
    return sorted(p.name for p in root.iterdir() if (p / PROFILE_FILE).is_file())


def validate_profile_document(doc: Any, dirname: str) -> list[contract.Violation]:
    """Schema violations of `doc`, then a violation at `name` if it differs from the profile's directory name."""
    validator = Draft202012Validator(contract.load_schema(PROFILE_SCHEMA_NAME))
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    violations = [contract.Violation(".".join(str(p) for p in e.absolute_path), e.message) for e in errors]
    name = doc.get("name") if isinstance(doc, dict) else None
    if isinstance(name, str) and name != dirname:
        violations.append(contract.Violation("name", f"name {name!r} does not match directory {dirname!r}"))
    return violations


def load(name: str) -> tuple[Path, dict[str, Any]]:
    """The directory and validated document of profile `name`; the name is checked before any filesystem access."""
    if not _NAME.fullmatch(name):
        raise ProfileError([f"invalid profile name {name!r}"])
    root = profiles_root()
    directory = root / name
    path = directory / PROFILE_FILE
    if not path.is_file():
        raise ProfileError([f"{name!r} not found (available: {', '.join(available(root))})"])
    try:
        doc, violations = contract._load_yaml(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise ProfileError([f"cannot read {name!r}: {exc}"]) from exc
    violations = violations or validate_profile_document(doc, name)
    if violations:
        raise ProfileError([f"{name!r} is invalid ({PROFILE_SCHEMA_ID}): {v}" for v in violations])
    document: dict[str, Any] = doc
    return directory, document


def resolve(name: str) -> dict[str, Any]:
    """The profile document as loaded, plus `dir`: the absolute path of the profile directory."""
    directory, doc = load(name)
    return {**doc, "dir": str(directory)}
