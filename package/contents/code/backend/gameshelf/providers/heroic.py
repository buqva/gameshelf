# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Heroic Games Launcher provider.

Heroic wraps three store CLIs (legendary for Epic, gogdl for GOG, nile for
Amazon) and also runs sideloaded apps. Each store is a toggle inside this one
provider.

A game counts as installed when the store's library cache says ``is_installed``
*or* the store's ``installed.json`` lists it. Both are needed: Heroic merges GOG's
installed state in memory and never writes it back into ``gog_library.json``, so
that flag stays ``false`` for an installed GOG game; Epic and sideloaded entries
carry the flag but have no comparable file for every store.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Iterable
from urllib.parse import quote

from ..models import Art, Game, make_key, sort_title_for
from ..util.art import to_url
from ..util.paths import (
    first_on_path,
    flatpak_run_command,
    home,
    is_flatpak_root,
    resolve_roots,
    xdg_config_home,
)
from .base import DetectResult, LauncherApp, Provider, SettingSpec

__all__ = ["HeroicProvider", "STORES"]

FLATPAK_APP_ID = "com.heroicgameslauncher.hgl"

# Heroic registers x-scheme-handler/heroic, but only for launching a named
# game: no documented URI just opens the window. So its tile runs the binary,
# whose name differs by packaging.
BINARY_NAMES = ("heroic", "heroic-games-launcher", "HeroicGamesLauncher")

# store id -> (runner name used in the launch URI, setting key, library file,
#              keys the library list may hide behind, installed.json candidates)
STORES: dict[str, dict[str, Any]] = {
    "epic": {
        "runner": "legendary",
        "setting": "store_epic",
        "library": ("store_cache/legendary_library.json",),
        "installed": (
            "legendaryConfig/legendary/installed.json",
            "legendary/installed.json",
        ),
    },
    "gog": {
        "runner": "gog",
        "setting": "store_gog",
        "library": ("store_cache/gog_library.json",),
        "installed": ("gog_store/installed.json",),
    },
    "amazon": {
        "runner": "nile",
        "setting": "store_amazon",
        "library": ("store_cache/nile_library.json",),
        # The plan documented nile_config/nile/; this machine has nile_store/.
        # Both are probed because neither could be confirmed with a real install.
        "installed": (
            "nile_config/nile/installed.json",
            "nile_store/installed.json",
        ),
    },
    "sideload": {
        "runner": "sideload",
        "setting": "store_sideload",
        "library": ("sideload_apps/library.json",),
        "installed": (),
    },
}

# Library caches wrap their list under one of these keys, depending on the store.
LIST_KEYS = ("library", "games", "installed")

# Heroic lists redistributables alongside real games.
REDIST_APP_NAMES = frozenset({"gog-redist"})


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _app_name_of(entry: dict[str, Any]) -> str:
    """legendary writes ``app_name``, gogdl ``appName``."""
    value = entry.get("app_name") or entry.get("appName")
    return str(value) if value else ""


def _as_entry_list(document: Any) -> list[dict[str, Any]]:
    """Pull the entry list out of a Heroic JSON file, whatever it wraps it in."""
    if isinstance(document, list):
        candidates: Iterable[Any] = document
    elif isinstance(document, dict):
        for key in LIST_KEYS:
            value = document.get(key)
            if isinstance(value, list):
                candidates = value
                break
            if isinstance(value, dict):
                candidates = value.values()
                break
        else:
            # An object keyed by app name, which is how legendary writes its
            # installed.json, is also acceptable.
            values = list(document.values())
            candidates = values if all(isinstance(v, dict) for v in values) else []
    else:
        candidates = []
    return [entry for entry in candidates if isinstance(entry, dict)]


def _parse_timestamp(value: Any) -> int | None:
    """Heroic writes ISO-8601 strings here, not unix seconds."""
    if isinstance(value, (int, float)) and value > 0:
        # Milliseconds appear in some older builds.
        return int(value / 1000) if value > 10_000_000_000 else int(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


class HeroicProvider(Provider):
    id: ClassVar[str] = "heroic"
    name: ClassVar[str] = "Heroic"
    icon: ClassVar[str] = "com.heroicgameslauncher.hgl"
    default_enabled: ClassVar[bool] = True

    @classmethod
    def settings_schema(cls) -> list[SettingSpec]:
        return [
            SettingSpec(
                key="install_type",
                type="enum",
                label="Installation",
                default="auto",
                options=[
                    {"value": "auto", "label": "Auto-detect"},
                    {"value": "native", "label": "Native"},
                    {"value": "flatpak", "label": "Flatpak"},
                    {"value": "custom", "label": "Custom path"},
                ],
            ),
            SettingSpec(
                key="custom_path",
                type="path",
                label="Custom Heroic config directory",
                default="",
                advanced=True,
            ),
            SettingSpec(key="store_epic", type="bool", label="Epic Games", default=True),
            SettingSpec(key="store_gog", type="bool", label="GOG", default=True),
            SettingSpec(key="store_amazon", type="bool", label="Amazon Games", default=True),
            SettingSpec(key="store_sideload", type="bool", label="Sideloaded games", default=True),
            SettingSpec(
                key="launch_uri_style",
                type="enum",
                label="Launch URI style",
                default="auto",
                help="Heroic changed its URI format; 'auto' uses the modern query form.",
                options=[
                    {"value": "auto", "label": "Auto"},
                    {"value": "modern", "label": "Modern (?appName=...&runner=...)"},
                    {"value": "legacy", "label": "Legacy (/runner/appName)"},
                ],
                advanced=True,
            ),
        ]

    # -- location ------------------------------------------------------------

    def roots(self) -> list[Path]:
        native = [xdg_config_home() / "heroic"]
        flatpak = [home() / ".var/app/com.heroicgameslauncher.hgl/config/heroic"]
        return resolve_roots(
            self.setting("install_type", "auto"),
            self.setting("custom_path", ""),
            native,
            flatpak,
        )

    def detect(self) -> DetectResult:
        roots = self.roots()
        if not roots:
            return DetectResult(available=False, paths=[], message="Heroic not found")
        message = "Flatpak install" if any(is_flatpak_root(r) for r in roots) else None
        return DetectResult(available=True, paths=[str(r) for r in roots], message=message)

    def launcher_app(self) -> LauncherApp | None:
        """Heroic itself, as a tile.

        Heroic is an Electron app with a single-instance lock, so running the
        binary again raises the existing window rather than starting a second
        copy. Returns None when the config directory is there but the program
        is not — a leftover ~/.config/heroic is not a launcher to offer.
        """
        roots = self.roots()
        if not roots:
            return None
        # A native Heroic is preferred when both are installed, but each kind of
        # root is only honoured if the program it implies is really there.
        command: list[str] | None = None
        if any(not is_flatpak_root(root) for root in roots):
            binary = first_on_path(*BINARY_NAMES)
            command = [binary] if binary else None
        if command is None and any(is_flatpak_root(root) for root in roots):
            command = flatpak_run_command(FLATPAK_APP_ID)
        if not command:
            return None
        return LauncherApp(title=self.name, launch_cmd=command)

    def enabled_stores(self) -> list[str]:
        return [
            store
            for store, spec in STORES.items()
            if self.bool_setting(spec["setting"], True)
        ]

    # -- launch --------------------------------------------------------------

    def launch_uri(self, runner: str, app_name: str) -> str:
        style = str(self.setting("launch_uri_style", "auto") or "auto").lower()
        encoded = quote(app_name, safe="")
        if style == "legacy":
            return f"heroic://launch/{runner}/{encoded}"
        # 'auto' resolves to modern: the Heroic that generated the Steam shortcuts
        # on the dev machine writes exactly this form.
        return f"heroic://launch?appName={encoded}&runner={runner}"

    # -- supporting data ------------------------------------------------------

    def _playtime_index(self, root: Path) -> dict[str, dict[str, int]]:
        document = _read_json(root / "store" / "timestamp.json")
        if not isinstance(document, dict):
            return {}
        index: dict[str, dict[str, int]] = {}
        for app_name, info in document.items():
            if not isinstance(info, dict):
                continue
            entry: dict[str, int] = {}
            last_played = _parse_timestamp(info.get("lastPlayed"))
            if last_played:
                entry["last_played"] = last_played
            total = info.get("totalPlayed")
            if isinstance(total, (int, float)) and total > 0:
                entry["playtime_minutes"] = int(total)
            if entry:
                index[str(app_name)] = entry
        return index

    def _installed_index(self, root: Path, store: str) -> dict[str, dict[str, Any]]:
        """Map app name -> what the store's installed.json knows about it.

        Authoritative for *whether* a game is installed, and the best source of
        its install path. A store with no installed.json falls back to the
        library cache's ``is_installed`` flag alone.
        """
        index: dict[str, dict[str, Any]] = {}
        for relative in STORES[store]["installed"]:
            for entry in _as_entry_list(_read_json(root / relative)):
                app_name = _app_name_of(entry)
                if not app_name or app_name in index:
                    continue
                if entry.get("is_dlc"):
                    continue
                location = (
                    entry.get("install_path")
                    or entry.get("platform_install_path")
                    or entry.get("base_path")
                    or entry.get("path")
                )
                info: dict[str, Any] = {}
                if isinstance(location, str) and location:
                    info["install_path"] = location
                title = entry.get("title")
                if isinstance(title, str) and title.strip():
                    info["title"] = title.strip()
                elif isinstance(location, str) and location:
                    # GOG records no title here; its install directory is named
                    # after the game.
                    info["title"] = PurePosixPath(location.rstrip("/")).name
                platform = entry.get("platform")
                if isinstance(platform, str) and platform:
                    info["platform"] = platform
                index[app_name] = info
        return index

    # -- scanning --------------------------------------------------------------

    def scan(self) -> list[Game]:
        show_uninstalled = self.bool_setting("show_uninstalled", False)
        stores = self.enabled_stores()
        games: list[Game] = []
        seen: set[str] = set()

        for root in self.roots():
            playtime = self._playtime_index(root)
            for store in stores:
                spec = STORES[store]
                installed_index = self._installed_index(root, store)
                listed: set[str] = set()
                for relative in spec["library"]:
                    entries = _as_entry_list(_read_json(root / relative))
                    for entry in entries:
                        app_name = _app_name_of(entry)
                        if app_name:
                            listed.add(app_name)
                        game = self._game_from_entry(
                            entry, store, spec["runner"], playtime, installed_index,
                            show_uninstalled,
                        )
                        if game is not None and game.key not in seen:
                            seen.add(game.key)
                            games.append(game)
                # A game installed since the library cache was last written is
                # in installed.json and nowhere else; it still has to show up.
                for app_name, info in installed_index.items():
                    if app_name in listed:
                        continue
                    game = self._game_from_entry(
                        {"app_name": app_name, "is_installed": True},
                        store, spec["runner"], playtime, installed_index,
                        show_uninstalled,
                    )
                    if game is not None and game.key not in seen:
                        seen.add(game.key)
                        games.append(game)
        return games

    def _game_from_entry(
        self,
        entry: dict[str, Any],
        store: str,
        runner: str,
        playtime: dict[str, dict[str, int]],
        installed_index: dict[str, dict[str, Any]],
        show_uninstalled: bool,
    ) -> Game | None:
        app_name = _app_name_of(entry)
        if not app_name:
            return None
        if app_name in REDIST_APP_NAMES:
            return None

        install_block = entry.get("install")
        install_block = install_block if isinstance(install_block, dict) else {}
        if install_block.get("is_dlc") or entry.get("is_dlc"):
            # DLC is listed beside the base game; it is not separately launchable.
            return None

        install_info = installed_index.get(app_name, {})
        installed = bool(entry.get("is_installed")) or app_name in installed_index
        if not installed and not show_uninstalled:
            return None

        title = str(entry.get("title") or install_info.get("title") or app_name).strip()
        title = title or app_name

        install_path = install_info.get("install_path")
        if not install_path:
            folder = entry.get("folder_name")
            # Sideload entries store an absolute path here; Epic stores a bare
            # directory name, which is useless on its own.
            if isinstance(folder, str) and folder.startswith("/"):
                install_path = folder
        if not install_path:
            candidate = install_block.get("install_path") or install_block.get("executable")
            if isinstance(candidate, str) and candidate.startswith("/"):
                install_path = candidate

        stats = playtime.get(app_name, {})
        return Game(
            key=make_key(self.id, store, app_name),
            provider=self.id,
            store=store,
            id=app_name,
            title=title,
            sort_title=sort_title_for(title),
            installed=installed,
            launch_uri=self.launch_uri(runner, app_name),
            launch_cmd=["xdg-open", self.launch_uri(runner, app_name)],
            art=Art(
                portrait=to_url(entry.get("art_square")),
                landscape=to_url(entry.get("art_cover")),
                logo=to_url(entry.get("art_logo")),
            ),
            last_played=stats.get("last_played"),
            playtime_minutes=stats.get("playtime_minutes"),
            install_path=install_path,
            extra={
                "runner": runner,
                "platform": install_block.get("platform") or install_info.get("platform"),
            },
        )

    def cache_inputs(self) -> list[Path]:
        inputs: list[Path] = []
        for root in self.roots():
            inputs.append(root / "store" / "timestamp.json")
            for store in self.enabled_stores():
                spec = STORES[store]
                inputs.extend(root / rel for rel in spec["library"])
                inputs.extend(root / rel for rel in spec["installed"])
        return inputs
