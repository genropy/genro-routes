# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for FilterPlugin."""

from __future__ import annotations

import pytest

from genro_routes import Router
from genro_routes.plugins.filter import FilterPlugin


class Owner:
    pass


def _make_router():
    return Router(Owner(), name="api")


class TestFilterPluginMatching:
    """Test the _match_tags algorithm."""

    def test_single_tag_match(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        assert plugin._match_tags("admin", {"admin", "internal"}) is True

    def test_single_tag_no_match(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        assert plugin._match_tags("admin", {"public"}) is False

    def test_or_with_comma(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # admin,public means admin OR public
        assert plugin._match_tags("admin,public", {"admin"}) is True
        assert plugin._match_tags("admin,public", {"public"}) is True
        assert plugin._match_tags("admin,public", {"internal"}) is False

    def test_or_with_pipe(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        assert plugin._match_tags("admin|public", {"admin"}) is True
        assert plugin._match_tags("admin|public", {"public"}) is True

    def test_and_with_ampersand(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        assert plugin._match_tags("admin&internal", {"admin", "internal"}) is True
        assert plugin._match_tags("admin&internal", {"admin"}) is False

    def test_not_operator(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        assert plugin._match_tags("!admin", {"public"}) is True
        assert plugin._match_tags("!admin", {"admin"}) is False

    def test_not_with_and(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # public AND NOT internal
        assert plugin._match_tags("public&!internal", {"public"}) is True
        assert plugin._match_tags("public&!internal", {"public", "internal"}) is False

    def test_parentheses_grouping(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # (admin OR public) AND NOT internal
        expr = "(admin|public)&!internal"
        assert plugin._match_tags(expr, {"admin"}) is True
        assert plugin._match_tags(expr, {"public"}) is True
        assert plugin._match_tags(expr, {"admin", "internal"}) is False
        assert plugin._match_tags(expr, {"other"}) is False

    def test_empty_tags_match_not(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # Entry with no tags should match "!admin"
        assert plugin._match_tags("!admin", set()) is True

    def test_invalid_rule_raises(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        with pytest.raises(ValueError, match="Invalid tag rule"):
            plugin._match_tags("admin; drop table", {"admin"})

    def test_nested_parentheses(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # ((admin OR public) AND internal) OR superuser
        expr = "((admin|public)&internal)|superuser"
        assert plugin._match_tags(expr, {"admin", "internal"}) is True
        assert plugin._match_tags(expr, {"public", "internal"}) is True
        assert plugin._match_tags(expr, {"superuser"}) is True
        assert plugin._match_tags(expr, {"admin"}) is False  # missing internal
        assert plugin._match_tags(expr, {"internal"}) is False  # missing admin/public

    def test_multiple_not_operators(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # NOT admin AND NOT internal
        expr = "!admin&!internal"
        assert plugin._match_tags(expr, {"public"}) is True
        assert plugin._match_tags(expr, {"admin"}) is False
        assert plugin._match_tags(expr, {"internal"}) is False
        assert plugin._match_tags(expr, {"admin", "internal"}) is False
        assert plugin._match_tags(expr, set()) is True

    def test_not_with_or(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # NOT admin OR NOT internal (true unless both are present)
        expr = "!admin|!internal"
        assert plugin._match_tags(expr, {"public"}) is True
        assert plugin._match_tags(expr, {"admin"}) is True  # !internal is true
        assert plugin._match_tags(expr, {"internal"}) is True  # !admin is true
        assert plugin._match_tags(expr, {"admin", "internal"}) is False

    def test_complex_three_tags(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # (admin AND internal) OR (public AND external)
        expr = "(admin&internal)|(public&external)"
        assert plugin._match_tags(expr, {"admin", "internal"}) is True
        assert plugin._match_tags(expr, {"public", "external"}) is True
        assert plugin._match_tags(expr, {"admin", "external"}) is False
        assert plugin._match_tags(expr, {"admin"}) is False

    def test_whitespace_in_tags_ignored(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # Tags with spaces should still work
        assert plugin._match_tags("admin", {"admin", "other"}) is True

    def test_single_tag_empty_entry_tags(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        assert plugin._match_tags("admin", set()) is False

    def test_only_not_expression(self):
        plugin = FilterPlugin.__new__(FilterPlugin)
        # Just !admin should work
        assert plugin._match_tags("!admin", {"other", "tags"}) is True
        assert plugin._match_tags("!admin", {"admin", "other"}) is False


class TestFilterPluginIntegration:
    """Test FilterPlugin with Router integration."""

    def test_nodes_filters_by_single_tag(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router.add_entry(lambda: "public", name="public_action", filter_tags="public")

        entries = router.nodes(tags="admin").get("entries", {})
        assert "admin_action" in entries
        assert "public_action" not in entries

    def test_nodes_filters_by_or(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router.add_entry(lambda: "public", name="public_action", filter_tags="public")
        router.add_entry(lambda: "internal", name="internal_action", filter_tags="internal")

        entries = router.nodes(tags="admin,public").get("entries", {})
        assert "admin_action" in entries
        assert "public_action" in entries
        assert "internal_action" not in entries

    def test_nodes_filters_by_and(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "both", name="both_action", filter_tags="admin,internal")
        router.add_entry(lambda: "admin", name="admin_only", filter_tags="admin")

        entries = router.nodes(tags="admin&internal").get("entries", {})
        assert "both_action" in entries
        assert "admin_only" not in entries

    def test_nodes_filters_by_not(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router.add_entry(lambda: "public", name="public_action", filter_tags="public")

        entries = router.nodes(tags="!admin").get("entries", {})
        assert "admin_action" not in entries
        assert "public_action" in entries

    def test_nodes_without_tags_filter_returns_all(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "admin", name="admin_action", filter_tags="admin")
        router.add_entry(lambda: "public", name="public_action", filter_tags="public")

        entries = router.nodes().get("entries", {})
        assert "admin_action" in entries
        assert "public_action" in entries

    def test_entry_without_tags_matches_not_expressions(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "tagged", name="tagged_action", filter_tags="admin")
        router.add_entry(lambda: "untagged", name="untagged_action")

        entries = router.nodes(tags="!admin").get("entries", {})
        assert "tagged_action" not in entries
        assert "untagged_action" in entries

    def test_complex_expression(self):
        router = _make_router().plug("filter")
        router.add_entry(lambda: "a", name="a", filter_tags="admin")
        router.add_entry(lambda: "b", name="b", filter_tags="public")
        router.add_entry(lambda: "c", name="c", filter_tags="admin,internal")
        router.add_entry(lambda: "d", name="d", filter_tags="public,internal")

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
        parent.api.add_entry(lambda: "parent_admin", name="parent_admin", filter_tags="admin")

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
        parent.api.add_entry(lambda: "admin", name="admin_action", filter_tags="admin")

        child = Child()
        parent.api.attach_instance(child, name="child")

        # Filter for admin - child has no admin entries
        result = parent.api.nodes(tags="admin")
        assert "admin_action" in result.get("entries", {})
        # Child should be pruned (empty after filter)
        assert "child" not in result.get("routers", {})
