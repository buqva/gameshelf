# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Command line interface. stdout carries JSON and nothing else."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from typing import Any

from . import SCHEMA_VERSION, __version__
from .cache import ScanCache
from .config import ConfigError, decode_config, provider_settings
from .models import Game
from .registry import discover, is_enabled, merge_settings, scan_all

__all__ = ["main"]


def _emit(document: dict[str, Any]) -> None:
    json.dump(document, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _sorted_games(games: list[Game]) -> list[Game]:
    return sorted(games, key=lambda g: (g.sort_title, g.key))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gameshelf", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_config(sub: argparse.ArgumentParser, required: bool = False) -> None:
        sub.add_argument("--config-b64", dest="config_b64", default=None, required=required)
        sub.add_argument("--verbose", action="store_true")

    list_cmd = subparsers.add_parser("list", help="scan and print the game list")
    add_config(list_cmd)
    list_cmd.add_argument("--no-cache", action="store_true", help="bypass the scan cache")
    list_cmd.add_argument("--timings", action="store_true", help="per-provider timings to stderr")
    list_cmd.add_argument("--no-parallel", action="store_true", help="scan providers serially")

    providers_cmd = subparsers.add_parser("providers", help="print provider settings schemas")
    add_config(providers_cmd)

    doctor_cmd = subparsers.add_parser("doctor", help="human-readable diagnostics")
    add_config(doctor_cmd)

    launch_cmd = subparsers.add_parser("launch", help="launch a game by key")
    launch_cmd.add_argument("key")
    add_config(launch_cmd)

    subparsers.add_parser("version", help="print the backend version")
    return parser


def cmd_list(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    config = decode_config(args.config_b64)
    cache = ScanCache(enabled=not args.no_cache)
    result = scan_all(
        provider_settings(config),
        verbose=args.verbose,
        parallel=not args.no_parallel,
        cache=cache,
    )
    cache.save()
    if args.timings:
        for report in sorted(result.reports, key=lambda r: -r.duration_ms):
            if report.enabled:
                source = "cached" if report.cached else "scanned"
                print(
                    f"gameshelf: {report.id:<10} {report.duration_ms:>5} ms  "
                    f"{report.count:>4} games  {source}",
                    file=sys.stderr,
                )
        total_ms = int((time.perf_counter() - started) * 1000)
        print(f"gameshelf: {'total':<10} {total_ms:>5} ms", file=sys.stderr)
    _emit(
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "games": [game.to_dict() for game in _sorted_games(result.games)],
            # The launcher applications themselves, as Game-shaped entries the
            # QML pins ahead of the grid. A separate array so that a client
            # which ignores it sees exactly the list it saw before.
            "launchers": [entry.to_dict() for entry in _sorted_games(result.launchers)],
            "providers": [report.to_dict() for report in result.reports],
            "errors": [error.to_dict() for error in result.errors],
        }
    )
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    config = decode_config(args.config_b64)
    settings_by_id = provider_settings(config)
    entries: list[dict[str, Any]] = []
    for cls in discover():
        merged = merge_settings(cls, settings_by_id.get(cls.id, {}), verbose=args.verbose)
        try:
            detection = cls(merged).detect().to_dict()
        except Exception as exc:  # noqa: BLE001 - a broken detect must not hide the form
            detection = {"available": False, "paths": [], "message": f"{type(exc).__name__}: {exc}"}
        entries.append(
            {
                "id": cls.id,
                "name": cls.name,
                "icon": cls.icon,
                "default_enabled": cls.default_enabled,
                "enabled": is_enabled(cls, merged),
                "settings_schema": [spec.to_dict() for spec in cls.full_schema()],
                "settings": merged,
                "detect": detection,
            }
        )
    _emit({"schema_version": SCHEMA_VERSION, "providers": entries})
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnostics for bug reports. This is the one command that writes prose to stdout."""
    config = decode_config(args.config_b64)
    out = sys.stdout
    print("Game Shelf doctor", file=out)
    print(f"  backend version : {__version__} (schema {SCHEMA_VERSION})", file=out)
    print(f"  python          : {platform.python_version()} ({sys.executable})", file=out)
    print(f"  platform        : {platform.platform()}", file=out)
    print("", file=out)

    from .cache import cache_path

    path = cache_path()
    print(f"  scan cache      : {path} ({'present' if path.exists() else 'absent'})", file=out)
    print("", file=out)

    # Deliberately uncached: doctor exists to show what the launchers really say.
    started = time.perf_counter()
    result = scan_all(provider_settings(config), verbose=args.verbose)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    launchers_by_provider = {entry.provider: entry for entry in result.launchers}

    print("Providers:", file=out)
    for report in sorted(result.reports, key=lambda r: r.id):
        if not report.enabled:
            print(f"  {report.id:<10} disabled", file=out)
            continue
        status = "ok" if report.available else "NOT DETECTED"
        print(
            f"  {report.id:<10} {status:<13} {report.count:>4} games  {report.duration_ms:>5} ms",
            file=out,
        )
        for path in report.detected_paths:
            print(f"      path: {path}", file=out)
        if report.message:
            print(f"      note: {report.message}", file=out)
        launcher = launchers_by_provider.get(report.id)
        if launcher is not None:
            how = launcher.launch_uri or " ".join(launcher.launch_cmd or [])
            print(f"      opens: {how}", file=out)

    print("", file=out)
    print(f"Total: {len(result.games)} games in {elapsed_ms} ms", file=out)
    if result.errors:
        print("", file=out)
        print("Errors:", file=out)
        for error in result.errors:
            print(f"  [{error.provider}] {error.message}", file=out)
            if error.detail and args.verbose:
                for line in error.detail.splitlines():
                    print(f"      {line}", file=out)
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    """Fallback launcher for providers with no URI handler."""
    config = decode_config(args.config_b64)
    result = scan_all(provider_settings(config), verbose=args.verbose, cache=ScanCache())
    for game in result.all_entries():
        if game.key == args.key:
            if not game.launch_cmd:
                _emit({"schema_version": SCHEMA_VERSION, "fatal": f"no launch command for {args.key}"})
                return 3
            subprocess.Popen(
                game.launch_cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _emit({"schema_version": SCHEMA_VERSION, "launched": game.key})
            return 0
    _emit({"schema_version": SCHEMA_VERSION, "fatal": f"no such game: {args.key}"})
    return 4


def cmd_version(_args: argparse.Namespace) -> int:
    _emit({"schema_version": SCHEMA_VERSION, "version": __version__})
    return 0


_COMMANDS = {
    "list": cmd_list,
    "providers": cmd_providers,
    "doctor": cmd_doctor,
    "launch": cmd_launch,
    "version": cmd_version,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse already wrote usage to stderr; keep stdout valid JSON.
        if exc.code not in (0, None):
            _emit({"schema_version": SCHEMA_VERSION, "fatal": "invalid arguments"})
        return int(exc.code or 0)
    try:
        return _COMMANDS[args.command](args)
    except ConfigError as exc:
        _emit({"schema_version": SCHEMA_VERSION, "fatal": str(exc)})
        return 2
    except Exception as exc:  # noqa: BLE001 - the envelope must survive anything
        _emit({"schema_version": SCHEMA_VERSION, "fatal": f"{type(exc).__name__}: {exc}"})
        return 1
