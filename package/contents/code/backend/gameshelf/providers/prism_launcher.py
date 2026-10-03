# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prism Launcher provider.

Prism manages Minecraft instances, not a store library. For now this provider
contributes the launcher itself and no games: :meth:`scan` returns nothing, so
Prism shows up as the pinned launcher tile and nothing else. Listing individual
instances as tiles is a separate step, and the shapes it will need are already
captured in ``tests/fixtures/prism_launcher/``.

Paths and file shapes here were read off a real native install. The Flatpak root
is the same layout under Flatpak's per-app ``XDG_DATA_HOME``; it could not be
confirmed on this machine, so it is probed rather than relied upon.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ..models import Game
from ..util.paths import (
    first_on_path,
    flatpak_run_command,
    home,
    is_flatpak_root,
    resolve_roots,
    xdg_data_home,
)
from .base import DetectResult, LauncherApp, Provider, SettingSpec

__all__ = ["PrismLauncherProvider"]

FLATPAK_APP_ID = "org.prismlauncher.PrismLauncher"

# Prism registers x-scheme-handler/prismlauncher, but its URLs are import
# requests ("prismlauncher://import?..."), and ``--help`` lists no option that
# only raises the window. So the tile runs the binary, which is safe: Prism is
# single-instance and hands a second invocation to the copy already running.
BINARY_NAMES = ("prismlauncher", "PrismLauncher")


class PrismLauncherProvider(Provider):
    id: ClassVar[str] = "prism_launcher"
    name: ClassVar[str] = "Prism Launcher"
    # The Icon= of org.prismlauncher.PrismLauncher.desktop.
    icon: ClassVar[str] = "org.prismlauncher.PrismLauncher"
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
                label="Custom Prism Launcher data directory",
                default="",
                help="The directory holding prismlauncher.cfg and instances/.",
                advanced=True,
            ),
        ]

    # -- location ------------------------------------------------------------

    def install_type(self) -> str:
        return str(self.setting("install_type", "auto") or "auto").strip().lower()

    def roots(self) -> list[Path]:
        native = [xdg_data_home() / "PrismLauncher"]
        flatpak = [home() / ".var/app" / FLATPAK_APP_ID / "data/PrismLauncher"]
        return resolve_roots(
            self.install_type(),
            self.setting("custom_path", ""),
            native,
            flatpak,
        )

    def program(self) -> list[str] | None:
        """The command that opens Prism, or None when it cannot be found.

        Which copy to open follows from the roots that were found; the setting
        only decides when there are none, because Prism writes its data
        directory on first run and an installed-but-never-opened Prism is still
        worth a tile. A custom path is the exception: the user named a
        directory, and if it is not there we have nothing to go on.
        """
        roots = self.roots()
        if roots:
            native = any(not is_flatpak_root(root) for root in roots)
            flatpak = any(is_flatpak_root(root) for root in roots)
        elif self.install_type() == "custom":
            return None
        else:
            native = self.install_type() in ("auto", "native")
            # Without a root there is nothing to confirm a Flatpak Prism exists,
            # and `flatpak run` on a missing app opens nothing. A native binary
            # is the only evidence worth acting on here.
            flatpak = False

        if native:
            binary = first_on_path(*BINARY_NAMES)
            if binary:
                return [binary]
        if flatpak:
            return flatpak_run_command(FLATPAK_APP_ID)
        return None

    def detect(self) -> DetectResult:
        roots = self.roots()
        if not roots:
            # No data directory: the program itself is the only thing left that
            # can say Prism is here, and doctor should show where it found it.
            program = self.program()
            if not program:
                return DetectResult(
                    available=False, paths=[], message="Prism Launcher not found"
                )
            return DetectResult(
                available=True, paths=[program[0]], message="Installed, but never run"
            )
        message = "Flatpak install" if any(is_flatpak_root(r) for r in roots) else None
        return DetectResult(
            available=True, paths=[str(root) for root in roots], message=message
        )

    def launcher_app(self) -> LauncherApp | None:
        program = self.program()
        return LauncherApp(title=self.name, launch_cmd=program) if program else None

    # -- scanning --------------------------------------------------------------

    def scan(self) -> list[Game]:
        """No games yet: Prism contributes only its own tile.

        Instances are deliberately not listed. Until they are, there is nothing
        to cache either, so :meth:`cache_inputs` stays empty.
        """
        return []
