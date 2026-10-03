# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from gameshelf import SCHEMA_VERSION, cli, registry
from gameshelf.config import ConfigError, decode_config, encode_config, provider_settings
from tests.conftest import BACKEND


def run(capsys, *argv) -> tuple[int, dict]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


# -- config encoding -------------------------------------------------------------


def test_round_trip():
    config = {"providers": {"steam": {"enabled": True, "hide_tools": False}}}
    assert decode_config(encode_config(config)) == config


def test_empty_config_means_defaults():
    assert decode_config(None) == {}
    assert decode_config("") == {}
    assert decode_config("   ") == {}


def test_non_ascii_survives_the_qt_encoding():
    config = {"providers": {"steam": {"custom_path": "/home/ünïcode/Štěam"}}}
    assert decode_config(encode_config(config)) == config


def test_bad_base64_raises():
    with pytest.raises(ConfigError):
        decode_config("not base64 !!!")


def test_valid_base64_that_is_not_json_raises():
    import base64

    with pytest.raises(ConfigError):
        decode_config(base64.b64encode(b"hello").decode())


def test_json_array_is_rejected():
    import base64
    from urllib.parse import quote

    payload = base64.b64encode(quote("[1,2]").encode()).decode()
    with pytest.raises(ConfigError):
        decode_config(payload)


def test_provider_settings_ignores_non_objects():
    assert provider_settings({"providers": {"steam": {"a": 1}, "bad": "x"}}) == {"steam": {"a": 1}}


def test_provider_settings_without_providers_key():
    assert provider_settings({}) == {}


# -- envelope ---------------------------------------------------------------------


def test_version(capsys):
    code, document = run(capsys, "version")
    assert code == 0
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["version"]


def test_list_envelope_shape(capsys):
    code, document = run(capsys, "list")
    assert code == 0
    assert set(document) == {
        "schema_version",
        "generated_at",
        "games",
        "launchers",
        "providers",
        "errors",
    }
    assert isinstance(document["games"], list)
    assert isinstance(document["launchers"], list)
    assert isinstance(document["providers"], list)


def test_list_games_are_sorted_by_sort_title(capsys):
    _, document = run(capsys, "list")
    titles = [game["sort_title"] for game in document["games"]]
    assert titles == sorted(titles)


def test_list_game_objects_carry_every_field(capsys):
    _, document = run(capsys, "list")
    if not document["games"]:
        pytest.skip("no launchers installed on this machine")
    expected = {
        "key", "provider", "store", "id", "title", "sort_title", "installed",
        "launch_uri", "launch_cmd", "art", "last_played", "playtime_minutes",
        "install_path", "extra",
    }
    assert set(document["games"][0]) == expected
    assert set(document["games"][0]["art"]) == {
        "portrait", "landscape", "hero", "logo", "icon"
    }


def test_disabling_every_provider_yields_no_games(capsys):
    config = encode_config(
        {"providers": {cls.id: {"enabled": False} for cls in cli.discover()}}
    )
    _, document = run(capsys, "list", "--config-b64", config)
    assert document["games"] == []
    assert document["errors"] == []


def test_providers_command_shape(capsys):
    code, document = run(capsys, "providers")
    assert code == 0
    steam = next(p for p in document["providers"] if p["id"] == "steam")
    assert set(steam) >= {"id", "name", "icon", "default_enabled", "settings_schema", "detect"}
    keys = {spec["key"] for spec in steam["settings_schema"]}
    assert {"enabled", "show_uninstalled", "install_type", "hide_tools"} <= keys


def test_providers_schema_entries_are_complete(capsys):
    _, document = run(capsys, "providers")
    for provider in document["providers"]:
        for spec in provider["settings_schema"]:
            assert set(spec) == {"key", "type", "label", "default", "help", "options", "advanced"}
            assert spec["type"] in ("bool", "string", "enum", "path", "stringlist", "int")
            if spec["type"] == "enum":
                assert spec["options"], f"{spec['key']} is an enum with no options"


def test_enum_defaults_are_listed_in_options(capsys):
    _, document = run(capsys, "providers")
    for provider in document["providers"]:
        for spec in provider["settings_schema"]:
            if spec["type"] == "enum":
                values = {option["value"] for option in spec["options"]}
                assert spec["default"] in values


# -- exit codes -------------------------------------------------------------------


def test_bad_config_is_fatal_and_still_prints_json(capsys):
    code, document = run(capsys, "list", "--config-b64", "!!!not base64!!!")
    assert code == 2
    assert "fatal" in document
    assert document["schema_version"] == SCHEMA_VERSION


def test_unknown_game_key_for_launch(capsys):
    code, document = run(capsys, "launch", "nope:-:0")
    assert code == 4
    assert "fatal" in document


def test_invalid_arguments_exit_nonzero_with_json(capsys):
    code, document = run(capsys, "list", "--nonsense")
    assert code != 0
    assert document["fatal"] == "invalid arguments"


# -- the real entry point ------------------------------------------------------------


def test_run_py_prints_only_json_on_stdout():
    result = subprocess.run(
        [sys.executable, str(BACKEND / "run.py"), "list", "--verbose"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    document = json.loads(result.stdout)  # would raise if anything else leaked to stdout
    assert document["schema_version"] == SCHEMA_VERSION


def test_run_py_survives_a_missing_config_argument():
    result = subprocess.run(
        [sys.executable, str(BACKEND / "run.py"), "list", "--config-b64", ""],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["schema_version"] == SCHEMA_VERSION


def test_timings_go_to_stderr_not_stdout():
    result = subprocess.run(
        [sys.executable, str(BACKEND / "run.py"), "list", "--timings"],
        capture_output=True, text=True, timeout=60,
    )
    json.loads(result.stdout)
    assert "ms" in result.stderr or result.stderr == ""


def test_doctor_is_human_readable():
    result = subprocess.run(
        [sys.executable, str(BACKEND / "run.py"), "doctor"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "Game Shelf doctor" in result.stdout
    assert "Providers:" in result.stdout


# -- cache flags (M4) ---------------------------------------------------------


def test_no_cache_flag_is_accepted(capsys):
    code, document = run(capsys, "list", "--no-cache")
    assert code == 0
    assert "games" in document


def test_provider_reports_carry_a_cached_flag(capsys):
    _, document = run(capsys, "list", "--no-cache")
    for report in document["providers"]:
        assert "cached" in report
        assert report["cached"] is False  # --no-cache can never report a hit


def test_list_writes_and_then_reuses_the_cache(tmp_path, monkeypatch):
    """A second run must not re-read the launcher files."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    env = dict(os.environ)

    def run_list(*extra):
        result = subprocess.run(
            [sys.executable, str(BACKEND / "run.py"), "list", *extra],
            capture_output=True, text=True, timeout=60, env=env,
        )
        assert result.returncode == 0
        return json.loads(result.stdout)

    first = run_list()
    assert (tmp_path / "gameshelf" / "scan-cache.json").is_file()
    second = run_list()

    assert [g["key"] for g in first["games"]] == [g["key"] for g in second["games"]]
    # Only providers that actually read files can report a cache hit; one that
    # declares no cache inputs, such as a launcher-tile-only provider, has
    # nothing to re-read in the first place.
    caching = {
        cls.id
        for cls in registry.discover()
        if cls(registry.merge_settings(cls, {})).cache_inputs()
    }
    reused = [
        r
        for r in second["providers"]
        if r["enabled"] and r["available"] and r["id"] in caching
    ]
    if reused:
        assert all(r["cached"] for r in reused)


def test_no_cache_bypasses_an_existing_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    env = dict(os.environ)

    def run_list(*extra):
        result = subprocess.run(
            [sys.executable, str(BACKEND / "run.py"), "list", *extra],
            capture_output=True, text=True, timeout=60, env=env,
        )
        return json.loads(result.stdout)

    run_list()
    document = run_list("--no-cache")
    assert all(not r["cached"] for r in document["providers"])


def test_doctor_never_reports_cached_results(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    env = dict(os.environ)
    subprocess.run([sys.executable, str(BACKEND / "run.py"), "list"],
                   capture_output=True, text=True, timeout=60, env=env)
    result = subprocess.run([sys.executable, str(BACKEND / "run.py"), "doctor"],
                            capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0
    assert "scan cache" in result.stdout


# -- launcher tiles in the envelope ----------------------------------------------


@pytest.fixture
def one_launcher(monkeypatch):
    """A single fake provider with one game and one launcher tile."""
    from gameshelf import registry
    from gameshelf.models import Game, make_key, sort_title_for
    from gameshelf.providers.base import DetectResult, LauncherApp, Provider

    class Fake(Provider):
        id = "fake"
        name = "Fake Launcher"
        icon = "fake-icon"

        def detect(self):
            return DetectResult(available=True, paths=["/fake"])

        def scan(self):
            return [
                Game(
                    key=make_key("fake", None, "1"),
                    provider="fake",
                    store=None,
                    id="1",
                    title="Fake Game",
                    sort_title=sort_title_for("Fake Game"),
                    installed=True,
                )
            ]

        def launcher_app(self):
            return LauncherApp(title="Fake Launcher", launch_cmd=["/usr/bin/fake"])

    monkeypatch.setattr(registry, "discover", lambda: [Fake])
    return Fake


def test_list_reports_launchers_separately(capsys, one_launcher):
    _, document = run(capsys, "list", "--no-cache")
    assert [g["title"] for g in document["games"]] == ["Fake Game"]
    assert [e["title"] for e in document["launchers"]] == ["Fake Launcher"]


def test_launcher_entries_are_marked_for_the_qml(capsys, one_launcher):
    _, document = run(capsys, "list", "--no-cache")
    entry = document["launchers"][0]
    assert entry["extra"]["is_launcher"] is True
    assert entry["extra"]["icon"] == "fake-icon"
    assert entry["store"] == "launcher"


def test_launcher_entries_have_the_same_shape_as_games(capsys, one_launcher):
    """One delegate renders both, so the QML must not meet a missing field."""
    _, document = run(capsys, "list", "--no-cache")
    assert set(document["launchers"][0]) == set(document["games"][0])


def test_launch_resolves_a_launcher_key(capsys, one_launcher, monkeypatch):
    calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    code, document = run(capsys, "launch", "fake:launcher:fake")
    assert code == 0
    assert document["launched"] == "fake:launcher:fake"
    assert calls == [["/usr/bin/fake"]]


def test_doctor_shows_how_a_launcher_opens(capsys, one_launcher):
    cli.main(["doctor"])
    assert "opens: /usr/bin/fake" in capsys.readouterr().out
