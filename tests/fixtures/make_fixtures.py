#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regenerate the binary fixtures: shortcuts.vdf and the placeholder artwork.

Text fixtures are committed as-is; these two kinds cannot be hand-edited, so they
are built here. Run from anywhere: python3 tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEAM = HERE / "steam"
ROOT = STEAM / "root"

# A 1x1 JPEG and a 1x1 PNG. The provider only ever checks that a file exists and
# records its path, so the smallest valid images are enough and keep the repo tiny.
JPEG_1X1 = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffc00011080001000101011100ffc40014000100000000"
    "000000000000000000000009ffc40014100100000000000000000000000000000000ffda000c03"
    "0100027f00fc7fffd9"
)
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a4944"
    "4154789c6300010000050001` 0d0a2db40000000049454e44ae426082".replace("` ", "")
)


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  {path.relative_to(HERE)}")


def _string(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"


def _int32(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\x00" + struct.pack("<i", value)


def _map(key: str, body: bytes) -> bytes:
    return b"\x00" + key.encode() + b"\x00" + body + b"\x08"


def build_shortcuts() -> bytes:
    """Two entries, mirroring the real file: lowercase 'appname', negative appid,
    and a second entry flagged IsHidden so the filter has something to catch."""
    visible = (
        _int32("appid", -486924258)          # -> 3808043038 unsigned
        + _string("appname", "GranBlue Fantasy Relink")
        + _string("Exe", '"/usr/lib64/heroic/heroic"')
        + _string("StartDir", "/usr/lib64/heroic/")
        + _string("icon", "")
        + _string("ShortcutPath", "/home/testuser/.local/share/applications/sideload.desktop")
        + _string("LaunchOptions", '"--no-gui" "heroic://launch?appName=abc&runner=sideload"')
        + _int32("IsHidden", 0)
        + _int32("LastPlayTime", 1789800000)
        + _map("tags", b"")
    )
    hidden = (
        _int32("appid", -651339046)          # -> 3643628250 unsigned
        + _string("appname", "Hidden Shortcut")
        + _string("Exe", '"/usr/bin/true"')
        + _string("StartDir", "/usr/bin/")
        + _int32("IsHidden", 1)
        + _int32("LastPlayTime", 0)
        + _map("tags", b"")
    )
    return _map("shortcuts", _map("0", visible) + _map("1", hidden))


def main() -> None:
    print("Writing fixtures:")
    write(ROOT / "userdata/12345678/config/shortcuts.vdf", build_shortcuts())

    # Artwork for Cyberpunk (nested, capsule-named) and Factorio (flat, 600x900),
    # which is exactly the two-layout mix found on the real machine.
    cache = ROOT / "appcache/librarycache"
    write(cache / "1091500/6399de67cce3cecadce7900e03f6e09ff910a235/library_capsule.jpg", JPEG_1X1)
    write(cache / "1091500/812a216dbc8e6bc613cbbebcdb797ae707900a9c/library_header.jpg", JPEG_1X1)
    write(cache / "1091500/cf8cec802dc47d0f24b75f9eee135e96812e2652/library_hero.jpg", JPEG_1X1)
    write(cache / "1091500/cf8cec802dc47d0f24b75f9eee135e96812e2652/library_hero_blur.jpg", JPEG_1X1)
    write(cache / "1091500/37680a273aeee84646db37ed0423aafee948d845/logo.png", PNG_1X1)
    write(cache / "427520/library_600x900.jpg", JPEG_1X1)
    write(cache / "427520/header.jpg", JPEG_1X1)

    grid = ROOT / "userdata/12345678/config/grid"
    write(grid / "3808043038p.jpg", JPEG_1X1)
    write(grid / "3808043038.jpg", JPEG_1X1)
    write(grid / "3808043038_hero.jpg", JPEG_1X1)
    write(grid / "3808043038_logo.jpg", JPEG_1X1)


if __name__ == "__main__":
    main()
