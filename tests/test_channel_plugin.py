# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for ChannelPlugin."""

from __future__ import annotations

import pytest

from genro_routes import Router, RoutingClass, route
from genro_routes.exceptions import NotAvailable


class Owner(RoutingClass):
    pass


def _make_router():
    return Router(Owner(), name="api").plug("channel")


class TestChannelPluginBasic:
    """Basic channel filtering via add_entry."""

    def test_default_closed_without_channels(self):
        """Entry without channels configured is not available."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action")
        entries = router.nodes(channel_channel="mcp").get("entries", {})
        assert "action" not in entries

    def test_wildcard_allows_all_channels(self):
        """channels='*' allows any channel."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="*")
        entries = router.nodes(channel_channel="mcp").get("entries", {})
        assert "action" in entries
        entries = router.nodes(channel_channel="rest").get("entries", {})
        assert "action" in entries

    def test_exact_channel_match(self):
        """Exact channel name matches."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="mcp")
        entries = router.nodes(channel_channel="mcp").get("entries", {})
        assert "action" in entries
        entries = router.nodes(channel_channel="rest").get("entries", {})
        assert "action" not in entries

    def test_multiple_channels(self):
        """Comma-separated channels all match."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="mcp,rest")
        for ch in ("mcp", "rest"):
            entries = router.nodes(channel_channel=ch).get("entries", {})
            assert "action" in entries
        entries = router.nodes(channel_channel="web").get("entries", {})
        assert "action" not in entries

    def test_regex_pattern(self):
        """Regex patterns via re.fullmatch."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="bot_.*")
        entries = router.nodes(channel_channel="bot_sourcerer").get("entries", {})
        assert "action" in entries
        entries = router.nodes(channel_channel="bot_slack").get("entries", {})
        assert "action" in entries
        entries = router.nodes(channel_channel="mcp").get("entries", {})
        assert "action" not in entries

    def test_mixed_exact_and_regex(self):
        """Mix of exact names and regex patterns."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="mcp,bot_.*")
        entries = router.nodes(channel_channel="mcp").get("entries", {})
        assert "action" in entries
        entries = router.nodes(channel_channel="bot_sourcerer").get("entries", {})
        assert "action" in entries
        entries = router.nodes(channel_channel="rest").get("entries", {})
        assert "action" not in entries

    def test_no_channel_in_request(self):
        """Request without channel_channel sees nothing (default closed)."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="mcp")
        entries = router.nodes().get("entries", {})
        assert "action" not in entries


class TestChannelPluginWithDecorator:
    """Channel filtering via @route decorator."""

    def test_decorator_channel_filtering(self):
        """@route with channel_channels filters correctly."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("channel")
                self.api.channel.configure(channels="*")

            @route("api", channel_channels="mcp")
            def mcp_only(self):
                return "mcp"

            @route("api")
            def everywhere(self):
                return "all"

        svc = Svc()
        entries = svc.api.nodes(channel_channel="mcp").get("entries", {})
        assert "mcp_only" in entries
        assert "everywhere" in entries

        entries = svc.api.nodes(channel_channel="rest").get("entries", {})
        assert "mcp_only" not in entries
        assert "everywhere" in entries

    def test_shorthand_syntax(self):
        """Shorthand channel='mcp' works via plugin_default_param."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("channel")

            @route("api", channel="mcp")
            def mcp_only(self):
                return "mcp"

        svc = Svc()
        entries = svc.api.nodes(channel_channel="mcp").get("entries", {})
        assert "mcp_only" in entries
        entries = svc.api.nodes(channel_channel="rest").get("entries", {})
        assert "mcp_only" not in entries


class TestChannelPluginNode:
    """Channel filtering via node() direct access."""

    def test_node_raises_not_available(self):
        """Direct node access raises NotAvailable for wrong channel."""
        router = _make_router()
        router.add_entry(lambda: "ok", name="action", channel_channels="mcp")
        node = router.node("action", channel_channel="rest")
        assert node.error == "not_available"
        with pytest.raises(NotAvailable):
            node()

    def test_node_works_for_matching_channel(self):
        """Direct node access works for matching channel."""
        router = _make_router()
        router.add_entry(lambda self: "ok", name="action", channel_channels="mcp")
        node = router.node("action", channel_channel="mcp")
        assert node.error is None
        assert node() == "ok"


class TestChannelPluginGlobalConfig:
    """Router-level channel configuration."""

    def test_global_default_inherited(self):
        """Router-level channels='*' inherited by entries without override."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("channel")
                self.api.channel.configure(channels="*")

            @route("api")
            def open_handler(self):
                return "open"

            @route("api", channel_channels="mcp")
            def restricted(self):
                return "mcp only"

        svc = Svc()
        entries = svc.api.nodes(channel_channel="rest").get("entries", {})
        assert "open_handler" in entries
        assert "restricted" not in entries

    def test_per_handler_override(self):
        """Per-handler config overrides router-level default."""
        router = _make_router()
        router.channel.configure(channels="*")
        router.channel.configure(_target="restricted", channels="mcp")
        router.add_entry(lambda: "open", name="open_handler")
        router.add_entry(lambda: "mcp", name="restricted")

        entries = router.nodes(channel_channel="rest").get("entries", {})
        assert "open_handler" in entries
        assert "restricted" not in entries


class TestChannelWithAuthPlugin:
    """Channel and auth plugins work together."""

    def test_channel_and_auth_combined(self):
        """Both channel and auth must pass for entry to be visible."""

        class Svc(RoutingClass):
            def __init__(self):
                self.api = Router(self, name="api").plug("channel").plug("auth")

            @route("api", channel_channels="mcp", auth_rule="admin")
            def admin_mcp(self):
                return "admin via mcp"

        svc = Svc()
        # Both match
        entries = svc.api.nodes(channel_channel="mcp", auth_tags="admin").get("entries", {})
        assert "admin_mcp" in entries

        # Channel matches, auth doesn't
        entries = svc.api.nodes(channel_channel="mcp", auth_tags="guest").get("entries", {})
        assert "admin_mcp" not in entries

        # Auth matches, channel doesn't
        entries = svc.api.nodes(channel_channel="rest", auth_tags="admin").get("entries", {})
        assert "admin_mcp" not in entries
