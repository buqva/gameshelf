# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gameshelf import registry
from gameshelf.cache import (
    CACHE_SCHEMA_VERSION,
    MISSING,
    ScanCache,
    settings_hash,
    stat_inputs,
)
from gameshelf.models import Art, Game, make_key, sort_title_for
from gameshelf.providers.base import DetectResult, Provider


def make_game(name: str = "Cached Game", **overrides) -> Game:
    defaults = dict(
        key=make_key("fake", None, name),
        provider="fake",
        store=None,
        id=name,
        title=name,
        sort_title=sort_title_for(name),
        installed=True,
        launch_uri="fake://run",
        launch_cmd=["true"],
        art=Art(portrait="file:///art.png", landscape=None, hero=None, logo=None, icon=None),
        last_played=1789800000,
        playtime_minutes=42,
        install_path="/games/cached",
        extra={"runner": "fake"},
    )
    defaults.update(overrides)
    return Game(**defaults)


@pytest.fixture
def cache_file(tmp_path: Path) -> Path:
    return tmp_path / "scan-cache.json"


# -- serialization round trip ---------------------------------------------------


def test_game_survives_a_round_trip():
    original = make_game()
    restored = Game.from_dict(original.to_dict())
    assert restored == original


def test_art_round_trip_preserves_none_fields():
    restored = Game.from_dict(make_game().to_dict())
    assert restored.art.portrait == "file:///art.png"
    assert restored.art.hero is None


def test_from_dict_ignores_unknown_fields():
    payload = make_game().to_dict()
    payload["field_from_a_future_version"] = 1
    assert Game.from_dict(payload).title == "Cached Game"


# -- settings hashing -------------------------------------------------------------


def test_settings_hash_is_order_independent():
    assert settings_hash({"a": 1, "b": 2}) == settings_hash({"b": 2, "a": 1})


def test_settings_hash_changes_with_values():
    assert settings_hash({"a": 1}) != settings_hash({"a": 2})


def test_settings_hash_handles_unserializable_values():
    assert settings_hash({"a": Path("/tmp")})  # must not raise


# -- input snapshots ----------------------------------------------------------------


def test_stat_inputs_records_missing_files(tmp_path):
    snapshot = stat_inputs([tmp_path / "absent"])
    assert snapshot[0][1] == MISSING


def test_stat_inputs_is_sorted_and_deduplicated(tmp_path):
    (tmp_path / "b").write_text("b")
    (tmp_path / "a").write_text("a")
    snapshot = stat_inputs([tmp_path / "b", tmp_path / "a", tmp_path / "b"])
    assert [Path(row[0]).name for row in snapshot] == ["a", "b"]


def test_stat_inputs_notices_size_change(tmp_path):
    target = tmp_path / "f"
    target.write_text("short")
    before = stat_inputs([target])
    target.write_text("much longer content")
    assert stat_inputs([target]) != before


# -- basic cache behaviour -------------------------------------------------------------


def test_miss_then_hit(cache_file, tmp_path):
    target = tmp_path / "input"
    target.write_text("x")
    inputs = stat_inputs([target])

    cache = ScanCache(cache_file)
    assert cache.get("fake", "h1", inputs) is None
    cache.put("fake", "h1", inputs, [make_game()])
    assert cache.save() is True

    reopened = ScanCache(cache_file)
    cached = reopened.get("fake", "h1", inputs)
    assert cached is not None and cached[0].title == "Cached Game"


def test_settings_change_invalidates(cache_file, tmp_path):
    inputs = stat_inputs([tmp_path])
    cache = ScanCache(cache_file)
    cache.put("fake", "h1", inputs, [make_game()])
    assert cache.get("fake", "h2", inputs) is None


def test_input_change_invalidates(cache_file, tmp_path):
    target = tmp_path / "input"
    target.write_text("x")
    cache = ScanCache(cache_file)
    cache.put("fake", "h1", stat_inputs([target]), [make_game()])

    os.utime(target, ns=(0, 12345))
    assert cache.get("fake", "h1", stat_inputs([target])) is None


def test_appearing_file_invalidates(cache_file, tmp_path):
    target = tmp_path / "later"
    cache = ScanCache(cache_file)
    cache.put("fake", "h1", stat_inputs([target]), [make_game()])
    target.write_text("now here")
    assert cache.get("fake", "h1", stat_inputs([target])) is None


def test_drop_forgets_one_provider(cache_file, tmp_path):
    inputs = stat_inputs([tmp_path])
    cache = ScanCache(cache_file)
    cache.put("a", "h", inputs, [make_game("A")])
    cache.put("b", "h", inputs, [make_game("B")])
    cache.drop("a")
    assert cache.get("a", "h", inputs) is None
    assert cache.get("b", "h", inputs) is not None


def test_disabled_cache_never_reads_or_writes(cache_file, tmp_path):
    inputs = stat_inputs([tmp_path])
    ScanCache(cache_file).put("fake", "h", inputs, [make_game()])
    ScanCache(cache_file).save()

    disabled = ScanCache(cache_file, enabled=False)
    assert disabled.get("fake", "h", inputs) is None
    disabled.put("fake", "h", inputs, [make_game()])
    assert disabled.save() is False


def test_save_is_a_noop_when_nothing_changed(cache_file, tmp_path):
    cache = ScanCache(cache_file)
    assert cache.save() is False
    cache.put("fake", "h", stat_inputs([tmp_path]), [])
    assert cache.save() is True
    assert cache.save() is False


# -- robustness ----------------------------------------------------------------------


def test_corrupt_cache_file_is_a_cold_start(cache_file, tmp_path):
    cache_file.write_text("{ this is not json")
    cache = ScanCache(cache_file)
    assert cache.get("fake", "h", stat_inputs([tmp_path])) is None


def test_schema_version_mismatch_discards_the_cache(cache_file, tmp_path):
    inputs = stat_inputs([tmp_path])
    cache_file.write_text(json.dumps({
        "cache_schema_version": CACHE_SCHEMA_VERSION + 1,
        "providers": {"fake": {"settings_hash": "h", "inputs": inputs, "games": []}},
    }))
    assert ScanCache(cache_file).get("fake", "h", inputs) is None


def test_unreadable_cache_directory_does_not_raise(tmp_path):
    blocked = tmp_path / "file-in-the-way" / "scan-cache.json"
    (tmp_path / "file-in-the-way").write_text("not a directory")
    cache = ScanCache(blocked)
    cache.put("fake", "h", [], [make_game()])
    assert cache.save() is False  # reported, not raised


def test_no_temporary_files_are_left_behind(cache_file, tmp_path):
    cache = ScanCache(cache_file)
    cache.put("fake", "h", stat_inputs([tmp_path]), [make_game()])
    cache.save()
    leftovers = [p for p in cache_file.parent.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_written_cache_is_valid_json(cache_file, tmp_path):
    cache = ScanCache(cache_file)
    cache.put("fake", "h", stat_inputs([tmp_path]), [make_game()])
    cache.save()
    document = json.loads(cache_file.read_text())
    assert document["cache_schema_version"] == CACHE_SCHEMA_VERSION
    assert document["providers"]["fake"]["games"][0]["title"] == "Cached Game"


def test_garbage_game_entries_are_a_miss(cache_file, tmp_path):
    inputs = stat_inputs([tmp_path])
    cache_file.write_text(json.dumps({
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "providers": {"fake": {"settings_hash": "h", "inputs": inputs,
                               "games": ["not an object"]}},
    }))
    assert ScanCache(cache_file).get("fake", "h", inputs) is None


# -- integration with scan_all ------------------------------------------------------------


class CountingProvider(Provider):
    id = "counting"
    name = "Counting"
    scans = 0
    watched: Path | None = None

    def detect(self):
        return DetectResult(available=True, paths=["/counting"])

    def scan(self):
        type(self).scans += 1
        return [make_game("Counted", key="counting:-:1", provider="counting")]

    def cache_inputs(self):
        return [type(self).watched] if type(self).watched else []


class OtherProvider(CountingProvider):
    id = "other"
    name = "Other"
    scans = 0

    def scan(self):
        type(self).scans += 1
        return [make_game("Othered", key="other:-:1", provider="other")]


@pytest.fixture
def counting(monkeypatch, tmp_path):
    watched = tmp_path / "watched"
    watched.write_text("v1")
    for cls in (CountingProvider, OtherProvider):
        cls.scans = 0
        cls.watched = watched
    monkeypatch.setattr(registry, "discover", lambda: [CountingProvider, OtherProvider])
    return watched


def test_second_scan_uses_the_cache(cache_file, counting):
    cache = ScanCache(cache_file)
    first = registry.scan_all({}, cache=cache)
    cache.save()
    assert CountingProvider.scans == 1
    assert all(not report.cached for report in first.reports)

    second = registry.scan_all({}, cache=ScanCache(cache_file))
    assert CountingProvider.scans == 1  # not scanned again
    assert all(report.cached for report in second.reports if report.enabled)
    assert len(second.games) == 2


def test_changed_input_invalidates_only_its_own_provider(cache_file, counting, tmp_path):
    cache = ScanCache(cache_file)
    registry.scan_all({}, cache=cache)
    cache.save()

    # Give one provider its own input and change it.
    separate = tmp_path / "separate"
    separate.write_text("x")
    CountingProvider.watched = separate
    cache = ScanCache(cache_file)
    registry.scan_all({}, cache=cache)
    cache.save()

    before_counting, before_other = CountingProvider.scans, OtherProvider.scans
    separate.write_text("changed")
    result = registry.scan_all({}, cache=ScanCache(cache_file))

    assert CountingProvider.scans == before_counting + 1
    assert OtherProvider.scans == before_other
    reports = {report.id: report for report in result.reports}
    assert reports["counting"].cached is False
    assert reports["other"].cached is True


def test_settings_change_forces_a_rescan(cache_file, counting):
    cache = ScanCache(cache_file)
    registry.scan_all({}, cache=cache)
    cache.save()
    registry.scan_all({"counting": {"show_uninstalled": True}}, cache=ScanCache(cache_file))
    assert CountingProvider.scans == 2
    assert OtherProvider.scans == 1


def test_provider_with_no_cache_inputs_is_never_cached(cache_file, counting):
    CountingProvider.watched = None
    cache = ScanCache(cache_file)
    registry.scan_all({}, cache=cache)
    registry.scan_all({}, cache=cache)
    assert CountingProvider.scans == 2  # no inputs means nothing to validate against


def test_scan_all_without_a_cache_always_scans(counting):
    registry.scan_all({})
    registry.scan_all({})
    assert CountingProvider.scans == 2
