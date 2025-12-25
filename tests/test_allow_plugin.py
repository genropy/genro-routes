# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for AllowPlugin with capability accumulation."""

from __future__ import annotations

import pytest

from genro_routes import NOT_AVAILABLE, NotAvailable, Router, RoutingClass, route


class TestAllowPluginBasic:
    """Basic AllowPlugin functionality tests."""

    def test_entry_without_rule_always_accessible(self):
        """Entry without allow_rule is always accessible."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api")
            def public(self):
                return "public"

        svc = Service()
        entries = svc.api.nodes().get("entries", {})
        assert "public" in entries

    def test_entry_with_rule_requires_capabilities(self):
        """Entry with allow_rule requires matching capabilities."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api", allow_rule="redis")
            def cached(self):
                return "cached"

        svc = Service()

        # Without capabilities - entry not accessible
        entries = svc.api.nodes().get("entries", {})
        assert "cached" not in entries

        # With matching capability - entry accessible
        entries = svc.api.nodes(allow_capabilities="redis").get("entries", {})
        assert "cached" in entries

    def test_or_rule_accepts_any_capability(self):
        """Entry with OR rule accepts any matching capability."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api", allow_rule="stripe|paypal")
            def payment(self):
                return "payment"

        svc = Service()

        # With stripe - accessible
        entries = svc.api.nodes(allow_capabilities="stripe").get("entries", {})
        assert "payment" in entries

        # With paypal - accessible
        entries = svc.api.nodes(allow_capabilities="paypal").get("entries", {})
        assert "payment" in entries

        # Without either - not accessible
        entries = svc.api.nodes(allow_capabilities="bitcoin").get("entries", {})
        assert "payment" not in entries

    def test_and_rule_requires_all_capabilities(self):
        """Entry with AND rule requires all capabilities."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api", allow_rule="pyjwt&redis")
            def jwt_cached(self):
                return "jwt_cached"

        svc = Service()

        # With only pyjwt - not accessible
        entries = svc.api.nodes(allow_capabilities="pyjwt").get("entries", {})
        assert "jwt_cached" not in entries

        # With both - accessible
        entries = svc.api.nodes(allow_capabilities="pyjwt,redis").get("entries", {})
        assert "jwt_cached" in entries


class TestAllowPluginInstanceCapabilities:
    """Test capability accumulation from RoutingClass instances."""

    def test_instance_capabilities_from_attribute(self):
        """Capabilities set on instance are used for filtering."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = {"redis", "pyjwt"}

            @route("api", allow_rule="redis")
            def cached(self):
                return "cached"

            @route("api", allow_rule="postgres")
            def db_only(self):
                return "db"

        svc = Service()

        # Instance has redis - cached accessible without passing capabilities
        entries = svc.api.nodes().get("entries", {})
        assert "cached" in entries
        assert "db_only" not in entries  # needs postgres, instance doesn't have it

    def test_instance_capabilities_from_property(self):
        """Capabilities computed via property are used for filtering."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self._has_stripe = True
                self._has_paypal = False

            @property
            def capabilities(self) -> set[str]:
                caps = set()
                if self._has_stripe:
                    caps.add("stripe")
                if self._has_paypal:
                    caps.add("paypal")
                return caps

            @route("api", allow_rule="stripe")
            def stripe_payment(self):
                return "stripe"

            @route("api", allow_rule="paypal")
            def paypal_payment(self):
                return "paypal"

        svc = Service()

        entries = svc.api.nodes().get("entries", {})
        assert "stripe_payment" in entries
        assert "paypal_payment" not in entries

        # Change runtime state
        svc._has_paypal = True
        entries = svc.api.nodes().get("entries", {})
        assert "stripe_payment" in entries
        assert "paypal_payment" in entries

    def test_request_capabilities_combine_with_instance(self):
        """Request capabilities are combined with instance capabilities."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = {"redis"}

            @route("api", allow_rule="redis&pyjwt")
            def jwt_cached(self):
                return "jwt_cached"

        svc = Service()

        # Instance has redis, but entry needs both redis AND pyjwt
        entries = svc.api.nodes().get("entries", {})
        assert "jwt_cached" not in entries

        # Pass pyjwt via request - now has both
        entries = svc.api.nodes(allow_capabilities="pyjwt").get("entries", {})
        assert "jwt_cached" in entries

    def test_capabilities_as_string(self):
        """Capabilities can be set as comma-separated string."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = "redis,pyjwt"

            @route("api", allow_rule="redis&pyjwt")
            def jwt_cached(self):
                return "jwt_cached"

        svc = Service()
        entries = svc.api.nodes().get("entries", {})
        assert "jwt_cached" in entries

    def test_capabilities_as_list(self):
        """Capabilities can be set as list."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = ["redis", "pyjwt"]

            @route("api", allow_rule="redis&pyjwt")
            def jwt_cached(self):
                return "jwt_cached"

        svc = Service()
        entries = svc.api.nodes().get("entries", {})
        assert "jwt_cached" in entries


class TestAllowPluginHierarchyAccumulation:
    """Test capability accumulation across router hierarchy."""

    def test_child_inherits_parent_capabilities(self):
        """Child router accumulates capabilities from parent instance."""

        class ChildService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = {"pyjwt"}

            @route("api", allow_rule="redis&pyjwt")
            def jwt_cached(self):
                return "jwt_cached"

        class ParentService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = {"redis"}
                self.child = ChildService()
                self.api.attach_instance(self.child, name="child")

        parent = ParentService()

        # Child entry needs redis&pyjwt
        # Parent has redis, child has pyjwt
        # Combined: {redis, pyjwt} - entry is accessible
        node = parent.api.node("child/jwt_cached")
        assert node
        assert node.is_callable

    def test_deep_hierarchy_accumulation(self):
        """Capabilities accumulate through multiple levels."""

        class Level3(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = {"level3"}

            @route("api", allow_rule="level1&level2&level3")
            def deep_action(self):
                return "deep"

        class Level2(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = {"level2"}
                self.level3 = Level3()
                self.api.attach_instance(self.level3, name="level3")

        class Level1(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = {"level1"}
                self.level2 = Level2()
                self.api.attach_instance(self.level2, name="level2")

        root = Level1()

        # Entry needs level1&level2&level3
        # Accumulated from hierarchy: {level1, level2, level3}
        node = root.api.node("level2/level3/deep_action")
        assert node
        assert node.is_callable

    def test_request_capabilities_add_to_hierarchy(self):
        """Request capabilities combine with hierarchy capabilities."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = {"child_cap"}

            @route("api", allow_rule="parent_cap&child_cap&request_cap")
            def action(self):
                return "action"

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = {"parent_cap"}
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Parent()

        # Without request_cap - not accessible
        node = root.api.node("child/action")
        assert not node.is_callable

        # With request_cap - accessible
        node = root.api.node("child/action", allow_capabilities="request_cap")
        assert node
        assert node.is_callable


class TestAllowPluginNodeBehavior:
    """Test node() behavior with AllowPlugin."""

    def test_node_returns_not_available_when_filtered(self):
        """node() returns NOT_AVAILABLE sentinel when capability missing."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api", allow_rule="required_cap")
            def protected(self):
                return "protected"

        svc = Service()
        node = svc.api.node("protected")
        assert node.error == "not_available"
        assert not node.is_callable

    def test_node_call_raises_not_available(self):
        """Calling node without required capability raises NotAvailable."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api", allow_rule="required_cap")
            def protected(self):
                return "protected"

        svc = Service()
        node = svc.api.node("protected")

        with pytest.raises(NotAvailable):
            node()

    def test_node_call_works_with_capability(self):
        """Calling node with required capability executes handler."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")
                self.capabilities = {"required_cap"}

            @route("api", allow_rule="required_cap")
            def protected(self):
                return "protected"

        svc = Service()
        node = svc.api.node("protected")
        assert node() == "protected"


class TestAllowPluginRuleValidation:
    """Test rule validation."""

    def test_comma_in_allow_rule_raises_error(self):
        """Comma in allow_rule raises ValueError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

        svc = Service()

        with pytest.raises(ValueError, match="Comma not allowed"):
            svc.routing.configure("api:allow/_all_", rule="stripe,paypal")

    def test_pipe_in_allow_rule_works(self):
        """Pipe (|) in allow_rule works for OR."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("allow")

            @route("api", allow_rule="stripe|paypal")
            def payment(self):
                return "payment"

        svc = Service()
        svc.capabilities = {"stripe"}
        entries = svc.api.nodes().get("entries", {})
        assert "payment" in entries


class TestCapabilitiesSetter:
    """Test capabilities property setter."""

    def test_capabilities_setter_with_none(self):
        """Setting capabilities to None results in empty set."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()
        svc.capabilities = {"redis"}
        assert svc.capabilities == {"redis"}

        svc.capabilities = None
        assert svc.capabilities == set()

    def test_capabilities_setter_invalid_type_raises(self):
        """Setting capabilities to invalid type raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be set, list, str, or None"):
            svc.capabilities = 123
