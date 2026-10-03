# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Decoding of the config blob the QML passes on the command line."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any
from urllib.parse import unquote

__all__ = ["ConfigError", "decode_config", "encode_config", "provider_settings"]


class ConfigError(ValueError):
    """Raised when --config-b64 cannot be decoded. Fatal: the CLI exits non-zero."""


def decode_config(encoded: str | None) -> dict[str, Any]:
    """Decode ``Qt.btoa(encodeURIComponent(JSON.stringify(cfg)))``.

    An empty or missing argument means "all defaults", which is what a fresh
    widget sends before the user has opened the config dialog.
    """
    if not encoded or not encoded.strip():
        return {}
    try:
        raw = base64.b64decode(encoded.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError(f"config is not valid base64: {exc}") from exc
    try:
        text = unquote(raw.decode("ascii"))
    except UnicodeDecodeError as exc:
        raise ConfigError(f"config is not ASCII after base64 decoding: {exc}") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError("config must be a JSON object")
    return parsed


def encode_config(config: dict[str, Any]) -> str:
    """Inverse of :func:`decode_config`. Used by tests and the doctor command."""
    from urllib.parse import quote

    text = quote(json.dumps(config, separators=(",", ":")))
    return base64.b64encode(text.encode("ascii")).decode("ascii")


def provider_settings(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Pull the ``providers`` object out of a decoded config, tolerantly."""
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return {}
    return {
        str(key): dict(value)
        for key, value in providers.items()
        if isinstance(value, dict)
    }
