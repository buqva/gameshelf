# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""The data types the backend emits."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any

__all__ = ["Art", "Game", "ProviderReport", "ProviderError", "make_key", "sort_title_for"]

_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_TRADEMARKS = str.maketrans({"®": "", "™": "", "©": ""})


@dataclass
class Art:
    portrait: str | None = None
    landscape: str | None = None
    hero: str | None = None
    logo: str | None = None
    icon: str | None = None

    def is_empty(self) -> bool:
        return not any((self.portrait, self.landscape, self.hero, self.logo, self.icon))

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Art":
        data = data or {}
        return cls(**{field: data.get(field) for field in
                      ("portrait", "landscape", "hero", "logo", "icon")})


@dataclass
class Game:
    key: str
    provider: str
    store: str | None
    id: str
    title: str
    sort_title: str
    installed: bool
    launch_uri: str | None = None
    launch_cmd: list[str] | None = None
    art: Art = field(default_factory=Art)
    last_played: int | None = None
    playtime_minutes: int | None = None
    install_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Game":
        """Rebuild a Game from its serialized form. Used by the scan cache."""
        payload = dict(data)
        payload["art"] = Art.from_dict(payload.get("art"))
        payload.setdefault("extra", {})
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class ProviderReport:
    """One row of the ``providers`` array in the output envelope."""

    id: str
    enabled: bool
    available: bool
    # Display name and freedesktop icon, copied from the provider class. They are
    # here so the QML can label filter chips and tile badges without a table of
    # launcher names of its own — adding a provider must not mean editing QML.
    name: str = ""
    icon: str = ""
    count: int = 0
    duration_ms: int = 0
    detected_paths: list[str] = field(default_factory=list)
    message: str | None = None
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderError:
    """One row of the ``errors`` array in the output envelope."""

    provider: str
    message: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_key(provider: str, store: str | None, native_id: str | int) -> str:
    """Build the stable game key described in plan section 4.2.

    The format is ``<provider>:<store-or-dash>:<id>``. Changing it resets every
    user's favorites and hidden list, so it must stay put.
    """
    return f"{provider}:{store or '-'}:{native_id}"


def sort_title_for(title: str) -> str:
    """Lowercase the title and drop a leading article, for name sorting.

    Trademark symbols are stripped too, so "Borderlands® 4" sorts next to other
    Borderlands entries rather than after every plain-ASCII title.
    """
    cleaned = (title or "").translate(_TRADEMARKS).strip().lower()
    cleaned = _LEADING_ARTICLE.sub("", cleaned, count=1)
    return re.sub(r"\s+", " ", cleaned).strip()
