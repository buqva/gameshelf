# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Steam provider.

Paths and file shapes here were verified against a real install.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar

from ..models import Art, Game, make_key, sort_title_for
from ..util import vdf_binary, vdf_text
from ..util.art import find_art, first_existing, to_url
from ..util.paths import (
    first_on_path,
    flatpak_run_command,
    home,
    is_flatpak_root,
    resolve_roots,
    xdg_data_home,
)
from .base import DetectResult, LauncherApp, Provider, SettingSpec

__all__ = ["SteamProvider"]

# SteamID64 of the first account; subtracting it yields the userdata directory name.
STEAMID64_BASE = 76561197960265728

# StateFlags bit 2 (value 4) means "fully installed".
STATE_FULLY_INSTALLED = 4

# Runtimes and redistributables that ship as ordinary apps. Extend freely.
TOOL_APPIDS = frozenset({
    "228980",   # Steamworks Common Redistributables
    "1070560",  # Steam Linux Runtime 1.0 (scout)
    "1391110",  # Steam Linux Runtime 2.0 (soldier)
    "1628350",  # Steam Linux Runtime 3.0 (sniper)
    "4183110",  # Steam Linux Runtime 4.0 — found on this machine, absent from the plan
    "1493710",  # Proton Experimental
    "2180100",  # Proton Hotfix
    "1826330",  # Proton EasyAntiCheat Runtime
    "1161040",  # Proton BattlEye Runtime
})

TOOL_NAME_RE = re.compile(r"^(?:Proton\b|Steam Linux Runtime|Steamworks)", re.IGNORECASE)

# Both the flat and the hash-nested artwork layouts use these stems, and a game
# may have one asset in each layout. Order is preference order.
PORTRAIT_STEMS = ("library_600x900", "library_capsule")
LANDSCAPE_STEMS = ("library_header", "header")
HERO_STEMS = ("library_hero",)
LOGO_STEMS = ("logo",)
ART_EXTENSIONS = (".jpg", ".jpeg", ".png")

GRID_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

REMOTE_ART_BASE = "https://cdn.cloudflare.steamstatic.com/steam/apps"

FLATPAK_APP_ID = "com.valvesoftware.Steam"

# Steam's own steam.desktop offers this as its "Library" action, so it is the
# vendor's way of opening the client at the game list. Going through the URI
# rather than the binary also means a running Steam is focused, not restarted.
LAUNCHER_URI = "steam://open/games"


class SteamProvider(Provider):
    id: ClassVar[str] = "steam"
    name: ClassVar[str] = "Steam"
    icon: ClassVar[str] = "steam"
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
                label="Custom Steam directory",
                default="",
                help="Used only when Installation is set to Custom path.",
                advanced=True,
            ),
            SettingSpec(
                key="hide_tools",
                type="bool",
                label="Hide runtimes and redistributables",
                default=True,
                help="Hides Proton, Steam Linux Runtime and Steamworks Common Redistributables.",
            ),
            SettingSpec(
                key="include_shortcuts",
                type="bool",
                label="Include non-Steam shortcuts",
                default=True,
            ),
            SettingSpec(
                key="remote_art_fallback",
                type="bool",
                label="Use Steam's CDN when artwork is missing locally",
                default=True,
            ),
        ]

    # -- location ---------------------------------------------------------------

    def roots(self) -> list[Path]:
        native = [
            xdg_data_home() / "Steam",
            home() / ".steam" / "steam",
            home() / ".steam" / "root",
        ]
        flatpak = [
            home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
            home() / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
        return resolve_roots(
            self.setting("install_type", "auto"),
            self.setting("custom_path", ""),
            native,
            flatpak,
        )

    def detect(self) -> DetectResult:
        roots = self.roots()
        if not roots:
            return DetectResult(available=False, paths=[], message="Steam not found")
        message = "Flatpak install" if any(is_flatpak_root(r) for r in roots) else None
        return DetectResult(available=True, paths=[str(r) for r in roots], message=message)

    def launcher_app(self) -> LauncherApp | None:
        """Steam itself, as a tile.

        The URI is what actually gets used, and it works for a Flatpak Steam too
        because the Flatpak exports the same ``x-scheme-handler/steam``. The
        command is only the fallback for a desktop with no handler registered.
        """
        roots = self.roots()
        if not roots:
            return None
        # With install_type=auto both kinds of root can be present; a native
        # Steam is the one to start when there is a choice.
        native = any(not is_flatpak_root(root) for root in roots)
        command = (
            first_on_path("steam") if native else flatpak_run_command(FLATPAK_APP_ID)
        )
        return LauncherApp(
            title=self.name,
            launch_uri=LAUNCHER_URI,
            launch_cmd=[command] if isinstance(command, str) else command,
        )

    def library_paths(self, root: Path) -> list[Path]:
        """Every library directory for ``root``, including the root's own.

        Libraries listed in libraryfolders.vdf may sit on drives that are not
        mounted; those are skipped silently, because an unmounted external drive
        is a normal state and not a scan failure.
        """
        libraries: list[Path] = []
        seen: set[Path] = set()

        def add(candidate: Path) -> None:
            try:
                if not (candidate / "steamapps").is_dir():
                    return
                resolved = candidate.resolve()
            except OSError:
                return
            if resolved not in seen:
                seen.add(resolved)
                libraries.append(resolved)

        add(root)
        manifest = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return libraries
        try:
            parsed = vdf_text.parse(text)
        except vdf_text.VdfError:
            return libraries
        folders = vdf_text.get_ci(parsed, "libraryfolders") or {}
        if not isinstance(folders, dict):
            return libraries
        for entry in folders.values():
            if isinstance(entry, dict):
                path = vdf_text.get_ci(entry, "path")
            else:
                path = entry  # very old format: "0" "/path"
            if isinstance(path, str) and path:
                add(Path(path))
        return libraries

    # -- the active Steam user ---------------------------------------------------

    def _account_id(self, root: Path) -> str | None:
        """Resolve the userdata directory for the logged-in account.

        loginusers.vdf does not always carry MostRecent, so this falls back to the
        newest Timestamp and finally to the only userdata directory present.
        """
        userdata = root / "userdata"
        available: list[str] = []
        try:
            available = [d.name for d in userdata.iterdir() if d.is_dir() and d.name.isdigit()]
        except OSError:
            available = []

        candidates: list[tuple[int, str]] = []
        try:
            parsed = vdf_text.parse(
                (root / "config" / "loginusers.vdf").read_text(encoding="utf-8", errors="replace")
            )
        except (OSError, vdf_text.VdfError):
            parsed = {}
        users = vdf_text.get_ci(parsed, "users") or {}
        if isinstance(users, dict):
            for steamid64, info in users.items():
                if not isinstance(info, dict) or not steamid64.isdigit():
                    continue
                account_id = str(int(steamid64) - STEAMID64_BASE)
                if str(vdf_text.get_ci(info, "MostRecent") or "") == "1":
                    return account_id
                try:
                    timestamp = int(str(vdf_text.get_ci(info, "Timestamp") or 0))
                except ValueError:
                    timestamp = 0
                candidates.append((timestamp, account_id))

        for _, account_id in sorted(candidates, reverse=True):
            if not available or account_id in available:
                return account_id
        if len(available) == 1:
            return available[0]
        return None

    def _playtime_index(self, root: Path, account_id: str | None) -> dict[str, dict[str, int]]:
        """Map appid -> {last_played, playtime_minutes} from localconfig.vdf."""
        if not account_id:
            return {}
        path = root / "userdata" / account_id / "config" / "localconfig.vdf"
        try:
            parsed = vdf_text.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, vdf_text.VdfError):
            return {}
        apps = vdf_text.get_ci(
            parsed, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps"
        )
        if not isinstance(apps, dict):
            return {}
        index: dict[str, dict[str, int]] = {}
        for appid, info in apps.items():
            if not isinstance(info, dict):
                continue
            entry: dict[str, int] = {}
            for source, target in (("LastPlayed", "last_played"), ("Playtime", "playtime_minutes")):
                raw = vdf_text.get_ci(info, source)
                if raw is None:
                    continue
                try:
                    value = int(str(raw))
                except ValueError:
                    continue
                if value > 0:
                    entry[target] = value
            if entry:
                index[str(appid)] = entry
        return index

    # -- artwork ------------------------------------------------------------------

    def _artwork(self, roots_art: list[Path], appid: str) -> Art:
        art = Art()
        for base in roots_art:
            directory = base / appid
            if not directory.is_dir():
                continue
            art.portrait = art.portrait or find_art(directory, PORTRAIT_STEMS, ART_EXTENSIONS)
            art.landscape = art.landscape or find_art(directory, LANDSCAPE_STEMS, ART_EXTENSIONS)
            art.hero = art.hero or find_art(directory, HERO_STEMS, ART_EXTENSIONS)
            art.logo = art.logo or find_art(directory, LOGO_STEMS, ART_EXTENSIONS)
        # The old flat layout kept every asset directly in librarycache/.
        for base in roots_art:
            art.portrait = art.portrait or first_existing(
                *(base / f"{appid}_{stem}{ext}" for stem in ("library_600x900", "library_capsule")
                  for ext in ART_EXTENSIONS)
            )
            art.landscape = art.landscape or first_existing(
                *(base / f"{appid}_header{ext}" for ext in ART_EXTENSIONS)
            )
            art.hero = art.hero or first_existing(
                *(base / f"{appid}_library_hero{ext}" for ext in ART_EXTENSIONS)
            )
            art.logo = art.logo or first_existing(
                *(base / f"{appid}_logo{ext}" for ext in ART_EXTENSIONS)
            )
        for field_name in ("portrait", "landscape", "hero", "logo"):
            setattr(art, field_name, to_url(getattr(art, field_name)))
        if self.bool_setting("remote_art_fallback", True):
            if not art.portrait:
                art.portrait = f"{REMOTE_ART_BASE}/{appid}/library_600x900.jpg"
            if not art.landscape:
                art.landscape = f"{REMOTE_ART_BASE}/{appid}/header.jpg"
        return art

    def _grid_artwork(self, grid_dir: Path, appid_u32: int) -> Art:
        art = Art()
        if not grid_dir.is_dir():
            return art
        for target, suffixes in (
            ("portrait", ("p",)),
            ("landscape", ("",)),
            ("hero", ("_hero",)),
            ("logo", ("_logo",)),
        ):
            found = first_existing(
                *(grid_dir / f"{appid_u32}{suffix}{ext}"
                  for suffix in suffixes for ext in GRID_EXTENSIONS)
            )
            setattr(art, target, to_url(found))
        return art

    # -- scanning -------------------------------------------------------------------

    def scan(self) -> list[Game]:
        games: list[Game] = []
        seen_keys: set[str] = set()
        for root in self.roots():
            account_id = self._account_id(root)
            playtime = self._playtime_index(root, account_id)
            art_roots = [root / "appcache" / "librarycache"]
            for game in self._scan_installed(root, playtime, art_roots):
                if game.key not in seen_keys:
                    seen_keys.add(game.key)
                    games.append(game)
            if self.bool_setting("include_shortcuts", True) and account_id:
                for game in self._scan_shortcuts(root, account_id):
                    if game.key not in seen_keys:
                        seen_keys.add(game.key)
                        games.append(game)
        return games

    def _scan_installed(
        self, root: Path, playtime: dict[str, dict[str, int]], art_roots: list[Path]
    ) -> list[Game]:
        hide_tools = self.bool_setting("hide_tools", True)
        show_uninstalled = self.bool_setting("show_uninstalled", False)
        games: list[Game] = []
        for library in self.library_paths(root):
            steamapps = library / "steamapps"
            try:
                manifests = sorted(steamapps.glob("appmanifest_*.acf"))
            except OSError:
                continue
            for manifest in manifests:
                game = self._game_from_manifest(
                    manifest, library, playtime, art_roots, hide_tools, show_uninstalled
                )
                if game is not None:
                    games.append(game)
        return games

    def _game_from_manifest(
        self,
        manifest: Path,
        library: Path,
        playtime: dict[str, dict[str, int]],
        art_roots: list[Path],
        hide_tools: bool,
        show_uninstalled: bool,
    ) -> Game | None:
        try:
            parsed = vdf_text.parse(manifest.read_text(encoding="utf-8", errors="replace"))
        except (OSError, vdf_text.VdfError):
            # One corrupt manifest must not cost the user their whole library.
            return None
        state = vdf_text.get_ci(parsed, "AppState")
        if not isinstance(state, dict):
            return None
        appid = str(vdf_text.get_ci(state, "appid") or "").strip()
        if not appid:
            return None
        title = str(vdf_text.get_ci(state, "name") or "").strip() or f"App {appid}"

        if hide_tools and (appid in TOOL_APPIDS or TOOL_NAME_RE.match(title)):
            return None

        try:
            state_flags = int(str(vdf_text.get_ci(state, "StateFlags") or 0))
        except ValueError:
            state_flags = 0
        installed = bool(state_flags & STATE_FULLY_INSTALLED)
        if not installed and not show_uninstalled:
            return None

        install_dir = str(vdf_text.get_ci(state, "installdir") or "").strip()
        install_path = str(library / "steamapps" / "common" / install_dir) if install_dir else None

        stats = playtime.get(appid, {})
        last_played = stats.get("last_played")
        if last_played is None:
            # Manifests carry LastPlayed too, and it is present for games the
            # active user never launched through the account in localconfig.
            try:
                manifest_last = int(str(vdf_text.get_ci(state, "LastPlayed") or 0))
            except ValueError:
                manifest_last = 0
            last_played = manifest_last or None

        return Game(
            key=make_key(self.id, None, appid),
            provider=self.id,
            store=None,
            id=appid,
            title=title,
            sort_title=sort_title_for(title),
            installed=installed,
            launch_uri=f"steam://rungameid/{appid}",
            launch_cmd=["steam", f"steam://rungameid/{appid}"],
            art=self._artwork(art_roots, appid),
            last_played=last_played,
            playtime_minutes=stats.get("playtime_minutes"),
            install_path=install_path,
            extra={"state_flags": state_flags, "library": str(library)},
        )

    def _scan_shortcuts(self, root: Path, account_id: str) -> list[Game]:
        config_dir = root / "userdata" / account_id / "config"
        path = config_dir / "shortcuts.vdf"
        try:
            parsed = vdf_binary.parse(path.read_bytes())
        except (OSError, vdf_text.VdfError, ValueError):
            return []
        shortcuts = vdf_text.get_ci(parsed, "shortcuts")
        if not isinstance(shortcuts, dict):
            return []
        grid_dir = config_dir / "grid"
        games: list[Game] = []
        for entry in shortcuts.values():
            if not isinstance(entry, dict):
                continue
            game = self._game_from_shortcut(entry, grid_dir)
            if game is not None:
                games.append(game)
        return games

    def _game_from_shortcut(self, entry: dict[str, Any], grid_dir: Path) -> Game | None:
        raw_appid = vdf_text.get_ci(entry, "appid")
        if not isinstance(raw_appid, int):
            return None
        # Steam writes these as signed int32; the unsigned value is what names the
        # grid artwork and what goes into the launch id.
        appid_u32 = raw_appid & 0xFFFFFFFF
        title = str(vdf_text.get_ci(entry, "AppName") or "").strip()
        if not title:
            return None
        if str(vdf_text.get_ci(entry, "IsHidden") or "0") not in ("0", "False", ""):
            # Hidden inside Steam itself; respect that rather than resurrecting it.
            return None

        executable = str(vdf_text.get_ci(entry, "Exe") or "").strip()
        start_dir = str(vdf_text.get_ci(entry, "StartDir") or "").strip().strip('"')
        try:
            last_played = int(str(vdf_text.get_ci(entry, "LastPlayTime") or 0)) or None
        except ValueError:
            last_played = None

        art = self._grid_artwork(grid_dir, appid_u32)
        if not art.portrait:
            icon = str(vdf_text.get_ci(entry, "icon") or "").strip()
            art.icon = to_url(first_existing(icon)) if icon else None

        run_id = (appid_u32 << 32) | 0x02000000
        return Game(
            key=make_key(self.id, "shortcut", appid_u32),
            provider=self.id,
            store="shortcut",
            id=str(appid_u32),
            title=title,
            sort_title=sort_title_for(title),
            installed=True,
            launch_uri=f"steam://rungameid/{run_id}",
            launch_cmd=["steam", f"steam://rungameid/{run_id}"],
            art=art,
            last_played=last_played,
            playtime_minutes=None,
            install_path=start_dir or None,
            extra={
                "exe": executable,
                "launch_options": str(vdf_text.get_ci(entry, "LaunchOptions") or ""),
            },
        )

    def cache_inputs(self) -> list[Path]:
        inputs: list[Path] = []
        for root in self.roots():
            inputs.append(root / "steamapps" / "libraryfolders.vdf")
            for library in self.library_paths(root):
                steamapps = library / "steamapps"
                # The directory mtime catches manifests being added or removed,
                # but not one being rewritten in place, which is what happens when
                # a game updates. Both are needed; stat is cheap even for a
                # thousand-game library.
                inputs.append(steamapps)
                try:
                    inputs.extend(sorted(steamapps.glob("appmanifest_*.acf")))
                except OSError:
                    pass
            account_id = self._account_id(root)
            if account_id:
                config_dir = root / "userdata" / account_id / "config"
                inputs.append(config_dir / "localconfig.vdf")
                inputs.append(config_dir / "shortcuts.vdf")
        return inputs
