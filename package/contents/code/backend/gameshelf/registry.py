# SPDX-FileCopyrightText: 2026 buqva <github.detergent089@passinbox.com>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Provider discovery, settings merging and isolated scanning."""

from __future__ import annotations

import importlib
import pkgutil
import sys
import threading
import time
import traceback
from typing import Any

from .cache import ScanCache, settings_hash, stat_inputs
from .models import Game, ProviderError, ProviderReport
from .providers.base import (
    DetectResult,
    Provider,
    ProviderContext,
    SettingSpec,
    launcher_game,
)

__all__ = ["discover", "merge_settings", "is_enabled", "scan_all", "ScanResult"]

DEFAULT_TIMEOUT_SECONDS = 5.0


def discover() -> list[type[Provider]]:
    """Import every module in ``gameshelf.providers`` and collect Provider subclasses.

    Import failures are reported to stderr and skipped: a provider module that
    cannot even be imported must not take the whole backend down with it.
    """
    from . import providers as providers_package

    found: dict[str, type[Provider]] = {}
    for module_info in pkgutil.iter_modules(providers_package.__path__):
        if module_info.name.startswith("_") or module_info.name == "base":
            continue
        try:
            module = importlib.import_module(f"{providers_package.__name__}.{module_info.name}")
        except Exception:  # noqa: BLE001 - reported, never fatal
            print(
                f"gameshelf: could not import provider module {module_info.name}",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
            continue
        for attribute in vars(module).values():
            if (
                isinstance(attribute, type)
                and issubclass(attribute, Provider)
                and attribute is not Provider
                and getattr(attribute, "id", "")
            ):
                found[attribute.id] = attribute
    return [found[key] for key in sorted(found)]


def merge_settings(
    provider_cls: type[Provider], user_settings: dict[str, Any], *, verbose: bool = False
) -> dict[str, Any]:
    """Overlay user settings on the schema defaults, dropping unknown keys."""
    schema: list[SettingSpec] = provider_cls.full_schema()
    merged = {spec.key: spec.default for spec in schema}
    known = set(merged)
    for key, value in (user_settings or {}).items():
        if key in known:
            merged[key] = value
        elif verbose:
            print(
                f"gameshelf: ignoring unknown setting {provider_cls.id}.{key}",
                file=sys.stderr,
            )
    return merged


def is_enabled(provider_cls: type[Provider], settings: dict[str, Any]) -> bool:
    value = settings.get("enabled", provider_cls.default_enabled)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


class ScanResult:
    def __init__(self) -> None:
        self.games: list[Game] = []
        # The launcher applications themselves, one per available provider that
        # offers one. Kept apart from ``games`` so they never count towards a
        # provider's game total, land in the scan cache, or reach the filter
        # chips; the QML pins them ahead of the games when the user wants them.
        self.launchers: list[Game] = []
        self.reports: list[ProviderReport] = []
        self.errors: list[ProviderError] = []

    def all_entries(self) -> list[Game]:
        """Everything a key can name, for resolving a launch request."""
        return [*self.launchers, *self.games]


def _launcher_for(instance: Provider, verbose: bool = False) -> Game | None:
    """The provider's launcher tile, or None if it has or wants none.

    Deliberately swallows a failure here rather than letting it abort the
    provider: losing every game because the code that finds a launcher's
    executable tripped over would be a poor trade for a cosmetic tile.
    """
    try:
        app = instance.launcher_app()
    except Exception:  # noqa: BLE001 - a missing tile must not cost the games
        if verbose:
            print(
                f"gameshelf: launcher_app failed for {type(instance).id}",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
        return None
    return launcher_game(type(instance), app) if app is not None else None


def _run_one(
    provider_cls: type[Provider],
    settings: dict[str, Any],
    context: ProviderContext,
    cache: ScanCache | None = None,
    verbose: bool = False,
) -> tuple[list[Game], Game | None, DetectResult, bool]:
    """Scan one provider, reusing its cached games when nothing it reads changed.

    Returns its games, its launcher tile if it offers one, what detection found,
    and whether the cached games were used. The launcher tile is resolved on
    every run: it costs a PATH lookup, and caching it would mean a launcher
    installed since the last scan stayed missing until a game changed.
    """
    instance = provider_cls(settings, context)
    detection = instance.detect()
    if not detection.available:
        if cache is not None:
            cache.drop(provider_cls.id)
        return [], None, detection, False

    launcher = _launcher_for(instance, verbose)

    if cache is None:
        return instance.scan(), launcher, detection, False

    digest = settings_hash(settings)
    try:
        inputs = stat_inputs(instance.cache_inputs())
    except Exception:  # noqa: BLE001 - a provider bug here must not block the scan
        inputs = []

    if inputs:
        cached = cache.get(provider_cls.id, digest, inputs)
        if cached is not None:
            return cached, launcher, detection, True

    games = instance.scan()
    if inputs:
        # Re-stat afterwards: if an input changed while the scan was running, the
        # result may already be stale, so it is not worth caching.
        if stat_inputs(instance.cache_inputs()) == inputs:
            cache.put(provider_cls.id, digest, inputs, games)
        else:
            cache.drop(provider_cls.id)
    return games, launcher, detection, False


def scan_all(
    provider_settings: dict[str, dict[str, Any]],
    *,
    verbose: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    parallel: bool = True,
    cache: ScanCache | None = None,
) -> ScanResult:
    """Scan every enabled provider, isolating failures and timeouts.

    No provider may raise out of here: a broken or hanging launcher shows up as an
    entry in ``errors`` while every other provider still reports its games.
    """
    result = ScanResult()
    classes = discover()
    merged: dict[str, dict[str, Any]] = {
        cls.id: merge_settings(cls, provider_settings.get(cls.id, {}), verbose=verbose)
        for cls in classes
    }
    enabled = [cls for cls in classes if is_enabled(cls, merged[cls.id])]
    context = ProviderContext(enabled_providers=frozenset(cls.id for cls in enabled))

    for cls in classes:
        if cls not in enabled:
            result.reports.append(
                ProviderReport(
                    id=cls.id,
                    enabled=False,
                    available=False,
                    name=cls.name,
                    icon=cls.icon,
                    message="Disabled",
                )
            )

    if not enabled:
        return result

    started: dict[str, float] = {}

    def record(
        cls: type[Provider],
        games: list[Game],
        launcher: Game | None,
        detection: DetectResult,
        cached: bool = False,
    ) -> None:
        duration_ms = int((time.perf_counter() - started[cls.id]) * 1000)
        result.games.extend(games)
        if launcher is not None:
            result.launchers.append(launcher)
        result.reports.append(
            ProviderReport(
                id=cls.id,
                enabled=True,
                available=detection.available,
                name=cls.name,
                icon=cls.icon,
                count=len(games),
                duration_ms=duration_ms,
                detected_paths=list(detection.paths),
                message=detection.message,
                cached=cached,
            )
        )

    def record_failure(cls: type[Provider], exc: BaseException, message: str | None = None) -> None:
        duration_ms = int((time.perf_counter() - started.get(cls.id, time.perf_counter())) * 1000)
        result.reports.append(
            ProviderReport(
                id=cls.id,
                enabled=True,
                available=False,
                name=cls.name,
                icon=cls.icon,
                duration_ms=duration_ms,
                message=message or "Scan failed",
            )
        )
        result.errors.append(
            ProviderError(
                provider=cls.id,
                message=message or f"{type(exc).__name__}: {exc}",
                detail="".join(traceback.format_exception(exc)).strip() or None,
            )
        )

    if not parallel:
        for cls in enabled:
            started[cls.id] = time.perf_counter()
            try:
                record(cls, *_run_one(cls, merged[cls.id], context, cache, verbose))
            except Exception as exc:  # noqa: BLE001 - isolation is the point
                record_failure(cls, exc)
        return result

    # Deliberately not ThreadPoolExecutor: its shutdown joins every worker, so a
    # hung provider would still block the whole scan for as long as it runs, which
    # is exactly what the timeout exists to prevent. Daemon threads are abandoned
    # on timeout and die with the process.
    outcomes: dict[
        str, tuple[list[Game], Game | None, DetectResult, bool] | BaseException
    ] = {}
    threads: list[tuple[type[Provider], threading.Thread]] = []

    def worker(cls: type[Provider]) -> None:
        try:
            outcomes[cls.id] = _run_one(cls, merged[cls.id], context, cache, verbose)
        except BaseException as exc:  # noqa: BLE001 - handed back to the main thread
            outcomes[cls.id] = exc

    for cls in enabled:
        started[cls.id] = time.perf_counter()
        thread = threading.Thread(target=worker, args=(cls,), daemon=True,
                                  name=f"gameshelf-{cls.id}")
        thread.start()
        threads.append((cls, thread))

    deadline = time.monotonic() + timeout
    for cls, thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
        outcome = outcomes.get(cls.id)
        if thread.is_alive() or outcome is None:
            record_failure(cls, TimeoutError(cls.id), f"Timed out after {timeout:g}s")
        elif isinstance(outcome, BaseException):
            record_failure(cls, outcome)
        else:
            record(cls, *outcome)
    return result
