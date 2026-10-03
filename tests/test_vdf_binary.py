# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import struct

import pytest

from gameshelf.util.vdf_binary import parse
from gameshelf.util.vdf_text import VdfError


def _string(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"


def _int32(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\x00" + struct.pack("<i", value)


def _map(key: str, body: bytes) -> bytes:
    return b"\x00" + key.encode() + b"\x00" + body + b"\x08"


def test_string_and_int():
    assert parse(_string("k", "v") + _int32("n", 7)) == {"k": "v", "n": 7}


def test_nested_map():
    assert parse(_map("outer", _map("inner", _string("k", "v")))) == {
        "outer": {"inner": {"k": "v"}}
    }


def test_empty_map():
    assert parse(_map("tags", b"")) == {"tags": {}}


def test_negative_int_survives():
    assert parse(_int32("appid", -486924258)) == {"appid": -486924258}


def test_unsigned_conversion():
    value = parse(_int32("appid", -486924258))["appid"] & 0xFFFFFFFF
    assert value == 3808043038


def test_invalid_utf8_is_replaced_not_fatal():
    data = b"\x01" + b"k\x00" + b"caf\xe9" + b"\x00"
    assert parse(data)["k"].startswith("caf")


def test_unknown_type_byte_raises():
    with pytest.raises(VdfError):
        parse(b"\x7f" + b"k\x00")


def test_unterminated_string_raises():
    with pytest.raises(VdfError):
        parse(b"\x01" + b"k\x00" + b"no terminator")


def test_non_bytes_input_rejected():
    with pytest.raises(TypeError):
        parse("not bytes")


def test_real_fixture(fixtures_dir):
    data = (fixtures_dir / "steam/root/userdata/12345678/config/shortcuts.vdf").read_bytes()
    parsed = parse(data)
    entries = parsed["shortcuts"]
    assert len(entries) == 2
    assert entries["0"]["appname"] == "GranBlue Fantasy Relink"
    # Real files use lowercase 'appname'; the capitalised form must NOT be present.
    assert "AppName" not in entries["0"]
    assert entries["1"]["IsHidden"] == 1
