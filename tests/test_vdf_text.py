# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import pytest

from gameshelf.util.vdf_text import VdfError, get_ci, parse


def test_simple_pairs():
    assert parse('"a" "1" "b" "2"') == {"a": "1", "b": "2"}


def test_nested_blocks():
    text = '"root" { "child" { "k" "v" } "n" "1" }'
    assert parse(text) == {"root": {"child": {"k": "v"}, "n": "1"}}


def test_empty_map():
    assert parse('"apps" { }') == {"apps": {}}


def test_comments_are_skipped():
    text = '// leading\n"a" "1" // trailing\n"b" "2"'
    assert parse(text) == {"a": "1", "b": "2"}


def test_comment_inside_block():
    assert parse('"r" {\n// note\n"a" "1"\n}') == {"r": {"a": "1"}}


def test_escapes():
    assert parse(r'"k" "a\"b"') == {"k": 'a"b'}
    assert parse(r'"k" "a\nb"') == {"k": "a\nb"}
    assert parse(r'"k" "a\tb"') == {"k": "a\tb"}
    assert parse(r'"k" "a\\b"') == {"k": "a\\b"}


def test_unknown_escape_keeps_backslash():
    # Windows paths appear unescaped in real .vdf files and must survive.
    assert parse(r'"path" "C:\games\steam"') == {"path": r"C:\games\steam"}


def test_bare_tokens():
    assert parse("key value") == {"key": "value"}


def test_bom_is_stripped():
    assert parse('\ufeff"a" "1"') == {"a": "1"}


def test_duplicate_keys_last_wins():
    assert parse('"a" "1" "a" "2"') == {"a": "2"}


def test_duplicate_keys_multi():
    assert parse('"a" "1" "a" "2"', multi=True) == {"a": ["1", "2"]}


def test_duplicate_keys_multi_three():
    assert parse('"a" "1" "a" "2" "a" "3"', multi=True) == {"a": ["1", "2", "3"]}


def test_trailing_key_without_value_is_tolerated():
    # Steam occasionally leaves a half-written file behind.
    assert parse('"a" "1" "b"') == {"a": "1", "b": ""}


def test_unbalanced_close_raises():
    with pytest.raises(VdfError):
        parse('"a" "1" }')


def test_unterminated_string_raises_with_line():
    with pytest.raises(VdfError) as excinfo:
        parse('"a" "1"\n"b" "unterminated')
    assert excinfo.value.line == 2


def test_unterminated_block_raises():
    with pytest.raises(VdfError):
        parse('"r" { "a" "1"')


def test_get_ci_is_case_insensitive():
    data = {"UserLocalConfigStore": {"Software": {"Valve": {"Steam": {"apps": {"1": {}}}}}}}
    assert get_ci(data, "userlocalconfigstore", "SOFTWARE", "valve", "steam", "Apps") == {"1": {}}


def test_get_ci_missing_returns_none():
    assert get_ci({"a": {}}, "a", "b", "c") is None


def test_get_ci_through_non_dict_returns_none():
    assert get_ci({"a": "scalar"}, "a", "b") is None


def test_real_manifest_shape(fixtures_dir):
    text = (fixtures_dir / "steam/root/steamapps/appmanifest_1091500.acf").read_text()
    parsed = parse(text)
    assert get_ci(parsed, "AppState", "name") == "Cyberpunk 2077"
    assert get_ci(parsed, "AppState", "InstalledDepots", "1091501", "size") == "66366228927"
