"""idp-gate build hook: ship allow-listed build profiles in the sdist and the wheel (IDP-21, IDP-24, ADR-0012)."""

import os
from pathlib import Path
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ALLOWED_SUFFIXES = frozenset({".yaml", ".mk", ".md"})
SDIST_DIR = "build-profiles"
WHEEL_DIR = "idp_gate/build_profiles"
TARGET_DIRS = {"wheel": WHEEL_DIR, "sdist": SDIST_DIR}


def profiles_source(project_root: Path) -> Path:
    """`<root>/build-profiles` first, then the checkout's `<root>/../../build-profiles`.

    Inside an unpacked sdist (`<root>/PKG-INFO` exists) only the sdist copy counts: never look outside the sdist.
    A symlinked candidate fails closed, with no fallback to the next candidate (IDP-24).
    """
    candidates = [project_root / SDIST_DIR]
    if not (project_root / "PKG-INFO").is_file():
        candidates.append(project_root.parent.parent / SDIST_DIR)
    for candidate in candidates:
        if candidate.is_symlink():
            raise RuntimeError(
                f"idp-gate build: build profiles source is a symlink, refusing to follow it: {candidate}"
            )
        if candidate.is_dir():
            return candidate
    looked_in = ", ".join(map(str, candidates))
    raise RuntimeError(f"idp-gate build: build profiles not found (looked in: {looked_in})")


def _is_allowed(path: Path, rel: Path) -> bool:
    """A regular, non-symlink *.yaml/*.mk/*.md file with no dot-prefixed path component."""
    if path.is_symlink() or not path.is_file():
        return False
    if any(part.startswith(".") for part in rel.parts):
        return False
    return path.suffix in ALLOWED_SUFFIXES


def select_profile_files(source: Path) -> list[Path]:
    """Sorted relative paths of the allow-listed profile files; fails closed if no `*/profile.yaml` is selected.

    The walk never descends into symlinked directories (IDP-24); file symlinks are rejected by `_is_allowed`.
    """
    paths = (Path(dirpath) / name for dirpath, _, filenames in os.walk(source, followlinks=False) for name in filenames)
    selected = sorted(rel for path in paths if _is_allowed(path, rel := path.relative_to(source)))
    if not any(len(rel.parts) == 2 and rel.name == "profile.yaml" for rel in selected):
        raise RuntimeError(f"idp-gate build: no */profile.yaml selected in {source}")
    return selected


class ProfilesBuildHook(BuildHookInterface[BuilderConfig]):
    """Adds the selected profile files to the sdist (`build-profiles/`) or the wheel (`idp_gate/build_profiles/`)."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        source = profiles_source(Path(self.root))
        prefix = TARGET_DIRS.get(self.target_name)
        if prefix is None:
            raise RuntimeError(f"idp-gate build: unsupported build target {self.target_name}")
        for rel in select_profile_files(source):
            build_data["force_include"][str(source / rel)] = f"{prefix}/{rel.as_posix()}"
