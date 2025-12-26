# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for EnvPlugin with capability accumulation."""

from __future__ import annotations

import pytest

from genro_routes import NotAvailable, Router, RoutingClass, route
from genro_routes.plugins.env import CapabilitiesSet, capability


# ---------------------------------------------------------------------------
# CapabilitiesSet helper classes for tests
# ---------------------------------------------------------------------------


class EmptyCapabilities(CapabilitiesSet):
    """No capabilities."""

    pass


class RedisCapabilities(CapabilitiesSet):
    """Redis capability only."""

    @capability
    def redis(self) -> bool:
        return True


class RedisPyjwtCapabilities(CapabilitiesSet):
    """Redis and pyjwt capabilities."""

    @capability
    def redis(self) -> bool:
        return True

    @capability
    def pyjwt(self) -> bool:
        return True


class PyjwtCapabilities(CapabilitiesSet):
    """Pyjwt capability only."""

    @capability
    def pyjwt(self) -> bool:
        return True


class StripeCapabilities(CapabilitiesSet):
    """Stripe capability only."""

    @capability
    def stripe(self) -> bool:
        return True


class PaypalCapabilities(CapabilitiesSet):
    """Paypal capability only."""

    @capability
    def paypal(self) -> bool:
        return True


class Cap1Capabilities(CapabilitiesSet):
    """cap1 capability."""

    @capability
    def cap1(self) -> bool:
        return True


class ChildCapCapabilities(CapabilitiesSet):
    """child_cap capability."""

    @capability
    def child_cap(self) -> bool:
        return True


class ParentCapCapabilities(CapabilitiesSet):
    """parent_cap capability."""

    @capability
    def parent_cap(self) -> bool:
        return True


class Level1Capabilities(CapabilitiesSet):
    """level1 capability."""

    @capability
    def level1(self) -> bool:
        return True


class Level2Capabilities(CapabilitiesSet):
    """level2 capability."""

    @capability
    def level2(self) -> bool:
        return True


class Level3Capabilities(CapabilitiesSet):
    """level3 capability."""

    @capability
    def level3(self) -> bool:
        return True


class RequiredCapCapabilities(CapabilitiesSet):
    """required_cap capability."""

    @capability
    def required_cap(self) -> bool:
        return True


class TestEnvPluginBasic:
    """Basic EnvPlugin functionality tests."""

    def test_entry_without_rule_always_accessible(self):
        """Entry without env_requires is always accessible."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api")
            def public(self):
                return "public"

        svc = Service()
        entries = svc.api.nodes().get("entries", {})
        assert "public" in entries

    def test_entry_with_rule_requires_capabilities(self):
        """Entry with env_requires requires matching capabilities."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="redis")
            def cached(self):
                return "cached"

        svc = Service()

        # Without capabilities - entry not accessible
        entries = svc.api.nodes().get("entries", {})
        assert "cached" not in entries

        # With matching capability - entry accessible
        entries = svc.api.nodes(env_capabilities="redis").get("entries", {})
        assert "cached" in entries

    def test_or_rule_accepts_any_capability(self):
        """Entry with OR rule accepts any matching capability."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="stripe|paypal")
            def payment(self):
                return "payment"

        svc = Service()

        # With stripe - accessible
        entries = svc.api.nodes(env_capabilities="stripe").get("entries", {})
        assert "payment" in entries

        # With paypal - accessible
        entries = svc.api.nodes(env_capabilities="paypal").get("entries", {})
        assert "payment" in entries

        # Without either - not accessible
        entries = svc.api.nodes(env_capabilities="bitcoin").get("entries", {})
        assert "payment" not in entries

    def test_and_rule_requires_all_capabilities(self):
        """Entry with AND rule requires all capabilities."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="pyjwt&redis")
            def jwt_cached(self):
                return "jwt_cached"

        svc = Service()

        # With only pyjwt - not accessible
        entries = svc.api.nodes(env_capabilities="pyjwt").get("entries", {})
        assert "jwt_cached" not in entries

        # With both - accessible
        entries = svc.api.nodes(env_capabilities="pyjwt,redis").get("entries", {})
        assert "jwt_cached" in entries


class TestEnvPluginInstanceCapabilities:
    """Test capability accumulation from RoutingClass instances."""

    def test_instance_capabilities_from_attribute(self):
        """Capabilities set on instance are used for filtering."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.capabilities = RedisPyjwtCapabilities()

            @route("api", env_requires="redis")
            def cached(self):
                return "cached"

            @route("api", env_requires="postgres")
            def db_only(self):
                return "db"

        svc = Service()

        # Instance has redis - cached accessible without passing capabilities
        entries = svc.api.nodes().get("entries", {})
        assert "cached" in entries
        assert "db_only" not in entries  # needs postgres, instance doesn't have it

    def test_instance_capabilities_from_dynamic_class(self):
        """Capabilities computed via CapabilitiesSet are used for filtering."""

        class DynamicPaymentCapabilities(CapabilitiesSet):
            """Dynamic payment capabilities based on runtime state."""

            def __init__(self, svc):
                self._svc = svc

            @capability
            def stripe(self) -> bool:
                return self._svc._has_stripe

            @capability
            def paypal(self) -> bool:
                return self._svc._has_paypal

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self._has_stripe = True
                self._has_paypal = False
                self.capabilities = DynamicPaymentCapabilities(self)

            @route("api", env_requires="stripe")
            def stripe_payment(self):
                return "stripe"

            @route("api", env_requires="paypal")
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
                self.api = Router(self, name="api").plug("env")
                self.capabilities = RedisCapabilities()

            @route("api", env_requires="redis&pyjwt")
            def jwt_cached(self):
                return "jwt_cached"

        svc = Service()

        # Instance has redis, but entry needs both redis AND pyjwt
        entries = svc.api.nodes().get("entries", {})
        assert "jwt_cached" not in entries

        # Pass pyjwt via request - now has both
        entries = svc.api.nodes(env_capabilities="pyjwt").get("entries", {})
        assert "jwt_cached" in entries


class TestEnvPluginHierarchyAccumulation:
    """Test capability accumulation across router hierarchy."""

    def test_child_inherits_parent_capabilities(self):
        """Child router accumulates capabilities from parent instance."""

        class ChildService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = PyjwtCapabilities()

            @route("api", env_requires="redis&pyjwt")
            def jwt_cached(self):
                return "jwt_cached"

        class ParentService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.capabilities = RedisCapabilities()
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
                self.capabilities = Level3Capabilities()

            @route("api", env_requires="level1&level2&level3")
            def deep_action(self):
                return "deep"

        class Level2(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = Level2Capabilities()
                self.level3 = Level3()
                self.api.attach_instance(self.level3, name="level3")

        class Level1(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.capabilities = Level1Capabilities()
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
                self.capabilities = ChildCapCapabilities()

            @route("api", env_requires="parent_cap&child_cap&request_cap")
            def action(self):
                return "action"

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.capabilities = ParentCapCapabilities()
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        root = Parent()

        # Without request_cap - not accessible
        node = root.api.node("child/action")
        assert not node.is_callable

        # With request_cap - accessible
        node = root.api.node("child/action", env_capabilities="request_cap")
        assert node
        assert node.is_callable


class TestEnvPluginNodeBehavior:
    """Test node() behavior with EnvPlugin."""

    def test_node_returns_not_available_when_filtered(self):
        """node() returns RouterNode with error='not_available' when capability missing."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="required_cap")
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
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="required_cap")
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
                self.api = Router(self, name="api").plug("env")
                self.capabilities = RequiredCapCapabilities()

            @route("api", env_requires="required_cap")
            def protected(self):
                return "protected"

        svc = Service()
        node = svc.api.node("protected")
        assert node() == "protected"


class TestEnvPluginRuleValidation:
    """Test rule validation."""

    def test_comma_in_env_requires_raises_error(self):
        """Comma in env_requires raises ValueError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

        svc = Service()

        with pytest.raises(ValueError, match="Comma not allowed"):
            svc.routing.configure("api:env/_all_", requires="stripe,paypal")

    def test_pipe_in_env_requires_works(self):
        """Pipe (|) in env_requires works for OR."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="stripe|paypal")
            def payment(self):
                return "payment"

        svc = Service()
        svc.capabilities = StripeCapabilities()
        entries = svc.api.nodes().get("entries", {})
        assert "payment" in entries


class TestEnvPluginSubRouterFiltering:
    """Test sub-router filtering based on entry accessibility."""

    def test_subrouter_visible_when_has_accessible_entries(self):
        """Sub-router is visible when at least one entry is accessible."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")
                self.capabilities = Cap1Capabilities()

            @route("api", env_requires="cap1")
            def action1(self):
                return "action1"

            @route("api", env_requires="cap2")
            def action2(self):
                return "action2"

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        parent = Parent()

        # Child router has cap1, so action1 is accessible
        # When checking "child" sub-router, should return True (at least one accessible)
        routers = parent.api.nodes().get("routers", {})
        assert "child" in routers

    def test_subrouter_hidden_when_all_entries_blocked(self):
        """Sub-router is hidden when all entries are blocked."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api", env_requires="missing_cap")
            def action1(self):
                return "action1"

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        parent = Parent()

        # Child router has no capabilities, entry requires missing_cap
        # Router should be filtered out
        routers = parent.api.nodes().get("routers", {})
        assert "child" not in routers


class TestCapabilitiesSetter:
    """Test capabilities property setter."""

    def test_capabilities_setter_with_capabilities_set(self):
        """Setting capabilities with CapabilitiesSet works."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()
        svc.capabilities = RedisCapabilities()
        assert "redis" in svc.capabilities

    def test_capabilities_setter_invalid_type_raises(self):
        """Setting capabilities to invalid type raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be a CapabilitiesSet instance"):
            svc.capabilities = {"redis"}  # type: ignore[assignment]

    def test_capabilities_setter_rejects_set(self):
        """Setting capabilities to set raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be a CapabilitiesSet instance"):
            svc.capabilities = {"redis", "pyjwt"}  # type: ignore[assignment]

    def test_capabilities_setter_rejects_string(self):
        """Setting capabilities to string raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be a CapabilitiesSet instance"):
            svc.capabilities = "redis,pyjwt"  # type: ignore[assignment]

    def test_capabilities_setter_rejects_list(self):
        """Setting capabilities to list raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be a CapabilitiesSet instance"):
            svc.capabilities = ["redis", "pyjwt"]  # type: ignore[assignment]

    def test_capabilities_setter_rejects_none(self):
        """Setting capabilities to None raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be a CapabilitiesSet instance"):
            svc.capabilities = None  # type: ignore[assignment]

    def test_capabilities_setter_rejects_int(self):
        """Setting capabilities to int raises TypeError."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        svc = Service()

        with pytest.raises(TypeError, match="must be a CapabilitiesSet instance"):
            svc.capabilities = 123  # type: ignore[assignment]


class TestNodesForbiddenParameter:
    """Test nodes(forbidden=True) includes blocked entries."""

    def test_forbidden_false_excludes_blocked_entries(self):
        """Default behavior: blocked entries are excluded."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api")
            def public(self):
                return "public"

            @route("api", env_requires="redis")
            def needs_redis(self):
                return "needs_redis"

        svc = Service()
        entries = svc.api.nodes().get("entries", {})
        assert "public" in entries
        assert "needs_redis" not in entries

    def test_forbidden_true_includes_blocked_entries(self):
        """With forbidden=True, blocked entries are included with reason."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api")
            def public(self):
                return "public"

            @route("api", env_requires="redis")
            def needs_redis(self):
                return "needs_redis"

        svc = Service()
        entries = svc.api.nodes(forbidden=True).get("entries", {})

        # Public entry has no forbidden field
        assert "public" in entries
        assert "forbidden" not in entries["public"]

        # Blocked entry has forbidden field with reason
        assert "needs_redis" in entries
        assert entries["needs_redis"]["forbidden"] == "not_available"

    def test_forbidden_propagates_to_child_routers(self):
        """forbidden=True propagates to child routers."""

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api", env_requires="child_cap")
            def child_action(self):
                return "child_action"

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")
                self.child = Child()
                self.api.attach_instance(self.child, name="child")

        parent = Parent()

        # Without forbidden, child router is filtered out (no accessible entries)
        routers = parent.api.nodes().get("routers", {})
        assert "child" not in routers

        # With forbidden=True, child router is visible with blocked entry
        result = parent.api.nodes(forbidden=True)
        routers = result.get("routers", {})
        assert "child" in routers

        child_entries = routers["child"].get("entries", {})
        assert "child_action" in child_entries
        assert child_entries["child_action"]["forbidden"] == "not_available"

    def test_forbidden_with_auth_plugin(self):
        """forbidden=True works with auth plugin too."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api")
            def public(self):
                return "public"

            @route("api", auth_rule="admin")
            def admin_only(self):
                return "admin_only"

        svc = Service()

        # Without auth_tags, admin_only is blocked (not_authenticated = no tags provided)
        entries = svc.api.nodes(forbidden=True).get("entries", {})
        assert "public" in entries
        assert "forbidden" not in entries["public"]
        assert "admin_only" in entries
        assert entries["admin_only"]["forbidden"] == "not_authenticated"

    def test_forbidden_entry_still_has_metadata(self):
        """Forbidden entries still have all metadata."""

        class Service(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("env")

            @route("api", env_requires="redis")
            def needs_redis(self):
                """This action requires redis."""
                return "needs_redis"

        svc = Service()
        entries = svc.api.nodes(forbidden=True).get("entries", {})

        entry = entries["needs_redis"]
        assert entry["forbidden"] == "not_available"
        assert entry["name"] == "needs_redis"
        assert entry["doc"] == "This action requires redis."
        assert "callable" in entry  # Still has callable for introspection


class TestCapabilitiesSetClass:
    """Test CapabilitiesSet class behavior."""

    def test_capabilities_set_iteration(self):
        """CapabilitiesSet iterates over active capabilities."""

        class DynamicCaps(CapabilitiesSet):
            def __init__(self):
                self._redis_active = True
                self._pyjwt_active = False

            @capability
            def redis(self) -> bool:
                return self._redis_active

            @capability
            def pyjwt(self) -> bool:
                return self._pyjwt_active

        caps = DynamicCaps()
        assert set(caps) == {"redis"}

        caps._pyjwt_active = True
        assert set(caps) == {"redis", "pyjwt"}

    def test_capabilities_set_contains(self):
        """CapabilitiesSet supports 'in' operator."""

        class MyCaps(CapabilitiesSet):
            @capability
            def redis(self) -> bool:
                return True

            @capability
            def postgres(self) -> bool:
                return False

        caps = MyCaps()
        assert "redis" in caps
        assert "postgres" not in caps
        assert "unknown" not in caps

    def test_capabilities_set_len(self):
        """CapabilitiesSet supports len()."""

        class MyCaps(CapabilitiesSet):
            @capability
            def redis(self) -> bool:
                return True

            @capability
            def pyjwt(self) -> bool:
                return True

            @capability
            def postgres(self) -> bool:
                return False

        caps = MyCaps()
        assert len(caps) == 2  # redis and pyjwt are active

    def test_capabilities_set_dynamic_evaluation(self):
        """Capabilities are evaluated dynamically on each access."""

        class TimeDependentCaps(CapabilitiesSet):
            def __init__(self):
                self.counter = 0

            @capability
            def dynamic(self) -> bool:
                self.counter += 1
                return self.counter % 2 == 1  # True on odd calls

        caps = TimeDependentCaps()

        # First check - counter=1, True
        assert "dynamic" in caps

        # Second check - counter=2, False
        assert "dynamic" not in caps

        # Third check - counter=3, True
        assert "dynamic" in caps
