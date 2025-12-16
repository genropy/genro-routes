# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for FilterPlugin."""

from __future__ import annotations

from genro_routes import RoutedClass, Router


class Owner(RoutedClass):
    pass


def _make_router():
    return Router(Owner(), name="api")


class TestFilterPluginIntegration:
    """Test FilterPlugin with Router integration."""

    def test_nodes_filters_by_single_tag(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router._add_entry(lambda: "public", name="public_action", filter_tags="public")

        entries = router.nodes(tags="admin").get("entries", {})
        assert "admin_action" in entries
        assert "public_action" not in entries

    def test_nodes_filters_by_or(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router._add_entry(lambda: "public", name="public_action", filter_tags="public")
        router._add_entry(lambda: "internal", name="internal_action", filter_tags="internal")

        entries = router.nodes(tags="admin,public").get("entries", {})
        assert "admin_action" in entries
        assert "public_action" in entries
        assert "internal_action" not in entries

    def test_nodes_filters_by_and(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "both", name="both_action", filter_tags="admin,internal")
        router._add_entry(lambda: "admin", name="admin_only", filter_tags="admin")

        entries = router.nodes(tags="admin&internal").get("entries", {})
        assert "both_action" in entries
        assert "admin_only" not in entries

    def test_nodes_filters_by_not(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router._add_entry(lambda: "public", name="public_action", filter_tags="public")

        entries = router.nodes(tags="!admin").get("entries", {})
        assert "admin_action" not in entries
        assert "public_action" in entries

    def test_nodes_without_tags_filter_returns_all(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router._add_entry(lambda: "public", name="public_action", filter_tags="public")

        entries = router.nodes().get("entries", {})
        assert "admin_action" in entries
        assert "public_action" in entries

    def test_entry_without_tags_matches_not_expressions(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "tagged", name="tagged_action", filter_tags="admin")
        router._add_entry(lambda: "untagged", name="untagged_action")

        entries = router.nodes(tags="!admin").get("entries", {})
        assert "tagged_action" not in entries
        assert "untagged_action" in entries

    def test_complex_expression(self):
        router = _make_router().plug("filter")
        router._add_entry(lambda: "a", name="a", filter_tags="admin")
        router._add_entry(lambda: "b", name="b", filter_tags="public")
        router._add_entry(lambda: "c", name="c", filter_tags="admin,internal")
        router._add_entry(lambda: "d", name="d", filter_tags="public,internal")

        # (admin OR public) AND NOT internal
        entries = router.nodes(tags="(admin|public)&!internal").get("entries", {})
        assert "a" in entries  # admin, not internal
        assert "b" in entries  # public, not internal
        assert "c" not in entries  # admin but also internal
        assert "d" not in entries  # public but also internal

    def test_filter_with_child_routers(self):
        """Test that filtering works with hierarchical routers."""
        from genro_routes import RoutedClass, route

        class Parent(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter")

        class Child(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api", filter_tags="admin")
            def child_admin(self):
                return "child_admin"

            @route("api", filter_tags="public")
            def child_public(self):
                return "child_public"

        parent = Parent()
        parent.api._add_entry(lambda: "parent_admin", name="parent_admin", filter_tags="admin")

        child = Child()
        # Attach child - plugin is inherited from parent
        parent.api.attach_instance(child, name="child")

        # Filter should apply to both parent and child
        result = parent.api.nodes(tags="admin")
        assert "parent_admin" in result.get("entries", {})
        # Child router should be present if it has matching entries
        assert "child" in result.get("routers", {})
        # Verify child has only admin entry
        child_entries = result["routers"]["child"].get("entries", {})
        assert "child_admin" in child_entries
        assert "child_public" not in child_entries

    def test_filter_removes_empty_child_routers(self):
        """Child routers with no matching entries should be pruned."""
        from genro_routes import RoutedClass, route

        class Parent(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter")

        class Child(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api")

            @route("api", filter_tags="public")
            def only_public(self):
                return "public"

        parent = Parent()
        parent.api._add_entry(lambda: "admin", name="admin_action", filter_tags="admin")

        child = Child()
        parent.api.attach_instance(child, name="child")

        # Filter for admin - child has no admin entries
        result = parent.api.nodes(tags="admin")
        assert "admin_action" in result.get("entries", {})
        # Child should be pruned (empty after filter)
        assert "child" not in result.get("routers", {})

    def test_filter_tag_inheritance_union(self):
        """Test that parent tags are merged with child tags via union."""
        from genro_routes import RoutedClass, route

        class Parent(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter", tags="corporate")

        class Child(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter", tags="internal")

            @route("api", filter_tags="admin")
            def admin_only(self):
                return "admin"

        parent = Parent()
        child = Child()
        parent.api.attach_instance(child, name="child")

        # Child should now have merged tags: "corporate,internal"
        child_plugin = child.api._plugins_by_name["filter"]
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "internal" in child_tags

        # Entry has "admin" tag, but inherits "corporate,internal" from router _all_
        # Filter by admin should see child entry
        result = parent.api.nodes(tags="admin")
        assert "child" in result.get("routers", {})

    def test_filter_tag_runtime_propagation(self):
        """Test that parent tag changes propagate to children at runtime."""
        from genro_routes import RoutedClass, route

        class Parent(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter", tags="corporate")

        class Child(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter", tags="internal")

            @route("api", filter_tags="admin")
            def admin_only(self):
                return "admin"

        parent = Parent()
        child = Child()
        parent.api.attach_instance(child, name="child")

        # Initial state: child has "corporate,internal"
        child_plugin = child.api._plugins_by_name["filter"]
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "internal" in child_tags

        # Parent changes tags: "corporate" → "corporate,hr"
        parent_plugin = parent.api._plugins_by_name["filter"]
        parent_plugin.configure(tags="corporate,hr")

        # Child should now have "corporate,hr,internal" (own + new parent)
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "hr" in child_tags
        assert "internal" in child_tags

    def test_filter_tag_runtime_propagation_removes_old_tags(self):
        """Test that old parent tags are removed when parent tags change."""
        from genro_routes import RoutedClass, route

        class Parent(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter", tags="corporate")

        class Child(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter", tags="internal")

            @route("api", filter_tags="admin")
            def admin_only(self):
                return "admin"

        parent = Parent()
        child = Child()
        parent.api.attach_instance(child, name="child")

        # Initial state: child has "corporate,internal"
        child_plugin = child.api._plugins_by_name["filter"]
        child_tags = child_plugin.configuration().get("tags", "")
        assert "corporate" in child_tags
        assert "internal" in child_tags

        # Parent changes tags completely: "corporate" → "hr"
        parent_plugin = parent.api._plugins_by_name["filter"]
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
        from genro_routes import RoutedClass

        class Parent(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api")

        class Child(RoutedClass):
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


class TestGetWithDefault:
    """Test get() with default_handler parameter."""

    def test_get_missing_child_with_default_handler(self):
        """Test get() returns default_handler when child path not found."""
        router = _make_router()
        router._add_entry(lambda: "a", name="entry_a")

        def fallback():
            return "fallback"

        # Path with missing child should return default_handler
        result = router.get("nonexistent/something", default_handler=fallback)
        assert result is fallback

    def test_get_missing_child_returns_none(self):
        """Test get() returns None when child not found and no default."""
        router = _make_router()

        result = router.get("nonexistent/something")
        assert result is None


class TestFilterPluginAllowNode:
    """Test allow_node with RouterInterface directly."""

    def test_allow_node_with_router_interface(self):
        """Test allow_node checks children when passed a RouterInterface."""
        from genro_routes import RoutedClass, route

        class Child(RoutedClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("filter")

            @route("api", filter_tags="admin")
            def admin_action(self):
                return "admin"

            @route("api", filter_tags="public")
            def public_action(self):
                return "public"

        child = Child()
        plugin = child.api._plugins_by_name["filter"]

        # Pass router directly to allow_node - should check children
        # Router has entries with "admin" and "public" tags
        assert plugin.allow_node(child.api, tags="admin") is True
        assert plugin.allow_node(child.api, tags="public") is True
        assert plugin.allow_node(child.api, tags="nonexistent") is False

    def test_allow_node_empty_router(self):
        """Test allow_node with router that has no matching entries."""

        class Child(RoutedClass):
            pass

        router = Router(Child(), name="api").plug("filter")
        router._add_entry(lambda: "x", name="only_internal", filter_tags="internal")

        plugin = router._plugins_by_name["filter"]

        # Filter for "admin" - no entries match
        assert plugin.allow_node(router, tags="admin") is False
        # Filter for "internal" - one entry matches
        assert plugin.allow_node(router, tags="internal") is True
