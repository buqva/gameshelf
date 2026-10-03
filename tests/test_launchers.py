# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""The launcher tiles: the launcher applications themselves, pinned in the grid."""

from __future__ import annotations

import pytest

from gameshelf import registry
from gameshelf.models import Game, make_key, sort_title_for
from gameshelf.providers.base import (
    LAUNCHER_STORE,
    DetectResult,
    LauncherApp,
    Provider,
    launcher_banner,
    launcher_game,
)
from gameshelf.providers.heroic import HeroicProvider
from gameshelf.providers.prism_launcher import PrismLauncherProvider
from gameshelf.providers.steam import SteamProvider
from gameshelf.util.paths import package_contents


def make_game(provider: str, title: str) -> Game:
    return Game(
        key=make_key(provider, None, title),
        provider=provider,
        store=None,
        id=title,
        title=title,
        sort_title=sort_title_for(title),
        installed=True,
    )


class WithLauncher(Provider):
    id = "withlauncher"
    name = "With Launcher"
    icon = "with-launcher-icon"

    def detect(self):
        return DetectResult(available=True, paths=["/somewhere"])

    def scan(self):
        return [make_game("withlauncher", "A Game")]

    def launcher_app(self):
        return LauncherApp(title="With Launcher", launch_cmd=["/usr/bin/withlauncher"])


class WithoutLauncher(Provider):
    id = "withoutlauncher"
    name = "Without Launcher"

    def detect(self):
        return DetectResult(available=True, paths=["/elsewhere"])

    def scan(self):
        return [make_game("withoutlauncher", "Another Game")]


class UnavailableWithLauncher(Provider):
    id = "gone"
    name = "Gone"

    def detect(self):
        return DetectResult(available=False, paths=[], message="not installed")

    def scan(self):  # pragma: no cover - must never be called
        raise AssertionError("scan() called on an unavailable provider")

    def launcher_app(self):  # pragma: no cover - must never be called
        raise AssertionError("launcher_app() called on an unavailable provider")


class BrokenLauncher(Provider):
    id = "brokenlauncher"
    name = "Broken Launcher"

    def detect(self):
        return DetectResult(available=True, paths=["/somewhere"])

    def scan(self):
        return [make_game("brokenlauncher", "Survivor")]

    def launcher_app(self):
        raise RuntimeError("finding the executable blew up")


@pytest.fixture
def fake_providers(monkeypatch):
    def install(*classes):
        monkeypatch.setattr(registry, "discover", lambda: list(classes))
        return classes

    return install


# -- the Game wrapper -----------------------------------------------------------


def test_launcher_key_uses_the_launcher_store():
    entry = launcher_game(WithLauncher, LauncherApp(title="With Launcher"))
    assert entry.key == "withlauncher:launcher:withlauncher"
    assert entry.store == LAUNCHER_STORE


def test_launcher_key_cannot_collide_with_a_real_game():
    """A game keyed on the provider's own id still differs from its launcher."""
    entry = launcher_game(WithLauncher, LauncherApp(title="With Launcher"))
    assert entry.key != make_key(WithLauncher.id, None, WithLauncher.id)


def test_launcher_is_marked_and_carries_an_icon():
    entry = launcher_game(WithLauncher, LauncherApp(title="With Launcher"))
    assert entry.extra["is_launcher"] is True
    # Falls back to the provider's own icon, which is the name from its .desktop.
    assert entry.extra["icon"] == "with-launcher-icon"


def test_launcher_app_may_override_the_icon():
    entry = launcher_game(WithLauncher, LauncherApp(title="X", icon="other-icon"))
    assert entry.extra["icon"] == "other-icon"


def test_launcher_falls_back_to_the_provider_name():
    entry = launcher_game(WithLauncher, LauncherApp())
    assert entry.title == "With Launcher"
    assert entry.sort_title == "with launcher"


def test_launcher_counts_as_installed():
    entry = launcher_game(WithLauncher, LauncherApp(title="With Launcher"))
    assert entry.installed is True


# -- the bundled banners --------------------------------------------------------


def test_banners_ship_inside_the_package():
    """They have to live under contents/, or kpackagetool6 will not install them."""
    directory = package_contents() / "images" / "launchers"
    assert directory.is_dir()
    assert (directory / "steam.jpg").is_file()


def test_every_working_provider_has_a_banner():
    """A launcher tile without one falls back to a lone icon, which looks unfinished."""
    for provider_cls in (SteamProvider, HeroicProvider, PrismLauncherProvider):
        assert launcher_banner(provider_cls.id), f"no banner for {provider_cls.id}"


def test_banner_is_looked_up_by_provider_id():
    entry = launcher_game(SteamProvider, LauncherApp(title="Steam"))
    assert entry.art.portrait is not None
    assert entry.art.portrait.startswith("file://")
    assert entry.art.portrait.endswith("/images/launchers/steam.jpg")


def test_a_provider_without_a_banner_falls_back_to_its_icon():
    """No banner is not an error: the QML then draws extra.icon instead."""
    assert launcher_banner("withlauncher") is None
    entry = launcher_game(WithLauncher, LauncherApp(title="With Launcher"))
    assert entry.art.is_empty()
    assert entry.extra["icon"] == "with-launcher-icon"


def test_a_launcher_app_may_override_the_banner(tmp_path):
    custom = tmp_path / "custom.png"
    custom.write_bytes(b"")
    entry = launcher_game(
        SteamProvider, LauncherApp(title="Steam", banner=str(custom))
    )
    assert entry.art.portrait == custom.as_uri()


def test_banner_url_is_percent_encoded():
    """The install path may hold spaces; QML Image needs a real URL."""
    entry = launcher_game(SteamProvider, LauncherApp(title="Steam"))
    assert " " not in entry.art.portrait


def test_a_provider_offers_no_launcher_by_default():
    assert WithoutLauncher({}).launcher_app() is None


# -- how the registry collects them ---------------------------------------------


def test_launchers_are_kept_out_of_the_games(fake_providers):
    fake_providers(WithLauncher)
    result = registry.scan_all({})
    assert [g.title for g in result.games] == ["A Game"]
    assert [entry.title for entry in result.launchers] == ["With Launcher"]


def test_launchers_do_not_count_towards_the_provider_total(fake_providers):
    fake_providers(WithLauncher)
    result = registry.scan_all({})
    report = next(r for r in result.reports if r.id == "withlauncher")
    assert report.count == 1


def test_a_provider_without_a_launcher_contributes_none(fake_providers):
    fake_providers(WithoutLauncher)
    result = registry.scan_all({})
    assert result.launchers == []


def test_an_undetected_launcher_gets_no_tile(fake_providers):
    fake_providers(UnavailableWithLauncher)
    result = registry.scan_all({})
    assert result.launchers == []


def test_a_disabled_provider_gets_no_tile(fake_providers):
    fake_providers(WithLauncher)
    result = registry.scan_all({"withlauncher": {"enabled": False}})
    assert result.launchers == []
    assert result.games == []


def test_a_broken_launcher_app_still_leaves_the_games(fake_providers):
    """A cosmetic tile is never worth a provider's whole library."""
    fake_providers(BrokenLauncher)
    result = registry.scan_all({})
    assert [g.title for g in result.games] == ["Survivor"]
    assert result.launchers == []
    assert result.errors == []


def test_launchers_are_collected_from_every_provider(fake_providers):
    fake_providers(WithLauncher, WithoutLauncher, BrokenLauncher)
    result = registry.scan_all({})
    assert [entry.provider for entry in result.launchers] == ["withlauncher"]
    assert len(result.games) == 3


def test_serial_mode_collects_launchers_too(fake_providers):
    fake_providers(WithLauncher)
    result = registry.scan_all({}, parallel=False)
    assert [entry.title for entry in result.launchers] == ["With Launcher"]


def test_all_entries_puts_launchers_first(fake_providers):
    fake_providers(WithLauncher)
    result = registry.scan_all({})
    assert [entry.title for entry in result.all_entries()] == ["With Launcher", "A Game"]


def test_launcher_survives_a_cached_scan(tmp_path, monkeypatch):
    """The tile is resolved on every run, not stored with the games.

    Otherwise a launcher installed since the last scan would stay missing until
    something made one of its games change.
    """
    from gameshelf.cache import ScanCache

    watched = tmp_path / "library"
    watched.write_text("x")

    class Cacheable(WithLauncher):
        id = "cacheable"

        def cache_inputs(self):
            return [watched]

    monkeypatch.setattr(registry, "discover", lambda: [Cacheable])
    cache = ScanCache(path=tmp_path / "scan-cache.json")

    first = registry.scan_all({}, cache=cache)
    assert first.reports[0].cached is False

    second = registry.scan_all({}, cache=cache)
    assert second.reports[0].cached is True, "the games should have come from the cache"
    assert [e.key for e in second.launchers] == [e.key for e in first.launchers]
