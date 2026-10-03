# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Helpers for turning artwork locations into values the QML Image element accepts."""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["first_existing", "to_url", "find_art"]


def first_existing(*candidates: str | os.PathLike[str] | None) -> str | None:
    """Return the first candidate that exists on disk, as an absolute path."""
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            if path.is_file():
                return str(path.resolve())
        except OSError:
            # A dead symlink or an unreadable mount point is just "not there".
            continue
    return None


def to_url(path_or_url: str | os.PathLike[str] | None) -> str | None:
    """Return a value the QML ``Image`` element can load.

    Remote URLs pass through untouched; local paths become percent-encoded
    ``file://`` URLs so that spaces and non-ASCII characters in game directories
    survive the trip through QML.
    """
    if not path_or_url:
        return None
    text = str(path_or_url)
    if text.startswith(("http://", "https://", "file://", "qrc:", "data:")):
        return text
    # Path.as_uri() percent-encodes and is stable across Python versions, unlike
    # urllib's pathname2url, whose POSIX output gained a "///" prefix in 3.14.
    return Path(os.path.abspath(text)).as_uri()


def find_art(directory: Path, stems: tuple[str, ...], extensions: tuple[str, ...]) -> str | None:
    """Find ``<stem><ext>`` anywhere under ``directory``, preferring earlier stems.

    Steam stores the same asset either directly in the app directory or one level
    down in a hash-named subdirectory, so this searches recursively. Matching is on
    the exact stem rather than a prefix glob: ``library_hero`` must not match
    ``library_hero_blur``.
    """
    if not directory.is_dir():
        return None
    try:
        entries = [p for p in directory.rglob("*") if p.is_file()]
    except OSError:
        return None
    by_name: dict[str, Path] = {}
    for entry in entries:
        by_name.setdefault(entry.name.lower(), entry)
    for stem in stems:
        for extension in extensions:
            match = by_name.get(f"{stem}{extension}".lower())
            if match is not None:
                return str(match.resolve())
    return None
