# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prism Launcher: for now it contributes its own tile and no games."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameshelf import registry
from gameshelf.providers import prism_launcher as prism_module
from gameshelf.providers.base import launcher_banner
from gameshelf.providers.prism_launcher import PrismLauncherProvider

BINARY = "/usr/bin/prismlauncher"
FLATPAK_RUN = ["/usr/bin/flatpak", "run", prism_module.FLATPAK_APP_ID]


@pytest.fixture(autouse=True)
def no_real_launcher(monkeypatch, tmp_path):
    """Nothing in here may depend on what is installed on the machine running it.

    Both program lookups are stubbed out as absent by default; a test that wants
    one back uses ``with_binary`` or ``with_flatpak``. HOME and XDG_DATA_HOME are
    pointed at an empty directory so the native and Flatpak roots start missing.
    """
    monkeypatch.setattr(prism_module, "first_on_path", lambda *names: None)
    monkeypatch.setattr(prism_module, "flatpak_run_command", lambda app_id: None)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


@pytest.fixture
def with_binary(monkeypatch):
    monkeypatch.setattr(prism_module, "first_on_path", lambda *names: BINARY)


@pytest.fixture
def with_flatpak(monkeypatch):
    monkeypatch.setattr(prism_module, "flatpak_run_command", lambda app_id: list(FLATPAK_RUN))


def make_provider(root: Path | None, settings: dict, **overrides) -> PrismLauncherProvider:
    merged = dict(settings)
    if root is not None:
        merged.update({"install_type": "custom", "custom_path": str(root)})
    merged.update(overrides)
    return PrismLauncherProvider(merged)


# -- detection ------------------------------------------------------------------


def test_detect_finds_the_custom_root(prism_root, prism_settings):
    result = make_provider(prism_root, prism_settings).detect()
    assert result.available is True
    assert result.paths == [str(prism_root.resolve())]
    assert result.message is None


def test_detect_finds_the_native_root(monkeypatch, prism_root, prism_settings):
    monkeypatch.setenv("XDG_DATA_HOME", str(prism_root.parent))
    result = make_provider(None, prism_settings).detect()
    assert result.available is True
    assert result.paths == [str(prism_root.resolve())]


def test_detect_finds_the_flatpak_root(monkeypatch, tmp_path, prism_settings):
    fake_home = tmp_path / "home"
    root = fake_home / ".var/app" / prism_module.FLATPAK_APP_ID / "data/PrismLauncher"
    root.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    result = make_provider(None, prism_settings).detect()
    assert result.available is True
    assert result.message == "Flatpak install"


def test_detect_reports_a_missing_root(prism_settings):
    provider = make_provider(None, prism_settings,
                             install_type="custom", custom_path="/nonexistent/prism")
    result = provider.detect()
    assert result.available is False
    assert result.paths == []


def test_detect_finds_an_install_that_has_never_been_run(prism_settings, with_binary):
    """Prism only writes its data directory on first launch."""
    result = make_provider(None, prism_settings).detect()
    assert result.available is True
    assert result.paths == [BINARY]
    assert result.message == "Installed, but never run"


def test_detect_finds_nothing_when_prism_is_absent(prism_settings):
    assert make_provider(None, prism_settings).detect().available is False


# -- the launcher tile ----------------------------------------------------------


def test_launcher_app_runs_the_native_binary(prism_root, prism_settings, with_binary):
    app = make_provider(prism_root, prism_settings).launcher_app()
    assert app is not None
    assert app.title == "Prism Launcher"
    assert app.launch_cmd == [BINARY]


def test_launcher_app_offers_no_uri(prism_root, prism_settings, with_binary):
    """Prism's own scheme imports packs; no documented URI just opens the window."""
    app = make_provider(prism_root, prism_settings).launcher_app()
    assert app.launch_uri is None


def test_launcher_app_uses_flatpak_for_a_flatpak_root(
    monkeypatch, tmp_path, prism_settings, with_binary, with_flatpak
):
    """A native binary on PATH must not hijack a Flatpak-only install."""
    fake_home = tmp_path / "home"
    (fake_home / ".var/app" / prism_module.FLATPAK_APP_ID / "data/PrismLauncher").mkdir(
        parents=True
    )
    monkeypatch.setenv("HOME", str(fake_home))
    app = make_provider(None, prism_settings).launcher_app()
    assert app is not None
    assert app.launch_cmd == FLATPAK_RUN


def test_launcher_app_prefers_native_when_both_are_installed(
    monkeypatch, tmp_path, prism_root, prism_settings, with_binary, with_flatpak
):
    fake_home = tmp_path / "home"
    (fake_home / ".var/app" / prism_module.FLATPAK_APP_ID / "data/PrismLauncher").mkdir(
        parents=True
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(prism_root.parent))
    app = make_provider(None, prism_settings).launcher_app()
    assert app is not None
    assert app.launch_cmd == [BINARY]


def test_no_tile_when_the_data_directory_outlived_the_program(prism_root, prism_settings):
    """A leftover ~/.local/share/PrismLauncher is not a launcher to offer."""
    assert make_provider(prism_root, prism_settings).launcher_app() is None


def test_a_missing_custom_path_offers_nothing_even_with_a_binary(
    prism_settings, with_binary
):
    """The user named a directory; if it is gone there is nothing to assume."""
    provider = make_provider(None, prism_settings,
                             install_type="custom", custom_path="/nonexistent/prism")
    assert provider.launcher_app() is None


def test_flatpak_is_not_guessed_without_a_root(prism_settings, with_flatpak):
    """`flatpak run` on an app that is not installed opens nothing at all."""
    assert make_provider(None, prism_settings).launcher_app() is None


def test_the_launcher_has_a_bundled_banner():
    assert launcher_banner(PrismLauncherProvider.id)


# -- scanning --------------------------------------------------------------------


def test_scan_reports_no_games_yet(prism_root, prism_settings):
    """Instances are a later step; today Prism is the tile and nothing else."""
    assert make_provider(prism_root, prism_settings).scan() == []


def test_nothing_is_cached_while_there_is_nothing_to_scan(prism_root, prism_settings):
    assert make_provider(prism_root, prism_settings).cache_inputs() == []


# -- settings ---------------------------------------------------------------------


def test_settings_schema_offers_the_usual_install_choices(prism_settings):
    assert prism_settings["install_type"] == "auto"
    assert prism_settings["custom_path"] == ""
    assert prism_settings["enabled"] is True


# -- how the registry sees it ------------------------------------------------------


def test_the_provider_is_discovered():
    assert PrismLauncherProvider in registry.discover()


def test_the_registry_pins_the_tile_and_counts_no_games(
    monkeypatch, prism_root, prism_settings, with_binary
):
    monkeypatch.setattr(registry, "discover", lambda: [PrismLauncherProvider])
    result = registry.scan_all(
        {"prism_launcher": {"install_type": "custom", "custom_path": str(prism_root)}}
    )
    assert result.games == []
    assert [entry.key for entry in result.launchers] == [
        "prism_launcher:launcher:prism_launcher"
    ]
    report = next(r for r in result.reports if r.id == "prism_launcher")
    assert report.available is True
    assert report.count == 0


def test_a_disabled_prism_contributes_nothing(monkeypatch, prism_root, with_binary):
    monkeypatch.setattr(registry, "discover", lambda: [PrismLauncherProvider])
    result = registry.scan_all(
        {"prism_launcher": {"enabled": False, "custom_path": str(prism_root)}}
    )
    assert result.launchers == []
