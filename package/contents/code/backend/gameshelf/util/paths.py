# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Resolution of launcher install locations (native, Flatpak or user-supplied)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

__all__ = [
    "home",
    "xdg_config_home",
    "xdg_data_home",
    "xdg_cache_home",
    "resolve_roots",
    "is_flatpak_root",
    "first_on_path",
    "flatpak_run_command",
    "package_contents",
]

INSTALL_TYPES = ("auto", "native", "flatpak", "custom")

# Every Flatpak keeps its per-app data under ~/.var/app/<app-id>/, so a root
# that goes through there came from a Flatpak install of the launcher.
FLATPAK_DATA_MARKER = ".var/app"

# This file is <contents>/code/backend/gameshelf/util/paths.py, so the plasmoid
# package's contents/ directory is five levels up. It is the one thing the
# backend reads from its own package rather than from a launcher: the bundled
# launcher artwork under contents/images/.
_CONTENTS_DEPTH = 4


def package_contents() -> Path:
    """The plasmoid package's ``contents/`` directory, wherever it is installed."""
    return Path(__file__).resolve().parents[_CONTENTS_DEPTH]


def home() -> Path:
    return Path(os.path.expanduser("~"))


def _xdg(variable: str, default: str) -> Path:
    value = os.environ.get(variable, "").strip()
    return Path(value) if value else home() / default


def xdg_config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def xdg_data_home() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def xdg_cache_home() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache")


def is_flatpak_root(path: Path | str) -> bool:
    """Whether a resolved launcher root belongs to a Flatpak install."""
    return FLATPAK_DATA_MARKER in str(path)


def first_on_path(*names: str) -> str | None:
    """The absolute path of the first of ``names`` that is on PATH.

    Used to find a launcher's own executable. Distributions disagree about the
    name, so providers pass every spelling they know of.
    """
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def flatpak_run_command(app_id: str) -> list[str] | None:
    """``flatpak run <app-id>`` as argv, or None when flatpak is not installed."""
    flatpak = shutil.which("flatpak")
    return [flatpak, "run", app_id] if flatpak else None


def resolve_roots(
    install_type: str,
    custom_path: str,
    native: list[Path],
    flatpak: list[Path],
) -> list[Path]:
    """Pick the launcher roots to scan, in the order given by ``install_type``.

    With ``auto`` both native and Flatpak roots are returned when both exist, so a
    user running two copies of a launcher sees both libraries. Results are
    resolved through symlinks and de-duplicated: ``~/.steam/steam`` and
    ``~/.local/share/Steam`` are usually the same directory, and returning both
    would list every game twice.
    """
    install_type = (install_type or "auto").strip().lower()
    if install_type not in INSTALL_TYPES:
        install_type = "auto"

    if install_type == "custom":
        candidates = [Path(os.path.expanduser(custom_path))] if custom_path else []
    elif install_type == "native":
        candidates = list(native)
    elif install_type == "flatpak":
        candidates = list(flatpak)
    else:
        candidates = [*native, *flatpak]

    seen: set[Path] = set()
    roots: list[Path] = []
    for candidate in candidates:
        try:
            if not candidate.is_dir():
                continue
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots
