# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Per-provider scan cache, invalidated by input mtimes.

A provider's games are reused only when both its effective settings and every
file it named in ``cache_inputs()`` are unchanged. Each provider is cached
independently, so installing a game invalidates that launcher alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .models import Game
from .util.paths import xdg_cache_home

__all__ = ["CACHE_SCHEMA_VERSION", "ScanCache", "cache_path", "settings_hash", "stat_inputs"]

# Bumped whenever the cached shape changes, or a provider starts producing
# different games from unchanged files; a mismatch discards the whole file.
# 2: Heroic began trusting each store's installed.json for installed state.
CACHE_SCHEMA_VERSION = 2

# A file that does not exist is recorded with this sentinel, so that creating it
# later counts as a change rather than looking identical to "still missing".
MISSING = -1


def cache_path() -> Path:
    return xdg_cache_home() / "gameshelf" / "scan-cache.json"


def settings_hash(settings: dict[str, Any]) -> str:
    """Stable digest of a provider's effective settings."""
    payload = json.dumps(settings, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stat_inputs(paths: list[Path]) -> list[list[Any]]:
    """Snapshot ``(path, mtime_ns, size)`` for each input, sorted for stability.

    Directories are included as-is: their mtime changes when an entry is added or
    removed, which is how a newly installed game is noticed.
    """
    snapshot: list[list[Any]] = []
    seen: set[str] = set()
    for path in paths:
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        try:
            info = os.stat(path)
            snapshot.append([text, info.st_mtime_ns, info.st_size])
        except OSError:
            snapshot.append([text, MISSING, MISSING])
    snapshot.sort(key=lambda row: row[0])
    return snapshot


class ScanCache:
    """Reads once, collects updates from provider threads, writes once."""

    def __init__(self, path: Path | None = None, *, enabled: bool = True) -> None:
        self.path = path or cache_path()
        self.enabled = enabled
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        if enabled:
            self._load()

    def _load(self) -> None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # A missing or corrupt cache is simply a cold start.
            return
        if not isinstance(document, dict):
            return
        if document.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
            return
        entries = document.get("providers")
        if isinstance(entries, dict):
            self._entries = {
                key: value for key, value in entries.items() if isinstance(value, dict)
            }

    def get(
        self, provider_id: str, digest: str, inputs: list[list[Any]]
    ) -> list[Game] | None:
        """Return cached games when settings and every input still match."""
        if not self.enabled:
            return None
        with self._lock:
            entry = self._entries.get(provider_id)
        if not entry or entry.get("settings_hash") != digest:
            return None
        if entry.get("inputs") != inputs:
            return None
        raw_games = entry.get("games")
        if not isinstance(raw_games, list):
            return None
        try:
            return [Game.from_dict(item) for item in raw_games]
        except (TypeError, ValueError):
            # A cache written by an incompatible build; treat as a miss.
            return None

    def put(
        self, provider_id: str, digest: str, inputs: list[list[Any]], games: list[Game]
    ) -> None:
        if not self.enabled:
            return
        entry = {
            "settings_hash": digest,
            "inputs": inputs,
            "games": [game.to_dict() for game in games],
        }
        with self._lock:
            self._entries[provider_id] = entry
            self._dirty = True

    def drop(self, provider_id: str) -> None:
        """Forget one provider, so a failed scan never leaves stale games behind."""
        with self._lock:
            if self._entries.pop(provider_id, None) is not None:
                self._dirty = True

    def save(self) -> bool:
        """Write the cache atomically. Never raises: caching is best-effort."""
        if not self.enabled or not self._dirty:
            return False
        with self._lock:
            document = {
                "cache_schema_version": CACHE_SCHEMA_VERSION,
                "providers": self._entries,
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            )
            try:
                with handle:
                    json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(handle.name, self.path)
            except BaseException:
                try:
                    os.unlink(handle.name)
                except OSError:
                    pass
                raise
        except OSError:
            return False
        with self._lock:
            self._dirty = False
        return True
