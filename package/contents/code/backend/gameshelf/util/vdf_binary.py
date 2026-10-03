# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Parser for Valve's binary KeyValues format, used by ``shortcuts.vdf``.

Layout: each entry starts with a type byte, followed by a NUL-terminated key.
``0x00`` opens a nested map, ``0x01`` is a NUL-terminated UTF-8 string, ``0x02``
is a little-endian int32, and ``0x08`` closes the current map.
"""

from __future__ import annotations

import struct
from typing import Any

from .vdf_text import VdfError

__all__ = ["parse", "loads", "TYPE_MAP", "TYPE_STRING", "TYPE_INT32", "TYPE_END"]

TYPE_MAP = 0x00
TYPE_STRING = 0x01
TYPE_INT32 = 0x02
TYPE_END = 0x08

# Valve also defines float32 (0x03), pointer (0x04), wide string (0x05),
# colour (0x06), uint64 (0x07) and int64 (0x0A). None appear in shortcuts.vdf;
# the two fixed-width ones are handled so an unexpected file degrades to a
# skipped field rather than an exception.
TYPE_FLOAT32 = 0x03
TYPE_UINT64 = 0x07
TYPE_INT64 = 0x0A


def _read_cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end == -1:
        raise VdfError("unterminated string: no NUL before end of file", 0)
    # Valve writes UTF-8 but does not validate it; a mangled byte in a game title
    # must not lose the whole shortcuts file.
    return data[pos:end].decode("utf-8", "replace"), end + 1


def _parse_map(data: bytes, pos: int, depth: int) -> tuple[dict[str, Any], int]:
    if depth > 32:
        raise VdfError("maximum nesting depth exceeded", 0)
    out: dict[str, Any] = {}
    while True:
        if pos >= len(data):
            if depth == 0:
                return out, pos
            raise VdfError("unexpected end of file inside map", 0)
        type_byte = data[pos]
        pos += 1
        if type_byte == TYPE_END:
            return out, pos
        key, pos = _read_cstring(data, pos)
        if type_byte == TYPE_MAP:
            out[key], pos = _parse_map(data, pos, depth + 1)
        elif type_byte == TYPE_STRING:
            out[key], pos = _read_cstring(data, pos)
        elif type_byte == TYPE_INT32:
            (out[key],), pos = struct.unpack_from("<i", data, pos), pos + 4
        elif type_byte == TYPE_FLOAT32:
            (out[key],), pos = struct.unpack_from("<f", data, pos), pos + 4
        elif type_byte in (TYPE_UINT64, TYPE_INT64):
            fmt = "<Q" if type_byte == TYPE_UINT64 else "<q"
            (out[key],), pos = struct.unpack_from(fmt, data, pos), pos + 8
        else:
            raise VdfError(f"unknown type byte {type_byte:#04x} at offset {pos - 1}", 0)


def parse(data: bytes) -> dict[str, Any]:
    """Parse a binary KeyValues document into nested dicts."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("binary VDF expects bytes")
    result, _ = _parse_map(bytes(data), 0, 0)
    return result


def loads(data: bytes) -> dict[str, Any]:
    """Alias for :func:`parse`."""
    return parse(data)
