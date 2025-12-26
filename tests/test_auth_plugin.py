# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for AuthPlugin."""

from __future__ import annotations

import pytest

from genro_routes import RoutingClass, Router


class Owner(RoutingClass):
    pass


def _make_router():
    return Router(Owner(), name="api")


class TestAuthPluginIntegration:
    """Test AuthPlugin with Router integration.

    Semantics:
    - Entry auth_rule = RULE (who can access this entry)
    - User auth_tags passed to nodes()/node() = USER CREDENTIALS

    Example: entry with auth_rule="admin" requires user to have "admin" tag.
    """

    def test_user_with_matching_tag_can_access(self):
        """User with 'admin' tag can access entry requiring 'admin'."""
        router = _make_router().plug("auth")
        router.add_entry(lambda: "admin", name="admin_action", auth_rule="admin")
        router.add_entry(lambda: "public", name="public_action", auth_rule="public")

        # User has 'admin' tag - can access admin_action
        entries = router.nodes(auth_tags="admin").get("entries", {})
        assert "admin_action" in entries
        assert "public_action" not in entries  # requires 'public', user has 'admin'

    def test_user_with_multiple_tags_can_access_matching_entries(self):
        """User with multiple tags can access entries matching any of their tags."""
        router = _make_router().plug("auth")
        router.add_entry(lambda: "admin", name="admin_action", auth_rule="admin")
        router.add_entry(lambda: "public", name="public_action", auth_rule="public")
        router.add_entry(lambda: "internal", name="internal_action", auth_rule="internal")

        # User has 'admin,public' tags - can access entries requiring admin OR public
        entries = router.nodes(auth_tags="admin,public").get("entries", {})
        assert "admin_action" in entries  # requires admin, user has admin
        assert "public_action" in entries  # requires public, user has public
        assert "internal_action" not in entries  # requires internal, user doesn't have

    def test_entry_with_or_rule_accepts_user_with_any_tag(self):
        """Entry with OR rule (admin|internal) accepts user with any matching tag."""
        router = _make_router().plug("auth")
        # Entry accepts admin OR internal users
        router.add_entry(lambda: "flexible", name="flexible_action", auth_rule="admin|internal")
        # Entry accepts only admin users
        router.add_entry(lambda: "strict", name="strict_admin", auth_rule="admin")

        # User has only 'internal' tag
        entries = router.nodes(auth_tags="internal").get("entries", {})
        assert "flexible_action" in entries  # accepts internal
        assert "strict_admin" not in entries  # requires admin, user has only internal

    def test_entry_with_and_rule_requires_all_tags(self):
        """Entry with AND rule (admin&internal) requires user to have all tags."""
        router = _make_router().plug("auth")
        # Entry requires BOTH admin AND internal
        router.add_entry(lambda: "strict", name="strict_action", auth_rule="admin&internal")
        # Entry requires only admin
        router.add_entry(lambda: "admin", name="admin_only", auth_rule="admin")

        # User has both tags
        entries = router.nodes(auth_tags="admin,internal").get("entries", {})
        assert "strict_action" in entries  # user has both required tags
        assert "admin_only" in entries  # user has admin

        # User has only admin
        entries = router.nodes(auth_tags="admin").get("entries", {})
        assert "strict_action" not in entries  # user missing internal
        assert "admin_only" in entries

    def test_entry_with_not_rule_excludes_user(self):
        """Entry with NOT rule (!dimissionario) excludes users with that tag."""
        router = _make_router().plug("auth")
        # Entry excludes dimissionario users
        router.add_entry(lambda: "active", name="active_only", auth_rule="!dimissionario")
        # Entry for everyone (no rule)
        router.add_entry(lambda: "all", name="for_all")

        # User has 'dimissionario' tag
        entries = router.nodes(auth_tags="dimissionario").get("entries", {})
        assert "active_only" not in entries  # user is excluded by !dimissionario
        assert "for_all" in entries  # no rule, always accessible

        # User has 'contabilita' tag (not dimissionario)
        entries = router.nodes(auth_tags="contabilita").get("entries", {})
        assert "active_only" in entries  # user is not dimissionario
        assert "for_all" in entries

    def test_nodes_without_auth_tags_filters_protected_entries(self):
        """nodes() without auth_tags filters out entries with rules (401 = not visible)."""
        router = _make_router().plug("auth")
        router.add_entry(lambda: "admin", name="admin_action", auth_rule="admin")
        router.add_entry(lambda: "public", name="public_action", auth_rule="public")
        router.add_entry(lambda: "open", name="open_action")  # No rule

        # No tags = only entries without rules are visible
        entries = router.nodes().get("entries", {})
        assert "admin_action" not in entries  # Has rule, no tags → 401 → filtered
        assert "public_action" not in entries  # Has rule, no tags → 401 → filtered
        assert "open_action" in entries  # No rule → always visible

    def test_entry_without_rule_always_accessible(self):
        """Entry without auth_tags is always accessible to any user."""
        router = _make_router().plug("auth")
        router.add_entry(lambda: "tagged", name="tagged_action", auth_rule="admin")
        router.add_entry(lambda: "untagged", name="untagged_action")  # no rule

        # User with 'public' tag can't access admin-only, but can access untagged
        entries = router.nodes(auth_tags="public").get("entries", {})
        assert "tagged_action" not in entries  # requires admin
        assert "untagged_action" in entries  # no rule = accessible

    def test_complex_rule_evaluation(self):
        """Test complex rules with AND, OR, NOT combinations."""
        router = _make_router().plug("auth")
        # Complex rule: (admin OR manager) AND NOT guest
        router.add_entry(lambda: "a", name="complex_action", auth_rule="(admin|manager)&!guest")

        # Admin without guest - OK
        entries = router.nodes(auth_tags="admin").get("entries", {})
        assert "complex_action" in entries

        # Manager without guest - OK
        entries = router.nodes(auth_tags="manager").get("entries", {})
        assert "complex_action" in entries

        # Admin AND guest - NOT OK (guest is excluded)
        entries = router.nodes(auth_tags="admin,guest").get("entries", {})
        assert "complex_action" not in entries

        # Only guest - NOT OK (no admin/manager, plus guest excluded)
        entries = router.nodes(auth_tags="guest").get("entries", {})
        assert "complex_action" not in entries

    def test_auth_with_child_routers(self):
        """Test that authorization works with hierarchical routers."""
        from genro_routes import RoutingClass, route

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api", auth_rule="admin")
            def child_admin(self):
                return "child_admin"

            @route("api", auth_rule="public")
            def child_public(self):
                return "child_public"

        parent = Parent()
        parent.api.add_entry(lambda: "parent_admin", name="parent_admin", auth_rule="admin")

        child = Child()
        # Attach child - plugin is inherited from parent
        parent.api.attach_instance(child, name="child")

        # Filter should apply to both parent and child
        result = parent.api.nodes(auth_tags="admin")
        assert "parent_admin" in result.get("entries", {})
        # Child router should be present if it has matching entries
        assert "child" in result.get("routers", {})
        # Verify child has only admin entry
        child_entries = result["routers"]["child"].get("entries", {})
        assert "child_admin" in child_entries
        assert "child_public" not in child_entries

    def test_auth_removes_empty_child_routers(self):
        """Child routers with no matching entries should be pruned."""
        from genro_routes import RoutingClass, route

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api", auth_rule="public")
            def only_public(self):
                return "public"

        parent = Parent()
        parent.api.add_entry(lambda: "admin", name="admin_action", auth_rule="admin")

        child = Child()
        parent.api.attach_instance(child, name="child")

        # Filter for admin - child has no admin entries
        result = parent.api.nodes(auth_tags="admin")
        assert "admin_action" in result.get("entries", {})
        # Child should be pruned (empty after filter)
        assert "child" not in result.get("routers", {})

class TestDictLikeInterface:
    """Test BaseRouter dict-like interface for coverage."""

    def test_iter_keys_values_items(self):
        """Test __iter__, keys(), values(), items()."""
        router = _make_router()
        router.add_entry(lambda: "a", name="entry_a")
        router.add_entry(lambda: "b", name="entry_b")

        # __iter__
        names = list(router)
        assert "entry_a" in names
        assert "entry_b" in names

        # keys()
        keys = list(router.keys())
        assert "entry_a" in keys
        assert "entry_b" in keys

        # values()
        values = list(router.values())
        assert len(values) == 2

        # items()
        items = list(router.items())
        assert len(items) == 2
        item_names = [name for name, _ in items]
        assert "entry_a" in item_names

    def test_len_and_contains(self):
        """Test __len__ and __contains__."""
        router = _make_router()
        router.add_entry(lambda: "a", name="entry_a")

        assert len(router) == 1
        assert "entry_a" in router
        assert "nonexistent" not in router

    def test_dict_interface_with_children(self):
        """Test dict interface includes children."""
        from genro_routes import RoutingClass

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api")

        parent = Parent()
        parent.api.add_entry(lambda: "p", name="parent_entry")

        child = Child()
        parent.api.attach_instance(child, name="child")

        # Should have both entry and child
        assert len(parent.api) == 2
        assert "parent_entry" in parent.api
        assert "child" in parent.api

        names = list(parent.api.keys())
        assert "parent_entry" in names
        assert "child" in names


class TestAuth401vs403:
    """Test 401 (NotAuthenticated) vs 403 (NotAuthorized) distinction."""

    def test_nodes_filters_out_both_401_and_403(self):
        """nodes() silently filters out entries that would be 401 or 403."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_rule="admin")
            def admin_action(self):
                return "admin"

            @route("api", auth_rule="public")
            def public_action(self):
                return "public"

            @route("api")  # No tags
            def open_action(self):
                return "open"

        svc = Svc()

        # With admin tags - sees admin and open, not public
        entries = svc.api.nodes(auth_tags="admin").get("entries", {})
        assert "admin_action" in entries
        assert "open_action" in entries
        assert "public_action" not in entries

        # With public tags - sees public and open, not admin
        entries = svc.api.nodes(auth_tags="public").get("entries", {})
        assert "public_action" in entries
        assert "open_action" in entries
        assert "admin_action" not in entries

        # Without any tags - only sees entries without rules (401 filtered out)
        entries = svc.api.nodes().get("entries", {})
        assert "admin_action" not in entries  # Has rule, no tags → 401
        assert "public_action" not in entries  # Has rule, no tags → 401
        assert "open_action" in entries  # No rule → always visible

    def test_custom_exception_classes(self):
        """Test that custom exception classes are used for 401 and 403."""
        from genro_routes import RoutingClass, route

        class Custom401(Exception):
            def __init__(self, path, router_name):
                self.path = path
                self.router_name = router_name

        class Custom403(Exception):
            def __init__(self, path, router_name):
                self.path = path
                self.router_name = router_name

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_rule="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()

        # Test 401 with custom exception
        node = svc.api.node("admin_action", errors={
            "not_authenticated": Custom401
        })
        with pytest.raises(Custom401) as exc_info:
            node()
        assert exc_info.value.path == "admin_action"

        # Test 403 with custom exception
        node = svc.api.node("admin_action", auth_tags="public", errors={
            "not_authorized": Custom403
        })
        with pytest.raises(Custom403) as exc_info:
            node()
        assert exc_info.value.path == "admin_action"


class TestAuthRuleValidation:
    """Test that comma is not allowed in auth_rule."""

    def test_comma_in_auth_rule_raises_error(self):
        """Using comma in auth_rule should raise ValueError in configure()."""
        from genro_routes import RoutingClass, route

        class MyService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api")
            def action(self):
                return "ok"

        svc = MyService()
        with pytest.raises(ValueError, match="Comma not allowed"):
            svc.api.auth.configure(rule="admin,manager")

    def test_pipe_in_auth_rule_works(self):
        """Using pipe for OR in auth_rule should work."""
        from genro_routes import RoutingClass, route

        class GoodService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_rule="admin|manager")
            def good_action(self):
                return "good"

        svc = GoodService()

        # User with admin can access
        entries = svc.api.nodes(auth_tags="admin").get("entries", {})
        assert "good_action" in entries

        # User with manager can access
        entries = svc.api.nodes(auth_tags="manager").get("entries", {})
        assert "good_action" in entries

    def test_comma_in_auth_tags_still_works(self):
        """Comma in auth_tags (user credentials) should still work."""
        from genro_routes import RoutingClass, route

        class StrictService(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_rule="admin&internal")
            def strict_action(self):
                return "strict"

        svc = StrictService()

        # User passes multiple tags with comma - should work
        entries = svc.api.nodes(auth_tags="admin,internal").get("entries", {})
        assert "strict_action" in entries
