# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for shorthand plugin syntax in @route decorator."""

from __future__ import annotations

from typing import Any

import pytest

from genro_routes import Router, RoutingClass, route
from genro_routes.core.router import _PLUGIN_REGISTRY
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class ShorthandPlugin(BasePlugin):
    """Test plugin that declares a default parameter."""

    plugin_code = "shorthand"
    plugin_description = "Test plugin for shorthand syntax"
    plugin_default_param = "rule"

    def configure(
        self, *, _target: str = "_all_", flags: str | None = None, rule: str = ""
    ) -> None:
        self._rule = rule

    def on_filter(
        self, router: Any, func: Any, entry: MethodEntry, **filters: Any
    ) -> MethodEntry | None:
        return entry


class NoDefaultPlugin(BasePlugin):
    """Test plugin without plugin_default_param."""

    plugin_code = "nodefault"
    plugin_description = "Test plugin without default param"

    def configure(
        self, *, _target: str = "_all_", flags: str | None = None, value: str = ""
    ) -> None:
        self._value = value

    def on_filter(
        self, router: Any, func: Any, entry: MethodEntry, **filters: Any
    ) -> MethodEntry | None:
        return entry


@pytest.fixture(autouse=True)
def _register_test_plugins():
    """Register and unregister test plugins for each test."""
    Router.register_plugin(ShorthandPlugin)
    Router.register_plugin(NoDefaultPlugin)
    yield
    _PLUGIN_REGISTRY.pop("shorthand", None)
    _PLUGIN_REGISTRY.pop("nodefault", None)


class Owner(RoutingClass):
    pass


def _make_router():
    return Router(Owner(), name="api").plug("shorthand").plug("nodefault")


def _get_plugin_config(router, entry_name):
    """Get plugin_config from the internal MethodEntry metadata."""
    entry = router._entries[entry_name]
    return entry.metadata.get("plugin_config", {})


class TestShorthandViaAddEntry:
    """Test shorthand syntax through add_entry()."""

    def test_shorthand_resolves_to_default_param(self):
        """shorthand='value' resolves to shorthand_rule='value'."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", shorthand="admin")
        cfg = _get_plugin_config(router, "action")
        assert cfg.get("shorthand") == {"rule": "admin"}

    def test_longform_still_works(self):
        """shorthand_rule='value' continues to work."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", shorthand_rule="admin")
        cfg = _get_plugin_config(router, "action")
        assert cfg.get("shorthand") == {"rule": "admin"}

    def test_plugin_without_default_param_not_shorthand(self):
        """Plugin without plugin_default_param: bare key goes to core_options."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", nodefault="something")
        cfg = _get_plugin_config(router, "action")
        assert "nodefault" not in cfg

    def test_shorthand_and_longform_coexist(self):
        """Shorthand on one plugin, longform on another."""
        router = _make_router()
        router.add_entry(
            lambda: "ok",
            name="action",
            shorthand="admin",
            nodefault_value="test",
        )
        cfg = _get_plugin_config(router, "action")
        assert cfg.get("shorthand") == {"rule": "admin"}
        assert cfg.get("nodefault") == {"value": "test"}


class TestShorthandViaDecorator:
    """Test shorthand syntax through @route decorator."""

    def test_shorthand_via_route_decorator(self):
        """@route('api', shorthand='admin') resolves to shorthand_rule='admin'."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("shorthand").plug("nodefault")

            @route("api", shorthand="admin")
            def action(self):
                return "ok"

        svc = Svc()
        cfg = _get_plugin_config(svc.api, "action")
        assert cfg.get("shorthand") == {"rule": "admin"}

    def test_longform_via_route_decorator(self):
        """@route('api', shorthand_rule='admin') still works."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("shorthand").plug("nodefault")

            @route("api", shorthand_rule="admin")
            def action(self):
                return "ok"

        svc = Svc()
        cfg = _get_plugin_config(svc.api, "action")
        assert cfg.get("shorthand") == {"rule": "admin"}

    def test_mixed_shorthand_and_longform_in_decorator(self):
        """@route with shorthand on one plugin, longform on another."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("shorthand").plug("nodefault")

            @route("api", shorthand="admin", nodefault_value="test")
            def action(self):
                return "ok"

        svc = Svc()
        cfg = _get_plugin_config(svc.api, "action")
        assert cfg.get("shorthand") == {"rule": "admin"}
        assert cfg.get("nodefault") == {"value": "test"}
