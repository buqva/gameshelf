# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared fixtures. Puts the in-package backend on sys.path for every test."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "package" / "contents" / "code" / "backend"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def steam_root(tmp_path: Path) -> Path:
    """A writable copy of the Steam fixture tree, with library paths patched.

    libraryfolders.vdf carries absolute paths, so it can only be built once the
    temporary directory exists. The third library it names is left dangling on
    purpose: an unmounted drive is a normal state the scanner must survive.
    """
    root = tmp_path / "Steam"
    lib2 = tmp_path / "lib2"
    shutil.copytree(FIXTURES / "steam" / "root", root)
    shutil.copytree(FIXTURES / "steam" / "lib2", lib2)

    manifest = root / "steamapps" / "libraryfolders.vdf"
    manifest.write_text(
        manifest.read_text().replace("__ROOT__", str(root)).replace("__LIB2__", str(lib2))
    )
    return root


@pytest.fixture
def steam_settings() -> dict:
    """Schema defaults for the Steam provider, with remote art off.

    Remote fallback is disabled so that a missing local file shows up as None in
    tests instead of being papered over by a CDN URL.
    """
    from gameshelf.providers.steam import SteamProvider
    from gameshelf.registry import merge_settings

    return merge_settings(SteamProvider, {"remote_art_fallback": False})


@pytest.fixture
def heroic_root(tmp_path: Path) -> Path:
    """A writable copy of the Heroic fixture tree."""
    root = tmp_path / "heroic"
    shutil.copytree(FIXTURES / "heroic" / "root", root)
    return root


@pytest.fixture
def heroic_settings() -> dict:
    from gameshelf.providers.heroic import HeroicProvider
    from gameshelf.registry import merge_settings

    return merge_settings(HeroicProvider, {})


@pytest.fixture
def prism_root(tmp_path: Path) -> Path:
    """A writable copy of the Prism Launcher fixture tree."""
    root = tmp_path / "PrismLauncher"
    shutil.copytree(FIXTURES / "prism_launcher" / "root", root)
    return root


@pytest.fixture
def prism_settings() -> dict:
    from gameshelf.providers.prism_launcher import PrismLauncherProvider
    from gameshelf.registry import merge_settings

    return merge_settings(PrismLauncherProvider, {})
