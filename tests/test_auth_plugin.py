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
    - Entry auth_tags = RULE (who can access this entry)
    - User tags passed to nodes()/node() = USER CREDENTIALS

    Example: entry with auth_tags="admin" requires user to have "admin" tag.
    """

    def test_user_with_matching_tag_can_access(self):
        """User with 'admin' tag can access entry requiring 'admin'."""
        router = _make_router().plug("auth")
        router._add_entry(lambda: "admin", name="admin_action", auth_tags="admin")
        router._add_entry(lambda: "public", name="public_action", auth_tags="public")

        # User has 'admin' tag - can access admin_action
        entries = router.nodes(auth_tags="admin").get("entries", {})
        assert "admin_action" in entries
        assert "public_action" not in entries  # requires 'public', user has 'admin'

    def test_user_with_multiple_tags_can_access_matching_entries(self):
        """User with multiple tags can access entries matching any of their tags."""
        router = _make_router().plug("auth")
        router._add_entry(lambda: "admin", name="admin_action", auth_tags="admin")
        router._add_entry(lambda: "public", name="public_action", auth_tags="public")
        router._add_entry(lambda: "internal", name="internal_action", auth_tags="internal")

        # User has 'admin,public' tags - can access entries requiring admin OR public
        entries = router.nodes(auth_tags="admin,public").get("entries", {})
        assert "admin_action" in entries  # requires admin, user has admin
        assert "public_action" in entries  # requires public, user has public
        assert "internal_action" not in entries  # requires internal, user doesn't have

    def test_entry_with_or_rule_accepts_user_with_any_tag(self):
        """Entry with OR rule (admin,internal) accepts user with any matching tag."""
        router = _make_router().plug("auth")
        # Entry accepts admin OR internal users
        router._add_entry(lambda: "flexible", name="flexible_action", auth_tags="admin,internal")
        # Entry accepts only admin users
        router._add_entry(lambda: "strict", name="strict_admin", auth_tags="admin")

        # User has only 'internal' tag
        entries = router.nodes(auth_tags="internal").get("entries", {})
        assert "flexible_action" in entries  # accepts internal
        assert "strict_admin" not in entries  # requires admin, user has only internal

    def test_entry_with_and_rule_requires_all_tags(self):
        """Entry with AND rule (admin&internal) requires user to have all tags."""
        router = _make_router().plug("auth")
        # Entry requires BOTH admin AND internal
        router._add_entry(lambda: "strict", name="strict_action", auth_tags="admin&internal")
        # Entry requires only admin
        router._add_entry(lambda: "admin", name="admin_only", auth_tags="admin")

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
        router._add_entry(lambda: "active", name="active_only", auth_tags="!dimissionario")
        # Entry for everyone (no rule)
        router._add_entry(lambda: "all", name="for_all")

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
        router._add_entry(lambda: "admin", name="admin_action", auth_tags="admin")
        router._add_entry(lambda: "public", name="public_action", auth_tags="public")
        router._add_entry(lambda: "open", name="open_action")  # No rule

        # No tags = only entries without rules are visible
        entries = router.nodes().get("entries", {})
        assert "admin_action" not in entries  # Has rule, no tags → 401 → filtered
        assert "public_action" not in entries  # Has rule, no tags → 401 → filtered
        assert "open_action" in entries  # No rule → always visible

    def test_entry_without_rule_always_accessible(self):
        """Entry without auth_tags is always accessible to any user."""
        router = _make_router().plug("auth")
        router._add_entry(lambda: "tagged", name="tagged_action", auth_tags="admin")
        router._add_entry(lambda: "untagged", name="untagged_action")  # no rule

        # User with 'public' tag can't access admin-only, but can access untagged
        entries = router.nodes(auth_tags="public").get("entries", {})
        assert "tagged_action" not in entries  # requires admin
        assert "untagged_action" in entries  # no rule = accessible

    def test_complex_rule_evaluation(self):
        """Test complex rules with AND, OR, NOT combinations."""
        router = _make_router().plug("auth")
        # Complex rule: (admin OR manager) AND NOT guest
        router._add_entry(lambda: "a", name="complex_action", auth_tags="(admin|manager)&!guest")

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

            @route("api", auth_tags="admin")
            def child_admin(self):
                return "child_admin"

            @route("api", auth_tags="public")
            def child_public(self):
                return "child_public"

        parent = Parent()
        parent.api._add_entry(lambda: "parent_admin", name="parent_admin", auth_tags="admin")

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

            @route("api", auth_tags="public")
            def only_public(self):
                return "public"

        parent = Parent()
        parent.api._add_entry(lambda: "admin", name="admin_action", auth_tags="admin")

        child = Child()
        parent.api.attach_instance(child, name="child")

        # Filter for admin - child has no admin entries
        result = parent.api.nodes(auth_tags="admin")
        assert "admin_action" in result.get("entries", {})
        # Child should be pruned (empty after filter)
        assert "child" not in result.get("routers", {})

    def test_auth_tag_inheritance_union(self):
        """Test that parent tags are merged with child tags via union."""
        from genro_routes import RoutingClass, route

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth", tags="corporate")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth", tags="internal")

            @route("api", auth_tags="admin")
            def admin_only(self):
                return "admin"

        parent = Parent()
        child = Child()
        parent.api.attach_instance(child, name="child")

        # Child should now have merged tags: "corporate,internal"
        child_plugin = child.api._plugins_by_name["auth"]
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "internal" in child_tags

        # Entry has "admin" tag, but inherits "corporate,internal" from router _all_
        # Filter by admin should see child entry
        result = parent.api.nodes(auth_tags="admin")
        assert "child" in result.get("routers", {})

    def test_auth_tag_runtime_propagation(self):
        """Test that parent tag changes propagate to children at runtime."""
        from genro_routes import RoutingClass, route

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth", tags="corporate")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth", tags="internal")

            @route("api", auth_tags="admin")
            def admin_only(self):
                return "admin"

        parent = Parent()
        child = Child()
        parent.api.attach_instance(child, name="child")

        # Initial state: child has "corporate,internal"
        child_plugin = child.api._plugins_by_name["auth"]
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "internal" in child_tags

        # Parent changes tags: "corporate" → "corporate,hr"
        parent_plugin = parent.api._plugins_by_name["auth"]
        parent_plugin.configure(tags="corporate,hr")

        # Child should now have "corporate,hr,internal" (own + new parent)
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "hr" in child_tags
        assert "internal" in child_tags

    def test_auth_tag_runtime_propagation_removes_old_tags(self):
        """Test that old parent tags are removed when parent tags change."""
        from genro_routes import RoutingClass, route

        class Parent(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth", tags="corporate")

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth", tags="internal")

            @route("api", auth_tags="admin")
            def admin_only(self):
                return "admin"

        parent = Parent()
        child = Child()
        parent.api.attach_instance(child, name="child")

        # Initial state: child has "corporate,internal"
        child_plugin = child.api._plugins_by_name["auth"]
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "internal" in child_tags

        # Parent changes tags completely: "corporate" → "hr"
        parent_plugin = parent.api._plugins_by_name["auth"]
        parent_plugin.configure(tags="hr")

        # Child should now have "hr,internal" (own + new parent, corporate removed)
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" not in child_tags  # old parent tag removed
        assert "hr" in child_tags  # new parent tag added
        assert "internal" in child_tags  # child's own tag preserved


class TestDictLikeInterface:
    """Test BaseRouter dict-like interface for coverage."""

    def test_iter_keys_values_items(self):
        """Test __iter__, keys(), values(), items()."""
        router = _make_router()
        router._add_entry(lambda: "a", name="entry_a")
        router._add_entry(lambda: "b", name="entry_b")

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
        router._add_entry(lambda: "a", name="entry_a")

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
        parent.api._add_entry(lambda: "p", name="parent_entry")

        child = Child()
        parent.api.attach_instance(child, name="child")

        # Should have both entry and child
        assert len(parent.api) == 2
        assert "parent_entry" in parent.api
        assert "child" in parent.api

        names = list(parent.api.keys())
        assert "parent_entry" in names
        assert "child" in names


class TestNodeWithFilters:
    """Test node() with filter parameters using new API."""

    def test_node_raises_not_authorized_when_filtered(self):
        """node() returns UNAUTHORIZED callable when entry exists but is filtered."""
        from genro_routes import NotAuthorized, RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()
        node = svc.api.node("admin_action", auth_tags="public")

        # Node exists but is unauthorized
        assert node
        assert not node.is_authorized

        # Calling raises NotAuthorized
        with pytest.raises(NotAuthorized) as exc_info:
            node()

        assert exc_info.value.selector == "admin_action"
        assert exc_info.value.router_name == "api"

    def test_node_returns_callable_when_tag_matches(self):
        """node() returns callable RouterNode when tag matches."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()
        node = svc.api.node("admin_action", auth_tags="admin")
        assert node
        assert node.is_authorized
        assert node() == "admin"

    def test_node_returns_empty_when_not_found(self):
        """node() returns empty RouterNode when entry doesn't exist."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()
        node = svc.api.node("nonexistent")
        assert not node  # Empty RouterNode is falsy
        assert node == {}  # Empty RouterNode equals empty dict

    def test_node_without_filter_on_open_entry_returns_callable(self):
        """node() without filter tags on entry without rule returns callable normally."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api")  # No auth_tags = open entry
            def open_action(self):
                return "open"

        svc = Svc()
        node = svc.api.node("open_action")
        assert node
        assert node.is_authorized
        assert node() == "open"

    def test_node_call_raises_not_found_when_empty(self):
        """Calling empty RouterNode raises NotFound."""
        from genro_routes import NotFound, RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()
        node = svc.api.node("nonexistent")

        with pytest.raises(NotFound) as exc_info:
            node()

        assert exc_info.value.selector == ""
        assert exc_info.value.router_name == "api"

    def test_node_call_executes_when_tag_matches(self):
        """Calling RouterNode executes handler when tag matches."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin result"

        svc = Svc()
        node = svc.api.node("admin_action", auth_tags="admin")
        assert node() == "admin result"

    def test_node_call_passes_args_to_handler(self):
        """Calling RouterNode passes args and kwargs to handler."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def action(self, x, y=10):
                return f"x={x}, y={y}"

        svc = Svc()
        node = svc.api.node("action", auth_tags="admin")
        result = node(5, y=20)
        assert result == "x=5, y=20"

    def test_node_best_match_with_extra_args(self):
        """node() with best-match puts unconsumed segments in extra_args for *args handlers."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="public")
            def index(self, *args):
                return f"caught: {args}"

        svc = Svc()
        # Best-match resolution finds "index" and puts rest in extra_args
        node = svc.api.node("unknown/path", auth_tags="public")
        assert node
        assert node.name == "index"
        # Handler accepts *args so path segments go to extra_args
        assert node.extra_args == ["unknown", "path"]
        assert node.partial_kwargs == {}
        # When called, extra_args are prepended automatically
        result = node()
        assert result == "caught: ('unknown', 'path')"


class TestAuth401vs403:
    """Test 401 (NotAuthenticated) vs 403 (NotAuthorized) distinction."""

    def test_entry_without_tags_always_accessible(self):
        """Entry without auth_tags is always accessible, no tags needed."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api")  # No auth_tags
            def public_action(self):
                return "public"

        svc = Svc()

        # No tags passed - still works
        node = svc.api.node("public_action")
        assert node.is_authorized
        assert node() == "public"

        # With some tags - still works
        node = svc.api.node("public_action", auth_tags="random")
        assert node.is_authorized
        assert node() == "public"

    def test_entry_with_tags_no_user_tags_raises_401(self):
        """Entry requires tags but user passes none → 401 NotAuthenticated."""
        from genro_routes import NotAuthenticated, RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()

        # Entry requires tags, no tags passed → 401
        node = svc.api.node("admin_action")
        assert not node.is_authorized

        with pytest.raises(NotAuthenticated) as exc_info:
            node()

        assert exc_info.value.selector == "admin_action"
        assert exc_info.value.router_name == "api"

    def test_entry_with_tags_user_tags_match_ok(self):
        """Entry requires tags, user tags match → access granted."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()

        # User has matching tags → OK
        node = svc.api.node("admin_action", auth_tags="admin")
        assert node.is_authorized
        assert node() == "admin"

    def test_entry_with_tags_user_tags_dont_match_raises_403(self):
        """Entry requires tags, user tags don't match → 403 NotAuthorized."""
        from genro_routes import NotAuthorized, RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

        svc = Svc()

        # User passes tags that don't match → 403
        node = svc.api.node("admin_action", auth_tags="public")
        assert not node.is_authorized

        with pytest.raises(NotAuthorized) as exc_info:
            node()

        assert exc_info.value.selector == "admin_action"
        assert exc_info.value.router_name == "api"

    def test_complex_rule_no_tags_raises_401(self):
        """Complex rule like '!dimissionario', no tags passed → 401."""
        from genro_routes import NotAuthenticated, RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="!dimissionario")
            def non_dimissionario_action(self):
                return "ok"

        svc = Svc()

        # Entry has rule, no tags passed → 401
        node = svc.api.node("non_dimissionario_action")
        assert not node.is_authorized

        with pytest.raises(NotAuthenticated):
            node()

    def test_complex_rule_tags_match_ok(self):
        """Complex rule like '!dimissionario', user tags satisfy rule → OK."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="!dimissionario")
            def non_dimissionario_action(self):
                return "ok"

        svc = Svc()

        # User has "contabilita" (not dimissionario) → matches !dimissionario
        node = svc.api.node("non_dimissionario_action", auth_tags="contabilita")
        assert node.is_authorized
        assert node() == "ok"

    def test_complex_rule_tags_dont_match_raises_403(self):
        """Complex rule like '!dimissionario', user has dimissionario → 403."""
        from genro_routes import NotAuthorized, RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="!dimissionario")
            def non_dimissionario_action(self):
                return "ok"

        svc = Svc()

        # User has "dimissionario" → doesn't match !dimissionario
        node = svc.api.node("non_dimissionario_action", auth_tags="dimissionario")
        assert not node.is_authorized

        with pytest.raises(NotAuthorized):
            node()

    def test_nodes_filters_out_both_401_and_403(self):
        """nodes() silently filters out entries that would be 401 or 403."""
        from genro_routes import RoutingClass, route

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

            @route("api", auth_tags="public")
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

            @route("api", auth_tags="admin")
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


class TestAuthPluginAllowNode:
    """Test allow_node with RouterInterface directly.

    Note: allow_node now returns bool | str:
    - True: access allowed
    - "not_authenticated": entry has rule but no tags provided
    - "not_authorized": tags provided but don't match rule
    """

    def test_allow_node_with_router_interface(self):
        """Test allow_node checks children when passed a RouterInterface."""
        from genro_routes import RoutingClass, route

        class Child(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("auth")

            @route("api", auth_tags="admin")
            def admin_action(self):
                return "admin"

            @route("api", auth_tags="public")
            def public_action(self):
                return "public"

        child = Child()
        plugin = child.api._plugins_by_name["auth"]

        # Pass router directly to allow_node - should check children
        # Router has entries with "admin" and "public" tags
        # Note: allow_node receives kwargs without prefix (already extracted by _allow_entry)
        assert plugin.allow_node(child.api, tags="admin") is True
        assert plugin.allow_node(child.api, tags="public") is True
        # No entry matches "nonexistent" tags → returns first child error (not_authorized)
        assert plugin.allow_node(child.api, tags="nonexistent") == "not_authorized"

    def test_allow_node_empty_router(self):
        """Test allow_node with router that has no matching entries."""

        class Child(RoutingClass):
            pass

        router = Router(Child(), name="api").plug("auth")
        router._add_entry(lambda: "x", name="only_internal", auth_tags="internal")

        plugin = router._plugins_by_name["auth"]

        # Filter for "admin" - entry requires "internal", user has "admin" → not_authorized
        assert plugin.allow_node(router, tags="admin") == "not_authorized"
        # Filter for "internal" - one entry matches
        assert plugin.allow_node(router, tags="internal") is True
