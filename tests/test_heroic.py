# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from gameshelf.providers import heroic as heroic_module
from gameshelf.providers.heroic import HeroicProvider, _parse_timestamp


def make_provider(heroic_root: Path, heroic_settings: dict, **overrides) -> HeroicProvider:
    settings = {**heroic_settings, "install_type": "custom", "custom_path": str(heroic_root)}
    settings.update(overrides)
    return HeroicProvider(settings)


def titles(games) -> set[str]:
    return {game.title for game in games}


def by_key(games) -> dict:
    return {game.key: game for game in games}


# -- detection ------------------------------------------------------------------


def test_detect_finds_root(heroic_root, heroic_settings):
    result = make_provider(heroic_root, heroic_settings).detect()
    assert result.available is True
    assert result.paths == [str(heroic_root.resolve())]


def test_detect_reports_missing_root(heroic_settings):
    provider = HeroicProvider(
        {**heroic_settings, "install_type": "custom", "custom_path": "/nonexistent/heroic"}
    )
    assert provider.detect().available is False


# -- installed state: library flag OR installed.json --------------------------------


def test_only_installed_games_by_default(heroic_root, heroic_settings):
    games = make_provider(heroic_root, heroic_settings).scan()
    assert titles(games) == {
        "HOT WHEELS UNLEASHED™",        # epic, is_installed true
        "Master of Magic Classic",      # gog, is_installed true
        "Flight of the Amazon Queen",   # gog, only gog_store/installed.json says so
        "Sideloaded Game One",          # sideload, is_installed true
    }


def test_gog_installed_json_overrides_a_stale_library_flag(heroic_root, heroic_settings):
    """Heroic never writes GOG's installed state back into gog_library.json."""
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:gog:1207659723"]
    assert game.installed is True
    assert game.install_path == "/games/GOG/Flight of the Amazon Queen"
    assert game.extra["platform"] == "windows"


def test_installed_json_dlc_is_not_promoted(heroic_root, heroic_settings):
    import json

    path = heroic_root / "gog_store/installed.json"
    document = json.loads(path.read_text())
    document["installed"].append(
        {"appName": "2056019722", "is_dlc": True, "install_path": "/games/GOG/House Party"}
    )
    path.write_text(json.dumps(document))
    assert "House Party" not in titles(make_provider(heroic_root, heroic_settings).scan())


def test_uninstalled_games_appear_when_requested(heroic_root, heroic_settings):
    games = make_provider(heroic_root, heroic_settings, show_uninstalled=True).scan()
    assert "City of Gangsters" in titles(games)
    assert "Sideloaded Game Two" in titles(games)
    uninstalled = next(g for g in games if g.title == "City of Gangsters")
    assert uninstalled.installed is False


def test_dlc_is_never_listed(heroic_root, heroic_settings):
    games = make_provider(heroic_root, heroic_settings, show_uninstalled=True).scan()
    assert "ARK The Center" not in titles(games)  # install.is_dlc is true


def test_redistributables_are_filtered(heroic_root, heroic_settings):
    games = make_provider(heroic_root, heroic_settings, show_uninstalled=True).scan()
    assert "Galaxy Common Redistributables" not in titles(games)
    assert not any(g.id == "gog-redist" for g in games)


# -- keys, stores and launch URIs ---------------------------------------------------


def test_keys_use_the_store_not_the_runner(heroic_root, heroic_settings):
    keys = set(by_key(make_provider(heroic_root, heroic_settings).scan()))
    assert "heroic:epic:0006475a83f143ba807174654bc09d38" in keys
    assert "heroic:gog:1207658855" in keys
    assert "heroic:sideload:sideloadAppOne" in keys


def test_launch_uri_modern_form(heroic_root, heroic_settings):
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:gog:1207658855"]
    assert game.launch_uri == "heroic://launch?appName=1207658855&runner=gog"


def test_launch_uri_uses_the_runner_name_not_the_store(heroic_root, heroic_settings):
    """Epic games launch through the 'legendary' runner."""
    games = by_key(make_provider(heroic_root, heroic_settings).scan())
    epic = games["heroic:epic:0006475a83f143ba807174654bc09d38"]
    assert "runner=legendary" in epic.launch_uri


def test_launch_uri_legacy_style(heroic_root, heroic_settings):
    provider = make_provider(heroic_root, heroic_settings, launch_uri_style="legacy")
    game = by_key(provider.scan())["heroic:gog:1207658855"]
    assert game.launch_uri == "heroic://launch/gog/1207658855"


def test_launch_uri_percent_encodes_app_name():
    provider = HeroicProvider({})
    assert provider.launch_uri("sideload", "a b&c") == (
        "heroic://launch?appName=a%20b%26c&runner=sideload"
    )


def test_auto_style_resolves_to_modern():
    provider = HeroicProvider({"launch_uri_style": "auto"})
    assert provider.launch_uri("gog", "x") == "heroic://launch?appName=x&runner=gog"


# -- per-store toggles --------------------------------------------------------------


@pytest.mark.parametrize(
    "setting,store,absent",
    [
        ("store_epic", "epic", "HOT WHEELS UNLEASHED™"),
        ("store_gog", "gog", "Master of Magic Classic"),
        ("store_sideload", "sideload", "Sideloaded Game One"),
    ],
)
def test_disabling_a_store_removes_its_games(
    heroic_root, heroic_settings, setting, store, absent
):
    games = make_provider(heroic_root, heroic_settings, **{setting: False}).scan()
    assert absent not in titles(games)
    assert not any(game.store == store for game in games)
    assert len({game.store for game in games}) == 2  # the other two stores still report


def test_disabling_every_store_yields_nothing(heroic_root, heroic_settings):
    provider = make_provider(
        heroic_root, heroic_settings,
        store_epic=False, store_gog=False, store_amazon=False, store_sideload=False,
    )
    assert provider.scan() == []


# -- artwork ---------------------------------------------------------------------------


def test_art_uses_remote_urls_unchanged(heroic_root, heroic_settings):
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:sideload:sideloadAppOne"]
    assert game.art.portrait == "https://cdn2.steamgriddb.com/grid/bbbbbbbb.png"
    assert game.art.landscape == "https://cdn2.steamgriddb.com/grid/aaaaaaaa.png"


def test_missing_art_field_is_none(heroic_root, heroic_settings):
    provider = make_provider(heroic_root, heroic_settings, show_uninstalled=True)
    game = by_key(provider.scan())["heroic:sideload:sideloadAppTwo"]
    assert game.art.landscape is None  # the fixture entry has no art_cover


# -- playtime ----------------------------------------------------------------------------


def test_iso8601_last_played_is_converted_to_unix_seconds(heroic_root, heroic_settings):
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:sideload:sideloadAppOne"]
    assert game.last_played == 1789803223  # 2026-09-19T07:33:43.469Z
    assert game.playtime_minutes == 42


def test_zero_total_played_is_not_reported(heroic_root, heroic_settings):
    provider = make_provider(heroic_root, heroic_settings, show_uninstalled=True)
    game = by_key(provider.scan())["heroic:sideload:sideloadAppTwo"]
    assert game.playtime_minutes is None


def test_game_without_playtime_entry_has_none(heroic_root, heroic_settings):
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:gog:1207658855"]
    assert game.last_played is None and game.playtime_minutes is None


@pytest.mark.parametrize("value,expected", [
    ("2026-09-19T07:33:43.469Z", 1789803223),
    ("2026-09-19T07:33:43+00:00", 1789803223),
    (1789803223, 1789803223),
    (1789803223469, 1789803223),   # milliseconds
    ("", None),
    ("not a date", None),
    (None, None),
    (0, None),
])
def test_parse_timestamp_variants(value, expected):
    assert _parse_timestamp(value) == expected


# -- install paths -------------------------------------------------------------------------


def test_install_path_from_legendary_installed_json(heroic_root, heroic_settings):
    games = by_key(make_provider(heroic_root, heroic_settings).scan())
    epic = games["heroic:epic:0006475a83f143ba807174654bc09d38"]
    assert epic.install_path == "/games/Epic/InstalledEpicGame"


def test_sideload_install_path_from_folder_name(heroic_root, heroic_settings):
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:sideload:sideloadAppOne"]
    assert game.install_path == "/games/Sideloaded One"


def test_relative_folder_name_is_not_used_as_a_path(heroic_root, heroic_settings):
    """Epic's folder_name is a bare directory name, not an absolute path."""
    (heroic_root / "legendaryConfig/legendary/installed.json").unlink()
    games = by_key(make_provider(heroic_root, heroic_settings).scan())
    assert games["heroic:epic:0006475a83f143ba807174654bc09d38"].install_path is None


def test_game_absent_from_installed_json_still_uses_the_library_flag(
    heroic_root, heroic_settings
):
    """A store whose installed.json is empty falls back to is_installed."""
    (heroic_root / "gog_store/installed.json").write_text('{"installed": []}')
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:gog:1207658855"]
    assert game.install_path is None
    assert game.installed is True


# -- resilience ----------------------------------------------------------------------------


def test_empty_amazon_library_is_not_an_error(heroic_root, heroic_settings):
    """nile_library.json is {} on the dev machine."""
    result = make_provider(heroic_root, heroic_settings).scan()
    assert not any(game.store == "amazon" for game in result)


def test_missing_library_file_is_skipped(heroic_root, heroic_settings):
    (heroic_root / "store_cache/gog_library.json").unlink()
    games = make_provider(heroic_root, heroic_settings).scan()
    assert "Master of Magic Classic" not in titles(games)
    assert "Sideloaded Game One" in titles(games)


def test_game_only_in_installed_json_is_still_listed(heroic_root, heroic_settings):
    """A game installed since the library cache was written has nothing else."""
    (heroic_root / "store_cache/gog_library.json").unlink()
    game = by_key(make_provider(heroic_root, heroic_settings).scan())["heroic:gog:1207659723"]
    assert game.installed is True
    assert game.title == "Flight of the Amazon Queen"  # from the install directory
    assert game.art.portrait is None


def test_corrupt_library_file_does_not_break_other_stores(heroic_root, heroic_settings):
    (heroic_root / "store_cache/legendary_library.json").write_text("{not json")
    games = make_provider(heroic_root, heroic_settings).scan()
    assert "Sideloaded Game One" in titles(games)


def test_missing_timestamp_store_is_not_an_error(heroic_root, heroic_settings):
    (heroic_root / "store/timestamp.json").unlink()
    games = make_provider(heroic_root, heroic_settings).scan()
    assert len(games) == 4
    assert all(game.last_played is None for game in games)


def test_entry_without_app_name_is_skipped(heroic_root, heroic_settings):
    import json

    path = heroic_root / "sideload_apps/library.json"
    document = json.loads(path.read_text())
    document["games"].append({"title": "No App Name", "is_installed": True})
    path.write_text(json.dumps(document))
    assert "No App Name" not in titles(make_provider(heroic_root, heroic_settings).scan())


def test_cache_inputs_include_library_and_timestamps(heroic_root, heroic_settings):
    names = {Path(p).name for p in make_provider(heroic_root, heroic_settings).cache_inputs()}
    assert {"timestamp.json", "legendary_library.json", "gog_library.json"} <= names


# -- the Heroic launcher tile ---------------------------------------------------


def test_launcher_app_runs_the_binary(heroic_root, heroic_settings, monkeypatch):
    """Heroic registers heroic:// only for launching a named game, so its tile
    runs the program; the Electron single-instance lock raises an open window."""
    monkeypatch.setattr(heroic_module, "first_on_path", lambda *names: "/usr/bin/heroic")
    app = make_provider(heroic_root, heroic_settings).launcher_app()
    assert app is not None
    assert app.launch_uri is None
    assert app.launch_cmd == ["/usr/bin/heroic"]


def test_launcher_app_is_none_when_only_the_config_survives(
    heroic_root, heroic_settings, monkeypatch
):
    """A leftover ~/.config/heroic is not a launcher worth offering."""
    monkeypatch.setattr(heroic_module, "first_on_path", lambda *names: None)
    monkeypatch.setattr(heroic_module, "flatpak_run_command", lambda app_id: None)
    assert make_provider(heroic_root, heroic_settings).launcher_app() is None


def test_launcher_app_does_not_offer_flatpak_for_a_native_root(
    heroic_root, heroic_settings, monkeypatch
):
    """A missing native binary must not be answered with `flatpak run`."""
    monkeypatch.setattr(heroic_module, "first_on_path", lambda *names: None)
    monkeypatch.setattr(
        heroic_module, "flatpak_run_command", lambda app_id: ["/usr/bin/flatpak", "run", app_id]
    )
    assert make_provider(heroic_root, heroic_settings).launcher_app() is None


def test_launcher_app_uses_flatpak_for_a_flatpak_root(tmp_path, heroic_settings, monkeypatch):
    root = tmp_path / ".var/app/com.heroicgameslauncher.hgl/config/heroic"
    root.mkdir(parents=True)
    monkeypatch.setattr(
        heroic_module, "flatpak_run_command", lambda app_id: ["/usr/bin/flatpak", "run", app_id]
    )
    provider = HeroicProvider(
        {**heroic_settings, "install_type": "custom", "custom_path": str(root)}
    )
    app = provider.launcher_app()
    assert app.launch_cmd == ["/usr/bin/flatpak", "run", "com.heroicgameslauncher.hgl"]


def test_launcher_app_is_none_without_a_root(heroic_settings):
    provider = HeroicProvider(
        {**heroic_settings, "install_type": "custom", "custom_path": "/nonexistent/heroic"}
    )
    assert provider.launcher_app() is None
