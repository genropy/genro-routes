# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for CapabilitiesSet and @capability decorator."""

from __future__ import annotations

import pytest

from genro_routes import Router, RoutingClass, route
from genro_routes.plugins.env import CapabilitiesSet, capability


class TestCapabilityDecorator:
    """Tests for the @capability decorator."""

    def test_marks_method_as_capability(self):
        """Decorator sets _is_capability attribute."""

        class Caps(CapabilitiesSet):
            @capability
            def foo(self) -> bool:
                return True

        caps = Caps()
        assert getattr(caps.foo, "_is_capability", False) is True

    def test_undecorated_method_not_capability(self):
        """Methods without decorator are not capabilities."""

        class Caps(CapabilitiesSet):
            def regular_method(self) -> bool:
                return True

        caps = Caps()
        assert getattr(caps.regular_method, "_is_capability", False) is False


class TestCapabilitiesSet:
    """Tests for CapabilitiesSet base class."""

    def test_iter_yields_active_capabilities(self):
        """Iteration yields only names of active capabilities."""

        class Caps(CapabilitiesSet):
            @capability
            def active(self) -> bool:
                return True

            @capability
            def inactive(self) -> bool:
                return False

        caps = Caps()
        result = list(caps)
        assert result == ["active"]

    def test_contains_active_capability(self):
        """'in' returns True for active capability."""

        class Caps(CapabilitiesSet):
            @capability
            def jwt(self) -> bool:
                return True

        caps = Caps()
        assert "jwt" in caps

    def test_contains_inactive_capability(self):
        """'in' returns False for inactive capability."""

        class Caps(CapabilitiesSet):
            @capability
            def jwt(self) -> bool:
                return False

        caps = Caps()
        assert "jwt" not in caps

    def test_contains_unknown_capability(self):
        """'in' returns False for unknown capability name."""

        class Caps(CapabilitiesSet):
            @capability
            def jwt(self) -> bool:
                return True

        caps = Caps()
        assert "unknown" not in caps

    def test_len_counts_active_capabilities(self):
        """len() returns count of active capabilities."""

        class Caps(CapabilitiesSet):
            @capability
            def a(self) -> bool:
                return True

            @capability
            def b(self) -> bool:
                return True

            @capability
            def c(self) -> bool:
                return False

        caps = Caps()
        assert len(caps) == 2

    def test_dynamic_evaluation(self):
        """Capabilities are evaluated dynamically on each access."""

        class Caps(CapabilitiesSet):
            def __init__(self):
                self._enabled = False

            @capability
            def feature(self) -> bool:
                return self._enabled

        caps = Caps()
        assert "feature" not in caps
        assert len(caps) == 0

        caps._enabled = True
        assert "feature" in caps
        assert len(caps) == 1

    def test_empty_capabilities_set(self):
        """Empty CapabilitiesSet works correctly."""

        class Caps(CapabilitiesSet):
            pass

        caps = Caps()
        assert list(caps) == []
        assert len(caps) == 0
        assert "anything" not in caps


class TestCapabilitiesSetWithRouting:
    """Tests for CapabilitiesSet integration with routing."""

    def test_capabilities_set_as_instance_capabilities(self):
        """CapabilitiesSet can be used as RoutingClass.capabilities."""

        class ServerCaps(CapabilitiesSet):
            @capability
            def redis(self) -> bool:
                return True

            @capability
            def postgres(self) -> bool:
                return False

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.capabilities = ServerCaps()

            @route("api", env_requires="redis")
            def needs_redis(self):
                return "ok"

            @route("api", env_requires="postgres")
            def needs_postgres(self):
                return "ok"

        svc = Service()

        # redis is active - entry visible in nodes()
        entries = svc.api.nodes().get("entries", {})
        assert "needs_redis" in entries

        # postgres is inactive - entry not visible
        assert "needs_postgres" not in entries

    def test_dynamic_capabilities_affect_routing(self):
        """Dynamic capability changes affect route availability."""

        class DynamicCaps(CapabilitiesSet):
            def __init__(self):
                self._maintenance = False

            @capability
            def online(self) -> bool:
                return not self._maintenance

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self._caps = DynamicCaps()
                self.capabilities = self._caps

            @route("api", env_requires="online")
            def process(self):
                return "processed"

        svc = Service()

        # Initially online - entry visible
        entries = svc.api.nodes().get("entries", {})
        assert "process" in entries

        # Enter maintenance mode - entry not visible
        svc._caps._maintenance = True
        entries = svc.api.nodes().get("entries", {})
        assert "process" not in entries

        # Exit maintenance mode - entry visible again
        svc._caps._maintenance = False
        entries = svc.api.nodes().get("entries", {})
        assert "process" in entries
