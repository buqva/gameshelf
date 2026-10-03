# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import time

import pytest

from gameshelf import registry
from gameshelf.models import Game, make_key, sort_title_for
from gameshelf.providers.base import DetectResult, Provider, SettingSpec
from gameshelf.providers.steam import SteamProvider


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


class GoodProvider(Provider):
    id = "good"
    name = "Good"
    icon = "applications-games"

    def detect(self):
        return DetectResult(available=True, paths=["/somewhere"])

    def scan(self):
        return [make_game("good", "Good Game")]


class BrokenProvider(Provider):
    id = "broken"
    name = "Broken"

    def detect(self):
        return DetectResult(available=True, paths=[])

    def scan(self):
        raise RuntimeError("this provider is deliberately broken")


class BrokenDetectProvider(Provider):
    id = "brokendetect"
    name = "Broken Detect"

    def detect(self):
        raise OSError("detect exploded")

    def scan(self):
        return []


class SlowProvider(Provider):
    id = "slow"
    name = "Slow"

    def detect(self):
        return DetectResult(available=True, paths=[])

    def scan(self):
        time.sleep(5)
        return []


class UnavailableProvider(Provider):
    id = "unavailable"
    name = "Unavailable"

    def detect(self):
        return DetectResult(available=False, paths=[], message="not installed")

    def scan(self):  # pragma: no cover - must never be called
        raise AssertionError("scan() called on an unavailable provider")


class ConfigurableProvider(Provider):
    id = "configurable"
    name = "Configurable"
    default_enabled = False

    @classmethod
    def settings_schema(cls):
        return [
            SettingSpec(key="depth", type="int", label="Depth", default=3),
            SettingSpec(key="mode", type="string", label="Mode", default="fast"),
        ]

    def detect(self):
        return DetectResult(available=True, paths=[])

    def scan(self):
        return []


@pytest.fixture
def fake_providers(monkeypatch):
    def install(*classes):
        monkeypatch.setattr(registry, "discover", lambda: list(classes))
        return classes

    return install


# -- discovery ------------------------------------------------------------------


def test_discover_finds_steam():
    assert SteamProvider in registry.discover()


def test_discover_skips_the_base_module():
    assert all(cls.id for cls in registry.discover())


# -- settings merging -------------------------------------------------------------


def test_merge_applies_defaults():
    merged = registry.merge_settings(ConfigurableProvider, {})
    assert merged["depth"] == 3
    assert merged["mode"] == "fast"
    assert merged["enabled"] is False  # this provider's default_enabled


def test_merge_overlays_user_values():
    merged = registry.merge_settings(ConfigurableProvider, {"depth": 9})
    assert merged["depth"] == 9
    assert merged["mode"] == "fast"


def test_merge_drops_unknown_keys():
    merged = registry.merge_settings(ConfigurableProvider, {"nonsense": 1})
    assert "nonsense" not in merged


def test_common_settings_are_present_for_every_provider():
    for cls in registry.discover():
        keys = {spec.key for spec in cls.full_schema()}
        assert {"enabled", "show_uninstalled"} <= keys


def test_is_enabled_accepts_string_booleans():
    assert registry.is_enabled(GoodProvider, {"enabled": "true"}) is True
    assert registry.is_enabled(GoodProvider, {"enabled": "false"}) is False
    assert registry.is_enabled(GoodProvider, {"enabled": 1}) is True


# -- isolation: the M1 acceptance criterion -----------------------------------------


def test_broken_provider_does_not_hide_a_working_one(fake_providers):
    fake_providers(GoodProvider, BrokenProvider)
    result = registry.scan_all({})
    assert [game.title for game in result.games] == ["Good Game"]
    assert [error.provider for error in result.errors] == ["broken"]
    assert "deliberately broken" in result.errors[0].message


def test_broken_provider_error_carries_a_traceback(fake_providers):
    fake_providers(BrokenProvider)
    result = registry.scan_all({})
    assert "RuntimeError" in result.errors[0].detail


def test_broken_detect_is_isolated(fake_providers):
    fake_providers(GoodProvider, BrokenDetectProvider)
    result = registry.scan_all({})
    assert len(result.games) == 1
    assert result.errors[0].provider == "brokendetect"


def test_slow_provider_times_out_without_blocking(fake_providers):
    fake_providers(GoodProvider, SlowProvider)
    started = time.perf_counter()
    result = registry.scan_all({}, timeout=0.2)
    assert time.perf_counter() - started < 4
    assert len(result.games) == 1
    assert "Timed out" in result.errors[0].message


def test_unavailable_provider_is_not_scanned(fake_providers):
    fake_providers(UnavailableProvider)
    result = registry.scan_all({})
    assert result.games == []
    assert result.errors == []
    report = result.reports[0]
    assert report.available is False
    assert report.message == "not installed"


# -- reports ------------------------------------------------------------------------


def test_disabled_provider_is_reported_but_not_scanned(fake_providers):
    fake_providers(GoodProvider)
    result = registry.scan_all({"good": {"enabled": False}})
    assert result.games == []
    report = next(r for r in result.reports if r.id == "good")
    assert report.enabled is False
    assert report.message == "Disabled"


def test_every_provider_gets_exactly_one_report(fake_providers):
    fake_providers(GoodProvider, BrokenProvider, UnavailableProvider)
    result = registry.scan_all({})
    ids = [report.id for report in result.reports]
    assert sorted(ids) == ["broken", "good", "unavailable"]


def test_report_counts_and_paths(fake_providers):
    fake_providers(GoodProvider)
    report = registry.scan_all({}).reports[0]
    assert report.count == 1
    assert report.detected_paths == ["/somewhere"]


def test_report_carries_the_display_name_and_icon(fake_providers):
    """The QML labels filter chips and tile badges from these."""
    fake_providers(GoodProvider)
    report = registry.scan_all({}).reports[0]
    assert report.name == "Good"
    assert report.icon == "applications-games"


def test_disabled_and_failed_reports_carry_the_name_too(fake_providers):
    """A chip or badge must still be labelled when the provider did not run."""
    fake_providers(GoodProvider, BrokenProvider)
    reports = {r.id: r for r in registry.scan_all({"good": {"enabled": False}}).reports}
    assert reports["good"].enabled is False
    assert reports["good"].name == "Good"
    assert reports["broken"].name == "Broken"


def test_serial_mode_matches_parallel(fake_providers):
    fake_providers(GoodProvider, BrokenProvider)
    parallel = registry.scan_all({}, parallel=True)
    serial = registry.scan_all({}, parallel=False)
    assert [g.key for g in parallel.games] == [g.key for g in serial.games]
    assert len(parallel.errors) == len(serial.errors) == 1


def test_context_lists_enabled_providers(fake_providers, monkeypatch):
    seen = {}

    class ContextSpy(Provider):
        id = "spy"
        name = "Spy"

        def detect(self):
            return DetectResult(available=True, paths=[])

        def scan(self):
            seen["enabled"] = self.context.enabled_providers
            return []

    fake_providers(GoodProvider, ContextSpy)
    registry.scan_all({})
    assert seen["enabled"] == frozenset({"good", "spy"})


def test_no_providers_enabled_returns_empty(fake_providers):
    fake_providers(GoodProvider)
    result = registry.scan_all({"good": {"enabled": False}})
    assert result.games == [] and result.errors == []
