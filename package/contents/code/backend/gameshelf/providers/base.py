# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""The contract every launcher provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, ClassVar, Literal

from ..models import Art, Game, make_key, sort_title_for
from ..util.art import to_url
from ..util.paths import package_contents

__all__ = [
    "SettingSpec",
    "DetectResult",
    "LauncherApp",
    "Provider",
    "ProviderContext",
    "COMMON_SETTINGS",
    "LAUNCHER_STORE",
    "launcher_game",
    "launcher_banner",
]

# The ``store`` field of a launcher tile's key, so ``steam:launcher:steam``
# can never collide with a real game. Part of the stable key format.
LAUNCHER_STORE = "launcher"

# Cover art for the launchers themselves ships with the widget, one portrait
# image per provider id, so a launcher tile reads like the game tiles beside it
# instead of being a lone icon. Dropping in <provider-id>.jpg is all a new
# provider needs; without one its tile falls back to the launcher's icon.
LAUNCHER_BANNER_DIR = "images/launchers"
LAUNCHER_BANNER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

SettingType = Literal["bool", "string", "enum", "path", "stringlist", "int"]


@dataclass
class SettingSpec:
    key: str
    type: SettingType
    label: str
    default: Any
    help: str | None = None
    options: list[dict[str, Any]] | None = None
    advanced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DetectResult:
    available: bool
    paths: list[str] = field(default_factory=list)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LauncherApp:
    """The launcher application itself, offered as a tile at the top of the grid.

    A provider returns one of these from :meth:`Provider.launcher_app` when its
    launcher can be started, so the widget can open Steam or Heroic and not only
    the games inside them. Either a URI or a command is enough; when both are
    given the QML prefers the URI, because a launcher's own handler focuses an
    already-running copy instead of starting a second one.
    """

    title: str = ""
    launch_uri: str | None = None
    launch_cmd: list[str] | None = None
    # Freedesktop icon name. Defaults to the provider's own icon, which is
    # already the name from the launcher's .desktop file.
    icon: str | None = None
    # Overrides the bundled banner looked up from the provider id. A path or a
    # URL; leave it unset unless the provider has a better image than the one
    # shipped under its own name.
    banner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def launcher_banner(provider_id: str) -> str | None:
    """The bundled portrait banner for a provider, as a file:// URL.

    Looked up by provider id so that adding artwork for a new launcher means
    adding a file, not editing this module.
    """
    directory = package_contents() / LAUNCHER_BANNER_DIR
    for extension in LAUNCHER_BANNER_EXTENSIONS:
        candidate = directory / f"{provider_id}{extension}"
        try:
            if candidate.is_file():
                return to_url(candidate)
        except OSError:
            continue
    return None


def launcher_game(provider_cls: type["Provider"], app: LauncherApp) -> Game:
    """Wrap a :class:`LauncherApp` as a Game, so one tile type renders both.

    ``extra.is_launcher`` is what the QML keys off to pin the tile ahead of the
    games, and to fall back to the launcher's icon when no banner is bundled.
    """
    title = app.title or provider_cls.name or provider_cls.id
    return Game(
        key=make_key(provider_cls.id, LAUNCHER_STORE, provider_cls.id),
        provider=provider_cls.id,
        store=LAUNCHER_STORE,
        id=provider_cls.id,
        title=title,
        sort_title=sort_title_for(title),
        installed=True,
        launch_uri=app.launch_uri,
        launch_cmd=list(app.launch_cmd) if app.launch_cmd else None,
        art=Art(portrait=to_url(app.banner) or launcher_banner(provider_cls.id)),
        extra={
            "is_launcher": True,
            "icon": app.icon or provider_cls.icon,
        },
    )


@dataclass
class ProviderContext:
    """What a provider may know about the rest of the scan.

    ``enabled_providers`` lets a provider avoid duplicating games another enabled
    provider will already report — Lutris uses it for its imported-library rows.
    """

    enabled_providers: frozenset[str] = frozenset()


def COMMON_SETTINGS(default_enabled: bool) -> list[SettingSpec]:
    """Settings the registry adds to every provider, so none has to declare them."""
    return [
        SettingSpec(
            key="enabled",
            type="bool",
            label="Enabled",
            default=default_enabled,
            help="Include this launcher's games in the list.",
        ),
        SettingSpec(
            key="show_uninstalled",
            type="bool",
            label="Show games that are not installed",
            default=False,
            help="Include owned but uninstalled games, where the launcher knows about them.",
        ),
    ]


class Provider(ABC):
    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    icon: ClassVar[str] = "applications-games"
    default_enabled: ClassVar[bool] = True

    def __init__(self, settings: dict[str, Any], context: ProviderContext | None = None) -> None:
        self.settings = settings
        self.context = context or ProviderContext()

    @classmethod
    def settings_schema(cls) -> list[SettingSpec]:
        """Provider-specific settings. The registry prepends the common ones."""
        return []

    @classmethod
    def full_schema(cls) -> list[SettingSpec]:
        return [*COMMON_SETTINGS(cls.default_enabled), *cls.settings_schema()]

    @abstractmethod
    def detect(self) -> DetectResult:
        """Report whether this launcher is installed, and where."""

    @abstractmethod
    def scan(self) -> list[Game]:
        """Return the games this launcher knows about."""

    def launcher_app(self) -> LauncherApp | None:
        """Describe the launcher application itself, for its tile in the grid.

        Called only after :meth:`detect` reported the launcher available. Return
        ``None`` when there is no way to start it — an unopenable tile is worse
        than no tile. Providers that do not implement this simply get no tile.
        """
        return None

    def cache_inputs(self) -> list[Path]:
        """Files and directories whose mtime invalidates this provider's cache."""
        return []

    # -- convenience for subclasses -------------------------------------------

    def setting(self, key: str, fallback: Any = None) -> Any:
        return self.settings.get(key, fallback)

    def bool_setting(self, key: str, fallback: bool = False) -> bool:
        value = self.settings.get(key, fallback)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
