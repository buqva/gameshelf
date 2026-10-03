# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from gameshelf.providers import steam as steam_module
from gameshelf.providers.steam import SteamProvider
from gameshelf.util.art import to_url


def make_provider(steam_root: Path, steam_settings: dict, **overrides) -> SteamProvider:
    settings = {**steam_settings, "install_type": "custom", "custom_path": str(steam_root)}
    settings.update(overrides)
    return SteamProvider(settings)


def titles(games) -> set[str]:
    return {game.title for game in games}


def by_key(games) -> dict:
    return {game.key: game for game in games}


def test_detect_finds_custom_root(steam_root, steam_settings):
    result = make_provider(steam_root, steam_settings).detect()
    assert result.available is True
    assert result.paths == [str(steam_root.resolve())]


def test_detect_reports_missing_root(steam_settings):
    provider = SteamProvider(
        {**steam_settings, "install_type": "custom", "custom_path": "/nonexistent/steam"}
    )
    assert provider.detect().available is False


def test_library_paths_skips_unmounted(steam_root, steam_settings):
    libraries = make_provider(steam_root, steam_settings).library_paths(steam_root.resolve())
    # Three libraries are listed; the third points at an unmounted drive.
    assert len(libraries) == 2
    assert not any("nonexistent" in str(path) for path in libraries)


def test_scan_finds_games_across_libraries(steam_root, steam_settings):
    games = make_provider(steam_root, steam_settings).scan()
    assert titles(games) == {"Cyberpunk 2077", "Factorio", "GranBlue Fantasy Relink"}


def test_tools_are_filtered_by_default(steam_root, steam_settings):
    games = make_provider(steam_root, steam_settings).scan()
    assert "Steamworks Common Redistributables" not in titles(games)
    assert "Steam Linux Runtime 4.0" not in titles(games)


def test_tools_shown_when_filter_disabled(steam_root, steam_settings):
    games = make_provider(steam_root, steam_settings, hide_tools=False).scan()
    assert "Steamworks Common Redistributables" in titles(games)
    # 4183110 is absent from the plan's appid list; the name regex must also catch it.
    assert "Steam Linux Runtime 4.0" in titles(games)


def test_uninstalled_game_hidden_by_default(steam_root, steam_settings):
    games = make_provider(steam_root, steam_settings).scan()
    assert "Half Downloaded Game" not in titles(games)


def test_uninstalled_game_shown_when_requested(steam_root, steam_settings):
    games = make_provider(steam_root, steam_settings, show_uninstalled=True).scan()
    game = by_key(games)["steam:-:9999990"]
    assert game.title == "Half Downloaded Game"
    assert game.installed is False


def test_game_key_and_launch_uri(steam_root, steam_settings):
    game = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:1091500"]
    assert game.provider == "steam"
    assert game.store is None
    assert game.launch_uri == "steam://rungameid/1091500"


def test_install_path_points_at_owning_library(steam_root, steam_settings):
    games = by_key(make_provider(steam_root, steam_settings).scan())
    assert games["steam:-:1091500"].install_path.endswith("Steam/steamapps/common/Cyberpunk 2077")
    assert games["steam:-:427520"].install_path.endswith("lib2/steamapps/common/Factorio")


def test_playtime_from_localconfig(steam_root, steam_settings):
    game = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:1091500"]
    assert game.playtime_minutes == 2625
    assert game.last_played == 1789722612


def test_last_played_falls_back_to_manifest(steam_root, steam_settings):
    """427520 is in localconfig; 1091500's manifest value should agree with it."""
    (steam_root / "userdata/12345678/config/localconfig.vdf").unlink()
    game = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:1091500"]
    assert game.playtime_minutes is None
    assert game.last_played == 1789722612  # read from the manifest instead


def test_account_id_resolved_without_mostrecent(steam_root, steam_settings):
    # The real loginusers.vdf has no MostRecent key; Timestamp must be enough.
    assert make_provider(steam_root, steam_settings)._account_id(steam_root.resolve()) == "12345678"


def test_account_id_falls_back_to_sole_userdata_dir(steam_root, steam_settings):
    (steam_root / "config/loginusers.vdf").unlink()
    assert make_provider(steam_root, steam_settings)._account_id(steam_root.resolve()) == "12345678"


def test_sort_title_strips_trademark_and_article():
    from gameshelf.models import sort_title_for

    assert sort_title_for("Borderlands® 4") == "borderlands 4"
    assert sort_title_for("The Witcher 3") == "witcher 3"
    assert sort_title_for("A Plague Tale") == "plague tale"


# -- artwork ------------------------------------------------------------------


def test_art_nested_capsule_layout(steam_root, steam_settings):
    """Cyberpunk's only portrait is library_capsule.jpg in a hash subdirectory."""
    art = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:1091500"].art
    assert art.portrait.endswith("library_capsule.jpg")
    assert art.landscape.endswith("library_header.jpg")
    assert art.logo.endswith("logo.png")


def test_art_flat_layout(steam_root, steam_settings):
    """Factorio uses the flat layout with the 600x900 name."""
    art = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:427520"].art
    assert art.portrait.endswith("library_600x900.jpg")
    assert art.landscape.endswith("header.jpg")


def test_hero_never_matches_the_blurred_variant(steam_root, steam_settings):
    art = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:1091500"].art
    assert art.hero.endswith("library_hero.jpg")
    assert "blur" not in art.hero


def test_art_is_returned_as_file_url(steam_root, steam_settings):
    art = by_key(make_provider(steam_root, steam_settings).scan())["steam:-:427520"].art
    assert art.portrait.startswith("file:///")


def test_remote_art_fallback_when_enabled(steam_root, steam_settings):
    """9999990 has no local art at all."""
    provider = make_provider(steam_root, steam_settings, remote_art_fallback=True,
                             show_uninstalled=True)
    art = by_key(provider.scan())["steam:-:9999990"].art
    assert art.portrait == (
        "https://cdn.cloudflare.steamstatic.com/steam/apps/9999990/library_600x900.jpg"
    )
    assert art.landscape.endswith("/9999990/header.jpg")


def test_remote_art_fallback_off_leaves_none(steam_root, steam_settings):
    provider = make_provider(steam_root, steam_settings, show_uninstalled=True)
    assert by_key(provider.scan())["steam:-:9999990"].art.portrait is None


# -- non-Steam shortcuts --------------------------------------------------------


def test_shortcut_is_included(steam_root, steam_settings):
    game = by_key(make_provider(steam_root, steam_settings).scan())["steam:shortcut:3808043038"]
    assert game.title == "GranBlue Fantasy Relink"
    assert game.store == "shortcut"
    assert game.installed is True


def test_shortcut_launch_id_encoding(steam_root, steam_settings):
    game = by_key(make_provider(steam_root, steam_settings).scan())["steam:shortcut:3808043038"]
    expected = (3808043038 << 32) | 0x02000000
    assert game.launch_uri == f"steam://rungameid/{expected}"


def test_hidden_shortcut_is_skipped(steam_root, steam_settings):
    """The second fixture entry has IsHidden=1; Steam hides it, so we do too."""
    games = make_provider(steam_root, steam_settings).scan()
    assert "Hidden Shortcut" not in titles(games)
    assert "steam:shortcut:3643628250" not in by_key(games)


def test_shortcut_grid_art(steam_root, steam_settings):
    art = by_key(make_provider(steam_root, steam_settings).scan())["steam:shortcut:3808043038"].art
    assert art.portrait.endswith("3808043038p.jpg")
    assert art.landscape.endswith("3808043038.jpg")
    assert art.hero.endswith("3808043038_hero.jpg")
    assert art.logo.endswith("3808043038_logo.jpg")  # .jpg, not the .png the plan assumed


def test_shortcuts_excluded_when_disabled(steam_root, steam_settings):
    games = make_provider(steam_root, steam_settings, include_shortcuts=False).scan()
    assert "GranBlue Fantasy Relink" not in titles(games)


def test_shortcut_last_play_time(steam_root, steam_settings):
    game = by_key(make_provider(steam_root, steam_settings).scan())["steam:shortcut:3808043038"]
    assert game.last_played == 1789800000


# -- resilience -------------------------------------------------------------------


def test_corrupt_manifest_does_not_break_the_scan(steam_root, steam_settings):
    (steam_root / "steamapps/appmanifest_5555555.acf").write_text('"AppState" { "appid" ')
    games = make_provider(steam_root, steam_settings).scan()
    assert "Cyberpunk 2077" in titles(games)


def test_missing_libraryfolders_still_scans_root(steam_root, steam_settings):
    (steam_root / "steamapps/libraryfolders.vdf").unlink()
    games = make_provider(steam_root, steam_settings).scan()
    assert "Cyberpunk 2077" in titles(games)
    assert "Factorio" not in titles(games)  # the second library is only known from that file


def test_missing_shortcuts_file_is_not_an_error(steam_root, steam_settings):
    (steam_root / "userdata/12345678/config/shortcuts.vdf").unlink()
    games = make_provider(steam_root, steam_settings).scan()
    assert "Cyberpunk 2077" in titles(games)


def test_cache_inputs_are_listed(steam_root, steam_settings):
    inputs = make_provider(steam_root, steam_settings).cache_inputs()
    names = {Path(p).name for p in inputs}
    assert {"libraryfolders.vdf", "localconfig.vdf", "shortcuts.vdf", "steamapps"} <= names


def test_symlinked_root_is_not_scanned_twice(steam_root, steam_settings, tmp_path):
    """~/.steam/steam is normally a symlink to the real root; games must not double."""
    link = tmp_path / "steam-link"
    link.symlink_to(steam_root)
    provider = SteamProvider(
        {**steam_settings, "install_type": "custom", "custom_path": str(link)}
    )
    games = provider.scan()
    assert len(games) == len({game.key for game in games})


# -- the Steam launcher tile ----------------------------------------------------


def test_launcher_app_prefers_the_uri(steam_root, steam_settings, monkeypatch):
    """The URI is what the QML uses; it focuses a running Steam, a second
    `steam` process would not."""
    monkeypatch.setattr(steam_module, "first_on_path", lambda *names: "/usr/bin/steam")
    app = make_provider(steam_root, steam_settings).launcher_app()
    assert app is not None
    assert app.launch_uri == "steam://open/games"
    assert app.launch_cmd == ["/usr/bin/steam"]


def test_launcher_app_still_offered_without_the_binary(steam_root, steam_settings, monkeypatch):
    """Whatever registered the steam:// handler can still answer the URI."""
    monkeypatch.setattr(steam_module, "first_on_path", lambda *names: None)
    app = make_provider(steam_root, steam_settings).launcher_app()
    assert app is not None
    assert app.launch_uri == "steam://open/games"
    assert app.launch_cmd is None


def test_launcher_app_is_none_without_a_root(steam_settings):
    provider = SteamProvider(
        {**steam_settings, "install_type": "custom", "custom_path": "/nonexistent/steam"}
    )
    assert provider.launcher_app() is None


def test_launcher_app_uses_flatpak_for_a_flatpak_root(tmp_path, steam_settings, monkeypatch):
    root = tmp_path / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
    root.mkdir(parents=True)
    monkeypatch.setattr(
        steam_module, "flatpak_run_command", lambda app_id: ["/usr/bin/flatpak", "run", app_id]
    )
    provider = SteamProvider(
        {**steam_settings, "install_type": "custom", "custom_path": str(root)}
    )
    app = provider.launcher_app()
    assert app.launch_cmd == ["/usr/bin/flatpak", "run", "com.valvesoftware.Steam"]
