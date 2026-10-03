# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Parser for Valve's text KeyValues format (``.vdf``, ``.acf``).

The grammar is small: a file is a sequence of ``"key" "value"`` pairs and
``"key" { ... }`` blocks. Tokens may be quoted or bare, ``//`` starts a comment,
and quoted strings understand a handful of escapes.
"""

from __future__ import annotations

from typing import Any

__all__ = ["VdfError", "parse", "loads", "get_ci"]

_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r"}
_WHITESPACE = " \t\r\n"


class VdfError(ValueError):
    """Raised when a VDF document cannot be parsed. Carries the line number."""

    def __init__(self, message: str, line: int) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


class _Tokenizer:
    def __init__(self, text: str) -> None:
        # A UTF-8 BOM survives decoding as U+FEFF; strip it before tokenizing.
        self.text = text.lstrip("\ufeff")
        self.pos = 0
        self.line = 1

    def _advance(self, count: int) -> None:
        chunk = self.text[self.pos : self.pos + count]
        self.line += chunk.count("\n")
        self.pos += count

    def _skip_trivia(self) -> None:
        text = self.text
        while self.pos < len(text):
            ch = text[self.pos]
            if ch in _WHITESPACE:
                self._advance(1)
            elif ch == "/" and text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                self._advance((len(text) if end == -1 else end) - self.pos)
            elif ch == "{" or ch == "}":
                return
            else:
                return

    def next_token(self) -> tuple[str, str] | None:
        """Return ``(kind, value)`` where kind is 'str', 'open' or 'close'."""
        self._skip_trivia()
        if self.pos >= len(self.text):
            return None
        ch = self.text[self.pos]
        if ch == "{":
            self._advance(1)
            return ("open", "{")
        if ch == "}":
            self._advance(1)
            return ("close", "}")
        if ch == '"':
            return ("str", self._read_quoted())
        return ("str", self._read_bare())

    def _read_quoted(self) -> str:
        start_line = self.line
        self._advance(1)  # opening quote
        out: list[str] = []
        text = self.text
        while True:
            if self.pos >= len(text):
                raise VdfError("unterminated quoted string", start_line)
            ch = text[self.pos]
            if ch == '"':
                self._advance(1)
                return "".join(out)
            if ch == "\\":
                if self.pos + 1 >= len(text):
                    raise VdfError("trailing escape in quoted string", self.line)
                nxt = text[self.pos + 1]
                # Unknown escapes keep the backslash: Windows paths in .vdf files
                # are written unescaped, so "C:\games" must survive intact.
                out.append(_ESCAPES.get(nxt, "\\" + nxt))
                self._advance(2)
                continue
            out.append(ch)
            self._advance(1)

    def _read_bare(self) -> str:
        text = self.text
        start = self.pos
        while self.pos < len(text):
            ch = text[self.pos]
            if ch in _WHITESPACE or ch in '{}"':
                break
            if ch == "/" and text.startswith("//", self.pos):
                break
            self._advance(1)
        return text[start:self.pos]


def _merge(target: dict[str, Any], key: str, value: Any, multi: bool) -> None:
    if not multi:
        target[key] = value
        return
    if key in target:
        existing = target[key]
        if isinstance(existing, list):
            existing.append(value)
        else:
            target[key] = [existing, value]
    else:
        target[key] = value


def _parse_block(tk: _Tokenizer, multi: bool, depth: int) -> dict[str, Any]:
    if depth > 64:
        raise VdfError("maximum nesting depth exceeded", tk.line)
    out: dict[str, Any] = {}
    while True:
        token = tk.next_token()
        if token is None:
            if depth == 0:
                return out
            raise VdfError("unexpected end of document inside block", tk.line)
        kind, key = token
        if kind == "close":
            if depth == 0:
                raise VdfError("unbalanced '}'", tk.line)
            return out
        if kind == "open":
            raise VdfError("expected a key, found '{'", tk.line)

        value_token = tk.next_token()
        if value_token is None:
            # Valve's own files are sometimes truncated mid-write. A dangling key
            # at the very end is treated as empty rather than fatal.
            _merge(out, key, "", multi)
            return out
        vkind, value = value_token
        if vkind == "open":
            _merge(out, key, _parse_block(tk, multi, depth + 1), multi)
        elif vkind == "close":
            raise VdfError(f"key {key!r} has no value", tk.line)
        else:
            _merge(out, key, value, multi)


def parse(text: str, *, multi: bool = False) -> dict[str, Any]:
    """Parse VDF text into nested dicts.

    With ``multi=False`` a repeated key keeps the last value. With ``multi=True``
    repeated keys collapse into a list.
    """
    return _parse_block(_Tokenizer(text), multi, 0)


def loads(text: str, *, multi: bool = False) -> dict[str, Any]:
    """Alias for :func:`parse`, for symmetry with the json module."""
    return parse(text, multi=multi)


def get_ci(data: Any, *path: str) -> Any:
    """Walk ``path`` through nested dicts, ignoring key case.

    Returns ``None`` if any step is missing or hits a non-dict. Valve varies the
    casing of keys like ``UserLocalConfigStore`` between client versions, so every
    lookup into their files goes through here.
    """
    current = data
    for segment in path:
        if not isinstance(current, dict):
            return None
        if segment in current:
            current = current[segment]
            continue
        lowered = segment.lower()
        for key, value in current.items():
            if key.lower() == lowered:
                current = value
                break
        else:
            return None
    return current
