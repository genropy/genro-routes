"""Logging plugin for Genro Routes.

Wraps handler calls with configurable logging messages including timing.

Configuration
-------------
Accepted keys (router-level or per-handler):
    - ``enabled``: Gate the plugin entirely (default True)
    - ``before``: Log "start" message (default True)
    - ``after``: Log "end" message with timing (default True)
    - ``log``: Use logger.info() when available (default True)
    - ``print``: Always use print() (default False)

Example::

    from genro_routes import Router, RoutedClass, route

    class MyService(RoutedClass):
        def __init__(self):
            self.api = Router(self, name="api").plug("logging")

        @route("api")
        def hello(self):
            return "Hello!"

    # Or configure per-handler:
    @route("api", logging_after=False)
    def fast_handler(self):
        return "fast"
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from genro_routes.core.router import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class LoggingPlugin(BasePlugin):
    """Logging plugin with configurable start/end messages and timing."""

    plugin_code = "logging"
    plugin_description = "Logs handler calls with timing"

    __slots__ = ("_logger",)

    def __init__(self, router, *, logger: logging.Logger | None = None, **cfg):
        self._logger = logger or logging.getLogger("genro_routes")
        super().__init__(router, **cfg)

    def configure(  # type: ignore[override]
        self,
        enabled: bool = True,
        before: bool = True,
        after: bool = True,
        log: bool = True,
        print: bool = False,  # noqa: A002 - shadowing builtin intentionally
    ):
        """Configure logging plugin options.

        Args:
            enabled: Enable/disable the plugin entirely.
            before: Log "{handler} start" before execution.
            after: Log "{handler} end (X ms)" after execution.
            log: Use logger.info() when handlers available.
            print: Always use print() instead of logger.
        """
        pass  # Storage is handled by the wrapper

    def _emit(self, message: str, *, cfg: dict | None = None):
        """Emit a log message via configured sink."""
        # If no config is provided, treat as disabled.
        if cfg is None:
            return
        if cfg.get("print"):
            print(message)
            return
        if cfg.get("log"):
            logger = self._logger
            has_handlers = getattr(logger, "hasHandlers", None) or getattr(
                logger, "has_handlers", None
            )
            can_log = callable(has_handlers) and has_handlers()
            if can_log:
                logger.info(message)
            else:
                print(message)

    def wrap_handler(self, route, entry: MethodEntry, call_next: Callable):
        """Wrap handler with start/end logging and timing."""

        def logged(*args, **kwargs):
            cfg = self._effective_config(entry.name)
            if not cfg["enabled"] or not route.is_plugin_enabled(entry.name, self.name):
                return call_next(*args, **kwargs)
            if cfg["before"]:
                self._emit(f"{entry.name} start", cfg=cfg)
            t0 = time.perf_counter()
            result = call_next(*args, **kwargs)
            elapsed = (time.perf_counter() - t0) * 1000
            if cfg["after"]:
                self._emit(f"{entry.name} end ({elapsed:.2f} ms)", cfg=cfg)
            return result

        return logged

    def _effective_config(self, entry_name: str) -> dict:
        """Get effective configuration for a handler, merging defaults."""
        defaults = {"enabled": True, "before": True, "after": True, "log": True, "print": False}
        cfg = defaults | self.configuration(entry_name)
        flags = cfg.pop("flags", None)
        if isinstance(flags, str):
            cfg.update(self._parse_flags(flags))

        def to_bool(key: str) -> bool:
            val = cfg.get(key)
            return defaults[key] if val is None else bool(val)

        return {key: to_bool(key) for key in defaults}


Router.register_plugin(LoggingPlugin)
